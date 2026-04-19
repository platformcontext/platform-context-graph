package reducer

import (
	"context"
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
