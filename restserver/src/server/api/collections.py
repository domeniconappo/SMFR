"""
Module to handle /collections API
"""
import logging

import ujson as json
from flask import abort
from flask_jwt_extended import jwt_required, get_jwt_identity

from smfrcore.models import TwitterCollection, User, Aggregation, Tweet
from smfrcore.client.marshmallow import Collection as CollectionSchema, Aggregation as AggregationSchema
from sqlalchemy.exc import OperationalError

from smfrcore.errors import SMFRRestException

from server.api.clients import AnnotatorClient, GeocoderClient
from server.api.decorators import check_identity, check_role
from server.config import NUM_SAMPLES, RestServerConfiguration
from server.helpers import (add_collection_helper, add_collection_from_rra_event,
                            fetch_rra_helper, events_to_collections_payload)

logger = logging.getLogger('RestServer API')


# @jwt_required
def add_collection(payload):
    """
    POST /collections
    Create a new Collection and start the associated Collector if runtime is specified.
    :param payload: a CollectorPayload schema object (plain text)
    :return: the created collection as a dict, 201
    """
    payload = json.loads(payload) if payload and not isinstance(payload, dict) else payload or {}
    if not payload.get('keywords'):
        payload['languages'], payload['keywords'] = RestServerConfiguration.default_keywords()
    payload['timezone'] = payload.get('tzclient') or '+00:00'
    collection = add_collection_helper(**payload)
    res = CollectionSchema().dump(collection).data
    return res, 201


# @check_role
# @jwt_required
def add_ondemand(payload):
    """
    Add a list of on demand collections running immediately which stop at given runtime parameter
    :param payload: list of dict with following format
    {'bbox': {'max_lat': 40.6587, 'max_lon': -1.14236, 'min_lat': 39.2267, 'min_lon': -3.16142},
     'trigger': 'on-demand', 'forecast': '2018061500', 'keywords': 'Cuenca', 'efas_id': 1436
     }
    :type: list
    :return:
    """
    collections = []
    for event in payload:
        collection = add_collection_from_rra_event(**event)
        collections.append(collection)
    return CollectionSchema().dump(collections, many=True).data, 201


# @check_role
# @jwt_required
def fetch_efas(since='latest'):
    """

    :param since:
    :return:
    """
    # events list: [{"ID":1414,"SM_meanLT":2.0},{"ID":1436,"SM_meanLT":3.0},{"ID":1673,"SM_meanLT":7.0}]
    events, date = fetch_rra_helper(since)
    results = events_to_collections_payload(events, date)
    return {'results': results}, 200


def get():
    """
    GET /collections
    Get all collections stored in DB (active and not active)
    :return:
    """
    try:
        collections = TwitterCollection.query.all()
        res = CollectionSchema().dump(collections, many=True).data
    except OperationalError:
        return {'error': {'description': 'DB link was lost. Try again'}}, 500
    else:
        return res, 200


def get_running_collections():
    """
    GET /collections/active
    Get running collections/collectors
    :return:
    """
    out_schema = CollectionSchema()
    res = [c.collection for _, c in RestServerConfiguration().running_collections]
    res = out_schema.dump(res, many=True).data
    return res, 200


# @check_identity
# @jwt_required
def stop_collection(collection_id):
    """
    POST /collections/{collection_id}/stop
    Stop an existing and running collection. It should only be background or manual
    :param collection_id:
    :return:
    """
    collection = TwitterCollection.get_collection(collection_id)
    if not collection:
        return {'error': {'description': 'No collection with id {} was found'.format(collection_id)}}, 404

    collection.deactivate()
    collector = RestServerConfiguration().collectors[collection.trigger]
    collector.restart()
    return {}, 204


# @check_identity
# @jwt_required
def start_collection(collection_id):
    """
    POST /collections/{collection_id}/start
    Start an existing collection. It can only be background or manual
    :param collection_id:
    :return:
    """
    collection = TwitterCollection.get_collection(collection_id)
    if not collection:
        return {'error': {'description': 'No collection with id {} was found'.format(collection_id)}}, 404

    collection.activate()
    collector = RestServerConfiguration().collectors[collection.trigger]
    collector.restart()
    return {}, 204


# @check_identity
# @jwt_required
def remove_collection(collection_id):
    """
    POST /collections/{collection_id}/remove
    Remove a collection from DB
    :param collection_id: int
    :return:
    """
    collection = TwitterCollection.query.get(collection_id)
    if not collection:
        return {'error': {'description': 'No collector with this id was found'}}, 404
    aggregation = Aggregation.query.filter_by(collection_id=collection.id).first()
    if aggregation:
        aggregation.delete()
    if collection.is_active:
        collection.deactivate()
        collector = RestServerConfiguration().collectors[collection.trigger]
        collector.restart()

    collection.delete()
    return {}, 204


# @check_identity
# @jwt_required
def get_collection_details(collection_id):
    """
    GET /collections/{collection_id}/details
    :param collection_id: int
    :return: A CollectionResponse marshmallow object
    """
    try:
        collection = TwitterCollection.query.get(collection_id)
        if not collection:
            return {'error': {'description': 'No collector with this id was found'}}, 404
        aggregation = Aggregation.query.filter_by(collection_id=collection.id).first()

        collection_schema = CollectionSchema()
        collection_dump = collection_schema.dump(collection).data
        aggregation_schema = AggregationSchema()
        aggregation_dump = aggregation_schema.dump(aggregation).data

        samples_tweets = {}
        for ttype in ('collected', 'annotated', 'geotagged'):
            samples_tweets[ttype] = []
            tweets = Tweet.get_samples(collection_id=collection_id, ttype=ttype, size=NUM_SAMPLES)
            for i, t in enumerate(tweets, start=1):
                samples_tweets[ttype].append(Tweet.make_table_object(i, t))

        res = {'collection': collection_dump, 'aggregation': aggregation_dump,
               'annotation_models': AnnotatorClient.models()[0]['models'],
               'running_annotators': AnnotatorClient.running()[0], 'running_geotaggers': GeocoderClient.running()[0],
               'datatable': samples_tweets['collected'], 'datatableannotated': samples_tweets['annotated'],
               'datatablegeotagged': samples_tweets['geotagged']}
    except OperationalError:
        return {'error': {'description': 'DB link was lost. Try again'}}, 500
    else:
        return res, 200


# @check_identity
# @jwt_required
def geolocalize(collection_id, startdate=None, enddate=None):
    """

    :param collection_id:
    :param startdate:
    :param enddate:
    :return:
    """
    try:
        res, code = GeocoderClient.start(collection_id, startdate, enddate)
    except SMFRRestException as e:
        return {'error': {'description': str(e)}}, 500
    else:
        return res, code


# @check_identity
# @jwt_required
def annotate(collection_id, startdate=None, enddate=None):
    """

    :param collection_id:
    :param startdate:
    :param enddate:
    :return:
    """
    try:
        res, code = AnnotatorClient.start(collection_id, start_date=startdate, end_date=enddate)
    except SMFRRestException as e:
        return {'error': {'description': str(e)}}, 500
    else:
        return res, code


# @check_identity
# @jwt_required
def stopgeolocalize(collection_id):
    """

    :param collection_id:
    :return:
    """
    try:
        res, code = GeocoderClient.stop(collection_id)
    except SMFRRestException as e:
        return {'error': {'description': str(e)}}, 500
    else:
        return res, code


# @check_identity
# @jwt_required
def stopannotate(collection_id):
    """

    :param collection_id:
    :return:
    """
    try:
        res, code = AnnotatorClient.stop(collection_id)
    except SMFRRestException as e:
        return {'error': {'description': str(e)}}, 500
    else:
        return res, code