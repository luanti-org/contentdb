#!/bin/bash

set -e
. "${BASH_SOURCE%/*}/common.sh"

docker exec "$(container app)" sh -c "FLASK_APP=app/__init__.py COVERAGE_FILE=/tmp/.coverage python -m pytest -p no:cacheprovider app/tests/ --cov=app --disable-warnings"
