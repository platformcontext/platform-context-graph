package query

import (
	"context"
	"sort"
)

// queryRepoDeploymentEvidence reads compact graph evidence pointers for
// repository relationships without embedding raw Postgres evidence payloads.
func queryRepoDeploymentEvidence(ctx context.Context, reader GraphQuery, params map[string]any) map[string]any {
	outgoing := queryRepoDeploymentEvidenceDirection(ctx, reader, params, `
		MATCH (r:Repository {id: $repo_id})-[source_rel:HAS_DEPLOYMENT_EVIDENCE]->(artifact:EvidenceArtifact)-[:EVIDENCES_REPOSITORY_RELATIONSHIP]->(target:Repository)
		RETURN 'outgoing' AS direction,
		       artifact.id AS artifact_id,
		       artifact.name AS name,
		       artifact.domain AS domain,
		       artifact.path AS path,
		       artifact.evidence_kind AS evidence_kind,
		       artifact.artifact_family AS artifact_family,
		       artifact.extractor AS extractor,
		       artifact.relationship_type AS relationship_type,
		       artifact.resolved_id AS resolved_id,
		       artifact.generation_id AS generation_id,
		       artifact.confidence AS confidence,
		       artifact.environment AS environment,
		       artifact.runtime_platform_kind AS runtime_platform_kind,
		       artifact.matched_alias AS matched_alias,
		       artifact.matched_value AS matched_value,
		       artifact.evidence_source AS evidence_source,
		       r.id AS source_repo_id,
		       r.name AS source_repo_name,
		       target.id AS target_repo_id,
		       target.name AS target_repo_name
		ORDER BY path, artifact_id
	`)
	incoming := queryRepoDeploymentEvidenceDirection(ctx, reader, params, `
		MATCH (r:Repository {id: $repo_id})
		MATCH (r)<-[target_rel:EVIDENCES_REPOSITORY_RELATIONSHIP]-(artifact:EvidenceArtifact)<-[:HAS_DEPLOYMENT_EVIDENCE]-(source:Repository)
		RETURN 'incoming' AS direction,
		       artifact.id AS artifact_id,
		       artifact.name AS name,
		       artifact.domain AS domain,
		       artifact.path AS path,
		       artifact.evidence_kind AS evidence_kind,
		       artifact.artifact_family AS artifact_family,
		       artifact.extractor AS extractor,
		       artifact.relationship_type AS relationship_type,
		       artifact.resolved_id AS resolved_id,
		       artifact.generation_id AS generation_id,
		       artifact.confidence AS confidence,
		       artifact.environment AS environment,
		       artifact.runtime_platform_kind AS runtime_platform_kind,
		       artifact.matched_alias AS matched_alias,
		       artifact.matched_value AS matched_value,
		       artifact.evidence_source AS evidence_source,
		       source.id AS source_repo_id,
		       source.name AS source_repo_name,
		       r.id AS target_repo_id,
		       r.name AS target_repo_name
		ORDER BY path, artifact_id
	`)
	rows := append(outgoing, incoming...)
	if len(rows) == 0 {
		return nil
	}
	return buildGraphDeploymentEvidence(rows)
}

func queryRepoDeploymentEvidenceDirection(ctx context.Context, reader GraphQuery, params map[string]any, cypher string) []map[string]any {
	rows, err := reader.Run(ctx, cypher, params)
	if err != nil || len(rows) == 0 {
		return nil
	}
	return rows
}

// buildGraphDeploymentEvidence converts EvidenceArtifact graph rows into the
// repository context contract and keeps Postgres drilldown keys explicit.
func buildGraphDeploymentEvidence(rows []map[string]any) map[string]any {
	artifacts := make([]map[string]any, 0, len(rows))
	var (
		families          []string
		evidenceKinds     []string
		relationshipTypes []string
		environments      []string
		sourceRepoIDs     []string
		targetRepoIDs     []string
		ciArtifactCount   int
	)
	for _, row := range rows {
		artifact := map[string]any{
			"id":                StringVal(row, "artifact_id"),
			"direction":         StringVal(row, "direction"),
			"name":              StringVal(row, "name"),
			"domain":            StringVal(row, "domain"),
			"path":              StringVal(row, "path"),
			"evidence_kind":     StringVal(row, "evidence_kind"),
			"artifact_family":   StringVal(row, "artifact_family"),
			"extractor":         StringVal(row, "extractor"),
			"relationship_type": StringVal(row, "relationship_type"),
			"source_repo_id":    StringVal(row, "source_repo_id"),
			"source_repo_name":  StringVal(row, "source_repo_name"),
			"target_repo_id":    StringVal(row, "target_repo_id"),
			"target_repo_name":  StringVal(row, "target_repo_name"),
			"evidence_source":   StringVal(row, "evidence_source"),
		}
		copyOptionalDeploymentEvidenceFields(artifact, row)

		family := StringVal(row, "artifact_family")
		if family == "github_actions" || family == "jenkins" {
			ciArtifactCount++
		}
		families = append(families, family)
		evidenceKinds = append(evidenceKinds, StringVal(row, "evidence_kind"))
		relationshipTypes = append(relationshipTypes, StringVal(row, "relationship_type"))
		environments = append(environments, StringVal(row, "environment"))
		sourceRepoIDs = append(sourceRepoIDs, StringVal(row, "source_repo_id"))
		targetRepoIDs = append(targetRepoIDs, StringVal(row, "target_repo_id"))
		artifacts = append(artifacts, artifact)
	}

	sort.Slice(artifacts, func(i, j int) bool {
		leftPath := StringVal(artifacts[i], "path")
		rightPath := StringVal(artifacts[j], "path")
		if leftPath != rightPath {
			return leftPath < rightPath
		}
		return StringVal(artifacts[i], "id") < StringVal(artifacts[j], "id")
	})

	return map[string]any{
		"truth_basis":        "graph",
		"artifact_count":     len(artifacts),
		"ci_artifact_count":  ciArtifactCount,
		"environment_count":  len(uniqueSortedStrings(environments)),
		"artifacts":          artifacts,
		"artifact_families":  uniqueSortedStrings(families),
		"evidence_kinds":     uniqueSortedStrings(evidenceKinds),
		"relationship_types": uniqueSortedStrings(relationshipTypes),
		"environments":       uniqueSortedStrings(environments),
		"source_repo_ids":    uniqueSortedStrings(sourceRepoIDs),
		"target_repo_ids":    uniqueSortedStrings(targetRepoIDs),
	}
}

func copyOptionalDeploymentEvidenceFields(dst map[string]any, src map[string]any) {
	if resolvedID := StringVal(src, "resolved_id"); resolvedID != "" {
		dst["resolved_id"] = resolvedID
		dst["postgres_lookup_basis"] = "resolved_id"
	}
	if generationID := StringVal(src, "generation_id"); generationID != "" {
		dst["generation_id"] = generationID
	}
	if confidence := relationshipFloatVal(src, "confidence"); confidence > 0 {
		dst["confidence"] = confidence
	}
	if environment := StringVal(src, "environment"); environment != "" {
		dst["environment"] = environment
	}
	if runtimePlatformKind := StringVal(src, "runtime_platform_kind"); runtimePlatformKind != "" {
		dst["runtime_platform_kind"] = runtimePlatformKind
	}
	if matchedAlias := StringVal(src, "matched_alias"); matchedAlias != "" {
		dst["matched_alias"] = matchedAlias
	}
	if matchedValue := StringVal(src, "matched_value"); matchedValue != "" {
		dst["matched_value"] = matchedValue
	}
}
