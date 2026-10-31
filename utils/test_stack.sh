#!/bin/bash

#
# Manage the throwaway test stack (docker-compose.test.yml).
#
#   utils/test_stack.sh up            Start the stack and run migrations
#   utils/test_stack.sh test [args]   Run pytest in the stack, starting it if needed
#   utils/test_stack.sh down          Stop the stack and discard all of its data
#
# Builds the working tree as contentdb:test, unless CDB_TEST_IMAGE is set.
#

set -e

cd "${BASH_SOURCE%/*}/.."

compose() {
	docker compose -f docker-compose.test.yml "$@"
}

up() {
	if [ -n "$CDB_TEST_IMAGE" ]; then
		compose up -d --no-build --wait
	else
		compose up -d --build --wait
	fi
	compose exec -T app sh -c "FLASK_APP=app/__init__.py flask db upgrade"
}

is_up() {
	[ -n "$(compose ps -q --status running app)" ]
}

case "$1" in
	up)
		up
		;;
	test)
		shift
		is_up || up
		if [ $# -eq 0 ]; then
			set -- app/tests
		fi
		compose exec -T app sh -c 'FLASK_APP=app/__init__.py COVERAGE_FILE=/tmp/.coverage python -m pytest -p no:cacheprovider --disable-warnings "$@"' pytest "$@"
		;;
	down)
		compose down -v --remove-orphans
		;;
	*)
		echo "Usage: $0 up|test [pytest args]|down" >&2
		exit 1
		;;
esac
