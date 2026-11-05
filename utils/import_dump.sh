#!/bin/bash

# Imports a database dump (backup-YYYY-MM-DD.zip) into the running instance.
# Packages that already exist are skipped, and imported users have the rank "Not Joined".
#
#   ./utils/import_dump.sh path/to/backup.zip [--dry-run]

set -e
. "${BASH_SOURCE%/*}/common.sh"

if [ -z "$1" ]; then
	echo "Usage: ./utils/import_dump.sh path/to/backup.zip [--dry-run]"
	exit 1
fi

DUMP=$1
shift

if [[ ! -f "$DUMP" ]]; then
	echo "No such file: $DUMP"
	exit 1
fi

docker exec -i "$(container app)" python utils/import_dump.py - "$@" < "$DUMP"
