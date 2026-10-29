#!/bin/bash

#
# Call from a docker host to rebuild and update running instances of CDB.
#    This is for production use. In debug mode, code changes are hot reloaded (see docker-compose.dev.yml).
#

set -e

docker compose build app
docker compose build worker

docker compose up --no-deps -d app
docker compose up --no-deps --scale worker=4 -d worker
