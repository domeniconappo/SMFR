import logging
from datetime import datetime

from twython import TwythonStreamer

from daemons.utils import safe_langdetect, tweet_normalization_aggressive


class CollectorStreamer(TwythonStreamer):
    """

    """

    def __init__(self, app_key, app_secret, oauth_token, oauth_token_secret,
                 client_args, collection, producer, quiet=False):
        from server.config import RestServerConfiguration, LOGGER_FORMAT, DATE_FORMAT
        logging.basicConfig(level=logging.INFO if not RestServerConfiguration.debug else logging.DEBUG,
                            format=LOGGER_FORMAT, datefmt=DATE_FORMAT)
        self.logger = logging.getLogger(__name__)
        self.kafka_topic = RestServerConfiguration.server_config['kafka_topic']
        self.quiet = quiet
        if self.quiet:
            logging.basicConfig(level=logging.ERROR)

        # A VirtualCollection object (it's a row in MySQL DB)
        self.collection = collection

        # A Kafka Producer
        self.producer = producer

        # starting streamer...
        self.logger.info('Instantiate a streamer with args %s', str(client_args))
        super().__init__(app_key, app_secret,
                         oauth_token, oauth_token_secret,
                         client_args=client_args)

    def on_success(self, data):

        if 'text' in data:
            lang = safe_langdetect(tweet_normalization_aggressive(data['text']))
            languages = self.collection.languages
            if lang in languages:
                from server.models import Tweet
                data['lang'] = lang
                tweet = Tweet.build_from_tweet(self.collection, data)
                # the tweet is sent immediately to kafka queue
                message = tweet.serialize()
                self.logger.info('Sending to queue: {}'.format(message[:120]))
                self.producer.send(self.kafka_topic, message)

    def on_error(self, status_code, data):
        self.logger.error(status_code)
        self.logger.error(str(data) or 'No data')
        self.disconnect()
        from server.models import VirtualTwitterCollection
        self.collection.status = VirtualTwitterCollection.INACTIVE_STATUS
        self.collection.stopped_at = datetime.utcnow()
        self.collection.save()

    def on_timeout(self):
        self.logger.error('Timeout')
