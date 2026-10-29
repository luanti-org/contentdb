#!/bin/bash

# Run all pending migrations

set -e
. "${BASH_SOURCE%/*}/common.sh"

# If dev, reload
if docker exec "$(container app)" test -d /source; then
	./utils/reload.sh
fi
docker exec "$(container app)" sh -c "FLASK_APP=app/__init__.py flask db upgrade"
