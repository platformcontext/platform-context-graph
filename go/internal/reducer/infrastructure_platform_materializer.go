package reducer

import (
	"context"
	"fmt"
)

// InfrastructurePlatformRow holds one inferred PROVISIONS_PLATFORM edge payload.
type InfrastructurePlatformRow struct {
	RepoID              string
	PlatformID          string
	PlatformName        string
	PlatformKind        string
	PlatformProvider    string
	PlatformEnvironment string
	PlatformRegion      string
	PlatformLocator     string
}

// InfrastructurePlatformResult holds counts from one materialization pass.
type InfrastructurePlatformResult struct {
	PlatformEdgesWritten int
}

// InfrastructurePlatformMaterializer writes PROVISIONS_PLATFORM edges to Neo4j.
// It is the Go equivalent of Python's materialize_infrastructure_platforms
// orchestrator for the graph-write portion.
type InfrastructurePlatformMaterializer struct {
	executor CypherExecutor
}

// NewInfrastructurePlatformMaterializer returns an InfrastructurePlatformMaterializer
// backed by the given CypherExecutor.
func NewInfrastructurePlatformMaterializer(executor CypherExecutor) *InfrastructurePlatformMaterializer {
	return &InfrastructurePlatformMaterializer{executor: executor}
}

// Materialize writes PROVISIONS_PLATFORM edges for each infrastructure
// platform row. Each row creates a Platform node (via MERGE) and a
// PROVISIONS_PLATFORM edge from the Repository.
func (m *InfrastructurePlatformMaterializer) Materialize(
	ctx context.Context,
	rows []InfrastructurePlatformRow,
) (InfrastructurePlatformResult, error) {
	if len(rows) == 0 {
		return InfrastructurePlatformResult{}, nil
	}
	if m.executor == nil {
		return InfrastructurePlatformResult{}, fmt.Errorf("infrastructure platform materializer executor is required")
	}

	var result InfrastructurePlatformResult

	for _, row := range rows {
		if err := m.executor.ExecuteCypher(ctx, infraPlatformUpsertCypher, map[string]any{
			"repo_id":              row.RepoID,
			"platform_id":          row.PlatformID,
			"platform_name":        row.PlatformName,
			"platform_kind":        row.PlatformKind,
			"platform_provider":    row.PlatformProvider,
			"platform_environment": row.PlatformEnvironment,
			"platform_region":      row.PlatformRegion,
			"platform_locator":     row.PlatformLocator,
			"evidence_source":      EvidenceSourceWorkloads,
		}); err != nil {
			return result, fmt.Errorf("write infrastructure platform %q for %q: %w",
				row.PlatformID, row.RepoID, err)
		}
		result.PlatformEdgesWritten++
	}

	return result, nil
}

// RetractStale removes PROVISIONS_PLATFORM edges for the given repository IDs
// that are no longer backed by current Terraform signals.
func (m *InfrastructurePlatformMaterializer) RetractStale(
	ctx context.Context,
	repoIDs []string,
) error {
	if len(repoIDs) == 0 {
		return nil
	}
	if m.executor == nil {
		return fmt.Errorf("infrastructure platform materializer executor is required")
	}

	return m.executor.ExecuteCypher(ctx, infraPlatformRetractCypher, map[string]any{
		"repo_ids":        repoIDs,
		"evidence_source": EvidenceSourceWorkloads,
	})
}

// Canonical Cypher templates — duplicated from storage/neo4j/canonical.go to
// avoid a circular import. These strings are identical.
const infraPlatformUpsertCypher = `MATCH (repo:Repository {id: $repo_id})
MERGE (p:Platform {id: $platform_id})
ON CREATE SET p.evidence_source = $evidence_source
SET p.type = 'platform',
    p.name = $platform_name,
    p.kind = $platform_kind,
    p.provider = $platform_provider,
    p.environment = $platform_environment,
    p.region = $platform_region,
    p.locator = $platform_locator
MERGE (repo)-[rel:PROVISIONS_PLATFORM]->(p)
SET rel.confidence = 0.98,
    rel.reason = 'Terraform cluster and module data declare platform provisioning',
    rel.evidence_source = $evidence_source`

const infraPlatformRetractCypher = `MATCH (repo:Repository)-[rel:PROVISIONS_PLATFORM]->(:Platform)
WHERE repo.id IN $repo_ids
  AND rel.evidence_source = $evidence_source
DELETE rel`
