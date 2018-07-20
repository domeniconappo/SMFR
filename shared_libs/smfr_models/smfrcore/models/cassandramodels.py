"""
Module for CQLAlchemy models to map to Cassandra keyspaces
"""
import logging
import os
import time
import datetime
from decimal import Decimal

import numpy as np
import ujson as json
from cassandra.cluster import Cluster, default_lbp_factory
from cassandra.cqlengine.connection import register_connection, set_default_connection
from cassandra.query import dict_factory
from cassandra.auth import PlainTextAuthProvider
from cassandra.util import OrderedMapSerializedKey
from flask_cqlalchemy import CQLAlchemy

from smfrcore.utils import RUNNING_IN_DOCKER, LOGGER_FORMAT, DATE_FORMAT
from smfrcore.models.sqlmodels import TwitterCollection


logging.basicConfig(format=LOGGER_FORMAT, datefmt=DATE_FORMAT)
logger = logging.getLogger('models')
logger.setLevel(os.environ.get('LOGGING_LEVEL', 'DEBUG'))
cqldb = CQLAlchemy()

_keyspace = os.environ.get('CASSANDRA_KEYSPACE', 'smfr_persistent')
_hosts = [os.environ.get('CASSANDRA_HOST', 'cassandrasmfr')]
_port = os.environ.get('CASSANDRA_PORT', 9042)
_cassandra_user = os.environ.get('CASSANDRA_USER')
_cassandra_password = os.environ.get('CASSANDRA_PASSWORD')


def cassandra_session_factory():
    # In Cassandra >= 2.0.x, the default cqlsh listen port is 9160
    # which is defined in cassandra.yaml by the rpc_port parameter.
    # https://stackoverflow.com/questions/36133127/how-to-configure-cassandra-for-remote-connection
    # Anyway, when using the cassandra-driver Cluster object, the port to use is still 9042.
    # Just ensure to open 9042 and 9160 ports on all nodes of the Swarm cluster.
    cluster = Cluster(_hosts, port=_port, compression=True,
                      auth_provider=PlainTextAuthProvider(username=_cassandra_user, password=_cassandra_password),
                      load_balancing_policy=default_lbp_factory()) if RUNNING_IN_DOCKER else Cluster()
    session = cluster.connect()
    session.row_factory = dict_factory
    session.execute("USE {}".format(_keyspace))
    return session


_session = cassandra_session_factory()
register_connection(str(_session), session=_session)
set_default_connection(str(_session))


class Tweet(cqldb.Model):
    """
    Object representing the `tweet` column family in Cassandra
    """
    __keyspace__ = _keyspace

    session = _session
    session.default_fetch_size = 5000

    TYPES = [
        ('annotated', 'Annotated'),
        ('collected', 'Collected'),
        ('geotagged', 'Geo Tagged'),
    ]

    tweetid = cqldb.columns.Text(primary_key=True, required=True)
    """
    Id of the tweet
    """
    created_at = cqldb.columns.DateTime(index=True, required=True)
    collectionid = cqldb.columns.Integer(required=True, default=0, partition_key=True, index=True, )
    """
    Relation to collection id in MySQL virtual_twitter_collection table
    """
    ttype = cqldb.columns.Text(required=True, partition_key=True)

    nuts2 = cqldb.columns.Text()
    nuts2source = cqldb.columns.Text()

    geo = cqldb.columns.Map(
        cqldb.columns.Text, cqldb.columns.Text,
    )
    """
    Map column for geo information
    """

    annotations = cqldb.columns.Map(
        cqldb.columns.Text,
        cqldb.columns.Tuple(
            cqldb.columns.Text,
            cqldb.columns.Decimal(9, 6)
        )
    )
    """
    Map column for annotations
    """

    tweet = cqldb.columns.Text(required=True)
    """
    Twitter data serialized as JSON text
    """

    latlong = cqldb.columns.Tuple(cqldb.columns.Decimal(9, 6), cqldb.columns.Decimal(9, 6))
    latlong.db_type = 'frozen<tuple<decimal, decimal>>'
    """
    Coordinates
    """

    lang = cqldb.columns.Text(index=True)
    """
    Language of the tweet
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Tweet.generate_prepared_statements()

    def __str__(self):
        return '\nTweet\n{o.nuts2} - {o.nuts2source}\n' \
               '{o.created_at} - {o.lang}: {o.full_text:.80}' \
               '\n{o.geo}\n{o.annotations}'.format(o=self)

    @classmethod
    def to_obj(cls, row):
        return cls(**row)

    @classmethod
    def to_dict(cls, row):
        return row

    @classmethod
    def to_json(cls, row):
        """
        Needs to be encoded because of OrderedMapSerializedKey and other specific Cassandra objects
        :param row: dictionary representing a row in Cassandra tweet table
        :return: A dictionary that can be serialized
        """
        for k, v in row.items():
            if isinstance(v, (np.float32, np.float64, Decimal)):
                row[k] = float(v)
            elif isinstance(v, (np.int32, np.int64)):
                row[k] = int(v)
            elif isinstance(v, datetime.datetime):
                row[k] = v.isoformat()
            elif isinstance(v, tuple):
                row[k] = [float(i) if isinstance(i, (np.float32, np.float64, Decimal)) else i for i in v]
            elif isinstance(v, OrderedMapSerializedKey):
                # cassandra Map column
                res = {}
                for inner_k, inner_v in v.items():
                    if isinstance(inner_v, tuple):
                        encoded_v = [float(i) if isinstance(i, (np.float32, np.float64, Decimal)) else i for i in inner_v]
                        try:
                            res[inner_k] = dict((encoded_v,))
                        except ValueError:
                            res[inner_k] = (encoded_v[0], encoded_v[1])
                    else:
                        res[inner_k] = inner_v

                row[k] = res
        return row

    @classmethod
    def get_iterator(cls, collection_id, ttype, lang=None, out_format='obj', last_tweetid=None):
        """

        :param collection_id:
        :param ttype:
        :param lang: two chars lang code (e.g. en)
        :param out_format: can be 'obj', 'json' or 'dict'
        :param last_tweetid:
        :return: smfrcore.models.cassandramodels.Tweet object, dictionary or JSON encoded
        """
        if out_format not in ('obj', 'json', 'dict'):
            raise ValueError('out_format is not valid')

        if not hasattr(cls, 'stmt'):
            cls.generate_prepared_statements()

        if last_tweetid:
            results = cls.session.execute(cls.stmt_with_last_tweetid, parameters=(collection_id, ttype, last_tweetid))
        else:
            results = cls.session.execute(cls.stmt, parameters=(collection_id, ttype))

        lang = lang.lower() if lang else None
        for row in results:
            if lang and row.get('lang') != lang:
                continue
            yield getattr(cls, 'to_{}'.format(out_format))(row)

    @classmethod
    def generate_prepared_statements(cls):
        """
        Generate prepared SQL statements for existing tables
        """
        cls.samples_stmt = cls.session.prepare(
            "SELECT * FROM tweet WHERE collectionid=? AND ttype=? ORDER BY tweetid DESC LIMIT ?"
        )
        cls.stmt = cls.session.prepare("SELECT * FROM tweet WHERE collectionid=? AND ttype=? ORDER BY tweetid DESC")
        cls.stmt_with_last_tweetid = cls.session.prepare(
            "SELECT * FROM tweet WHERE collectionid=? AND ttype=? AND tweetid > ? ORDER BY tweetid ASC"
        )

    @classmethod
    def make_table_object(cls, numrow, tweet_dict):
        """
        Return dictionary that can be used in HTML5 tables / Jinja templates
        :param numrow: int: numrow
        :param tweet_dict: dict representing Tweet row in smfr_persistent.tweet column family
        :return:
        """
        tweet_obj = cls(**tweet_dict)
        tweet_dict['tweet'] = json.loads(tweet_dict['tweet'])
        full_text = tweet_obj.full_text
        tweet_dict['tweet']['full_text'] = full_text
        twid = tweet_dict['tweetid']
        obj = {
            'rownum': numrow,
            'Full Text': full_text,
            'Tweet id': '<a href="https://twitter.com/statuses/{}">{}</a>'.format(twid, twid),
            'original_tweet': tweet_obj.original_tweet_as_string,
            'Type': tweet_dict['ttype'],
            'Lang': tweet_dict['lang'] or '-',
            'Annotations': tweet_obj.pretty_annotations,
            'LatLon': '<a href="https://www.openstreetmap.org/#map=13/{}/{}" target="_blank">lat: {}, lon: {}</a>'.format(
                tweet_obj.latlong[0], tweet_obj.latlong[1], tweet_obj.latlong[0], tweet_obj.latlong[1]
            ) if tweet_obj.latlong else '',
            'Collected at': tweet_dict['created_at'] or '',
            'Tweeted at': tweet_dict['tweet']['created_at'] or ''
        }
        return obj

    @classmethod
    def get_samples(cls, collection_id, ttype, size=10):
        if not hasattr(cls, 'stmt'):
            cls.generate_prepared_statements()
        rows = cls.session.execute(cls.samples_stmt, parameters=[collection_id, ttype, size])
        return rows

    def validate(self):
        # TODO validate tweet content
        super().validate()

    @property
    def original_tweet_as_string(self):
        """
        The string of the original tweet to store in Cassandra column.
        :return: JSON string representing the original tweet dictionary as received from Twitter Streaming API
        """
        return json.dumps(self.original_tweet_as_dict, indent=2, sort_keys=True)

    @property
    def original_tweet_as_dict(self):
        """
        The string of the original tweet to store in Cassandra column.
        :return: JSON string representing the original tweet dictionary as received from Twitter Streaming API
        """
        return json.loads(self.tweet)

    @property
    def pretty_annotations(self):
        if not self.annotations:
            return '-'
        out = ''
        for k, v in self.annotations.items():
            out += '{}: {} - {}\n'.format(k, v[0], v[1])

        return '<pre>{}</pre>'.format(out)

    def serialize(self):
        """
        Method to serialize object to Kafka
        :return: string version in JSON format
        """

        outdict = {}
        for k, v in self.__dict__['_values'].items():
            if isinstance(v.value, (datetime.datetime, datetime.date)):
                outdict[k] = v.value.isoformat()
            else:
                outdict[k] = v.value
        return json.dumps(outdict, ensure_ascii=False).encode('utf-8')

    @classmethod
    def build_from_tweet(cls, collection, tweet, ttype='collected'):
        """

        :param ttype:
        :param collection:
        :param tweet:
        :return:
        """
        return cls(
            tweetid=tweet['id_str'],
            collectionid=collection.id if isinstance(collection, TwitterCollection) else int(collection),
            created_at=time.mktime(time.strptime(tweet['created_at'], '%a %b %d %H:%M:%S +0000 %Y')),
            ttype=ttype,
            nuts2=collection.nuts2 if isinstance(collection, TwitterCollection) else '',
            nuts2source=collection.nuts2source if isinstance(collection, TwitterCollection) else '',
            annotations={}, lang=tweet['lang'], geo={},
            tweet=json.dumps(tweet, ensure_ascii=False),
        )

    @classmethod
    def build_from_kafka_message(cls, message):
        """

        :param message:
        :return:
        """
        values = json.loads(message)
        obj = cls()
        for k, v in values.items():
            if k == 'created_at':
                v = datetime.datetime.strptime(
                    v.partition('.')[0], '%Y-%m-%dT%H:%M:%S') if v is not None else datetime.datetime.now()\
                    .replace(microsecond=0)
            setattr(obj, k, v)
        return obj

    @property
    def full_text(self):
        tweet = json.loads(self.tweet)
        full_text = None

        for status in ('retweeted_status', 'quoted_status'):

            if status in tweet:
                nature = status.split('_')[0].title()
                extended = tweet[status].get('extended_tweet', {})
                if not (extended.get('full_text') or extended.get('text')):
                    continue
                full_text = '{} - {}'.format(nature, extended.get('full_text') or extended.get('text', ''))
                break

        if not full_text:
            full_text = tweet.get('full_text') or tweet.get('extended_tweet', {}).get('full_text', '') or tweet.get('text', '')

        return full_text
