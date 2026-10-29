#!/bin/bash

# Create a database migration, and copy it back to the host.

set -e
. "${BASH_SOURCE%/*}/common.sh"

# Runs as root, as migrations/ is mounted from the host and is read-only to the container user
docker exec -u root "$(container app)" sh -c "FLASK_APP=app/__init__.py flask db migrate"

USER=$(whoami)
sudo chown -R "$USER:$USER" migrations/versions
