#!/usr/bin/env bash
set -euo pipefail

# PCG Database Restore Script
# Restores Neo4j and PostgreSQL backups from ops-qa into the local docker-compose stack.
#
# Prerequisites:
#   - docker-compose stack must be running (docker-compose up -d)
#   - Backup files from ~/pcg-backup.sh
#
# Usage:
#   restore-ops-qa-backup.sh                          # Use latest backups
#   restore-ops-qa-backup.sh -p postgres.dump -n neo4j.tar.gz  # Specific files
#   restore-ops-qa-backup.sh --latest                 # Auto-detect latest backups

usage() {
  echo "Usage: $0 [-p postgres_dump] [-n neo4j_tar] [--latest]" >&2
  echo "" >&2
  echo "Options:" >&2
  echo "  -p FILE    Path to PostgreSQL dump file (.dump)" >&2
  echo "  -n FILE    Path to Neo4j tar.gz backup" >&2
  echo "  --latest   Auto-detect latest backup files from ~/pcg-backups/" >&2
  echo "" >&2
  echo "If no options given, --latest is assumed." >&2
  exit 1
}

BACKUP_DIR="$HOME/pcg-backups"
PG_FILE=""
NEO4J_FILE=""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${GREEN}[+]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
err()  { echo -e "${RED}[x]${NC} $*" >&2; exit 1; }
info() { echo -e "${CYAN}[i]${NC} $*"; }

# Parse arguments
USE_LATEST=false
while [[ $# -gt 0 ]]; do
  case $1 in
    -p) PG_FILE="$2"; shift 2 ;;
    -n) NEO4J_FILE="$2"; shift 2 ;;
    --latest) USE_LATEST=true; shift ;;
    -h|--help) usage ;;
    *) err "Unknown option: $1" ;;
  esac
done

# Default to latest if nothing specified
if [[ -z "$PG_FILE" && -z "$NEO4J_FILE" ]]; then
  USE_LATEST=true
fi

# Auto-detect latest backups
if $USE_LATEST; then
  [[ -d "$BACKUP_DIR" ]] || err "No backup directory found at $BACKUP_DIR. Run ~/pcg-backup.sh first."

  if [[ -z "$PG_FILE" ]]; then
    PG_FILE=$(ls -1t "$BACKUP_DIR"/postgres-*.dump 2>/dev/null | head -1)
    [[ -n "$PG_FILE" ]] || err "No PostgreSQL backup found in $BACKUP_DIR"
  fi
  if [[ -z "$NEO4J_FILE" ]]; then
    NEO4J_FILE=$(ls -1t "$BACKUP_DIR"/neo4j-*.tar.gz 2>/dev/null | head -1)
    [[ -n "$NEO4J_FILE" ]] || err "No Neo4j backup found in $BACKUP_DIR"
  fi
fi

# Validate files exist
[[ -f "$PG_FILE" ]] || err "PostgreSQL dump not found: $PG_FILE"
[[ -f "$NEO4J_FILE" ]] || err "Neo4j backup not found: $NEO4J_FILE"

PG_SIZE=$(du -h "$PG_FILE" | cut -f1)
NEO4J_SIZE=$(du -h "$NEO4J_FILE" | cut -f1)

info "PostgreSQL dump: $PG_FILE ($PG_SIZE)"
info "Neo4j backup:    $NEO4J_FILE ($NEO4J_SIZE)"
echo ""

# Detect docker-compose project
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="$PROJECT_DIR/docker-compose.template.yml"

[[ -f "$COMPOSE_FILE" ]] || err "docker-compose.template.yml not found at $PROJECT_DIR"

# Check that containers are running
PG_CONTAINER=$(docker-compose -f "$COMPOSE_FILE" ps -q postgres 2>/dev/null) || true
NEO4J_CONTAINER=$(docker-compose -f "$COMPOSE_FILE" ps -q neo4j 2>/dev/null) || true

if [[ -z "$PG_CONTAINER" || -z "$NEO4J_CONTAINER" ]]; then
  warn "Docker-compose services not all running. Starting stack..."
  cd "$PROJECT_DIR"
  docker-compose -f docker-compose.template.yml up -d neo4j postgres
  log "Waiting for services to become healthy..."
  sleep 10
  PG_CONTAINER=$(docker-compose -f "$COMPOSE_FILE" ps -q postgres)
  NEO4J_CONTAINER=$(docker-compose -f "$COMPOSE_FILE" ps -q neo4j)
fi

[[ -n "$PG_CONTAINER" ]] || err "PostgreSQL container not running"
[[ -n "$NEO4J_CONTAINER" ]] || err "Neo4j container not running"

echo ""
log "Starting restore..."
echo ""

# --- Restore PostgreSQL ---
log "Restoring PostgreSQL..."

# Drop and recreate the database
info "Dropping existing database..."
docker exec -i "$PG_CONTAINER" psql -U pcg -d postgres -c "
  SELECT pg_terminate_backend(pid) FROM pg_stat_activity
  WHERE datname = 'platform_context_graph' AND pid <> pg_backend_pid();
" > /dev/null 2>&1 || true

docker exec -i "$PG_CONTAINER" psql -U pcg -d postgres -c \
  "DROP DATABASE IF EXISTS platform_context_graph;" > /dev/null 2>&1

docker exec -i "$PG_CONTAINER" psql -U pcg -d postgres -c \
  "CREATE DATABASE platform_context_graph OWNER pcg;" > /dev/null 2>&1

info "Loading PostgreSQL dump..."
# The ops-qa dump uses user 'platformcontextgraph', remap to local 'pcg'
docker exec -i "$PG_CONTAINER" pg_restore \
  --no-owner --role=pcg \
  -U pcg -d platform_context_graph \
  < "$PG_FILE" 2>&1 | grep -v "WARNING" || true

log "PostgreSQL restore complete."
echo ""

# --- Restore Neo4j ---
log "Restoring Neo4j..."

info "Stopping Neo4j container for data replacement..."
docker stop "$NEO4J_CONTAINER" > /dev/null 2>&1 || true
sleep 2

info "Clearing existing Neo4j data..."
# Use a temporary container to access the volume while neo4j is stopped
docker run --rm -v platform-context-graph_neo4j_data:/data alpine \
  sh -c "rm -rf /data/databases /data/transactions"

info "Extracting Neo4j backup into volume..."
docker run --rm -v platform-context-graph_neo4j_data:/data -v "$NEO4J_FILE":/backup.tar.gz alpine \
  sh -c "tar xzf /backup.tar.gz -C /data/ && chown -R 7474:7474 /data/databases /data/transactions"

info "Starting Neo4j container..."
docker start "$NEO4J_CONTAINER" > /dev/null 2>&1

log "Waiting for Neo4j to become available..."
for i in $(seq 1 30); do
  if docker exec "$NEO4J_CONTAINER" cypher-shell -u neo4j -p "${PCG_NEO4J_PASSWORD:-change-me}" "RETURN 1" > /dev/null 2>&1; then
    break
  fi
  sleep 2
done

# Verify Neo4j
REPO_COUNT=$(docker exec "$NEO4J_CONTAINER" cypher-shell -u neo4j -p "${PCG_NEO4J_PASSWORD:-change-me}" \
  "MATCH (r:Repository) RETURN count(r) AS count" 2>/dev/null | tail -1 | tr -d ' "' || echo "?")

log "Neo4j restore complete. Repositories in graph: $REPO_COUNT"
echo ""

# --- Verification ---
log "Running verification..."
echo ""

# Postgres verification
PG_TABLES=$(docker exec -i "$PG_CONTAINER" psql -U pcg -d platform_context_graph -t -c \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';" 2>/dev/null | tr -d ' ')
info "PostgreSQL tables: $PG_TABLES"

# Neo4j node counts
NODE_COUNTS=$(docker exec "$NEO4J_CONTAINER" cypher-shell -u neo4j -p "${PCG_NEO4J_PASSWORD:-change-me}" \
  "MATCH (n) RETURN labels(n)[0] AS label, count(n) AS count ORDER BY count DESC LIMIT 10" 2>/dev/null || echo "Could not query")
info "Neo4j top node labels:"
echo "$NODE_COUNTS"
echo ""

log "Restore complete!"
echo ""
echo "Next steps:"
echo "  1. Run standalone finalization:"
echo "     PYTHONPATH=src NEO4J_URI=bolt://localhost:7687 NEO4J_USERNAME=neo4j NEO4J_PASSWORD=change-me \\"
echo "       DATABASE_TYPE=neo4j \\"
echo "       PCG_POSTGRES_DSN=postgresql://pcg:change-me@localhost:15432/platform_context_graph \\"
echo "       uv run pcg finalize"
echo ""
echo "  2. Verify deployment chains:"
echo "     PYTHONPATH=src uv run pcg cypher \"MATCH (r:Repository)-[rel]->(t) WHERE r.name='api-node-boats' AND type(rel) IN ['RUNS_ON','PROVISIONS_DEPENDENCY_FOR'] RETURN type(rel), t.name LIMIT 10\""
