from dateutil.parser import parse

from flask import Flask
from flask_bootstrap import Bootstrap


def create_app():
    application = Flask(__name__)
    application.secret_key = 'development key'
    Bootstrap(application)
    return application


app = create_app()

import views


def datetimeformat(value, format='%Y-%m-%d %H:%M'):
    """
    A jinja2 filter for dates/times
    :param value: a string like 2018-02-23T13:24:04+00:00
    :param format: output rendered format
    :return:
    """
    if value is None:
        return ''
    value = parse(value)
    return value.strftime(format)


app.jinja_env.filters['datetimeformat'] = datetimeformat
