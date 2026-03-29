#!/usr/bin/env bash
# NornicDB compatibility test for PlatformContextGraph.
#
# Starts the full PCG stack with NornicDB replacing Neo4j, verifies Bolt
# connectivity, runs the integration test suite, and reports results.
#
# Usage:
#   ./scripts/test-nornicdb-compat.sh              # Full run
#   ./scripts/test-nornicdb-compat.sh --no-build   # Skip docker build (reuse existing images)
#   ./scripts/test-nornicdb-compat.sh --keep        # Don't tear down on exit
#
# Prerequisites:
#   - Docker and docker-compose (hyphenated) installed
#   - uv and Python available on PATH
#   - The neo4j Python driver installed (uv run handles this)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

BUILD_FLAG="--build"
KEEP=false

for arg in "$@"; do
    case "$arg" in
        --no-build) BUILD_FLAG="" ;;
        --keep)     KEEP=true ;;
        --help|-h)
            echo "Usage: $0 [--no-build] [--keep]"
            echo "  --no-build  Skip docker image rebuild"
            echo "  --keep      Don't tear down the stack on exit"
            exit 0
            ;;
    esac
done

COMPOSE="docker-compose -f $REPO_ROOT/docker-compose.yaml -f $REPO_ROOT/docker-compose.nornicdb.yml"

log() { echo "[$(date +%H:%M:%S)] $*"; }

cleanup() {
    if [ "$KEEP" = false ]; then
        log "Tearing down NornicDB stack..."
        cd "$REPO_ROOT"
        $COMPOSE down -v 2>/dev/null || true
    else
        log "Stack left running (--keep). Tear down with:"
        log "  $COMPOSE down -v"
    fi
}

# ---------------------------------------------------------------------------
# 1. Start the stack
# ---------------------------------------------------------------------------
log "=== Step 1: Starting PCG stack with NornicDB ==="
cd "$REPO_ROOT"

# Clean up any previous run
$COMPOSE down -v 2>/dev/null || true

# Register cleanup trap
trap cleanup EXIT

$COMPOSE up $BUILD_FLAG -d 2>&1 | tail -10

# ---------------------------------------------------------------------------
# 2. Wait for NornicDB to become healthy
# ---------------------------------------------------------------------------
log "=== Step 2: Waiting for NornicDB to be healthy ==="

MAX_WAIT=120
WAITED=0
while [ $WAITED -lt $MAX_WAIT ]; do
    HEALTH=$($COMPOSE ps neo4j --format '{{.Health}}' 2>/dev/null || echo "unknown")
    if echo "$HEALTH" | grep -qi "healthy"; then
        log "NornicDB is healthy after ${WAITED}s"
        break
    fi
    if [ $WAITED -gt 0 ] && [ $((WAITED % 10)) -eq 0 ]; then
        log "  Still waiting... ${WAITED}s (status: $HEALTH)"
    fi
    sleep 2
    WAITED=$((WAITED + 2))
done

if [ $WAITED -ge $MAX_WAIT ]; then
    log "ERROR: NornicDB did not become healthy within ${MAX_WAIT}s"
    log "Container logs:"
    $COMPOSE logs neo4j 2>&1 | tail -30
    exit 1
fi

# ---------------------------------------------------------------------------
# 3. Basic Bolt connectivity test
# ---------------------------------------------------------------------------
log "=== Step 3: Bolt connectivity test ==="

export NEO4J_URI=bolt://localhost:${NEO4J_BOLT_PORT:-7687}
export NEO4J_USERNAME=neo4j
export NEO4J_PASSWORD=${PCG_NEO4J_PASSWORD:-change-me}
export DATABASE_TYPE=neo4j
export PYTHONPATH="$REPO_ROOT/src"

BOLT_RESULT=$(uv run python -c "
from neo4j import GraphDatabase
import os

uri = os.environ['NEO4J_URI']
user = os.environ['NEO4J_USERNAME']
password = os.environ['NEO4J_PASSWORD']

print(f'Connecting to {uri} as {user}...')
driver = GraphDatabase.driver(uri, auth=(user, password))
try:
    with driver.session() as session:
        result = session.run('RETURN 1 AS n')
        record = result.single()
        assert record is not None, 'No result from RETURN 1'
        assert record['n'] == 1, f'Unexpected value: {record[\"n\"]}'
        print('Bolt connectivity: OK')

        # Test basic write + read
        session.run('CREATE (t:_NornicDBTest {ts: timestamp()}) RETURN t')
        count = session.run('MATCH (t:_NornicDBTest) RETURN count(t) AS cnt').single()['cnt']
        print(f'Write/read test: OK (count={count})')

        # Clean up
        session.run('MATCH (t:_NornicDBTest) DELETE t')
        print('Cleanup: OK')
finally:
    driver.close()

print('All Bolt connectivity checks passed.')
" 2>&1) || {
    log "FAIL: Bolt connectivity test failed"
    echo "$BOLT_RESULT"
    exit 1
}

echo "$BOLT_RESULT"

# ---------------------------------------------------------------------------
# 4. Wait for bootstrap indexer to complete
# ---------------------------------------------------------------------------
log "=== Step 4: Waiting for bootstrap indexer ==="

BOOTSTRAP_CONTAINER=$($COMPOSE ps -q bootstrap-index 2>/dev/null || echo "")
if [ -z "$BOOTSTRAP_CONTAINER" ]; then
    log "WARNING: bootstrap-index container not found, skipping wait"
else
    MAX_WAIT=300
    WAITED=0
    while [ $WAITED -lt $MAX_WAIT ]; do
        STATUS=$(docker inspect --format='{{.State.Status}}' "$BOOTSTRAP_CONTAINER" 2>/dev/null || echo "unknown")
        if [ "$STATUS" = "exited" ]; then
            EXIT_CODE=$(docker inspect --format='{{.State.ExitCode}}' "$BOOTSTRAP_CONTAINER" 2>/dev/null || echo "?")
            log "Bootstrap indexer exited with code $EXIT_CODE after ${WAITED}s"
            if [ "$EXIT_CODE" != "0" ]; then
                log "ERROR: Bootstrap indexer failed"
                $COMPOSE logs bootstrap-index 2>&1 | tail -40
                exit 1
            fi
            break
        fi
        sleep 5
        WAITED=$((WAITED + 5))
        if [ $((WAITED % 30)) -eq 0 ]; then
            log "  Bootstrap still running... ${WAITED}s"
        fi
    done

    if [ $WAITED -ge $MAX_WAIT ]; then
        log "ERROR: Bootstrap indexer timed out after ${MAX_WAIT}s"
        $COMPOSE logs bootstrap-index 2>&1 | tail -40
        exit 1
    fi
fi

# ---------------------------------------------------------------------------
# 5. Run integration test suite
# ---------------------------------------------------------------------------
log "=== Step 5: Running integration tests ==="

export PCG_CONTENT_STORE_DSN="postgresql://pcg:${PCG_POSTGRES_PASSWORD:-change-me}@localhost:${PCG_POSTGRES_PORT:-15432}/platform_context_graph"
export PCG_POSTGRES_DSN="$PCG_CONTENT_STORE_DSN"

INTEGRATION_RESULT=0
uv run python -m pytest "$REPO_ROOT/tests/integration/" -v --tb=short 2>&1 || INTEGRATION_RESULT=$?

# ---------------------------------------------------------------------------
# 6. Summary
# ---------------------------------------------------------------------------
log ""
log "========================================="
log "  NornicDB Compatibility Test Results"
log "========================================="
log ""
log "  Bolt connectivity:     PASS"

if [ $INTEGRATION_RESULT -eq 0 ]; then
    log "  Integration tests:     PASS"
else
    log "  Integration tests:     FAIL (exit code $INTEGRATION_RESULT)"
fi

log ""
log "  NornicDB image:        ${NORNICDB_IMAGE:-timothyswt/nornicdb-arm64-metal:latest}"
log "  Bolt URI:              $NEO4J_URI"
log ""

if [ $INTEGRATION_RESULT -ne 0 ]; then
    log "Some tests failed. Review output above for details."
    log "NornicDB logs:"
    $COMPOSE logs neo4j 2>&1 | tail -20
    exit 1
fi

log "All tests passed -- NornicDB is compatible with this PCG build."
