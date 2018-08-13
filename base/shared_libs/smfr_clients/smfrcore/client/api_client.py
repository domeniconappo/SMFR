"""
Module for API client to the SMFR Rest Server
"""
import os
import json
import logging

import requests
from flask.json import jsonify
from werkzeug.datastructures import FileStorage

from smfrcore.client.conf import ServerConfiguration
from smfrcore.errors import SMFRError
from smfrcore.utils import LOGGER_FORMAT, LOGGER_DATE_FORMAT, smfr_json_encoder

from .marshmallow import OnDemandPayload, CollectionPayload

logging.basicConfig(level=os.environ.get('LOGGING_LEVEL', 'DEBUG'),
                    format=LOGGER_FORMAT, datefmt=LOGGER_DATE_FORMAT)


class ApiLocalClient:
    """
    Simple requests client to SMFR Rest Server
    """
    logger = logging.getLogger(__name__)
    endpoints = {
        'list_collections': '/collections',
        'new_collection': '/collections',
        'stop_collector': '/collections/{id}/stop',
        'start_collector': '/collections/{id}/start',
        'list_running_collectors': '/collections/active',
        'list_inactive_collectors': '/collections/inactive',
        'remove_collection': '/collections/{id}/remove',
        'collection_details': '/collections/{id}',
        'annotate_collection': '/collections/{id}/annotate',
        'geotag_collection': '/collections/{id}/geo',
        'signup_user': '/users',
        'signin_user': '/users/signin',
        'fetch_efas': '/collections/fetch_efas',
        'add_ondemand': '/collections/add_ondemand',
    }

    def __init__(self):
        self.config = ServerConfiguration
        self.base_uri = self.config.restserver_baseurl

    def _build_url(self, endpoint, path_kwargs=None):
        endpoint = self.endpoints[endpoint]
        if path_kwargs:
            endpoint = endpoint.format(**path_kwargs)
        return '{}{}'.format(self.base_uri, endpoint)

    @classmethod
    def _check_response(cls, res):
        code = res.status_code
        if code >= 400:
            raise SMFRRestException(res.json(), code)

    def _get(self, endpoint, path_kwargs=None, query_params=None):
        try:
            url = self._build_url(endpoint, path_kwargs)
            requests_kwargs = {}
            if query_params:
                requests_kwargs['params'] = query_params
            res = requests.get(url, **requests_kwargs)
            self._check_response(res)
        except SMFRRestException as e:
            self.logger.error('REST API Error %s', str(e))
            raise e
        except ConnectionError:
            self.logger.error('SMFR REST API server is not listening...')
        else:
            return res.json()

    def _post(self, endpoint, payload=None, path_kwargs=None, query_params=None):
        """
        Main method that executes POST calls
        :param query_params: dict for querystring part to put into `params` kwarg of request.post
        :param endpoint: endpoint url name (see ApiLocalClient.endpoints)
        :param payload: dict to put into `data` kwarg of request.post
        :param path_kwargs: dict used for variable replacement in endpoint paths
        :return: dict representing JSON response
        """
        headers = {'Content-Type': 'application/json'}
        requests_kwargs = {'headers': headers,
                           'data': json.dumps(payload, default=smfr_json_encoder) if payload else '{}',
                           }

        if query_params:
            requests_kwargs['params'] = query_params

        url = self._build_url(endpoint, path_kwargs)

        self.logger.debug('POST %s %s', url, requests_kwargs)
        try:
            res = requests.post(url, **requests_kwargs)
            self._check_response(res)
        except SMFRRestException as e:
            self.logger.error('REST API Error %s', str(e))
            raise e
        except ConnectionError as e:
            self.logger.error('SMFR REST API server is not listening...%s', str(e))
            raise SMFRRestException({'error': {'description': 'SMFR Rest Server is not listening'}},
                                    status_code=500)
        else:
            try:
                return res.json()
            except ValueError:
                return {}

    def list_collections(self):
        """
        Get all collections defined in SMFR
        :return: collections defined in SMFR
        """
        return self._get('list_collections')

    def list_running_collectors(self):
        """
        Get collections that are currently fetching from Twitter Stream
        :return: running collections
        """
        return self._get('list_running_collectors')

    def list_inactive_collectors(self):
        """
        Get inactive collections
        :return: Collections for whose collector was paused
        """
        return self._get('list_inactive_collectors')

    def new_collection(self, input_payload):
        schema = CollectionPayload()
        payload = schema.load(input_payload).data
        self.logger.debug('Payload %s', input_payload)
        return self._post('new_collection', payload=payload)

    def signup_user(self, input_payload):
        data = {'username': input_payload['username'], 'password': input_payload['password']}
        return self._post('signup_user', data)

    def login_user(self, input_payload):
        data = {'username': input_payload['username'], 'password': input_payload['password']}
        return self._post('login_user', data)

    def logout_user(self, user_id):
        return self._post('logout_user', path_kwargs={'id': user_id})

    def remove_collection(self, collection_id):
        return self._post('remove_collection', path_kwargs={'id': collection_id}), 204

    def stop_collector(self, collector_id):
        return self._post('stop_collector', path_kwargs={'id': collector_id})

    def start_collector(self, collector_id):
        return self._post('start_collector', path_kwargs={'id': collector_id})

    def get_collection(self, collection_id):
        return self._get('collection_details', path_kwargs={'id': collection_id})

    def start_annotation(self, collection_id, lang='en'):
        return self._post('annotate_collection', path_kwargs={'id': collection_id}, query_params={'lang': lang})

    def start_geotagging(self, collection_id):
        return self._post('geotag_collection', path_kwargs={'id': collection_id})

    def fetch_efas(self, since='latest'):
        return self._get('fetch_efas', query_params={'since': since}), 200

    def add_ondemand_collections(self, events):
        payload = OnDemandPayload().load(events, many=True).data
        return self._post('add_ondemand', payload=payload), 201


class SMFRRestException(SMFRError):
    def __init__(self, response, status_code):
        err = response.get('error', {})
        message = err.get('description', 'No details.') if err else str(response)
        self.status_code = status_code
        self.message = message
        super().__init__(message)

    def __str__(self):
        return '<{o.status_code}: {o.message}>'.format(o=self)