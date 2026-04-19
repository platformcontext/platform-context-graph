package reducer

import (
	"fmt"

	"github.com/platformcontext/platform-context-graph/go/internal/relationships"
)

func applyResolvedDeploymentSources(
	candidates []WorkloadCandidate,
	resolved []relationships.ResolvedRelationship,
) []WorkloadCandidate {
	if len(candidates) == 0 || len(resolved) == 0 {
		return candidates
	}

	type deploymentSourceMetadata struct {
		repoID     string
		confidence float64
		provenance string
	}

	deploymentRepoBySource := make(map[string]deploymentSourceMetadata, len(resolved))
	for _, relationship := range resolved {
		if relationship.RelationshipType != relationships.RelDeploysFrom {
			continue
		}
		if relationship.SourceRepoID == "" || relationship.TargetRepoID == "" {
			continue
		}
		if !hasArgoDeploymentEvidence(relationship.Details) {
			continue
		}
		provenance := argoDeploymentProvenance(relationship.Details)
		if provenance == "" {
			provenance = "argocd_application_source"
		}
		existing, exists := deploymentRepoBySource[relationship.SourceRepoID]
		if exists && existing.confidence >= relationship.Confidence {
			continue
		}
		deploymentRepoBySource[relationship.SourceRepoID] = deploymentSourceMetadata{
			repoID:     relationship.TargetRepoID,
			confidence: relationship.Confidence,
			provenance: provenance,
		}
	}

	if len(deploymentRepoBySource) == 0 {
		return candidates
	}

	enriched := make([]WorkloadCandidate, len(candidates))
	for i, candidate := range candidates {
		enriched[i] = candidate
		if metadata, ok := deploymentRepoBySource[candidate.RepoID]; ok {
			enriched[i].DeploymentRepoID = metadata.repoID
			if metadata.confidence > enriched[i].Confidence {
				enriched[i].Confidence = metadata.confidence
			}
			enriched[i].Provenance = appendUniqueString(enriched[i].Provenance, metadata.provenance)
			if enriched[i].Classification == "" {
				enriched[i].Classification = InferWorkloadClassification(enriched[i])
			}
		}
	}

	return enriched
}

func hasArgoDeploymentEvidence(details map[string]any) bool {
	rawKinds, ok := details["evidence_kinds"]
	if !ok {
		return false
	}

	for _, kind := range toStringSlice(rawKinds) {
		switch relationships.EvidenceKind(kind) {
		case relationships.EvidenceKindArgoCDAppSource,
			relationships.EvidenceKindArgoCDApplicationSetDeploySource:
			return true
		}
	}

	return false
}

func argoDeploymentProvenance(details map[string]any) string {
	for _, kind := range toStringSlice(details["evidence_kinds"]) {
		switch relationships.EvidenceKind(kind) {
		case relationships.EvidenceKindArgoCDApplicationSetDeploySource:
			return "argocd_applicationset_deploy_source"
		case relationships.EvidenceKindArgoCDAppSource:
			return "argocd_application_source"
		}
	}
	return ""
}

func toStringSlice(value any) []string {
	switch typed := value.(type) {
	case []string:
		return typed
	case []any:
		result := make([]string, 0, len(typed))
		for _, item := range typed {
			text := fmt.Sprint(item)
			if text == "" || text == "<nil>" {
				continue
			}
			result = append(result, text)
		}
		return result
	default:
		text := fmt.Sprint(value)
		if text == "" || text == "<nil>" {
			return nil
		}
		return []string{text}
	}
}

func appendUniqueString(values []string, value string) []string {
	if value == "" {
		return values
	}
	for _, existing := range values {
		if existing == value {
			return values
		}
	}
	return append(values, value)
}
