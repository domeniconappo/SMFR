import os
import logging
import signal

from flask_restful import Resource, Api, fields, marshal_with, marshal_with_field

from smfrcore.models.sql import create_app
from smfrcore.utils import DEFAULT_HANDLER

from geocodercontainer import GeocoderContainer


app = create_app()
api = Api(app)

logger = logging.getLogger('GEOCODER')
logger.setLevel(os.getenv('LOGGING_LEVEL', 'DEBUG'))
logger.addHandler(DEFAULT_HANDLER)

logging.getLogger('cassandra').setLevel(logging.WARNING)
logging.getLogger('kafka').setLevel(logging.WARNING)


class GeocoderApi(Resource):
    """
    Flask Restful API for Geocoder microservice
    """

    @marshal_with(
        {'error': fields.Nested({'description': fields.Raw}),
         'result': fields.Raw, 'action_performed': fields.Raw}
    )
    def put(self, collection_id, action):
        action = action.lower()
        if action not in ('start', 'stop'):
            return {'error': {'description': 'Unknown operation {}'.format(action)}}, 400

        if action == 'start':
            if GeocoderContainer.is_running_for(collection_id):
                return {'error': {'description': 'Geocoder already running for {}'.format(collection_id)}}, 400
            GeocoderContainer.iterator_in_background(collection_id)
        elif action == 'stop':
            GeocoderContainer.stop(collection_id)

        return {'result': 'success', 'action_performed': action}, 201


class RunningGeotaggersApi(Resource):
    """
    Flask Restful API for Geocoder microservice for `/running` endpoint
    """

    @marshal_with_field(fields.List(fields.Integer))
    def get(self):
        return GeocoderContainer.running(), 200


class GeotaggerCounters(Resource):
    """
    API for `/counters` endpoint
    """

    @marshal_with_field(fields.Raw)
    def get(self):
        return GeocoderContainer.counters(), 200


if __name__ == 'start':
    api.add_resource(GeocoderApi, '/<int:collection_id>/<string:action>')
    api.add_resource(RunningGeotaggersApi, '/running')
    api.add_resource(GeotaggerCounters, '/counters')
    logger.info('[OK] Geocoder Microservice ready for incoming requests')
    process = GeocoderContainer.consumer_in_background()

    def stop_geocoder(signum, _):
        logger.debug("Received %d", signum)
        logger.debug("Stopping any running producer/consumer...")

        if process:
            logger.info("Stopping consumer %s", str(GeocoderContainer))
            process.terminate()

    signal.signal(signal.SIGINT, stop_geocoder)
    signal.signal(signal.SIGTERM, stop_geocoder)
    signal.signal(signal.SIGQUIT, stop_geocoder)
    logger.debug('Registered %d %d and %d', signal.SIGINT, signal.SIGTERM, signal.SIGQUIT)
