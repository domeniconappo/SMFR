import sys
import os
import logging
import time

from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import NoBrokersAvailable

from smfrcore.utils import IN_DOCKER, DEFAULT_HANDLER

kafka_bootstrap_servers = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'kafka:9092,kafka:9094').split(',') if IN_DOCKER else '127.0.0.1:9092,127.0.0.1:9094'.split(',')
alternatives = ['kafka:9092', 'kafka:9094', '127.0.0.1:9092', '127.0.0.1:9094', 'localhost:9092', 'localhost:9094', 'localhost:9092', 'kafka:9092', '127.0.0.1:9092']
persister_kafka_topic = os.getenv('PERSISTER_KAFKA_TOPIC', 'persister')

logger = logging.getLogger('KAFKA utils')
logger.setLevel(os.getenv('LOGGING_LEVEL', 'DEBUG'))
logger.addHandler(DEFAULT_HANDLER)


def _get_kafka_servers(retries):
    i = retries if 0 <= retries < len(alternatives) else 0
    return alternatives[i]


def make_kafka_consumer(topic, kafka_servers=None):
    if not kafka_servers:
        kafka_servers = kafka_bootstrap_servers
    retries = 10
    while retries >= 0:
        try:
            logger.info('Consumer %s-> Trying to connect to %s', topic, str(kafka_servers))
            consumer = KafkaConsumer(
                topic, check_crcs=False,
                group_id=topic,
                auto_offset_reset='earliest',
                max_poll_records=300, max_poll_interval_ms=1000000,
                bootstrap_servers=kafka_servers,
                session_timeout_ms=10000, heartbeat_interval_ms=3000
            )
            logger.info('[OK] KAFKA Consumer to %s', topic)
        except NoBrokersAvailable:
            time.sleep(5)
            retries -= 1
            if retries < 0:
                logger.error('Kafka server was not listening. Exiting...')
                sys.exit(1)
            kafka_servers = _get_kafka_servers(retries)
        else:
            return consumer


def make_kafka_producer(kafka_servers=None):
    if not kafka_servers:
        kafka_servers = kafka_bootstrap_servers
    retries = 10
    while retries >= 0:
        try:
            logger.info('Producer-> Trying to connect to %s', str(kafka_servers))
            producer = KafkaProducer(bootstrap_servers=kafka_servers, retries=5, max_block_ms=120000,
                                     compression_type='gzip', buffer_memory=134217728,
                                     linger_ms=500, batch_size=1048576, )
            logger.info('[OK] KAFKA Producer')

        except NoBrokersAvailable:
            time.sleep(5)
            retries -= 1
            if retries < 0:
                logger.error('Kafka server was not listening. Exiting...')
                sys.exit(1)
            kafka_servers = _get_kafka_servers(retries)
        else:
            return producer


def send_to_persister(producer, tweet):
    """

    :param producer: a KafkaProducer instance
    :param tweet: smfrcore.models.cassandra.Tweet object
    :return:
    """
    message = tweet.serialize()
    sent_to_persister = False
    retries = 5
    while not sent_to_persister and retries >= 0:
        try:
            producer.send(persister_kafka_topic, message)
        except KafkaTimeoutError as e:
            # try to mitigate kafka timeout error
            # KafkaTimeoutError: Failed to allocate memory
            # within the configured max blocking time
            logger.error(e)
            time.sleep(3)
            retries -= 1
        except Exception as e:
            logger.error(type(e))
            logger.error(e)
            logger.error(message)
            retries -= 1
        else:
            sent_to_persister = True
