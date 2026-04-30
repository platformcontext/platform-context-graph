package neo4j

// CanonicalRepoRelationshipParams holds the parameters for a typed repository
// relationship upsert.
type CanonicalRepoRelationshipParams struct {
	RepoID           string
	TargetRepoID     string
	RelationshipType string
	EvidenceType     string
	ResolvedID       string
	GenerationID     string
	EvidenceCount    int
	EvidenceKinds    []string
	ResolutionSource string
	Confidence       float64
	Rationale        string
}

// CanonicalRunsOnParams holds the parameters for a repository-scoped RUNS_ON
// upsert that resolves to workload instances.
type CanonicalRunsOnParams struct {
	RepoID     string
	PlatformID string
}

const canonicalRepoRelationshipUpsertCypher = `UNWIND $rows AS row
MERGE (source_repo:Repository {id: row.repo_id})
MERGE (target_repo:Repository {id: row.target_repo_id})
FOREACH (_ IN CASE WHEN row.relationship_type = 'DEPLOYS_FROM' THEN [1] ELSE [] END |
    MERGE (source_repo)-[rel:DEPLOYS_FROM]->(target_repo)
    SET rel.confidence = row.confidence,
        rel.reason = 'Runtime services list declares repository dependency',
        rel.evidence_source = row.evidence_source,
        rel.evidence_type = row.evidence_type,
        rel.relationship_type = row.relationship_type,
        rel.resolved_id = row.resolved_id,
        rel.generation_id = row.generation_id,
        rel.evidence_count = row.evidence_count,
        rel.evidence_kinds = row.evidence_kinds,
        rel.resolution_source = row.resolution_source,
        rel.rationale = row.rationale
)
FOREACH (_ IN CASE WHEN row.relationship_type = 'DISCOVERS_CONFIG_IN' THEN [1] ELSE [] END |
    MERGE (source_repo)-[rel:DISCOVERS_CONFIG_IN]->(target_repo)
    SET rel.confidence = row.confidence,
        rel.reason = 'Runtime services list declares repository dependency',
        rel.evidence_source = row.evidence_source,
        rel.evidence_type = row.evidence_type,
        rel.relationship_type = row.relationship_type,
        rel.resolved_id = row.resolved_id,
        rel.generation_id = row.generation_id,
        rel.evidence_count = row.evidence_count,
        rel.evidence_kinds = row.evidence_kinds,
        rel.resolution_source = row.resolution_source,
        rel.rationale = row.rationale
)
FOREACH (_ IN CASE WHEN row.relationship_type = 'PROVISIONS_DEPENDENCY_FOR' THEN [1] ELSE [] END |
    MERGE (source_repo)-[rel:PROVISIONS_DEPENDENCY_FOR]->(target_repo)
    SET rel.confidence = row.confidence,
        rel.reason = 'Runtime services list declares repository dependency',
        rel.evidence_source = row.evidence_source,
        rel.evidence_type = row.evidence_type,
        rel.relationship_type = row.relationship_type,
        rel.resolved_id = row.resolved_id,
        rel.generation_id = row.generation_id,
        rel.evidence_count = row.evidence_count,
        rel.evidence_kinds = row.evidence_kinds,
        rel.resolution_source = row.resolution_source,
        rel.rationale = row.rationale
)
FOREACH (_ IN CASE WHEN row.relationship_type = 'USES_MODULE' THEN [1] ELSE [] END |
    MERGE (source_repo)-[rel:USES_MODULE]->(target_repo)
    SET rel.confidence = row.confidence,
        rel.reason = 'Runtime services list declares repository dependency',
        rel.evidence_source = row.evidence_source,
        rel.evidence_type = row.evidence_type,
        rel.relationship_type = row.relationship_type,
        rel.resolved_id = row.resolved_id,
        rel.generation_id = row.generation_id,
        rel.evidence_count = row.evidence_count,
        rel.evidence_kinds = row.evidence_kinds,
        rel.resolution_source = row.resolution_source,
        rel.rationale = row.rationale
)
FOREACH (_ IN CASE WHEN row.relationship_type IS NULL OR row.relationship_type = '' OR row.relationship_type = 'DEPENDS_ON' THEN [1] ELSE [] END |
    MERGE (source_repo)-[rel:DEPENDS_ON]->(target_repo)
    SET rel.confidence = row.confidence,
        rel.reason = 'Runtime services list declares repository dependency',
        rel.evidence_source = row.evidence_source,
        rel.evidence_type = row.evidence_type,
        rel.relationship_type = row.relationship_type,
        rel.resolved_id = row.resolved_id,
        rel.generation_id = row.generation_id,
        rel.evidence_count = row.evidence_count,
        rel.evidence_kinds = row.evidence_kinds,
        rel.resolution_source = row.resolution_source,
        rel.rationale = row.rationale
)`

const canonicalDeploysFromRepoRelationshipUpsertCypher = `MERGE (source_repo:Repository {id: $repo_id})
MERGE (target_repo:Repository {id: $target_repo_id})
MERGE (source_repo)-[rel:DEPLOYS_FROM]->(target_repo)
SET rel.confidence = $confidence,
    rel.reason = 'Runtime services list declares repository dependency',
    rel.evidence_source = $evidence_source,
    rel.evidence_type = $evidence_type,
    rel.relationship_type = 'DEPLOYS_FROM',
    rel.resolved_id = $resolved_id,
    rel.generation_id = $generation_id,
    rel.evidence_count = $evidence_count,
    rel.evidence_kinds = $evidence_kinds,
    rel.resolution_source = $resolution_source,
    rel.rationale = $rationale`

const canonicalDiscoversConfigInRepoRelationshipUpsertCypher = `MERGE (source_repo:Repository {id: $repo_id})
MERGE (target_repo:Repository {id: $target_repo_id})
MERGE (source_repo)-[rel:DISCOVERS_CONFIG_IN]->(target_repo)
SET rel.confidence = $confidence,
    rel.reason = 'Runtime services list declares repository dependency',
    rel.evidence_source = $evidence_source,
    rel.evidence_type = $evidence_type,
    rel.relationship_type = 'DISCOVERS_CONFIG_IN',
    rel.resolved_id = $resolved_id,
    rel.generation_id = $generation_id,
    rel.evidence_count = $evidence_count,
    rel.evidence_kinds = $evidence_kinds,
    rel.resolution_source = $resolution_source,
    rel.rationale = $rationale`

const canonicalProvisionsDependencyForRepoRelationshipUpsertCypher = `MERGE (source_repo:Repository {id: $repo_id})
MERGE (target_repo:Repository {id: $target_repo_id})
MERGE (source_repo)-[rel:PROVISIONS_DEPENDENCY_FOR]->(target_repo)
SET rel.confidence = $confidence,
    rel.reason = 'Runtime services list declares repository dependency',
    rel.evidence_source = $evidence_source,
    rel.evidence_type = $evidence_type,
    rel.relationship_type = 'PROVISIONS_DEPENDENCY_FOR',
    rel.resolved_id = $resolved_id,
    rel.generation_id = $generation_id,
    rel.evidence_count = $evidence_count,
    rel.evidence_kinds = $evidence_kinds,
    rel.resolution_source = $resolution_source,
    rel.rationale = $rationale`

const canonicalUsesModuleRepoRelationshipUpsertCypher = `MERGE (source_repo:Repository {id: $repo_id})
MERGE (target_repo:Repository {id: $target_repo_id})
MERGE (source_repo)-[rel:USES_MODULE]->(target_repo)
SET rel.confidence = $confidence,
    rel.reason = 'Runtime services list declares repository dependency',
    rel.evidence_source = $evidence_source,
    rel.evidence_type = $evidence_type,
    rel.relationship_type = 'USES_MODULE',
    rel.resolved_id = $resolved_id,
    rel.generation_id = $generation_id,
    rel.evidence_count = $evidence_count,
    rel.evidence_kinds = $evidence_kinds,
    rel.resolution_source = $resolution_source,
    rel.rationale = $rationale`

const batchCanonicalDeploysFromRepoRelationshipUpsertCypher = `UNWIND $rows AS row
MERGE (source_repo:Repository {id: row.repo_id})
MERGE (target_repo:Repository {id: row.target_repo_id})
MERGE (source_repo)-[rel:DEPLOYS_FROM]->(target_repo)
SET rel.confidence = row.confidence,
    rel.reason = 'Runtime services list declares repository dependency',
    rel.evidence_source = row.evidence_source,
    rel.evidence_type = row.evidence_type,
    rel.relationship_type = 'DEPLOYS_FROM',
    rel.resolved_id = row.resolved_id,
    rel.generation_id = row.generation_id,
    rel.evidence_count = row.evidence_count,
    rel.evidence_kinds = row.evidence_kinds,
    rel.resolution_source = row.resolution_source,
    rel.rationale = row.rationale`

const batchCanonicalDiscoversConfigInRepoRelationshipUpsertCypher = `UNWIND $rows AS row
MERGE (source_repo:Repository {id: row.repo_id})
MERGE (target_repo:Repository {id: row.target_repo_id})
MERGE (source_repo)-[rel:DISCOVERS_CONFIG_IN]->(target_repo)
SET rel.confidence = row.confidence,
    rel.reason = 'Runtime services list declares repository dependency',
    rel.evidence_source = row.evidence_source,
    rel.evidence_type = row.evidence_type,
    rel.relationship_type = 'DISCOVERS_CONFIG_IN',
    rel.resolved_id = row.resolved_id,
    rel.generation_id = row.generation_id,
    rel.evidence_count = row.evidence_count,
    rel.evidence_kinds = row.evidence_kinds,
    rel.resolution_source = row.resolution_source,
    rel.rationale = row.rationale`

const batchCanonicalProvisionsDependencyForRepoRelationshipUpsertCypher = `UNWIND $rows AS row
MERGE (source_repo:Repository {id: row.repo_id})
MERGE (target_repo:Repository {id: row.target_repo_id})
MERGE (source_repo)-[rel:PROVISIONS_DEPENDENCY_FOR]->(target_repo)
SET rel.confidence = row.confidence,
    rel.reason = 'Runtime services list declares repository dependency',
    rel.evidence_source = row.evidence_source,
    rel.evidence_type = row.evidence_type,
    rel.relationship_type = 'PROVISIONS_DEPENDENCY_FOR',
    rel.resolved_id = row.resolved_id,
    rel.generation_id = row.generation_id,
    rel.evidence_count = row.evidence_count,
    rel.evidence_kinds = row.evidence_kinds,
    rel.resolution_source = row.resolution_source,
    rel.rationale = row.rationale`

const batchCanonicalUsesModuleRepoRelationshipUpsertCypher = `UNWIND $rows AS row
MERGE (source_repo:Repository {id: row.repo_id})
MERGE (target_repo:Repository {id: row.target_repo_id})
MERGE (source_repo)-[rel:USES_MODULE]->(target_repo)
SET rel.confidence = row.confidence,
    rel.reason = 'Runtime services list declares repository dependency',
    rel.evidence_source = row.evidence_source,
    rel.evidence_type = row.evidence_type,
    rel.relationship_type = 'USES_MODULE',
    rel.resolved_id = row.resolved_id,
    rel.generation_id = row.generation_id,
    rel.evidence_count = row.evidence_count,
    rel.evidence_kinds = row.evidence_kinds,
    rel.resolution_source = row.resolution_source,
    rel.rationale = row.rationale`

const canonicalRunsOnUpsertCypher = `UNWIND $rows AS row
MATCH (repo:Repository {id: row.repo_id})
MATCH (repo)-[:DEFINES]->(:Workload)<-[:INSTANCE_OF]-(i:WorkloadInstance)
MATCH (p:Platform {id: row.platform_id})
MERGE (i)-[rel:RUNS_ON]->(p)
SET rel.confidence = 0.97,
    rel.reason = 'Repository workload instance runs on inferred platform',
    rel.evidence_source = row.evidence_source`

const batchCanonicalRunsOnUpsertCypher = canonicalRunsOnUpsertCypher

const retractRepoRelationshipAndRunsOnEdgesCypher = `UNWIND $repo_ids AS repo_id
MATCH (source_repo:Repository {id: repo_id})-[rel:DEPENDS_ON|DEPLOYS_FROM|DISCOVERS_CONFIG_IN|PROVISIONS_DEPENDENCY_FOR|USES_MODULE]->(:Repository)
WHERE rel.evidence_source = $evidence_source
DELETE rel
WITH DISTINCT repo_id, $evidence_source AS evidence_source
MATCH (repo:Repository {id: repo_id})-[:DEFINES]->(:Workload)<-[:INSTANCE_OF]-(i:WorkloadInstance)-[rel:RUNS_ON]->(:Platform)
WHERE rel.evidence_source = evidence_source
DELETE rel`

// BuildCanonicalRepoRelationshipUpsert builds a typed repository relationship statement.
func BuildCanonicalRepoRelationshipUpsert(p CanonicalRepoRelationshipParams, evidenceSource string) Statement {
	cypher := canonicalTypedRepoRelationshipUpsertCypher(p.RelationshipType)
	return Statement{
		Operation: OperationCanonicalUpsert,
		Cypher:    cypher,
		Parameters: map[string]any{
			"repo_id":           p.RepoID,
			"target_repo_id":    p.TargetRepoID,
			"relationship_type": p.RelationshipType,
			"evidence_type":     p.EvidenceType,
			"evidence_source":   evidenceSource,
			"resolved_id":       p.ResolvedID,
			"generation_id":     p.GenerationID,
			"evidence_count":    p.EvidenceCount,
			"evidence_kinds":    p.EvidenceKinds,
			"resolution_source": p.ResolutionSource,
			"confidence":        repoRelationshipConfidence(p.Confidence),
			"rationale":         p.Rationale,
		},
	}
}

func repoRelationshipConfidence(value float64) float64 {
	if value <= 0 {
		return 0.9
	}
	return value
}

func canonicalTypedRepoRelationshipUpsertCypher(relationshipType string) string {
	switch relationshipType {
	case "DEPLOYS_FROM":
		return canonicalDeploysFromRepoRelationshipUpsertCypher
	case "DISCOVERS_CONFIG_IN":
		return canonicalDiscoversConfigInRepoRelationshipUpsertCypher
	case "PROVISIONS_DEPENDENCY_FOR":
		return canonicalProvisionsDependencyForRepoRelationshipUpsertCypher
	case "USES_MODULE":
		return canonicalUsesModuleRepoRelationshipUpsertCypher
	default:
		return canonicalRepoDependencyUpsertCypher
	}
}

func batchCanonicalTypedRepoRelationshipUpsertCypher(relationshipType string) (string, bool) {
	switch relationshipType {
	case "DEPLOYS_FROM":
		return batchCanonicalDeploysFromRepoRelationshipUpsertCypher, true
	case "DISCOVERS_CONFIG_IN":
		return batchCanonicalDiscoversConfigInRepoRelationshipUpsertCypher, true
	case "PROVISIONS_DEPENDENCY_FOR":
		return batchCanonicalProvisionsDependencyForRepoRelationshipUpsertCypher, true
	case "USES_MODULE":
		return batchCanonicalUsesModuleRepoRelationshipUpsertCypher, true
	default:
		return "", false
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
