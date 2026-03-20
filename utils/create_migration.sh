#!/bin/bash

# Create a database migration, and copy it back to the host.

set -e
. "${BASH_SOURCE%/*}/common.sh"

docker exec "$(container app)" sh -c "FLASK_CONFIG=../config.cfg FLASK_APP=app/__init__.py flask db migrate"
docker exec -u root "$(container app)" sh -c "cp /home/cdb/migrations/versions/* /source/migrations/versions/" || true

USER=$(whoami)
sudo chown -R "$USER:$USER" migrations/versions
