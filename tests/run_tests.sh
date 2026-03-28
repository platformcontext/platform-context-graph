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

configure_local_e2e_content_store() {
    if [[ "${DATABASE_TYPE:-}" != "neo4j" ]]; then
        return
    fi
    if [[ -n "${PCG_CONTENT_STORE_DSN:-}" || -n "${PCG_POSTGRES_DSN:-}" ]]; then
        return
    fi

    local postgres_port="${PCG_POSTGRES_PORT:-15432}"
    local postgres_password="${PCG_POSTGRES_PASSWORD:-change-me}"
    export PCG_CONTENT_STORE_DSN="postgresql://pcg:${postgres_password}@localhost:${postgres_port}/platform_context_graph"
    export PCG_POSTGRES_DSN="${PCG_CONTENT_STORE_DSN}"
    export PCG_E2E_USING_LOCAL_COMPOSE_POSTGRES="true"
}

should_run_e2e_in_local_compose() {
    [[ "${PCG_E2E_USING_LOCAL_COMPOSE_POSTGRES:-}" == "true" ]] \
        && command -v docker-compose &> /dev/null \
        && [[ -f "docker-compose.yaml" ]]
}

run_e2e_in_local_compose() {
    local e2e_workers="$1"
    local postgres_password="${PCG_POSTGRES_PASSWORD:-change-me}"
    local neo4j_username="${NEO4J_USERNAME:-neo4j}"
    local neo4j_password="${NEO4J_PASSWORD:-change-me}"
    local seed_graph="${PCG_E2E_SEED_GRAPH:-true}"
    local compose_content_store_dsn="postgresql://pcg:${postgres_password}@postgres:5432/platform_context_graph"

    echo -e "${YELLOW}Running e2e suite inside the compose network for reliable Neo4j/Postgres access...${NC}"
    docker-compose -p pcgprompt -f docker-compose.yaml run --rm --no-deps \
        -e DATABASE_TYPE=neo4j \
        -e DEFAULT_DATABASE=neo4j \
        -e NEO4J_URI=bolt://neo4j:7687 \
        -e NEO4J_USERNAME="${neo4j_username}" \
        -e NEO4J_PASSWORD="${neo4j_password}" \
        -e PCG_CONTENT_STORE_DSN="${compose_content_store_dsn}" \
        -e PCG_POSTGRES_DSN="${compose_content_store_dsn}" \
        -e PCG_E2E_SEED_GRAPH="${seed_graph}" \
        -e PCG_E2E_PYTEST_WORKERS="${e2e_workers}" \
        -e PYTHONPATH=/app-src/src:/app-src \
        --entrypoint sh platform-context-graph \
        -lc 'cd /app-src \
            && python -m pip install -q -e ".[dev]" \
            && if [ "${PCG_E2E_SEED_GRAPH:-true}" = "true" ]; then python scripts/seed_e2e_graph.py; fi \
            && python -m pytest tests/e2e/ -n "${PCG_E2E_PYTEST_WORKERS:-4}" -v'
}

seed_e2e_graph_if_configured() {
    if [[ "${PCG_E2E_SEED_GRAPH:-true}" != "true" ]]; then
        return
    fi
    if [[ "${DATABASE_TYPE:-}" != "neo4j" ]]; then
        return
    fi
    if [[ ! -f "scripts/seed_e2e_graph.py" ]]; then
        return
    fi

    echo -e "${YELLOW}Seeding Docker-backed e2e graph fixtures...${NC}"
    if command -v uv &> /dev/null; then
        PYTHONPATH="${PYTHONPATH}" uv run python scripts/seed_e2e_graph.py
    else
        python3 scripts/seed_e2e_graph.py
    fi
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
        configure_local_e2e_content_store
        if should_run_e2e_in_local_compose; then
            run_e2e_in_local_compose "${E2E_WORKERS}"
        else
            seed_e2e_graph_if_configured
            run_pytest tests/e2e/ -n "${E2E_WORKERS}" -v
        fi
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
