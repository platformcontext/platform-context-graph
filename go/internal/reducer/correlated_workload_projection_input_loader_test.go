package reducer

import (
	"context"
	"fmt"
	"testing"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/facts"
	"github.com/platformcontext/platform-context-graph/go/internal/relationships"
)

func TestCorrelatedWorkloadProjectionInputLoaderRejectsDockerfileOnlyCandidate(t *testing.T) {
	t.Parallel()

	now := time.Now().UTC()
	loader := CorrelatedWorkloadProjectionInputLoader{
		FactLoader: &stubFactLoader{
			envelopes: []facts.Envelope{
				{
					FactID:   "fact-repo-1",
					ScopeID:  "scope-service",
					FactKind: "repository",
					Payload: map[string]any{
						"graph_id": "repo-service",
						"name":     "service-repo",
					},
					ObservedAt: now,
				},
				{
					FactID:   "fact-file-1",
					ScopeID:  "scope-service",
					FactKind: "file",
					Payload: map[string]any{
						"repo_id":       "repo-service",
						"language":      "dockerfile",
						"relative_path": "Dockerfile",
						"parsed_file_data": map[string]any{
							"dockerfile_stages": []any{map[string]any{"name": "runtime"}},
						},
					},
					ObservedAt: now,
				},
			},
		},
	}

	intent := Intent{
		IntentID:        "intent-correlation-1",
		ScopeID:         "scope-service",
		GenerationID:    "gen-1",
		SourceSystem:    "git",
		Domain:          DomainWorkloadMaterialization,
		Cause:           "test",
		EntityKeys:      []string{"repo-service"},
		RelatedScopeIDs: []string{"scope-service"},
		EnqueuedAt:      now,
		AvailableAt:     now,
		Status:          IntentStatusPending,
	}

	candidates, _, err := loader.LoadWorkloadProjectionInputs(context.Background(), intent)
	if err != nil {
		t.Fatalf("LoadWorkloadProjectionInputs() error = %v", err)
	}
	if len(candidates) != 0 {
		t.Fatalf("len(candidates) = %d, want 0 for Dockerfile-only evidence", len(candidates))
	}
}

func TestCorrelatedWorkloadProjectionInputLoaderAdmitsResolvedDeploymentEvidence(t *testing.T) {
	t.Parallel()

	now := time.Now().UTC()
	loader := CorrelatedWorkloadProjectionInputLoader{
		FactLoader: &stubFactLoader{
			envelopes: []facts.Envelope{
				{
					FactID:   "fact-repo-1",
					ScopeID:  "scope-service",
					FactKind: "repository",
					Payload: map[string]any{
						"graph_id": "repo-service",
						"name":     "service-repo",
					},
					ObservedAt: now,
				},
				{
					FactID:   "fact-file-1",
					ScopeID:  "scope-service",
					FactKind: "file",
					Payload: map[string]any{
						"repo_id":       "repo-service",
						"language":      "dockerfile",
						"relative_path": "docker/api.Dockerfile",
						"parsed_file_data": map[string]any{
							"dockerfile_stages": []any{map[string]any{"name": "runtime"}},
						},
					},
					ObservedAt: now,
				},
			},
		},
		ResolvedLoader: &stubResolvedRelationshipLoader{
			resolved: []relationships.ResolvedRelationship{
				{
					SourceRepoID:     "repo-delivery",
					TargetRepoID:     "repo-service",
					RelationshipType: relationships.RelDeploysFrom,
					Confidence:       0.96,
					Details: map[string]any{
						"evidence_kinds": []any{string(relationships.EvidenceKindKustomizeResource)},
					},
				},
			},
		},
	}

	intent := Intent{
		IntentID:        "intent-correlation-2",
		ScopeID:         "scope-service",
		GenerationID:    "gen-1",
		SourceSystem:    "git",
		Domain:          DomainWorkloadMaterialization,
		Cause:           "test",
		EntityKeys:      []string{"repo-service"},
		RelatedScopeIDs: []string{"scope-service"},
		EnqueuedAt:      now,
		AvailableAt:     now,
		Status:          IntentStatusPending,
	}

	candidates, _, err := loader.LoadWorkloadProjectionInputs(context.Background(), intent)
	if err != nil {
		t.Fatalf("LoadWorkloadProjectionInputs() error = %v", err)
	}
	if len(candidates) != 1 {
		t.Fatalf("len(candidates) = %d, want 1", len(candidates))
	}
	if got, want := candidates[0].DeploymentRepoID, "repo-delivery"; got != want {
		t.Fatalf("DeploymentRepoID = %q, want %q", got, want)
	}
	if got, want := candidates[0].WorkloadName, "api"; got != want {
		t.Fatalf("WorkloadName = %q, want %q", got, want)
	}
	if got, want := candidates[0].Confidence, 0.96; got != want {
		t.Fatalf("Confidence = %v, want %v", got, want)
	}
}

func TestCorrelatedWorkloadProjectionInputLoaderEnrichesDeploymentRepoEnvironments(t *testing.T) {
	t.Parallel()

	now := time.Now().UTC()

	// Source repo: has a K8s Deployment (passes admission at 0.98 confidence)
	// but no overlay directories → no environments from source facts.
	sourceEnvelopes := []facts.Envelope{
		{
			FactID: "fact-repo", ScopeID: "scope-app", FactKind: "repository",
			Payload:    map[string]any{"graph_id": "repo-app", "name": "my-service"},
			ObservedAt: now,
		},
		{
			FactID: "fact-file-k8s", ScopeID: "scope-app", FactKind: "file",
			Payload: map[string]any{
				"repo_id": "repo-app", "language": "yaml",
				"relative_path": "k8s/deployment.yaml",
				"parsed_file_data": map[string]any{
					"k8s_resources": []any{
						map[string]any{"kind": "Deployment", "namespace": ""},
					},
				},
			},
			ObservedAt: now,
		},
	}

	// Deployment repo: has overlay environments in overlays/ directories.
	deployEnvelopes := []facts.Envelope{
		{
			FactID: "fact-deploy-repo", ScopeID: "scope-deploy", FactKind: "repository",
			Payload:    map[string]any{"graph_id": "repo-deploy", "name": "helm-charts"},
			ObservedAt: now,
		},
		{
			FactID: "fact-deploy-overlay-qa", ScopeID: "scope-deploy", FactKind: "file",
			Payload: map[string]any{
				"repo_id": "repo-deploy", "language": "yaml",
				"relative_path":   "apps/my-service/overlays/bg-qa/kustomization.yaml",
				"parsed_file_data": map[string]any{},
			},
			ObservedAt: now,
		},
		{
			FactID: "fact-deploy-overlay-prod", ScopeID: "scope-deploy", FactKind: "file",
			Payload: map[string]any{
				"repo_id": "repo-deploy", "language": "yaml",
				"relative_path":   "apps/my-service/overlays/production/kustomization.yaml",
				"parsed_file_data": map[string]any{},
			},
			ObservedAt: now,
		},
	}

	loader := CorrelatedWorkloadProjectionInputLoader{
		FactLoader: &scopedFactLoader{
			envelopesByScope: map[string][]facts.Envelope{
				"scope-app":    sourceEnvelopes,
				"scope-deploy": deployEnvelopes,
			},
		},
		ResolvedLoader: &stubResolvedRelationshipLoader{
			resolved: []relationships.ResolvedRelationship{
				{
					SourceRepoID:     "repo-deploy",
					TargetRepoID:     "repo-app",
					RelationshipType: relationships.RelDeploysFrom,
					Confidence:       0.96,
					Details: map[string]any{
						"evidence_kinds": []any{string(relationships.EvidenceKindKustomizeResource)},
					},
				},
			},
		},
		ScopeResolver: &stubScopeResolver{
			generations: map[string]RepoScopeIdentity{
				"repo-deploy": {ScopeID: "scope-deploy", GenerationID: "gen-deploy-1"},
			},
		},
	}

	intent := Intent{
		IntentID:        "intent-cross-repo-env",
		ScopeID:         "scope-app",
		GenerationID:    "gen-1",
		SourceSystem:    "git",
		Domain:          DomainWorkloadMaterialization,
		Cause:           "replay after cross-repo resolution",
		EntityKeys:      []string{"repo-app"},
		RelatedScopeIDs: []string{"scope-app"},
		EnqueuedAt:      now,
		AvailableAt:     now,
		Status:          IntentStatusPending,
	}

	candidates, deploymentEnvs, err := loader.LoadWorkloadProjectionInputs(context.Background(), intent)
	if err != nil {
		t.Fatalf("LoadWorkloadProjectionInputs() error = %v", err)
	}

	if len(candidates) != 1 {
		t.Fatalf("len(candidates) = %d, want 1", len(candidates))
	}
	if got, want := candidates[0].DeploymentRepoID, "repo-deploy"; got != want {
		t.Fatalf("DeploymentRepoID = %q, want %q", got, want)
	}

	// Critical assertion: deployment repo overlay environments must be populated.
	envs := deploymentEnvs["repo-deploy"]
	if len(envs) != 2 {
		t.Fatalf("deploymentEnvs[repo-deploy] = %v, want 2 environments (bg-qa, production)", envs)
	}
	if envs[0] != "bg-qa" || envs[1] != "production" {
		t.Fatalf("deploymentEnvs[repo-deploy] = %v, want [bg-qa production]", envs)
	}
}

func TestCorrelatedWorkloadProjectionInputLoaderSkipsCrossRepoWhenResolverNil(t *testing.T) {
	t.Parallel()

	now := time.Now().UTC()

	// Source repo with K8s signal but no overlays. Deployment repo linked via
	// resolved relationship, but ScopeResolver is nil → no cross-repo env loading.
	loader := CorrelatedWorkloadProjectionInputLoader{
		FactLoader: &stubFactLoader{
			envelopes: []facts.Envelope{
				{
					FactID: "fact-repo", ScopeID: "scope-app", FactKind: "repository",
					Payload:    map[string]any{"graph_id": "repo-app", "name": "my-service"},
					ObservedAt: now,
				},
				{
					FactID: "fact-file-k8s", ScopeID: "scope-app", FactKind: "file",
					Payload: map[string]any{
						"repo_id": "repo-app", "language": "yaml",
						"relative_path": "k8s/deployment.yaml",
						"parsed_file_data": map[string]any{
							"k8s_resources": []any{
								map[string]any{"kind": "Deployment", "namespace": ""},
							},
						},
					},
					ObservedAt: now,
				},
			},
		},
		ResolvedLoader: &stubResolvedRelationshipLoader{
			resolved: []relationships.ResolvedRelationship{
				{
					SourceRepoID:     "repo-deploy",
					TargetRepoID:     "repo-app",
					RelationshipType: relationships.RelDeploysFrom,
					Confidence:       0.96,
					Details: map[string]any{
						"evidence_kinds": []any{string(relationships.EvidenceKindKustomizeResource)},
					},
				},
			},
		},
		// ScopeResolver intentionally nil.
	}

	intent := Intent{
		IntentID:        "intent-no-resolver",
		ScopeID:         "scope-app",
		GenerationID:    "gen-1",
		SourceSystem:    "git",
		Domain:          DomainWorkloadMaterialization,
		Cause:           "test",
		EntityKeys:      []string{"repo-app"},
		RelatedScopeIDs: []string{"scope-app"},
		EnqueuedAt:      now,
		AvailableAt:     now,
		Status:          IntentStatusPending,
	}

	candidates, deploymentEnvs, err := loader.LoadWorkloadProjectionInputs(context.Background(), intent)
	if err != nil {
		t.Fatalf("LoadWorkloadProjectionInputs() error = %v", err)
	}
	if len(candidates) != 1 {
		t.Fatalf("len(candidates) = %d, want 1", len(candidates))
	}

	// Without ScopeResolver, deployment repo envs should be empty.
	if envs := deploymentEnvs["repo-deploy"]; len(envs) != 0 {
		t.Fatalf("deploymentEnvs[repo-deploy] = %v, want empty (no ScopeResolver)", envs)
	}
}

func TestCorrelatedWorkloadProjectionInputLoaderSkipsSameRepoDeployment(t *testing.T) {
	t.Parallel()

	now := time.Now().UTC()

	// Source repo that also has its own overlays. DeploymentRepoID == RepoID.
	// Environments should come from source facts, not trigger a cross-repo load.
	sourceEnvelopes := []facts.Envelope{
		{
			FactID: "fact-repo", ScopeID: "scope-app", FactKind: "repository",
			Payload:    map[string]any{"graph_id": "repo-self-deploy", "name": "self-deploy-svc"},
			ObservedAt: now,
		},
		{
			FactID: "fact-file-k8s", ScopeID: "scope-app", FactKind: "file",
			Payload: map[string]any{
				"repo_id": "repo-self-deploy", "language": "yaml",
				"relative_path": "k8s/deployment.yaml",
				"parsed_file_data": map[string]any{
					"k8s_resources": []any{
						map[string]any{"kind": "Deployment", "namespace": ""},
					},
				},
			},
			ObservedAt: now,
		},
		{
			FactID: "fact-file-overlay", ScopeID: "scope-app", FactKind: "file",
			Payload: map[string]any{
				"repo_id": "repo-self-deploy", "language": "yaml",
				"relative_path":   "overlays/staging/kustomization.yaml",
				"parsed_file_data": map[string]any{},
			},
			ObservedAt: now,
		},
	}

	resolver := &stubScopeResolver{calls: 0}
	loader := CorrelatedWorkloadProjectionInputLoader{
		FactLoader:    &stubFactLoader{envelopes: sourceEnvelopes},
		ScopeResolver: resolver,
	}

	intent := Intent{
		IntentID:        "intent-self-deploy",
		ScopeID:         "scope-app",
		GenerationID:    "gen-1",
		SourceSystem:    "git",
		Domain:          DomainWorkloadMaterialization,
		Cause:           "test",
		EntityKeys:      []string{"repo-self-deploy"},
		RelatedScopeIDs: []string{"scope-app"},
		EnqueuedAt:      now,
		AvailableAt:     now,
		Status:          IntentStatusPending,
	}

	candidates, deploymentEnvs, err := loader.LoadWorkloadProjectionInputs(context.Background(), intent)
	if err != nil {
		t.Fatalf("LoadWorkloadProjectionInputs() error = %v", err)
	}
	if len(candidates) != 1 {
		t.Fatalf("len(candidates) = %d, want 1", len(candidates))
	}

	// Source repo's own overlays should be present.
	if envs := deploymentEnvs["repo-self-deploy"]; len(envs) != 1 || envs[0] != "staging" {
		t.Fatalf("deploymentEnvs[repo-self-deploy] = %v, want [staging]", envs)
	}

	// ScopeResolver should NOT be called for same-repo deployment.
	if resolver.calls != 0 {
		t.Fatalf("ScopeResolver.calls = %d, want 0 (no cross-repo lookup for same repo)", resolver.calls)
	}
}

// -- test fakes for cross-repo loading --

type scopedFactLoader struct {
	envelopesByScope map[string][]facts.Envelope
	calls            int
}

func (f *scopedFactLoader) ListFacts(_ context.Context, scopeID, _ string) ([]facts.Envelope, error) {
	f.calls++
	envelopes, ok := f.envelopesByScope[scopeID]
	if !ok {
		return nil, fmt.Errorf("no envelopes for scope %q", scopeID)
	}
	return envelopes, nil
}

type stubScopeResolver struct {
	generations map[string]RepoScopeIdentity
	calls       int
}

func (r *stubScopeResolver) ResolveRepoActiveGenerations(
	_ context.Context,
	repoIDs []string,
) (map[string]RepoScopeIdentity, error) {
	r.calls++
	result := make(map[string]RepoScopeIdentity)
	for _, id := range repoIDs {
		if identity, ok := r.generations[id]; ok {
			result[id] = identity
		}
	}
	return result, nil
}
