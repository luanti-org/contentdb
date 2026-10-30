#!/bin/bash

# Run the tests in the throwaway test stack. Your dev database is not touched.
# Pass pytest arguments to run specific tests, for example:
#
#     utils/tests.sh app/tests/integ/test_user.py

set -e

exec "${BASH_SOURCE%/*}/test_stack.sh" test "$@"
