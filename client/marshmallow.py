# -*- coding:utf-8 -*-
# this is auto-generated by swagger-marshmallow-codegen
from client._marshmallow_custom import BaseSchema
from marshmallow import fields
from marshmallow.validate import (
    OneOf
)
from swagger_marshmallow_codegen.fields import (
    DateTime
)


class Collection(BaseSchema):
    id = fields.Integer()
    trigger = fields.String(validate=[OneOf(choices=['background', 'on-demand', 'manual'], labels=[])])
    ctype = fields.String(validate=[OneOf(choices=['keywords', 'geo'], labels=[])])
    forecast_id = fields.String()
    tracking_keywords = fields.List(fields.String())
    locations = fields.String()
    languages = fields.List(fields.String())
    runtime = DateTime()
    nuts3 = fields.String()
    nuts3source = fields.String()
    status = fields.String(validate=[OneOf(choices=['active', 'inactive'], labels=[])])
    started_at = DateTime()
    stopped_at = DateTime()


class CollectorPayload(BaseSchema):
    trigger = fields.String(required=True, validate=[OneOf(choices=['background', 'on-demand', 'manual'], labels=[])])
    forecast_id = fields.String()
    runtime = DateTime()
    nuts3 = fields.String()
    nuts3source = fields.String()


class CollectorResponse(BaseSchema):
    collection = fields.Nested('Collection')
    id = fields.Integer()
