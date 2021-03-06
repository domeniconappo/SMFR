import datetime
import copy
import os
import statistics

import arrow
from arrow.parser import ParserError
from cachetools import TTLCache
from fuzzywuzzy import process, fuzz
from sqlalchemy import Column, Integer, ForeignKey, TIMESTAMP, Boolean, BigInteger, orm
from sqlalchemy_utils import ChoiceType, ScalarListType, JSONType, Choice

from .base import sqldb, SMFRModel, LongJSONType
from .users import User
from .nuts import Nuts2


class TwitterCollection(SMFRModel):
    """

    """
    __tablename__ = 'virtual_twitter_collection'
    __table_args__ = {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8mb4', 'mysql_collate': 'utf8mb4_general_ci'}

    ACTIVE_STATUS = 'active'
    INACTIVE_STATUS = 'inactive'

    TRIGGER_ONDEMAND = 'on-demand'
    TRIGGER_BACKGROUND = 'background'
    TRIGGER_MANUAL = 'manual'

    TRIGGERS = [
        (TRIGGER_BACKGROUND, 'Background'),
        (TRIGGER_ONDEMAND, 'On Demand'),
        (TRIGGER_MANUAL, 'Manual'),
    ]

    STATUSES = [
        (ACTIVE_STATUS, 'Running'),
        (INACTIVE_STATUS, 'Stopped'),
    ]

    ACTIVE_CHOICE = Choice(ACTIVE_STATUS, 'Running')
    INACTIVE_CHOICE = Choice(INACTIVE_STATUS, 'Stopped')
    TRIGGER_BACKGROUND_CHOICE = Choice(TRIGGER_BACKGROUND, 'Background')
    TRIGGER_ONDEMAND_CHOICE = Choice(TRIGGER_ONDEMAND, 'On Demand')
    TRIGGER_MANUAL_CHOICE = Choice(TRIGGER_MANUAL, 'Manual')

    CHOICES = {
        ACTIVE_STATUS: ACTIVE_CHOICE,
        INACTIVE_STATUS: INACTIVE_CHOICE,
        TRIGGER_BACKGROUND: TRIGGER_BACKGROUND_CHOICE,
        TRIGGER_ONDEMAND: TRIGGER_ONDEMAND_CHOICE,
        TRIGGER_MANUAL: TRIGGER_MANUAL_CHOICE,
    }

    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    forecast_id = Column(Integer)
    trigger = Column(ChoiceType(TRIGGERS), nullable=False)
    tracking_keywords = Column(ScalarListType(str), nullable=True)
    locations = Column(JSONType, nullable=True)
    languages = Column(ScalarListType(str), nullable=True)
    status = Column(ChoiceType(STATUSES), nullable=False, default='inactive')
    efas_id = Column(Integer, nullable=True)
    started_at = Column(TIMESTAMP, nullable=True)
    created_at = Column(TIMESTAMP, nullable=True, default=datetime.datetime.utcnow)
    stopped_at = Column(TIMESTAMP, nullable=True)
    runtime = Column(TIMESTAMP, nullable=True)
    use_pipeline = Column(Boolean, nullable=False, default=False)
    user_id = Column(Integer, ForeignKey('users.id'))
    user = sqldb.relationship('User', backref=sqldb.backref('collections', uselist=True))

    cache = TTLCache(500, 60 * 60 * 6)  # max size 500, 6 hours caching

    cache_keys = {
        'all-on-demand': 'all-on-demand',
        'on-demand': 'active-on-demand',
        'background': 'background-collection',
        'collection': 'id-{}',
        'manual': 'active-manual',
        'active': 'active',
        'running': 'running',
    }

    # init caches
    for key in cache_keys:
        if key in ('collection', 'background'):
            continue
        cache[cache_keys[key]] = []
    cache['background'] = None

    def __repr__(self):
        return str(self)

    def __str__(self):
        return 'Collection<{o.id}: {o.forecast_id}' \
               '\n Tracking: {o.tracking_keywords}' \
               '\n Bbox: {o.locations}'\
               '\n Trigger: {x}'.format(o=self, x=self.trigger.value)

    def __eq__(self, other):
        if not other:
            return False
        return self.efas_id == other.efas_id and self.trigger == other.trigger \
            and self.tracking_keywords == other.tracking_keywords and self.languages == other.languages

    def __init__(self, *args, **kwargs):
        self.nuts2 = None
        if kwargs.get('efas_id') is not None:
            self.nuts2 = Nuts2.get_by_efas_id(kwargs['efas_id'])
        self.created_at = kwargs.get('created_at') or datetime.datetime.utcnow()
        super().__init__(*args, **kwargs)

    # the two methods below (_set_keywords_and_languages and _set_locations)
    # are a bit intricated as they deal with WEB UI input forms
    def _set_keywords_and_languages(self, keywords, languages):

        if not keywords:
            keywords = []
        if not languages:
            languages = []

        self.languages = []
        self.tracking_keywords = []

        if isinstance(keywords, list):
            self.tracking_keywords = keywords
        elif isinstance(keywords, str):
            if ':' in keywords:
                # keywords from Web UI as text in the form of groups "lang1:kw1,kw2 lang2:kw3,kw4"
                kwdict = {}
                groups = keywords.split(' ')
                for g in groups:
                    lang, kws = list(map(str.strip, g.split(':')))
                    kwdict[lang] = list(map(str.strip, kws.split(',')))
                self.languages = sorted(list(kwdict.keys()))
                self.tracking_keywords = sorted(list(set(w for s in kwdict.values() for w in s)))
            else:
                # keywords from Web UI as text in the form of comma separated words "kw1,kw2,kw3,kw4".
                # No language specified
                self.tracking_keywords = list(map(str.strip, sorted(list(set(w for w in keywords.split(','))))))
                self.languages = []

        if languages and not self.languages and isinstance(languages, list):
            # default keywords with languages
            self.languages = languages

        # refine keywords: some NUTS3 names contains more than one city
        refined_keywords = []
        for kw in self.tracking_keywords:
            l_split = kw.split(' and ')
            for subkw in l_split:
                sub_list = subkw.split(' & ')
                refined_keywords += sub_list
        self.tracking_keywords = list(set(refined_keywords))

    def _set_locations(self, locations):
        locations = locations or {}
        if isinstance(locations, dict) and not all(locations.get(k) for k in ('min_lon', 'min_lat', 'max_lon', 'max_lat')):
            locations = {}
        if locations:
            if isinstance(locations, str):
                coords = list(map(str.strip, locations.split(',')))
                locations = {'min_lon': coords[0], 'min_lat': coords[1], 'max_lon': coords[2], 'max_lat': coords[3]}
            elif isinstance(locations, dict):
                tmp_locations = locations.copy()
                for k, v in tmp_locations.items():
                    if k not in ('min_lon', 'min_lat', 'max_lon', 'max_lat'):
                        del locations[k]
                        continue
                    locations[k] = round(float(v), 3)
        self.locations = locations

    @orm.reconstructor
    def init_on_load(self):
        self.nuts2 = None
        if self.efas_id is not None:
            self.nuts2 = Nuts2.get_by_efas_id(efas_id=self.efas_id)

    @classmethod
    def create(cls, **data):
        user = data.get('user') or User.query.filter_by(role='admin').first()
        if not user:
            raise ValueError('You have to configure at least one admin user for SMFR system')

        obj = cls()
        obj.user_id = user.id
        obj.status = cls.CHOICES.get(data.get('status') or cls.INACTIVE_STATUS)
        obj.trigger = cls.CHOICES.get(data['trigger'])
        obj.runtime = cls.convert_runtime(data.get('runtime'))
        obj.forecast_id = data.get('forecast_id')
        obj.efas_id = int(data.get('efas_id', 0)) or None
        obj.use_pipeline = data.get('use_pipeline', False)

        keywords = data.get('keywords') or []
        languages = data.get('languages') or []
        locations = data.get('bounding_box') or data.get('locations') or {}

        if obj.is_background:
            existing = cls.get_active_background()
            if existing:
                raise ValueError("You can't have more than one running background collection. "
                                 "First stop the active background collection.")
            obj._set_keywords_and_languages(keywords, languages)
            obj._set_locations(locations)
            obj.save()
        else:
            obj.status = cls.ACTIVE_CHOICE  # force active status when creating/updating on demand collections
            efas_id = int(data.get('efas_id', -9999))
            existing = cls.query.filter_by(efas_id=efas_id, status=cls.ACTIVE_CHOICE).first()
            if existing:
                # a collection for this efas region is already active and running
                if existing.trigger == obj.trigger:
                    existing.runtime = existing.runtime if existing.forecast_id == obj.forecast_id else obj.runtime
                    existing.save()
                else:
                    # example case here: adding a manual collection for a EFAS ID while there's already an on-demand collection that is running
                    raise ValueError('You can\'t have more than one running collection per EFAS/NUTS2 area.')
                obj = existing
            else:
                # create a new collection (it's a new event)
                obj.started_at = datetime.datetime.utcnow()
                obj._set_keywords_and_languages(keywords, languages)
                obj._set_locations(locations)
                obj.save()
        # updating caches
        cls._update_caches(obj)
        return obj

    @classmethod
    def add_rra_events(cls, events):
        """

        :param events: Dictionary with the structure
            events[event['ID']] = {
            'efas_id': efas_id,  # event['ID'] is the same of efas_id
            'trigger': 'on-demand', 'efas_name': nuts2.efas_name,
            'nuts': nuts_id, 'country': country_name, 'lead_time': lead_time,
            'keywords': cities, 'bbox': bbox, 'forecast': date  # forecast will have format YYYYMMDDHH
            }
        :type events: dict
        :return:
        """
        collections = []
        for efas_id, event in events.items():
            runtime = cls.runtime_from_leadtime(event['lead_time'])
            data = {'trigger': event['trigger'], 'runtime': runtime, 'status': cls.ACTIVE_STATUS,
                    'locations': event['bbox'], 'use_pipeline': True,
                    'timezone': event.get('tzclient', '+00:00'), 'keywords': event['keywords'],
                    'efas_id': event['efas_id'], 'forecast_id': int(event['forecast'])}
            collection = cls.create(**data)
            collections.append(collection)
        return collections

    @classmethod
    def get_active_background(cls):
        key = cls.cache_keys['background']
        res = cls.cache.get(key)
        if not res:
            res = cls.query.filter_by(trigger=cls.TRIGGER_BACKGROUND, status=cls.ACTIVE_STATUS).first()
            cls.cache[key] = res
        return res

    @classmethod
    def get_active(cls):
        """
        alias for get_running
        :return:
        """
        return cls.get_running()

    @classmethod
    def get_running(cls):
        """
        All active collections
        :return:
        """
        key = cls.cache_keys['running']
        res = cls.cache.get(key)
        if not res:
            res = cls.query.filter_by(
                status=cls.ACTIVE_STATUS
            ).order_by(cls.started_at.desc(), cls.runtime.desc()).all()
            cls.cache[key] = res
        return res

    @classmethod
    def get_active_ondemand(cls):
        key = cls.cache_keys['on-demand']
        res = cls.cache.get(key)
        if not res:
            included_collections = []
            res = cls.query.filter(
                cls.trigger == cls.TRIGGER_ONDEMAND, cls.status == cls.ACTIVE_STATUS,
            ).order_by(cls.status, cls.started_at.desc(), cls.runtime.desc()).all()
            past_collections_ids = [int(i) for i in os.getenv('INCLUDE_PAST_COLLECTIONS', '').split(',') if i]
            if past_collections_ids:
                included_collections = (cls.query.get(i) for i in past_collections_ids)
                included_collections = [c for c in included_collections if c]
            cls.cache[key] = res + included_collections
        return cls.cache[key]

    @classmethod
    def get_ondemand(cls):
        key = cls.cache_keys['all-on-demand']
        res = cls.cache.get(key)
        if not res:
            res = cls.query.filter_by(
                trigger=cls.TRIGGER_ONDEMAND
            ).order_by(cls.started_at.desc(), cls.runtime.desc()).all()
            cls.cache[key] = res
        return res

    @classmethod
    def get_active_manual(cls):
        key = cls.cache_keys['manual']
        res = cls.cache.get(key)
        if not res:
            res = cls.query.filter_by(trigger=cls.TRIGGER_MANUAL, status=cls.ACTIVE_STATUS).all()
            cls.cache[key] = res
        return copy.deepcopy(res)

    @classmethod
    def get_collection(cls, collection_id):
        key = cls.cache_keys['collection'].format(collection_id)
        res = cls.cache.get(key)
        if not res:
            res = cls.query.get(collection_id)
            cls.cache[key] = res
        return res

    @classmethod
    def get_collections(cls, collection_ids):
        return cls.query.filter(cls.id.in_(collection_ids)).all()

    def deactivate(self):
        self.status = self.INACTIVE_CHOICE
        self.stopped_at = datetime.datetime.utcnow()
        self.save()
        self._update_caches(self, action='deactivate')

    def activate(self):
        self.status = self.ACTIVE_CHOICE
        self.started_at = datetime.datetime.utcnow()
        self.save()
        self._update_caches(self, action='activate')

    def delete(self):
        super().delete()
        self._update_caches(obj=self, action='delete')

    @classmethod
    def _update_caches(cls, obj, action='create'):
        """
        Updating all caches:
        'on-demand': 'active-on-demand',
        'background': 'background-collection',
        'collection': 'id-{}',
        'manual': 'active-manual',
        'active': 'active',
        'running': 'running',
        :param obj: TwitterCollection object
        :param action: 'create' or 'delete'
        """

        collection_key = obj.cache_keys['collection'].format(obj.id)

        def _update_cached_list(cache_key):
            current_cached_collections = cls.cache.get(cache_key) or []
            updated_collections_cache = copy.deepcopy(current_cached_collections)
            for c in current_cached_collections:
                if obj.efas_id == c.efas_id:
                    updated_collections_cache.remove(c)
                    break
            if obj not in updated_collections_cache:
                # This test would fail if keywords/locations are different.
                # That's why we first remove the collection with same efas_id of the one we are adding
                updated_collections_cache.append(obj)
            cls.cache[cache_key] = updated_collections_cache

        def _update_delete():
            cls.cache[collection_key] = None
            try:
                if obj.is_active:
                    cls.cache.get(cls.cache_keys['active'], []).remove(obj)
                    cls.cache.get(cls.cache_keys['running'], []).remove(obj)
                    if obj.is_manual:
                        cls.cache.get(cls.cache_keys['manual'], []).remove(obj)
                    elif obj.is_background:
                        cls.cache[cls.cache_keys['background']] = None
                    elif obj.is_ondemand:
                        cls.cache.get(cls.cache_keys['on-demand'], []).remove(obj)
                        cls.cache.get(cls.cache_keys['all-on-demand'], []).remove(obj)
            except ValueError:
                pass

        def _update_create():
            cls.cache[collection_key] = obj
            if obj.is_active:
                _update_cached_list(cls.cache_keys['running'])
                if obj.is_manual:
                    # update manual active
                    current_manual_collections = copy.deepcopy(cls.cache[cls.cache_keys['manual']])
                    current_manual_collections.append(obj)
                    cls.cache[cls.cache_keys['manual']] = current_manual_collections
                elif obj.is_background:
                    # update background active
                    cls.cache[cls.cache_keys['background']] = obj
                elif obj.is_ondemand:
                    # update ondemand active
                    _update_cached_list(cls.cache_keys['on-demand'])
                    _update_cached_list(cls.cache_keys['all-on-demand'])

        def _update_deactivate():
            try:
                cls.cache.get(cls.cache_keys['running'], []).remove(obj)
                if obj.is_manual:
                    cls.cache.get(cls.cache_keys['manual'], []).remove(obj)
                elif obj.is_background:
                    cls.cache[cls.cache_keys['background']] = None
                elif obj.is_ondemand:
                    cls.cache.get(cls.cache_keys['on-demand'], []).remove(obj)
            except ValueError:
                pass

        def _update_activate():
            cls.cache.get(cls.cache_keys['active'], []).append(obj)
            cls.cache.get(cls.cache_keys['running'], []).append(obj)
            if obj.is_manual:
                cls.cache.get(cls.cache_keys['manual'], []).append(obj)
            elif obj.is_background:
                cls.cache[cls.cache_keys['background']] = obj
            elif obj.is_ondemand:
                cls.cache.get(cls.cache_keys['on-demand'], []).append(obj)

        update_cache_methods = {
            'delete': _update_delete,
            'create': _update_create,
            'activate': _update_activate,
            'deactivate': _update_deactivate
        }

        update_cache_methods[action]()

    @classmethod
    def update_status_by_runtime(cls):
        """
        Deactivate collections if runtime is 'expired'
        This method should be scheduled every 12 hours
        """
        updated = False
        collections = cls.query.filter(cls.runtime.isnot(None), cls.status == cls.ACTIVE_STATUS)
        now = datetime.datetime.utcnow()
        for c in collections:
            if c.runtime < now:
                cls.deactivate(c)
                updated = True
        return updated

    @classmethod
    def runtime_from_leadtime(cls, lead_time):
        """

        :param lead_time: number of days before the peak occurs
        :return: runtime in format %Y-%m-%d %H:%M
        """
        runtime = (datetime.datetime.utcnow() +
                   datetime.timedelta(days=int(lead_time) + 2)).replace(hour=0, minute=0, second=0, microsecond=0)
        return runtime.strftime('%Y-%m-%d %H:%M')

    @classmethod
    def convert_runtime(cls, runtime):
        """
        datetime objects are serialized by Flask json decoder in the format 'Thu, 02 Aug 2018 02:45:00 GMT'
        arrow format is 'ddd, DD MMM YYYY HH:mm:ss ZZZ', equivalent to '%a, %d %b %Y %I:%M:%S %Z'
        :param runtime:
        :return: datetime object
        """
        if not runtime:
            return None
        try:
            res = arrow.get(runtime).datetime.replace(tzinfo=None)
        except ParserError:
            res = arrow.get(runtime, 'ddd, DD MMM YYYY HH:mm:ss ZZZ').datetime.replace(tzinfo=None)
        return res

    @property
    def efas_name(self):
        return None if self.efas_id is None else self.nuts2.efas_name

    @property
    def efas_country(self):
        return None if self.efas_id is None else self.nuts2.country

    @property
    def bboxfinder(self):
        bbox = ''
        if self.locations and all(v for v in self.locations.values()):
            bbox = '{},{},{},{}'.format(self.locations['min_lat'], self.locations['min_lon'],
                                        self.locations['max_lat'], self.locations['max_lon'])
        return '' if not bbox else 'http://bboxfinder.com/#{}'.format(bbox)

    @property
    def bounding_box(self):
        bbox = ''
        if self.locations and all(v for v in self.locations.values()):
            bbox = 'Lower left: {min_lon} - {min_lat}, Upper Right: {max_lon} - {max_lat}'.format(**self.locations)
        return bbox

    def is_tweet_in_bounding_box(self, tweet):

        from smfrcore.models.cassandra import Tweet
        if not self.locations or not self.locations.get('min_lat'):
            return False
        res = False
        original_tweet_dict = tweet.original_tweet_as_dict
        min_lat, max_lat, min_lon, max_lon = self.locations['min_lat'], self.locations['max_lat'], self.locations['min_lon'], self.locations['max_lon']
        lat, lon = Tweet.coords_from_raw_tweet(original_tweet_dict)
        min_tweet_lat, max_tweet_lat, min_tweet_lon, max_tweet_lon = Tweet.get_tweet_bbox(original_tweet_dict)

        if lat and lon:
            res = min_lat <= lat <= max_lat and min_lon <= lon <= max_lon

        if not res and all((min_tweet_lat, min_tweet_lon, max_tweet_lat, max_tweet_lon)):
            # determine the coordinates of the intersection rectangle
            lon_left = max(min_lon, min_tweet_lon)
            lat_bottom = max(min_lat, min_tweet_lat)
            lon_right = min(max_lon, max_tweet_lon)
            lat_top = min(max_lat, max_tweet_lat)

            res = lon_left <= lon_right and lat_bottom <= lat_top
        return res

    @property
    def centroid(self):
        """
        Provide a relatively accurate center lat, lon returned as a list pair, given
        a list of list pairs.
        ex: in: geolocations = ((lat1,lon1), (lat2,lon2),)
            out: (center_lat, center_lon)
        """
        if not self.locations or not self.locations.get('min_lat'):
            # return europe center (ukraine)
            return 48.499998, 23.3833318
        coords = (self.locations['min_lat'], self.locations['max_lat'], self.locations['min_lon'], self.locations['max_lon'])
        return statistics.mean(coords[:2]), statistics.mean(coords[2:])

    def tweet_matched_keyword(self, tweet):
        """
        Returns the matched tweet keyword for this collection if existing, None otherwise
        :param tweet: smfrcore.models.Tweet object
        :return: matched keyword
        :rtype: str
        """
        from smfrcore.models.cassandra import Tweet

        original_tweet_dict = tweet.original_tweet_as_dict
        text_to_match = Tweet.get_contributing_match_keywords_fields(original_tweet_dict).strip()
        for kw in self.tracking_keywords:
            if kw in text_to_match:
                return kw
        res = process.extractOne(text_to_match, self.tracking_keywords, scorer=fuzz.partial_ratio, score_cutoff=80)
        return res[0] if res else None

    @property
    def is_active(self):
        return self.status in (self.ACTIVE_STATUS, self.CHOICES[self.ACTIVE_STATUS])

    @property
    def is_ondemand(self):
        return self.trigger in (self.TRIGGER_ONDEMAND, self.CHOICES[self.TRIGGER_ONDEMAND])

    @property
    def is_manual(self):
        return self.trigger in (self.TRIGGER_MANUAL, self.CHOICES[self.TRIGGER_MANUAL])

    @property
    def is_background(self):
        return self.trigger in (self.TRIGGER_BACKGROUND, self.CHOICES[self.TRIGGER_BACKGROUND])

    @property
    def is_using_pipeline(self):
        return self.is_ondemand or self.use_pipeline

    @property
    def is_active_or_recent(self):
        return self.status in (self.ACTIVE_STATUS, self.CHOICES[self.ACTIVE_STATUS]) or \
               (self.stopped_at and
                self.stopped_at >= (datetime.datetime.utcnow() - datetime.timedelta(days=2)))


class Aggregation(SMFRModel):
    """

    """
    __tablename__ = 'aggregation'
    __table_args__ = {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8mb4', 'mysql_collate': 'utf8mb4_general_ci'}

    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    collection_id = Column(Integer, ForeignKey('virtual_twitter_collection.id'))
    collection = sqldb.relationship('TwitterCollection', backref=sqldb.backref('aggregation', uselist=False))
    values = Column(LongJSONType, nullable=False)
    last_tweetid_collected = Column(BigInteger, nullable=True)
    last_tweetid_annotated = Column(BigInteger, nullable=True)
    last_tweetid_geotagged = Column(BigInteger, nullable=True)
    timestamp_start = Column(TIMESTAMP, nullable=True)
    timestamp_end = Column(TIMESTAMP, nullable=True)
    relevant_tweets = Column(LongJSONType, nullable=True)
    trends = Column(LongJSONType, nullable=True)
    created_at = Column(TIMESTAMP, nullable=True, default=datetime.datetime.utcnow)

    def __init__(self, *args, **kwargs):
        self.created_at = kwargs.get('created_at') or datetime.datetime.utcnow()
        super().__init__(*args, **kwargs)

    @property
    def data(self):
        # TODO rearrange values dictionary for cleaner output...
        return self.values

    @property
    def aggregated_tweets(self):
        return self.relevant_tweets

    @classmethod
    def get_by_collection(cls, collection_id):
        return cls.query.filter_by(collection_id=collection_id).first()

    def __str__(self):
        return 'Aggregation ID: {} (collection: {})'.format(self.id, self.collection_id)
