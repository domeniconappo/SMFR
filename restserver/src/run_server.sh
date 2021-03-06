#!/usr/bin/env bash

gunicorn -b 0.0.0.0:5555 --workers 1 --threads 4 --log-level warning --timeout 240 -k gthread --reload --access-logfile - --name restserver --preload start:app
