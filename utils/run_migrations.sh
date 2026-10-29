#!/bin/bash

# Run all pending migrations

set -e
. "${BASH_SOURCE%/*}/common.sh"

docker exec "$(container app)" sh -c "FLASK_APP=app/__init__.py flask db upgrade"
