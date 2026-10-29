#!/bin/bash

set -e
. "${BASH_SOURCE%/*}/common.sh"

docker exec "$(container app)" sh -c "FLASK_APP=app/__init__.py python -m pytest app/tests/ --cov=app --disable-warnings"
