import os
import logging
from collections import defaultdict
from logging.handlers import RotatingFileHandler
import time
import multiprocessing

import ujson as json
from cassandra import InvalidRequest, WriteTimeout
from cassandra.cqlengine import ValidationError, CQLEngineException
from kafka.errors import CommitFailedError, KafkaTimeoutError

from smfrcore.models.cassandra import Tweet, new_cassandra_session
from smfrcore.models.sql import TwitterCollection, create_app
from smfrcore.utils import IN_DOCKER, NULL_HANDLER, DEFAULT_HANDLER, DefaultDictSyncManager
from smfrcore.utils.kafka import make_kafka_consumer, make_kafka_producer
from smfrcore.client.api_client import AnnotatorClient


logging.getLogger('kafka').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('cassandra').setLevel(logging.WARNING)

os.environ['NO_PROXY'] = ','.join((AnnotatorClient.host,))

logger = logging.getLogger('PERSISTER')
logger.addHandler(DEFAULT_HANDLER)
logger.setLevel(os.getenv('LOGGING_LEVEL', 'DEBUG'))
logger.propagate = False

file_logger = logging.getLogger('UNRECONCILED')
file_logger.addHandler(NULL_HANDLER)
file_logger.setLevel(logging.ERROR)
file_logger.propagate = False

if IN_DOCKER:
    filelog_path = os.path.join(os.path.dirname(__file__), '../../logs/not_reconciled_tweets.log') if not IN_DOCKER else '/logs/not_reconciled_tweets.log'
    hdlr = RotatingFileHandler(filelog_path, maxBytes=10485760, backupCount=2)
    hdlr.setLevel(logging.ERROR)
    file_logger.addHandler(hdlr)


class Persister:
    """
        Persister component to save Tweet messages in Cassandra.
        It listens to the Kafka queue, build a Tweet object from messages and save it in Cassandra.
        """
    _lock = multiprocessing.RLock()
    _manager = DefaultDictSyncManager()
    _manager.start()
    shared_counter = _manager.defaultdict(int)
    persister_kafka_topic = os.getenv('PERSISTER_KAFKA_TOPIC', 'persister')
    kafka_bootstrap_servers = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'kafka:9090,kafka:9092') if IN_DOCKER else '127.0.0.1:9090,127.0.0.1:9092'
    annotator_kafka_topic = os.getenv('ANNOTATOR_KAFKA_TOPIC', 'annotator')
    geocoder_kafka_topic = os.getenv('GEOCODER_KAFKA_TOPIC', 'geocoder')

    app = create_app()

    def __init__(self):
        self.topic = self.persister_kafka_topic
        self.bootstrap_servers = self.kafka_bootstrap_servers.split(',')
        self.language_models = AnnotatorClient.available_languages()
        self.background_process = None
        self.active = True
        self.collections_by_trigger = defaultdict(list)
        with self.app.app_context():
            running = TwitterCollection.get_running()
            self.collections = [c for c in running if c.trigger.code != TwitterCollection.TRIGGER_BACKGROUND]
            for c in self.collections:
                self.collections_by_trigger[c.trigger.code].append(c)

    def set_collections(self, collections):
        with self._lock:
            self.collections = collections

    def reconcile_tweet_with_collection(self, tweet, trigger=TwitterCollection.TRIGGER_ONDEMAND):
        # if there is only one collection in the set, we just reconcile with it.
        # e.g. if the tweet was collected by the manual collections streamer, and there is only one manual collection defined,
        # tweet is assigned to that collection without any further check
        if len(self.collections_by_trigger.get(trigger, [])) == 1:
            return self.collections_by_trigger[trigger][0]
        for c in self.collections_by_trigger.get(trigger, []):
            if c.is_tweet_in_bounding_box(tweet) or c.tweet_matched_keyword(tweet):
                return c
        # no collection found for ingested tweet...
        return None

    def start_in_background(self):
        p = multiprocessing.Process(target=self.start, name='PersisterProcess')
        self.background_process = p
        p.daemon = True
        p.start()
        return p

    def start(self):
        """
        Main method that iterate over messages coming from Kafka queue, build a Tweet object and save it in Cassandra
        """
        logger.info('Starting %s...Reset counters and making kafka connections', str(self))
        Tweet.session = new_cassandra_session()
        producer = make_kafka_producer()
        consumer = make_kafka_consumer(topic=self.topic)

        while self.active:
            try:
                logger.info('===> Entering in consumer loop...')
                for i, msg in enumerate(consumer, start=1):
                    tweet = None
                    try:
                        msg = msg.value.decode('utf-8')
                        msg = json.loads(msg)
                        trigger = msg.pop('trigger', TwitterCollection.TRIGGER_ONDEMAND)
                        tweet = Tweet.from_json(msg)

                        if logger.isEnabledFor(logging.DEBUG):
                            logger.debug('***** Fetched message from persister queue %s %s', trigger, tweet.tweetid)

                        if tweet.collectionid == Tweet.NO_COLLECTION_ID:
                            # reconcile with running collections
                            # trigger should be either 'manual' or 'on-demand'
                            collection = self.reconcile_tweet_with_collection(tweet, trigger)
                            if not collection:
                                if logger.isEnabledFor(logging.DEBUG):
                                    logger.debug('***** Not reconciled %s %s', trigger, tweet.tweetid)
                                with self._lock:
                                    self.shared_counter['not-reconciled'] += 1
                                file_logger.error('%s', msg)
                                continue  # continue the consumer loop without saving tweet
                            tweet.collectionid = collection.id

                        if logger.isEnabledFor(logging.DEBUG):
                            logger.debug('***** Gonna save in cassandra %s %s', trigger, tweet.tweetid)
                        tweet.save()
                        if logger.isEnabledFor(logging.DEBUG):
                            logger.debug('Saved tweet: %s - collection %d', tweet.tweetid, tweet.collectionid)

                        collection = tweet.collection
                        trigger_key = collection.trigger.code

                        with self._lock:
                            self.shared_counter['{}-{}'.format(trigger_key, tweet.ttype)] += 1
                            self.shared_counter[tweet.ttype] += 1
                            self.shared_counter['{}-{}'.format(tweet.lang, tweet.ttype)] += 1

                        self.send_to_pipeline(producer, tweet)

                    except (ValidationError, ValueError, TypeError, InvalidRequest) as e:
                        logger.error(e)
                        logger.error('Poison message for Cassandra: %s', tweet or msg)
                    except (CQLEngineException, WriteTimeout) as e:
                        logger.error(e)
            except KafkaTimeoutError:
                logger.warning('Consumer Timeout...sleep 5 seconds')
                time.sleep(5)
            except CommitFailedError:
                self.active = False
                logger.error('Persister was disconnected during I/O operations. Exited.')
            except ValueError:
                # tipically an I/O operation on closed epoll object
                # as the consumer can be disconnected in another thread (see signal handling in start.py)
                if consumer._closed:
                    logger.info('Persister was disconnected during I/O operations. Exited.')
                    self.active = False
            except KeyboardInterrupt:
                self.stop()
                self.active = False
        if not consumer._closed:
            consumer.close(30)
        if not producer._closed:
            producer.close(30)

    def send_to_pipeline(self, producer, tweet):
        if not tweet.use_pipeline or tweet.ttype == Tweet.GEOTAGGED_TYPE:
            return
        topic = None
        if tweet.ttype == Tweet.COLLECTED_TYPE and tweet.lang in self.language_models:
            # collected tweet will go to the next in pipeline: annotator queue
            topic = '{}-{}'.format(self.annotator_kafka_topic, tweet.lang)
        elif tweet.ttype == Tweet.ANNOTATED_TYPE:
            # annotated tweet will go to the next in pipeline: geocoder queue
            topic = self.geocoder_kafka_topic

        if not topic:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug('No topic were determined for: %s %s %s', tweet.ttype, tweet.tweetid, tweet.lang)
            return

        message = tweet.serialize()
        producer.send(topic, message)

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug('Sent to pipeline: %s %s', topic, tweet.tweetid)

    def stop(self):
        """
        Stop processing messages from queue, close KafkaConsumer and unset running instance.
        """
        if self.background_process:
            self.background_process.terminate()
        with self._lock:
            self.active = False
        logger.info('Persister connection closed!')

    def __str__(self):
        return 'Persister ({}): {}@{}'.format(id(self), self.topic, self.bootstrap_servers)

    def counters(self):
        with self._lock:
            return dict(self.shared_counter)
