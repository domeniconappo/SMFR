import datetime
import http
import logging
import signal
from http.client import IncompleteRead
import os
import socket
import multiprocessing
import time

import urllib3

import requests
from twython import TwythonStreamer

from smfrcore.models.cassandra import Tweet
from smfrcore.models.sql import TwitterCollection
from smfrcore.utils import DEFAULT_HANDLER, IS_DEVELOPMENT
from smfrcore.utils.kafka import make_kafka_producer
from smfrcore.utils.text import safe_langdetect, tweet_normalization_aggressive


logger = logging.getLogger('Streamer')
logger.setLevel(os.getenv('LOGGING_LEVEL', 'DEBUG'))
logger.addHandler(DEFAULT_HANDLER)
logger.propagate = False


class BaseStreamer(TwythonStreamer):
    """

    """
    trigger = None
    mp_manager = multiprocessing.Manager()
    max_errors_len = 15

    def __init__(self, **api_keys):
        self.query = {}
        self.lock = multiprocessing.RLock()
        self.consumer_key = api_keys['consumer_key']
        self.consumer_secret = api_keys['consumer_secret']
        self.access_token = api_keys['access_token']
        self.access_token_secret = api_keys['access_token_secret']
        self.persister_kafka_topic = os.getenv('PERSISTER_KAFKA_TOPIC', 'persister')
        self._shared_errors = self.mp_manager.list([])
        self.incremental_sleep = 1

        self.producer = None

        # the Streamer process
        self.process = None

        self._collections = self.mp_manager.list([])
        self.collection = None

        self.client_args = {}
        if os.getenv('http_proxy'):
            # Setting proxies for twython streamer
            self.client_args = dict(proxies=dict(http=os.getenv('http_proxy'),
                                                 https=os.getenv('https_proxy') or os.getenv('http_proxy')))
        logger.debug('Instantiate a %s streamer with args %s', self.trigger, str(self.client_args))
        super().__init__(self.consumer_key, self.consumer_secret,
                         self.access_token, self.access_token_secret,
                         retry_count=None, retry_in=120, chunk_size=512,
                         client_args=self.client_args)
        self.is_connected = multiprocessing.Value('i', 0)

    def __str__(self):
        return '{o.__class__.__name__}'.format(o=self)

    @classmethod
    def _detect_language(cls, data):
        text = Tweet.full_text_from_raw_tweet(data)
        if not text:
            return None
        lang = safe_langdetect(tweet_normalization_aggressive(text))
        return lang

    def _build_query_for(self):
        query = {}
        locations = []
        track = set()
        languages = []
        for collection in self._collections:
            if collection.locations:
                bbox = collection.locations
                locations += ['{},{},{},{}'.format(bbox['min_lon'], bbox['min_lat'], bbox['max_lon'], bbox['max_lat'])]
            if collection.tracking_keywords:
                track.update(collection.tracking_keywords)
            if collection.languages:
                languages += collection.languages
        if track:
            # max 400 keywords for Twitter API Stream
            query['track'] = list(track)[:400]
        if locations:
            # max 25 bounding boxes for Twitter API Stream
            query['locations'] = locations[:25]
        if languages:
            query['languages'] = languages
        return query

    def log(self, tweet):
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug('Sent to %s topic: %s', self.persister_kafka_topic, tweet.tweetid)

    def on_error(self, status_code, data):
        status_code = int(status_code)
        data = data.decode('utf-8') if isinstance(data, bytes) else str(data)
        err = str(data) or 'No error message'
        logger.error('ON ERROR EVENT: %s', status_code)
        logger.error('ON ERROR EVENT: %s', err)
        self.track_error(status_code, err)
        self.disconnect(deactivate_collections=False)
        self._collections = self.mp_manager.list([])
        self.collection = None
        sleep_time = 30
        if status_code == 420:
            sleep_time = 60 * self.incremental_sleep
            self.incremental_sleep *= 2
        logger.info('Sleeping %d secs after error', sleep_time)
        time.sleep(sleep_time)
        self.run_collections()

    def on_timeout(self):
        logger.error('Timeout...sleeping 30 secs')
        self.track_error(500, 'Timeout')
        time.sleep(30)

    def use_pipeline(self, collection):
        return collection.is_using_pipeline

    def run_collections(self):
        self._collections = self.mp_manager.list(self._get_collections())
        if not self._collections:
            return None
        p = multiprocessing.Process(target=self.connect, name=str(self), args=(self._collections,))
        p.daemon = True
        p.start()
        self.process = p

    def handle_termination(self, signum, _):
        logger.info('Streamer %s process Terminated. Disconnecting...')
        self.disconnect(deactivate_collections=False)
        time.sleep(3)

    def connect(self, collections):

        with self.lock:
            if self.is_connected.value == 1:
                logger.warning('Trying to connect to an already connected stream. Ignoring...')
                return

        signal.signal(signal.SIGTERM, self.handle_termination)

        self.producer = make_kafka_producer()
        self.query = self._build_query_for()
        filter_args = {k: ','.join(v).strip(',') for k, v in self.query.items() if k != 'languages' and v}
        logger.info('Streaming for collections: \n%s', '\n'.join(str(c) for c in collections))

        with self.lock:
            stay_active = True
            self.connected = True
            self.is_connected.value = 1

        # Main Twython consumer loop
        while stay_active:
            try:
                logger.info('Connecting to streamer %s', str(filter_args))
                self.statuses.filter(**filter_args)
            except (urllib3.exceptions.ReadTimeoutError, socket.timeout, requests.exceptions.ConnectionError,) as e:
                # FIXME
                # check: this code should never be executed as parent class will call on_timeout and on_error methods, without raising exceptions
                logger.warning('A timeout occurred. Streamer is sleeping for 10 seconds: %s', e)
                self.track_error(500, 'Timeout')
                time.sleep(10)
            except (requests.exceptions.ChunkedEncodingError, http.client.IncompleteRead) as e:
                logger.warning('Incomplete Read: %s.', e)
                self.track_error(400, 'Incomplete Read')
            except Exception as e:
                logger.warning('An error occurred during filtering in Streamer %s: %s. '
                               'Disconnecting collector due an unexpected error', self.__class__.__name__, e)
                self.disconnect(deactivate_collections=False)
                self.track_error(500, str(e))
                if IS_DEVELOPMENT:
                    import traceback
                    traceback.print_exc()

    def disconnect(self, deactivate_collections=True):
        logger.info('Disconnecting twitter streamer')

        if self.process and isinstance(self.process, multiprocessing.Process):
            self.process.terminate()  # this will call handle_termination method because it sends SIGTERM signal
        if self.producer:
            # closing Kafka producer client
            self.producer.flush()
            self.producer.close()

        with self.lock:
            self.connected = False
            self.is_connected.value = 0
            super().disconnect()
            if deactivate_collections:
                logger.warning('Deactivating all collections!')
                for c in self._collections:
                    c.deactivate()

    @property
    def errors(self):
        return self._shared_errors[:self.max_errors_len]

    @property
    def collections(self):
        return self._collections

    @property
    def keys(self):
        return ['{}{}'.format(s[:8].ljust(len(s) - 8, '*'), s[-8:])
                for s in (self.consumer_key, self.consumer_secret, self.access_token, self.access_token_secret)]

    def track_error(self, http_error_code, message):
        message = message.decode('utf-8') if isinstance(message, bytes) else str(message)
        with self.lock:
            self._shared_errors.insert(0, '{code}: {date} - {error}'.format(
                code=http_error_code,
                date=datetime.datetime.now().strftime('%Y%m%d %H:%M'),
                error=message.strip('\r\n'))
            )
            if len(self._shared_errors) > self.max_errors_len:
                self._shared_errors = self._shared_errors[:self.max_errors_len]

    def _get_collections(self):
        pass


class BackgroundStreamer(BaseStreamer):
    """

    """
    trigger = TwitterCollection.TRIGGER_BACKGROUND

    def _get_collections(self):
        collection = TwitterCollection.get_active_background()
        if not collection:
            return []
        return [collection]

    def connect(self, collections):
        self.collection = collections[0]
        super().connect(collections)

    def on_success(self, data):

        lang = self._detect_language(data)
        if not lang:
            return
        if lang == 'en' or lang in self.collection.languages:
            data['lang'] = lang
            tweet = Tweet.from_tweet(self.collection.id, data, ttype=Tweet.COLLECTED_TYPE)
            message = tweet.serialize(**{'trigger': self.trigger})
            self.producer.send(self.persister_kafka_topic, message)
            self.log(tweet)


class OnDemandStreamer(BaseStreamer):
    """

    """
    trigger = TwitterCollection.TRIGGER_ONDEMAND

    def _get_collections(self):
        collections = TwitterCollection.get_active_ondemand()
        return collections or []

    def on_success(self, data):

        lang = self._detect_language(data)
        if not lang:
            return
        data['lang'] = lang
        tweet = Tweet.from_tweet(Tweet.NO_COLLECTION_ID, data, ttype=Tweet.COLLECTED_TYPE)
        message = tweet.serialize(**{'trigger': self.trigger})
        self.producer.send(self.persister_kafka_topic, message)
        self.log(tweet)

    def use_pipeline(self, collection):
        return True


class ManualStreamer(OnDemandStreamer):
    trigger = TwitterCollection.TRIGGER_MANUAL

    def _get_collections(self):
        collections = TwitterCollection.get_active_manual()
        return collections or []

    def use_pipeline(self, collection):
        return collection.is_using_pipeline
