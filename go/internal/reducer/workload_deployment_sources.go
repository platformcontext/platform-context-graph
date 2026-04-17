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

	deploymentRepoBySource := make(map[string]string, len(resolved))
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
		if _, exists := deploymentRepoBySource[relationship.SourceRepoID]; exists {
			continue
		}
		deploymentRepoBySource[relationship.SourceRepoID] = relationship.TargetRepoID
	}

	if len(deploymentRepoBySource) == 0 {
		return candidates
	}

	enriched := make([]WorkloadCandidate, len(candidates))
	for i, candidate := range candidates {
		enriched[i] = candidate
		if deploymentRepoID, ok := deploymentRepoBySource[candidate.RepoID]; ok {
			enriched[i].DeploymentRepoID = deploymentRepoID
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
