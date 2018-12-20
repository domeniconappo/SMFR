"""
Module for functions to be executed as scheduled jobs
"""

import datetime
import logging
import os

import schedule

from smfrcore.models.sql import TwitterCollection, create_app
from smfrcore.utils import logged_job, job_exceptions_catcher, run_continuously, DEFAULT_HANDLER

from server.helpers import fetch_rra_helper, events_to_collections_payload
from server.config import RestServerConfiguration, DEVELOPMENT

logger = logging.getLogger('RRA Scheduled Jobs')
logger.setLevel(RestServerConfiguration.logger_level)
logger.addHandler(DEFAULT_HANDLER)


@logged_job
@job_exceptions_catcher
def add_rra_events(since='latest', restart_ondemand=True):
    current_app = create_app()
    with current_app.app_context():
        running_collections = TwitterCollection.get_active_ondemand()
        events, date = fetch_rra_helper(since)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug('FETCHED RRA %s', events)
        results = events_to_collections_payload(events, date)
        collections = TwitterCollection.add_rra_events(results)
        if any(c not in running_collections for c in collections) and restart_ondemand:
            # There is at least one new collection (even the same one with updated keywords)
            # Collector must be restarted
            logger.info(' ============= Adding/Updating on-demand collections from RRA EFAS events:\n\n%s',
                        '\n'.join(str(c) for c in collections))
            on_demand_collector = RestServerConfiguration().collectors[TwitterCollection.TRIGGER_ONDEMAND]
            on_demand_collector.restart()


@logged_job
@job_exceptions_catcher
def update_ondemand_collections_status(restart_ondemand=True):
    current_app = create_app()
    with current_app.app_context():
        updated = TwitterCollection.update_status_by_runtime()
        if updated and restart_ondemand:
            logger.info(' ============== Some on demand collections were stopped...restarting collector')
            on_demand_collector = RestServerConfiguration().collectors[TwitterCollection.TRIGGER_ONDEMAND]
            on_demand_collector.restart()


def schedule_rra_jobs():
    check_jobs_interval = int(os.getenv('CHECK_JOBS_INTERVAL_SECONDS', 60 * 60))
    if not DEVELOPMENT:
        rra_fetch_scheduling = os.getenv('RRA_FETCH_SCHEDULING', '00,12').split(',')
        check_ondemand_runtime_scheduling = os.getenv('CHECK_ONDEMAND_RUNTIME_SCHEDULING', '00,12').split(',')
    else:
        hours = [datetime.time(i).strftime('%H') for i in range(24)]
        rra_fetch_scheduling = hours
        check_ondemand_runtime_scheduling = hours

    kwargs = {'since': 'latest'}
    logger.info('====== Scheduling "Fetch RRA" jobs at {} of every day ======'.format(rra_fetch_scheduling))
    for hour in rra_fetch_scheduling:
        schedule.every().day.at('{}:05'.format(hour)).do(add_rra_events, **kwargs).tag('add-rra-events')

    logger.info('====== Scheduling "Updating On Demand collections" jobs at {} of every day ======'.format(check_ondemand_runtime_scheduling))
    for hour in check_ondemand_runtime_scheduling:
        schedule.every().day.at('{}:20'.format(hour)).do(update_ondemand_collections_status).tag('update-collection-status')

    run_continuously(interval=check_jobs_interval)
