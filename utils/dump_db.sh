#!/bin/bash

# Creates backup

set -e
. "${BASH_SOURCE%/*}/common.sh"

if [ -z "$1" ]; then
        echo "Usage: ./utils/dump_bk.sh path/to/backup.sql"
        exit 1
fi

BKFILE=$1

echo "Exporting backup to $BKFILE"
docker exec -i "$(container db)" pg_dump contentdb -U contentdb > $BKFILE
