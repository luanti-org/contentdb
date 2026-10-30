#!/bin/bash

# Run the tests with coverage in the throwaway test stack.

set -e

exec "${BASH_SOURCE%/*}/test_stack.sh" test app/tests/ --cov=app "$@"
