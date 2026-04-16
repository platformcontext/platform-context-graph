package neo4j

// CanonicalRepoRelationshipParams holds the parameters for a typed repository
// relationship upsert.
type CanonicalRepoRelationshipParams struct {
	RepoID           string
	TargetRepoID     string
	RelationshipType string
}

// CanonicalRunsOnParams holds the parameters for a repository-scoped RUNS_ON
// upsert that resolves to workload instances.
type CanonicalRunsOnParams struct {
	RepoID     string
	PlatformID string
}

const canonicalRepoRelationshipUpsertCypher = `UNWIND $rows AS row
MATCH (source_repo:Repository {id: row.repo_id})
MATCH (target_repo:Repository {id: row.target_repo_id})
FOREACH (_ IN CASE WHEN row.relationship_type = 'DEPLOYS_FROM' THEN [1] ELSE [] END |
    MERGE (source_repo)-[rel:DEPLOYS_FROM]->(target_repo)
    SET rel.confidence = 0.9,
        rel.reason = 'Runtime services list declares repository dependency',
        rel.evidence_source = row.evidence_source,
        rel.relationship_type = row.relationship_type
)
FOREACH (_ IN CASE WHEN row.relationship_type = 'DISCOVERS_CONFIG_IN' THEN [1] ELSE [] END |
    MERGE (source_repo)-[rel:DISCOVERS_CONFIG_IN]->(target_repo)
    SET rel.confidence = 0.9,
        rel.reason = 'Runtime services list declares repository dependency',
        rel.evidence_source = row.evidence_source,
        rel.relationship_type = row.relationship_type
)
FOREACH (_ IN CASE WHEN row.relationship_type = 'PROVISIONS_DEPENDENCY_FOR' THEN [1] ELSE [] END |
    MERGE (source_repo)-[rel:PROVISIONS_DEPENDENCY_FOR]->(target_repo)
    SET rel.confidence = 0.9,
        rel.reason = 'Runtime services list declares repository dependency',
        rel.evidence_source = row.evidence_source,
        rel.relationship_type = row.relationship_type
)
FOREACH (_ IN CASE WHEN row.relationship_type IS NULL OR row.relationship_type = '' OR row.relationship_type = 'DEPENDS_ON' THEN [1] ELSE [] END |
    MERGE (source_repo)-[rel:DEPENDS_ON]->(target_repo)
    SET rel.confidence = 0.9,
        rel.reason = 'Runtime services list declares repository dependency',
        rel.evidence_source = row.evidence_source,
        rel.relationship_type = row.relationship_type
)`

const batchCanonicalTypedRepoRelationshipUpsertCypher = canonicalRepoRelationshipUpsertCypher

const canonicalRunsOnUpsertCypher = `UNWIND $rows AS row
MATCH (repo:Repository {id: row.repo_id})
MATCH (repo)-[:DEFINES]->(:Workload)<-[:INSTANCE_OF]-(i:WorkloadInstance)
MATCH (p:Platform {id: row.platform_id})
MERGE (i)-[rel:RUNS_ON]->(p)
SET rel.confidence = 0.97,
    rel.reason = 'Repository workload instance runs on inferred platform',
    rel.evidence_source = row.evidence_source`

const batchCanonicalRunsOnUpsertCypher = canonicalRunsOnUpsertCypher

const retractRepoRelationshipAndRunsOnEdgesCypher = `MATCH (source_repo:Repository)-[rel:DEPENDS_ON|DEPLOYS_FROM|DISCOVERS_CONFIG_IN|PROVISIONS_DEPENDENCY_FOR]->(:Repository)
WHERE source_repo.id IN $repo_ids
  AND rel.evidence_source = $evidence_source
DELETE rel
WITH $repo_ids AS repo_ids, $evidence_source AS evidence_source
MATCH (repo:Repository)-[:DEFINES]->(:Workload)<-[:INSTANCE_OF]-(i:WorkloadInstance)-[rel:RUNS_ON]->(:Platform)
WHERE repo.id IN repo_ids
  AND rel.evidence_source = evidence_source
DELETE rel`

// BuildCanonicalRepoRelationshipUpsert builds a typed repository relationship statement.
func BuildCanonicalRepoRelationshipUpsert(p CanonicalRepoRelationshipParams, evidenceSource string) Statement {
	return Statement{
		Operation: OperationCanonicalUpsert,
		Cypher:    canonicalRepoRelationshipUpsertCypher,
		Parameters: map[string]any{
			"repo_id":           p.RepoID,
			"target_repo_id":    p.TargetRepoID,
			"relationship_type": p.RelationshipType,
			"evidence_source":   evidenceSource,
		},
	}
}

// BuildCanonicalRunsOnUpsert builds a repository-scoped RUNS_ON statement.
func BuildCanonicalRunsOnUpsert(p CanonicalRunsOnParams, evidenceSource string) Statement {
	return Statement{
		Operation: OperationCanonicalUpsert,
		Cypher:    canonicalRunsOnUpsertCypher,
		Parameters: map[string]any{
			"repo_id":         p.RepoID,
			"platform_id":     p.PlatformID,
			"evidence_source": evidenceSource,
		},
	}
}
