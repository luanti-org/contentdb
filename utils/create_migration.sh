#!/bin/bash

# Create a database migration, and copy it back to the host.

set -e
. "${BASH_SOURCE%/*}/common.sh"

# migrations/ is mounted from the host and is only writable by the host user. Running as root doesn't help, as the
# container drops all capabilities (including CAP_DAC_OVERRIDE), so run as the host user instead.
docker exec -u "$(id -u):$(id -g)" "$(container app)" sh -c "FLASK_APP=app/__init__.py flask db migrate"
