import codecs
import logging
import os
import re
import socket
import sys
from time import sleep

import yaml
from cassandra.auth import PlainTextAuthProvider
from cassandra.cluster import NoHostAvailable, default_lbp_factory
from cassandra.cqlengine import connection
from flask import Flask
from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy_utils import database_exists, create_database
from flask_migrate import Migrate


from smfrcore.utils import IN_DOCKER, DEFAULT_HANDLER, IS_DEVELOPMENT, UNDER_TESTS, Singleton, CustomJSONEncoder


DEVELOPMENT = IS_DEVELOPMENT
SERVER_BOOTSTRAP = 'gunicorn' in sys.argv[0]
MYSQL_MIGRATION = all(os.path.basename(a) in ('flask', 'db', 'migrate') for a in sys.argv) \
                  or all(os.path.basename(a) in ('flask', 'db', 'upgrade') for a in sys.argv) \
                  or all(os.path.basename(a) in ('flask', 'db', 'init') for a in sys.argv)

CONFIG_STORE_PATH = os.getenv('SERVER_PATH_UPLOADS', os.path.join(os.path.dirname(__file__), '../../../uploads/'))
CONFIG_FOLDER = '/configuration/' if IN_DOCKER else os.path.join(os.path.dirname(__file__), '../config/')
NUM_SAMPLES = os.getenv('NUM_SAMPLES', 100)

logging.getLogger('cassandra').setLevel(logging.WARNING)
logging.getLogger('kafka').setLevel(logging.WARNING)
logging.getLogger('connexion').setLevel(logging.ERROR)
logging.getLogger('swagger_spec_validator').setLevel(logging.ERROR)
logging.getLogger('urllib3').setLevel(logging.ERROR)
logging.getLogger('requests_oauthlib').setLevel(logging.ERROR)
logging.getLogger('paramiko').setLevel(logging.ERROR)
logging.getLogger('oauthlib').setLevel(logging.ERROR)

os.makedirs(CONFIG_STORE_PATH, exist_ok=True)

codecs.register(lambda name: codecs.lookup('utf8') if name.lower() == 'utf8mb4' else None)


class RestServerConfiguration(metaclass=Singleton):
    """
    A class whose objects hold SMFR Rest Server Configuration as singletons.
    Constructor accepts a connexion app object.
    """
    geonames_host = '127.0.0.1' if not IN_DOCKER else 'geonames'
    kafka_bootstrap_servers = ['127.0.0.1:9090', '127.0.0.1:9092'] if not IN_DOCKER else os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'kafka:9092,kafka:9094').split(',')
    mysql_host = '127.0.0.1' if not IN_DOCKER else os.getenv('MYSQL_HOST', 'mysql')
    __mysql_user = os.getenv('MYSQL_USER', 'root')
    __mysql_pass = os.getenv('MYSQL_PASSWORD', 'example')
    cassandra_host = '127.0.0.1' if not IN_DOCKER else os.getenv('CASSANDRA_HOST', 'cassandrasmfr')
    annotator_host = '127.0.0.1' if not IN_DOCKER else os.getenv('ANNOTATOR_HOST', 'annotator')
    persister_host = '127.0.0.1' if not IN_DOCKER else os.getenv('PERSISTER_HOST', 'persister')
    collectors_host = '127.0.0.1' if not IN_DOCKER else os.getenv('COLLECTORS_HOST', 'collectors')
    geocoder_host = '127.0.0.1' if not IN_DOCKER else os.getenv('GEOCODER_HOST', 'geocoder')
    restserver_host = '127.0.0.1' if not IN_DOCKER else os.getenv('RESTSERVER_HOST', 'restserver')

    cassandra_keyspace = '{}{}'.format(os.getenv('CASSANDRA_KEYSPACE', 'smfr_persistent'), '_test' if UNDER_TESTS else '')
    mysql_db_name = '{}{}'.format(os.getenv('MYSQL_DBNAME', 'smfr'), '_test' if UNDER_TESTS else '')
    restserver_port = os.getenv('RESTSERVER_PORT', 5555)
    annotator_port = os.getenv('ANNOTATOR_PORT', 5556)
    persister_port = os.getenv('PERSISTER_PORT_PORT', 5558)
    geocoder_port = os.getenv('GEOCODER_PORT', 5557)
    persister_kafka_topic = os.getenv('PERSISTER_KAFKA_TOPIC', 'persister')

    debug = not UNDER_TESTS and os.getenv('DEVELOPMENT', True)

    logger_level = logging.ERROR if UNDER_TESTS else logging.getLevelName(os.getenv('LOGGING_LEVEL', 'DEBUG').upper())
    logger = logging.getLogger('RestServer config')
    logger.setLevel(logger_level)
    logger.addHandler(DEFAULT_HANDLER)

    def _bootstrap_cassandra(self):
        up = False
        retries = 5
        while not up and retries <= 5:
            try:
                from smfrcore.models.cassandra import cqldb
                cqldb.init_app(self.flask_app)
                self.db_cassandra = cqldb
            except (NoHostAvailable, socket.gaierror):
                self.logger.error('Missing link with Cassandra.')
                self.logger.warning('Mysql was not up. Wait 5 seconds before retrying')
                sleep(5)
                retries += 1
            else:
                up = True
            finally:
                if not up and retries >= 5:
                    self.logger.error('Too many retries. CASSANDRA still not reachable! Exiting...')
                    sys.exit(1)

    def _bootstrap_mysql(self):
        up = False
        retries = 5
        while not up and retries <= 5:
            try:
                from smfrcore.models.sql import sqldb
                sqldb.init_app(self.flask_app)
                self.db_mysql = sqldb
                self.migrate = Migrate(self.flask_app, self.db_mysql)
            except (OperationalError, socket.gaierror):
                self.logger.error('Missing link with MySQL.')
                self.logger.warning('Mysql were not up. Wait 5 seconds before retrying')
                sleep(5)
                retries += 1
            else:
                up = True
            finally:
                if not up and retries >= 5:
                    self.logger.error('Too many retries. MySQL still not reachable! Exiting...')
                    sys.exit(1)

    def _bootstrap_kafka(self):
        if not SERVER_BOOTSTRAP or self.producer:
            return
        up = False
        retries = 5
        while not up and retries <= 5:
            try:
                # Flask apps are setup when issuing CLI commands as well.
                # This code is executed in case of launching REST Server
                self.producer = KafkaProducer(
                    bootstrap_servers=self.kafka_bootstrap_servers, linger_ms=500,
                    batch_size=1048576, retries=5, compression_type='gzip',
                    buffer_memory=134217728
                )
            except (NoBrokersAvailable, socket.gaierror):
                self.logger.error('Missing link with Kafka.')
                self.logger.warning('Kafka were not up. Wait 5 seconds before retrying')
                sleep(5)
                retries += 1
            else:
                up = True
            finally:
                if not up and retries >= 5:
                    self.logger.error('Too many retries. Kafka still not reachable! Exiting...')
                    sys.exit(1)

    def __init__(self, connexion_app=None):

        if not connexion_app:
            if RestServerConfiguration not in self.__class__.instances:
                from start import app
            # noinspection PyMethodFirstArgAssignment
            self = self.__class__.instances[RestServerConfiguration]
        else:
            self.flask_app = self.set_flaskapp(connexion_app)
            self.flask_app.config['JWT_SECRET_KEY'] = os.getenv('SECRET_KEY', 'super-secret')
            self.producer = None
            # self.collectors = {}
            self._bootstrap_cassandra()
            self._bootstrap_mysql()
            self._bootstrap_kafka()
            self.log_configuration()
            self.flask_app.app_context().push()

    @classmethod
    def default_keywords(cls):
        with open(os.path.join(CONFIG_FOLDER, 'flood_keywords.yaml')) as f:
            floods_keywords = yaml.load(f)
            languages = sorted(list(floods_keywords.keys()))
            track = sorted(list(set(w for s in floods_keywords.values() for w in s)))
        return languages, track

    # @classmethod
    # def admin_twitter_keys(cls, iden):
    #     keys = {
    #         k: os.getenv('{}_{}'.format(iden, k).upper())
    #         for k in ('consumer_key', 'consumer_secret', 'access_token', 'access_token_secret')
    #     }
    #     return keys

    @classmethod
    def configure_migrations(cls):
        app = Flask(__name__)
        app.json_encoder = CustomJSONEncoder
        app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql://{}:{}@{}/{}?charset=utf8mb4'.format(
            cls.__mysql_user, cls.__mysql_pass, cls.mysql_host, cls.mysql_db_name
        )
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        up = False
        retries = 1
        while not up and retries <= 5:
            try:
                from smfrcore.models.sql import sqldb
                sqldb.init_app(app)
                cls.db_mysql = sqldb
                cls.migrate = Migrate(app, cls.db_mysql)
            except (OperationalError, socket.gaierror):
                cls.logger.warning('Cannot apply migrations because Mysql was not up...wait 5 seconds before retrying')
                sleep(5)
                retries += 1
            else:
                up = True
                return app
            finally:
                if not up and retries >= 5:
                    cls.logger.error('Missing link with MySQL. Exiting...')
                    sys.exit(1)

    def set_flaskapp(self, connexion_app):
        app = connexion_app.app
        app.json_encoder = CustomJSONEncoder
        app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql://{}:{}@{}/{}?charset=utf8mb4'.format(
            self.__mysql_user, self.__mysql_pass, self.mysql_host, self.mysql_db_name
        )
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        app.config['SQLALCHEMY_POOL_TIMEOUT'] = 360
        app.config['SQLALCHEMY_POOL_RECYCLE'] = 120
        app.config['SQLALCHEMY_POOL_SIZE'] = 10

        app.config['CASSANDRA_HOSTS'] = [self.cassandra_host]
        app.config['CASSANDRA_KEYSPACE'] = self.cassandra_keyspace
        app.config['CASSANDRA_SETUP_KWARGS'] = {
            'auth_provider': PlainTextAuthProvider(username=os.getenv('CASSANDRA_USER'),
                                                   password=os.getenv('CASSANDRA_PASSWORD')),
            'load_balancing_policy': default_lbp_factory(),
            'compression': True,
        }
        return app

    @property
    def base_path(self):
        return os.getenv('RESTSERVER_BASEPATH', '/1.0')

    def init_cassandra(self):
        """

        :return:
        """
        session = connection._connections[connection.DEFAULT_CONNECTION].session
        session.execute(
            "CREATE KEYSPACE IF NOT EXISTS %s WITH replication = {'class':'SimpleStrategy','replication_factor':'1'};" %
            self.cassandra_keyspace
        )

        # do not remove the import below
        from smfrcore.models.cassandra import Tweet
        self.db_cassandra.sync_db()

    def init_mysql(self):
        """

        :return:
        """
        with self.flask_app.app_context():
            engine = create_engine(self.flask_app.config['SQLALCHEMY_DATABASE_URI'], encoding='UTF8MB4')
            if not database_exists(engine.url):
                create_database(engine.url)

    @property
    def kafka_producer(self):
        return self.producer

    def log_configuration(self):

        self.logger.info('SMFR Rest Server and Collector manager')
        self.logger.info('======= START LOGGING Configuration =======')
        self.logger.info('+++ Kafka')
        self.logger.info(' - Persister Topic: {}'.format(self.persister_kafka_topic))
        self.logger.info(' - Bootstrap servers: {}'.format(self.kafka_bootstrap_servers))
        self.logger.info('+++ Cassandra')
        self.logger.info(' - Host: {}'.format(self.flask_app.config['CASSANDRA_HOSTS']))
        self.logger.info(' - Keyspace: {}'.format(self.flask_app.config['CASSANDRA_KEYSPACE']))
        self.logger.info('+++ MySQL')

        masked = re.sub(r'(?<=:)(.*)(?=@)', '******', self.flask_app.config['SQLALCHEMY_DATABASE_URI'])

        self.logger.info(' - URI: {}'.format(masked))
        self.logger.info('+++ Annotator microservice')
        self.logger.info(' - {}:{}'.format(self.annotator_host, self.annotator_port))
        self.logger.info('+++ Geocoder microservice')
        self.logger.info(' - {}:{}'.format(self.geocoder_host, self.geocoder_port))
        self.logger.info('+++ Geonames service (used by Geocoder/mordecai)')
        self.logger.info(' - {}'.format(self.geonames_host))
        self.logger.info('======= END LOGGING Configuration =======')
