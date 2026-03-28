#!/usr/bin/env bash
# Local integration test runner for PCG.
# Copies real repos into a flat workspace, runs docker-compose ingestion,
# waits for completion, and validates the results.
#
# Usage:
#   ./scripts/local-integration-test.sh                    # Tier 1 (10 repos)
#   ./scripts/local-integration-test.sh --tier2            # Tier 2 (10 + youboat)
#   ./scripts/local-integration-test.sh --workspace-only   # Just prepare workspace, don't start compose
#   ./scripts/local-integration-test.sh --validate-only    # Just run validation against running stack
#
# Environment overrides:
#   PCG_WORKSPACE=/path/to/workspace    # Override workspace location
#   PCG_GRAPH_WRITE_TX_FILE_BATCH_SIZE=25  # Pass through to docker-compose
#   PCG_REPO_FILE_PARSE_MULTIPROCESS=true  # Pass through to docker-compose

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Defaults
TIER="tier1"
WORKSPACE_ONLY=false
VALIDATE_ONLY=false
WORKSPACE="${PCG_WORKSPACE:-/Users/allen/pcg-test-workspace}"

# Parse args
for arg in "$@"; do
    case "$arg" in
        --tier2) TIER="tier2" ;;
        --workspace-only) WORKSPACE_ONLY=true ;;
        --validate-only) VALIDATE_ONLY=true ;;
        --help|-h)
            echo "Usage: $0 [--tier2] [--workspace-only] [--validate-only]"
            exit 0
            ;;
    esac
done

# Tier 1 repos (10 repos, ~2,060 parseable files)
TIER1_REPOS=(
    "$HOME/repos/mobius/iac-eks-argocd"
    "$HOME/repos/mobius/helm-charts"
    "$HOME/repos/mobius/iac-eks-addons"
    "$HOME/repos/mobius/iac-eks-crossplane"
    "$HOME/repos/mobius/iac-eks-observability"
    "$HOME/repos/mobius/crossplane-xrd-irsa-role"
    "$HOME/repos/terraform-modules/terraform-module-core-irsa"
    "$HOME/repos/services/api-node-boats"
    "$HOME/repos/services/api-node-bw-home"
    "$HOME/repos/terraform-stacks/terraform-stack-boattrader"
)

# Tier 2 adds stress test repos
TIER2_REPOS=(
    "$HOME/repos/services/websites-php-youboat"
    "$HOME/repos/terraform-stacks/terraform-stack-youboat"
)

log() { echo "[$(date +%H:%M:%S)] $*"; }

prepare_workspace() {
    log "Preparing $TIER workspace at $WORKSPACE"
    rm -rf "$WORKSPACE"
    mkdir -p "$WORKSPACE"

    local repos=("${TIER1_REPOS[@]}")
    if [ "$TIER" = "tier2" ]; then
        repos+=("${TIER2_REPOS[@]}")
    fi

    for repo in "${repos[@]}"; do
        local name
        name=$(basename "$repo")
        if [ ! -d "$repo" ]; then
            log "WARNING: $repo not found, skipping"
            continue
        fi
        log "  Copying $name..."
        rsync -a --exclude='.git/objects' --exclude='node_modules' --exclude='vendor' \
            "$repo/" "$WORKSPACE/$name/"
        # Ensure .git dir exists for repo identity detection
        mkdir -p "$WORKSPACE/$name/.git"
    done

    local count
    count=$(ls -1 "$WORKSPACE" | wc -l | tr -d ' ')
    log "Workspace ready: $count repos in $WORKSPACE"
}

start_stack() {
    log "Stopping existing stack..."
    cd "$REPO_ROOT"
    docker-compose down -v 2>/dev/null || true
    sleep 2

    log "Starting docker-compose with $TIER workspace..."
    PCG_FILESYSTEM_HOST_ROOT="$WORKSPACE" docker-compose up --build --force-recreate -d 2>&1 | tail -5

    log "Waiting for bootstrap indexer to complete..."
    local waited=0
    local max_wait=1800  # 30 min for tier2
    if [ "$TIER" = "tier1" ]; then
        max_wait=300  # 5 min for tier1
    fi

    while [ $waited -lt $max_wait ]; do
        local status
        status=$(docker inspect --format='{{.State.Status}}' platform-context-graph-bootstrap-index-1 2>/dev/null || echo "unknown")
        if [ "$status" = "exited" ]; then
            local exit_code
            exit_code=$(docker inspect --format='{{.State.ExitCode}}' platform-context-graph-bootstrap-index-1 2>/dev/null || echo "?")
            log "Bootstrap exited with code $exit_code after ${waited}s"
            break
        fi
        sleep 5
        waited=$((waited + 5))
        if [ $((waited % 30)) -eq 0 ]; then
            log "  Still running... ${waited}s"
        fi
    done

    if [ $waited -ge $max_wait ]; then
        log "ERROR: Bootstrap timed out after ${max_wait}s"
        docker-compose logs bootstrap-index 2>&1 | tail -30
        exit 1
    fi

    # Show finalization timing
    log "=== Finalization Timing ==="
    docker-compose logs bootstrap-index 2>&1 | rg "Finalization timings" | tail -1 | python3 -c "
import sys, json
for line in sys.stdin:
    try:
        j = json.loads(line.strip().split('| ', 1)[-1])
        ek = j.get('extra_keys', {})
        for k, v in sorted(ek.items()):
            if k.endswith('_seconds'):
                print(f'  {k}: {v}s')
    except:
        print(f'  {line.strip()[:200]}')
" 2>/dev/null || true

    # Show memory
    log "=== Peak Memory ==="
    docker-compose logs bootstrap-index 2>&1 | rg "After finalization" | tail -1 | python3 -c "
import sys, json
for line in sys.stdin:
    try:
        j = json.loads(line.strip().split('| ', 1)[-1])
        print(f'  {j.get(\"message\", \"?\")}')
    except:
        pass
" 2>/dev/null || true
}

validate() {
    log "=== Validation ==="
    cd "$REPO_ROOT"

    PYTHONPATH=src uv run python -c "
import os
os.environ.setdefault('DATABASE_TYPE', 'neo4j')
os.environ.setdefault('NEO4J_URI', 'bolt://localhost:7687')
os.environ.setdefault('NEO4J_USERNAME', 'neo4j')
os.environ.setdefault('NEO4J_PASSWORD', 'change-me')

from platform_context_graph.core import get_database_manager
db = get_database_manager()
driver = db.get_driver()

with driver.session() as s:
    # Repos
    repos = s.run('MATCH (r:Repository) RETURN r.name as name ORDER BY r.name').data()
    print(f'Repos: {len(repos)}')
    for r in repos:
        print(f'  {r[\"name\"]}')

    # Variables (should be 0)
    cnt = s.run('MATCH (v:Variable) RETURN count(v) as cnt').single()
    var_count = cnt['cnt']
    print(f'Variable nodes: {var_count}')
    if var_count > 0:
        print('  FAIL: INDEX_VARIABLES=false but Variable nodes exist!')

    # Functions
    fn = s.run('MATCH (f:Function) RETURN count(f) as cnt').single()
    print(f'Function nodes: {fn[\"cnt\"]}')

    # Cross-repo relationships
    rels = s.run('''
        MATCH (a:Repository)-[r]->(b:Repository)
        RETURN a.name as source, type(r) as rel, b.name as target
        ORDER BY source, rel, target
    ''').data()
    print(f'Cross-repo relationships: {len(rels)}')
    for r in rels:
        print(f'  {r[\"source\"]} --[{r[\"rel\"]}]--> {r[\"target\"]}')

    # ArgoCD ApplicationSets
    argo = s.run('MATCH (a:ArgoCDApplicationSet) RETURN count(a) as cnt').single()
    print(f'ArgoCD ApplicationSets: {argo[\"cnt\"]}')

    # Crossplane
    xrd = s.run('MATCH (x:CrossplaneXRD) RETURN count(x) as cnt').single()
    print(f'Crossplane XRDs: {xrd[\"cnt\"]}')

    # Terraform
    tf = s.run('MATCH (t:TerraformResource) RETURN count(t) as cnt').single()
    print(f'Terraform resources: {tf[\"cnt\"]}')
"

    # API health
    log "=== API Check ==="
    local api_key
    api_key=$(docker exec platform-context-graph-platform-context-graph-1 cat /data/.platform-context-graph/.env 2>/dev/null | rg "PCG_API_KEY=" | cut -d= -f2)
    if [ -n "$api_key" ]; then
        local repo_count
        repo_count=$(curl -s -H "Authorization: Bearer $api_key" http://localhost:8080/api/v0/repositories 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d) if isinstance(d,list) else len(d.get('repositories',[])))" 2>/dev/null || echo "?")
        log "  API repos: $repo_count"
    else
        log "  WARNING: Could not read API key"
    fi

    log "=== Validation complete ==="
}

# Main
if [ "$VALIDATE_ONLY" = true ]; then
    validate
    exit 0
fi

if [ "$WORKSPACE_ONLY" = true ]; then
    prepare_workspace
    exit 0
fi

prepare_workspace
start_stack
validate
