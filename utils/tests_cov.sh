#!/bin/bash

# Run the tests with coverage in the throwaway test stack.

set -e

# Application code only, see utils/test/coverage.cfg. Fails if coverage drops below the minimum set there.
exec "${BASH_SOURCE%/*}/test_stack.sh" test app/tests/ --cov=app --cov-config=utils/test/coverage.cfg "$@"
