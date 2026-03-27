#!/bin/bash
# Quick test runner for PlatformContextGraph Final Test Suite

set -e  # Exit on error

echo "🧪 PlatformContextGraph Final Test Suite"
echo "==================================="
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Export PYTHONPATH to include src
export PYTHONPATH=$PYTHONPATH:$(pwd)/src

PYTEST_CMD=()

resolve_pytest_command() {
    if command -v uv &> /dev/null; then
        PYTEST_CMD=(uv run --extra dev pytest)
        return
    fi

    if command -v pytest &> /dev/null; then
        PYTEST_CMD=(pytest)
        return
    fi

    echo -e "${RED}❌ No supported pytest runner found.${NC}"
    echo "   Install uv (recommended) or pytest in the active environment."
    exit 1
}

run_pytest() {
    "${PYTEST_CMD[@]}" "$@"
}

# Run repository guardrails before executing the requested test slice.
run_repository_checks() {
    echo -e "${YELLOW}Running repository guardrails...${NC}"
    python3 scripts/check_python_file_lengths.py
    python3 scripts/check_python_docstrings.py
}

# Parse arguments
TEST_TYPE="${1:-all}"
resolve_pytest_command

case "$TEST_TYPE" in
    "unit"|"1")
        echo -e "${YELLOW}Running Unit Tests (Core, Parsers)...${NC}"
        run_repository_checks
        run_pytest tests/unit/ -v
        ;;
    
    "integration"|"int"|"2")
        echo -e "${YELLOW}Running Integration Tests (CLI, MCP, API, deployment assets)...${NC}"
        run_repository_checks
        run_pytest tests/integration/ -v
        ;;
    
    "e2e"|"3")
        E2E_WORKERS="${PCG_E2E_PYTEST_WORKERS:-4}"
        echo -e "${YELLOW}Running E2E User Journeys (Slow, workers=${E2E_WORKERS})...${NC}"
        run_repository_checks
        run_pytest tests/e2e/ -n "${E2E_WORKERS}" -v
        ;;
    
    "fast")
        echo -e "${YELLOW}Running Fast Tests (Unit + Integration + deployment assets)...${NC}"
        run_repository_checks
        run_pytest tests/unit/ tests/integration/ -v
        ;;
    
    "all")
        echo -e "${YELLOW}Running All Tests...${NC}"
        run_repository_checks
        run_pytest tests/ -v
        ;;
    
    "help"|"-h"|"--help")
        echo "Usage: ./tests/run_tests.sh [option]"
        echo ""
        echo "Options:"
        echo "  unit         - Run unit tests (fast)"
        echo "  integration  - Run integration tests (mid)"
        echo "  e2e          - Run E2E tests (slow, requires environment)"
        echo "  fast         - Run unit + integration"
        echo "  all          - Run everything [default]"
        exit 0
        ;;
    
    *)
        echo -e "${RED}❌ Unknown option: $TEST_TYPE${NC}"
        echo "Run './tests/run_tests.sh help' for usage information"
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}✅ Tests completed!${NC}"
