#!/bin/bash
# Run test suite
set -euo pipefail

# Colors
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

# Default values
TEST_TYPE="all"
ENVIRONMENT="dev"
VERBOSE=""
COVERAGE=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --type)
            TEST_TYPE="$2"
            shift 2
            ;;
        --environment)
            ENVIRONMENT="$2"
            shift 2
            ;;
        -v|--verbose)
            VERBOSE="-v"
            shift
            ;;
        --coverage)
            COVERAGE="--cov=src --cov-report=term-missing"
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --type TYPE        Test type: unit, contract, integration, e2e, all (default: all)"
            echo "  --environment ENV  Environment for integration tests (default: dev)"
            echo "  -v, --verbose      Verbose output"
            echo "  --coverage         Generate coverage report"
            echo "  -h, --help         Show this help"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo -e "${GREEN}Running tests...${NC}"
echo "  Type: $TEST_TYPE"
echo "  Environment: $ENVIRONMENT"
echo ""

# Set environment variables
export ENVIRONMENT="$ENVIRONMENT"
export PYTHONPATH="${PYTHONPATH:-}:$(pwd)"

run_tests() {
    local test_path=$1
    local test_name=$2

    echo -e "${YELLOW}Running $test_name tests...${NC}"
    if pytest "$test_path" $VERBOSE $COVERAGE; then
        echo -e "${GREEN}✓ $test_name tests passed${NC}"
        return 0
    else
        echo -e "${RED}✗ $test_name tests failed${NC}"
        return 1
    fi
}

FAILED=0

case $TEST_TYPE in
    unit)
        run_tests "tests/unit/" "unit" || FAILED=1
        ;;
    contract)
        run_tests "tests/contract/" "contract" || FAILED=1
        ;;
    integration)
        run_tests "tests/integration/" "integration" || FAILED=1
        ;;
    e2e)
        run_tests "tests/e2e/" "e2e" || FAILED=1
        ;;
    all)
        run_tests "tests/unit/" "unit" || FAILED=1
        run_tests "tests/contract/" "contract" || FAILED=1
        ;;
    *)
        echo -e "${RED}Unknown test type: $TEST_TYPE${NC}"
        exit 1
        ;;
esac

echo ""
if [[ $FAILED -eq 0 ]]; then
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed!${NC}"
    exit 1
fi
