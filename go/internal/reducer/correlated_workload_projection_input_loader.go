package reducer

import (
	"context"
	"fmt"
	"strings"

	"github.com/platformcontext/platform-context-graph/go/internal/correlation/engine"
	correlationmodel "github.com/platformcontext/platform-context-graph/go/internal/correlation/model"
)

// CorrelatedWorkloadProjectionInputLoader reuses deployable-unit correlation
// semantics as the authoritative gate for workload materialization inputs.
type CorrelatedWorkloadProjectionInputLoader struct {
	FactLoader     FactLoader
	ResolvedLoader ResolvedRelationshipLoader
}

// LoadWorkloadProjectionInputs loads workload candidates, enriches them with
// resolved deployment sources, and returns only admitted deployable units.
func (l CorrelatedWorkloadProjectionInputLoader) LoadWorkloadProjectionInputs(
	ctx context.Context,
	intent Intent,
) ([]WorkloadCandidate, map[string][]string, error) {
	if l.FactLoader == nil {
		return nil, nil, fmt.Errorf("correlated workload projection fact loader is required")
	}

	envelopes, err := l.FactLoader.ListFacts(ctx, intent.ScopeID, intent.GenerationID)
	if err != nil {
		return nil, nil, fmt.Errorf("load facts for correlated workload projection: %w", err)
	}

	candidates, deploymentEnvironments := ExtractWorkloadCandidates(envelopes)
	if l.ResolvedLoader != nil {
		resolved, err := loadResolvedRelationshipsForIntent(ctx, l.ResolvedLoader, intent)
		if err != nil {
			return nil, nil, fmt.Errorf("load resolved relationships for correlated workload projection: %w", err)
		}
		candidates = applyResolvedDeploymentSources(candidates, resolved)
	}

	if len(intent.EntityKeys) > 0 {
		entityKeys, err := deployableUnitCorrelationEntityKeys(intent)
		if err != nil {
			return nil, nil, err
		}
		candidates = filterDeployableUnitCandidates(candidates, entityKeys)
	}

	admitted, err := admittedCorrelatedWorkloadCandidates(intent, candidates)
	if err != nil {
		return nil, nil, err
	}
	return admitted, deploymentEnvironments, nil
}

func admittedCorrelatedWorkloadCandidates(
	intent Intent,
	candidates []WorkloadCandidate,
) ([]WorkloadCandidate, error) {
	admitted := make([]WorkloadCandidate, 0, len(candidates))
	seen := make(map[string]struct{}, len(candidates))

	for _, candidate := range candidates {
		evaluation, err := engine.Evaluate(
			deployableUnitRulePack(candidate),
			deployableUnitModelCandidates(intent, candidate),
		)
		if err != nil {
			return nil, fmt.Errorf("evaluate correlated workload candidate %q: %w", candidate.RepoName, err)
		}
		for _, result := range evaluation.Results {
			if result.Candidate.State != correlationmodel.CandidateStateAdmitted {
				continue
			}
			correlatedCandidate := candidate
			correlatedCandidate.WorkloadName = correlatedWorkloadName(candidate, result.Candidate)
			correlatedCandidate.Confidence = result.Candidate.Confidence

			candidateKey := fmt.Sprintf("%s:%s", correlatedCandidate.RepoID, correlatedCandidate.WorkloadName)
			if _, ok := seen[candidateKey]; ok {
				continue
			}
			seen[candidateKey] = struct{}{}
			admitted = append(admitted, correlatedCandidate)
		}
	}

	return admitted, nil
}

func correlatedWorkloadName(
	candidate WorkloadCandidate,
	evaluatedCandidate correlationmodel.Candidate,
) string {
	prefix := candidate.RepoID + ":"
	if strings.HasPrefix(evaluatedCandidate.CorrelationKey, prefix) {
		if unitKey := strings.TrimSpace(strings.TrimPrefix(evaluatedCandidate.CorrelationKey, prefix)); unitKey != "" {
			return unitKey
		}
	}
	return candidateWorkloadName(candidate)
}
