#!/bin/bash

#
# The entrypoint for the docker containers
#

# Debug
# FLASK_APP=app/__init__.py FLASK_CONFIG=../config.cfg FLASK_DEBUG=1 python3 -m flask run -h 0.0.0.0 -p 5123

if [ -z "$FLASK_DEBUG" ]; then
	echo "FLASK_DEBUG is required in .env"
	exit 1
fi

if [ "$FLASK_DEBUG" -eq "1" ]; then
	FLASK_APP=app/__init__.py FLASK_CONFIG=../config.cfg FLASK_RUN_PORT=5123 flask run --host=0.0.0.0
else
	ENV="-e FLASK_APP=app/__init__.py -e FLASK_CONFIG=../config.cfg -e FLASK_DEBUG=$FLASK_DEBUG"
	gunicorn -w 4 -b :5123 $ENV app:app
fi
