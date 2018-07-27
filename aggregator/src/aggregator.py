from collections import Counter
import functools
from datetime import timedelta, datetime
import logging
from multiprocessing import cpu_count
from multiprocessing.pool import ThreadPool
import os

import cassandra
from sqlalchemy import or_

from smfrcore.utils import LOGGER_FORMAT, DATE_FORMAT

from smfrcore.models.sqlmodels import TwitterCollection, Aggregation, create_app


logging.basicConfig(level=os.environ.get('LOGGING_LEVEL', 'DEBUG'), format=LOGGER_FORMAT, datefmt=DATE_FORMAT)

logger = logging.getLogger(__name__)
logging.getLogger('cassandra').setLevel(logging.ERROR)

flask_app = create_app()

running_aggregators = set()
flood_propability_ranges = ((0, 10), (10, 90), (90, 100))


def with_logging(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        logger.info('Running job "%s"(args="%s", kwargs="%s")' % (func.__name__, str(args), str(kwargs)))
        result = func(*args, **kwargs)
        logger.info('Job "%s" completed' % func.__name__)
        return result
    return wrapper


def inc_annotated_counter(counter, flood_probability, nuts2=None):
    flood_probability *= 100
    for range_a, range_b in flood_propability_ranges:
        if range_a < flood_probability <= range_b:
            counter_key = '{}num_tweets_{}-{}'.format('{}_'.format(nuts2) if nuts2 else '', range_a, range_b)
            counter[counter_key] += 1


@with_logging
def aggregate(running_conf=None):
    """

    :param running_conf: ArgumentParser object with running, all and background attributes
    :return:
    """
    if not running_conf:
        raise ValueError('No parsed arguments were passed')
    running = running_conf.running
    everything = running_conf.all
    background = running_conf.background
    with flask_app.app_context():
        if running:
            collections_to_aggregate = TwitterCollection.query.filter(
                or_(
                    TwitterCollection.status == 'active',
                    TwitterCollection.stopped_at >= datetime.now() - timedelta(hours=6)
                )
            )
        elif everything:
            collections_to_aggregate = TwitterCollection.query.all()
        elif background:
            collections_to_aggregate = TwitterCollection.query.filter_by(trigger='background')
        else:
            raise ValueError('Aggregator must be started with a parameter: [-r (running)| -a (all) | -b (background)]')

        if not list(collections_to_aggregate):
            logger.info('No collections to aggregate with configuration: %s', pretty_running_conf(running_conf))
        aggregations_args = []
        for coll in collections_to_aggregate:
            aggregation = Aggregation.query.filter_by(collection_id=coll.id).first()
            if not aggregation:
                aggregation = Aggregation(collection_id=coll.id, values={})
                aggregation.save()
            aggregations_args.append(
                (coll.id,
                 aggregation.last_tweetid_collected,
                 aggregation.last_tweetid_annotated,
                 aggregation.last_tweetid_geotagged,
                 aggregation.timestamp_start, aggregation.timestamp_end,
                 aggregation.values)
            )

        # cpu_count() - 1 aggregation threads running at same time
        with ThreadPool(cpu_count() - 1) as p:
            p.starmap(run_single_aggregation, aggregations_args)


def run_single_aggregation(collection_id,
                           last_tweetid_collected, last_tweetid_annotated, last_tweetid_geotagged,
                           timestamp_start, timestamp_end,
                           initial_values):
    """
    Calculating stats with attributes:
    - NUTS2
    - timestamp_start
    - timestamp_end
    - num_tweets_00-20
    - num_tweets_20-40
    - num_tweets_40-60
    - num_tweets_60-80
    - num_tweets_80-100
    - NUTSID_num_tweets_60-80 etc.
    :param collection_id:
    :param last_tweetid_collected:
    :param last_tweetid_annotated:
    :param last_tweetid_geotagged:
    :param timestamp_end:
    :param timestamp_start:
    :param initial_values:
    :return:
    """
    from smfrcore.models.cassandramodels import Tweet

    if collection_id in running_aggregators:
        logger.warning('!!!!!! Previous aggregation for collection id %d is not finished yet !!!!!!' % collection_id)
        return 0
    max_collected_tweetid = 0
    max_annotated_tweetid = 0
    max_geotagged_tweetid = 0
    last_timestamp_start = timestamp_start or datetime(2100, 12, 31)
    last_timestamp_end = timestamp_end or datetime(1970, 1, 1)
    last_tweetid_collected = int(last_tweetid_collected) if last_tweetid_collected else 0
    last_tweetid_annotated = int(last_tweetid_annotated) if last_tweetid_annotated else 0
    last_tweetid_geotagged = int(last_tweetid_geotagged) if last_tweetid_geotagged else 0
    counter = Counter(initial_values)

    logger.info(' >>>>>>>>>>>> Starting aggregation for collection id %d' % collection_id)

    running_aggregators.add(collection_id)

    try:
        collected_tweets = Tweet.get_iterator(collection_id, 'collected', last_tweetid=last_tweetid_collected)
        for t in collected_tweets:
            max_collected_tweetid = max(max_collected_tweetid, t.tweet_id)
            last_timestamp_start = min(last_timestamp_start, t.created_at)
            last_timestamp_end = max(last_timestamp_end, t.created_at)
            counter['collected'] += 1

        annotated_tweets = Tweet.get_iterator(collection_id, 'annotated', last_tweetid=last_tweetid_annotated)
        for t in annotated_tweets:
            max_annotated_tweetid = max(max_annotated_tweetid, t.tweet_id)
            counter['annotated'] += 1
            inc_annotated_counter(counter, t.annotations['flood_probability'][1])
            # TODO put here most representative tweets logic....?

        geotagged_tweets = Tweet.get_iterator(collection_id, 'geotagged', last_tweetid=last_tweetid_geotagged)
        for t in geotagged_tweets:
            max_geotagged_tweetid = max(max_geotagged_tweetid, t.tweet_id)
            counter['geotagged'] += 1
            nuts2 = t.geo.get('nuts_id') or t.geo.get('efas_id')
            inc_annotated_counter(counter, t.annotations['flood_probability'][1], nuts2=nuts2)
    except cassandra.ReadFailure:
        logger.error('Cassandra Read failure...just exit. Hope you are lucky at next round...')
        return 1

    with flask_app.app_context():
        aggregation = Aggregation.query.filter_by(collection_id=collection_id).first()
        aggregation.last_tweetid_collected = max_collected_tweetid if max_collected_tweetid else last_tweetid_collected
        aggregation.last_tweetid_annotated = max_annotated_tweetid if max_annotated_tweetid else last_tweetid_annotated
        aggregation.last_tweetid_geotagged = max_geotagged_tweetid if max_geotagged_tweetid else last_tweetid_geotagged
        aggregation.timestamp_start = last_timestamp_start
        aggregation.timestamp_end = last_timestamp_end
        aggregation.values = dict(counter)
        aggregation.save()
        logger.info(' <<<<<<<<<<< Aggregation terminated for collection %d: %s', collection_id, str(aggregation.values))
        running_aggregators.remove(collection_id)
    return 0


def pretty_running_conf(conf):
    for k, v in vars(conf).items():
        if v:
            return 'Aggregation on {} collections'.format(k)