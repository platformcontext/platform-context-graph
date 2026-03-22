#!/usr/bin/env bash
# Full integration test: Neo4j via docker-compose + PCG indexing + MCP tools
set -euo pipefail

cd "$(dirname "$0")/.."

echo "=== 1. Starting Neo4j ==="
docker-compose up -d
echo "Waiting for Neo4j to be healthy..."
for i in $(seq 1 30); do
    if docker-compose exec neo4j cypher-shell -u neo4j -p testpassword "RETURN 1" &>/dev/null; then
        echo "Neo4j is ready."
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "ERROR: Neo4j did not start in time."
        docker-compose logs neo4j
        exit 1
    fi
    sleep 2
done

export NEO4J_URI=bolt://localhost:7687
export NEO4J_USERNAME=neo4j
export NEO4J_PASSWORD=testpassword
export DATABASE_TYPE=neo4j

echo ""
echo "=== 2. Running integration tests ==="
uv run python -m pytest tests/integration/test_full_flow.py -v

echo ""
echo "=== 3. CLI smoke test: pcg index ==="
uv run pcg index tests/fixtures/sample_projects/sample_project_yaml_infra --force

echo ""
echo "=== 4. CLI smoke test: pcg list ==="
uv run pcg list

echo ""
echo "=== 5. Querying graph via Cypher ==="
docker-compose exec neo4j cypher-shell -u neo4j -p testpassword \
    "MATCH ()-[r]->() WHERE type(r) IN ['SELECTS','CONFIGURES','SATISFIED_BY','IMPLEMENTED_BY','ROUTES_TO','RUNS_IMAGE','PATCHES'] RETURN type(r) AS rel, count(*) AS cnt ORDER BY rel"

echo ""
echo "=== 6. Full chain query: Service → Deployment → Image ==="
docker-compose exec neo4j cypher-shell -u neo4j -p testpassword \
    "MATCH (svc:K8sResource {kind:'Service'})-[:SELECTS]->(d:K8sResource {kind:'Deployment'}) RETURN svc.name AS service, d.name AS deployment, d.container_images AS images"

echo ""
echo "=== All tests passed! ==="
echo "Neo4j Browser: http://localhost:7474"
echo "Tear down with: docker-compose down -v"
