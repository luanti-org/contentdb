#!/bin/bash

#
# Rebuild and restart the worker, for development as workers aren't hot reloaded.
#   Requires docker-compose.dev.yml to be enabled, see docs/getting_started.md.
#

set -e

docker compose build worker
docker compose up --no-deps -d worker
