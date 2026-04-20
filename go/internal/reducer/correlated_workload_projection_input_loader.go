package reducer

import (
	"context"
	"fmt"
	"log/slog"
	"strings"

	"github.com/platformcontext/platform-context-graph/go/internal/correlation/engine"
	correlationmodel "github.com/platformcontext/platform-context-graph/go/internal/correlation/model"
)

// CorrelatedWorkloadProjectionInputLoader reuses deployable-unit correlation
// semantics as the authoritative gate for workload materialization inputs.
type CorrelatedWorkloadProjectionInputLoader struct {
	FactLoader     FactLoader
	ResolvedLoader ResolvedRelationshipLoader
	ScopeResolver  DeploymentRepoScopeResolver
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

	if l.ScopeResolver != nil {
		deploymentEnvironments = l.enrichDeploymentRepoEnvironments(
			ctx, candidates, deploymentEnvironments,
		)
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

// enrichDeploymentRepoEnvironments loads facts from deployment repos that are
// not the source repo, extracts overlay environments, and merges them into the
// deploymentEnvironments map. This enables cross-repo environment resolution
// when the source repo is deployed via a separate helm-charts/argocd repo.
func (l CorrelatedWorkloadProjectionInputLoader) enrichDeploymentRepoEnvironments(
	ctx context.Context,
	candidates []WorkloadCandidate,
	deploymentEnvironments map[string][]string,
) map[string][]string {
	// Collect unique deployment repo IDs that differ from the source repo
	// and don't already have environments.
	needed := make(map[string]struct{})
	sourceRepos := make(map[string]struct{})
	for _, c := range candidates {
		sourceRepos[c.RepoID] = struct{}{}
	}
	for _, c := range candidates {
		if c.DeploymentRepoID == "" {
			continue
		}
		if _, isSameRepo := sourceRepos[c.DeploymentRepoID]; isSameRepo {
			continue
		}
		if _, hasEnvs := deploymentEnvironments[c.DeploymentRepoID]; hasEnvs {
			continue
		}
		needed[c.DeploymentRepoID] = struct{}{}
	}
	if len(needed) == 0 {
		return deploymentEnvironments
	}

	repoIDs := make([]string, 0, len(needed))
	for id := range needed {
		repoIDs = append(repoIDs, id)
	}

	identities, err := l.ScopeResolver.ResolveRepoActiveGenerations(ctx, repoIDs)
	if err != nil {
		slog.Warn("resolve deployment repo active generations",
			"error", err, "repo_ids", repoIDs)
		return deploymentEnvironments
	}

	for repoID, identity := range identities {
		envelopes, err := l.FactLoader.ListFacts(ctx, identity.ScopeID, identity.GenerationID)
		if err != nil {
			slog.Warn("load deployment repo facts for environment extraction",
				"error", err, "repo_id", repoID,
				"scope_id", identity.ScopeID, "generation_id", identity.GenerationID)
			continue
		}
		envs := ExtractOverlayEnvironmentsFromEnvelopes(envelopes)
		for envRepoID, environments := range envs {
			if _, exists := deploymentEnvironments[envRepoID]; !exists {
				deploymentEnvironments[envRepoID] = environments
			}
		}
	}

	return deploymentEnvironments
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
