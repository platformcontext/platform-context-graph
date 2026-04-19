package reducer

import (
	"context"
	"fmt"
	"strings"
	"testing"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/facts"
	"github.com/platformcontext/platform-context-graph/go/internal/relationships"
)

type stubDeployableUnitFactLoader struct {
	envelopes []facts.Envelope
	err       error
	calls     int
}

func (f *stubDeployableUnitFactLoader) ListFacts(
	_ context.Context,
	_,
	_ string,
) ([]facts.Envelope, error) {
	f.calls++
	if f.err != nil {
		return nil, f.err
	}
	return f.envelopes, nil
}

type stubDeployableUnitResolvedLoader struct {
	resolved []relationships.ResolvedRelationship
	err      error
	calls    int
}

func (f *stubDeployableUnitResolvedLoader) GetResolvedRelationships(
	_ context.Context,
	_ string,
) ([]relationships.ResolvedRelationship, error) {
	f.calls++
	if f.err != nil {
		return nil, f.err
	}
	return f.resolved, nil
}

func TestDeployableUnitCorrelationHandleRejectsWrongDomain(t *testing.T) {
	t.Parallel()

	handler := DeployableUnitCorrelationHandler{
		FactLoader: &stubDeployableUnitFactLoader{},
	}

	_, err := handler.Handle(context.Background(), Intent{
		IntentID:        "intent-1",
		ScopeID:         "repository:service-gha",
		GenerationID:    "generation-1",
		SourceSystem:    "git",
		Domain:          DomainDeploymentMapping,
		Cause:           "facts committed",
		EntityKeys:      []string{"service-gha"},
		RelatedScopeIDs: []string{"repository:deploy-repo"},
	})
	if err == nil {
		t.Fatal("Handle() error = nil, want non-nil")
	}
}

func TestDeployableUnitCorrelationHandleRequiresFactLoader(t *testing.T) {
	t.Parallel()

	handler := DeployableUnitCorrelationHandler{}

	_, err := handler.Handle(context.Background(), Intent{
		IntentID:        "intent-1",
		ScopeID:         "repository:service-gha",
		GenerationID:    "generation-1",
		SourceSystem:    "git",
		Domain:          DomainDeployableUnitCorrelation,
		Cause:           "facts committed",
		EntityKeys:      []string{"service-gha"},
		RelatedScopeIDs: []string{"repository:deploy-repo"},
	})
	if err == nil {
		t.Fatal("Handle() error = nil, want non-nil")
	}
}

func TestDeployableUnitCorrelationHandleRequiresEntityKeys(t *testing.T) {
	t.Parallel()

	handler := DeployableUnitCorrelationHandler{
		FactLoader: &stubDeployableUnitFactLoader{},
	}

	_, err := handler.Handle(context.Background(), Intent{
		IntentID:        "intent-1",
		ScopeID:         "repository:service-gha",
		GenerationID:    "generation-1",
		SourceSystem:    "git",
		Domain:          DomainDeployableUnitCorrelation,
		Cause:           "facts committed",
		RelatedScopeIDs: []string{"repository:deploy-repo"},
	})
	if err == nil {
		t.Fatal("Handle() error = nil, want non-nil")
	}
}

func TestDeployableUnitCorrelationHandleReturnsNoCandidates(t *testing.T) {
	t.Parallel()

	handler := DeployableUnitCorrelationHandler{
		FactLoader: &stubDeployableUnitFactLoader{
			envelopes: deployableUnitCorrelationEnvelopes(
				"repo-docs",
				"documentation",
				nil,
			),
		},
	}

	got, err := handler.Handle(context.Background(), deployableUnitIntent("documentation"))
	if err != nil {
		t.Fatalf("Handle() error = %v, want nil", err)
	}
	if got.Status != ResultStatusSucceeded {
		t.Fatalf("Handle().Status = %q, want %q", got.Status, ResultStatusSucceeded)
	}
	if got.EvidenceSummary != "no deployable unit candidates found" {
		t.Fatalf("Handle().EvidenceSummary = %q, want no-candidates summary", got.EvidenceSummary)
	}
}

func TestDeployableUnitCorrelationHandleAdmitsDockerfileOnlyCandidate(t *testing.T) {
	t.Parallel()

	handler := DeployableUnitCorrelationHandler{
		FactLoader: &stubDeployableUnitFactLoader{
			envelopes: deployableUnitCorrelationEnvelopes(
				"repo-edge-api",
				"edge-api",
				[]map[string]any{
					{
						"repo_id":       "repo-edge-api",
						"language":      "dockerfile",
						"relative_path": "Dockerfile",
						"parsed_file_data": map[string]any{
							"dockerfile_stages": []any{
								map[string]any{"name": "runtime"},
							},
						},
					},
				},
			),
		},
	}

	got, err := handler.Handle(context.Background(), deployableUnitIntent("edge-api"))
	if err != nil {
		t.Fatalf("Handle() error = %v, want nil", err)
	}
	if !strings.Contains(got.EvidenceSummary, "admitted=1") {
		t.Fatalf("Handle().EvidenceSummary = %q, want admitted=1", got.EvidenceSummary)
	}
	if !strings.Contains(got.EvidenceSummary, "rejected=0") {
		t.Fatalf("Handle().EvidenceSummary = %q, want rejected=0", got.EvidenceSummary)
	}
}

func TestDeployableUnitCorrelationHandleAdmitsResolvedDeploymentEvidence(t *testing.T) {
	t.Parallel()

	factLoader := &stubDeployableUnitFactLoader{
		envelopes: deployableUnitCorrelationEnvelopes(
			"repo-edge-api",
			"edge-api",
			[]map[string]any{
				{
					"repo_id":       "repo-edge-api",
					"language":      "dockerfile",
					"relative_path": "Dockerfile",
					"parsed_file_data": map[string]any{
						"dockerfile_stages": []any{
							map[string]any{"name": "runtime"},
						},
					},
				},
			},
		),
	}
	resolvedLoader := &stubDeployableUnitResolvedLoader{
		resolved: []relationships.ResolvedRelationship{
			{
				SourceRepoID:     "repo-edge-api",
				TargetRepoID:     "repo-deployments",
				RelationshipType: relationships.RelDeploysFrom,
				Confidence:       0.94,
				Details: map[string]any{
					"evidence_kinds": []string{
						string(relationships.EvidenceKindArgoCDAppSource),
					},
				},
			},
		},
	}

	handler := DeployableUnitCorrelationHandler{
		FactLoader:     factLoader,
		ResolvedLoader: resolvedLoader,
	}

	got, err := handler.Handle(context.Background(), deployableUnitIntent("edge-api"))
	if err != nil {
		t.Fatalf("Handle() error = %v, want nil", err)
	}
	if factLoader.calls != 1 {
		t.Fatalf("FactLoader calls = %d, want 1", factLoader.calls)
	}
	if resolvedLoader.calls != 1 {
		t.Fatalf("ResolvedLoader calls = %d, want 1", resolvedLoader.calls)
	}
	if !strings.Contains(got.EvidenceSummary, "admitted=1") {
		t.Fatalf("Handle().EvidenceSummary = %q, want admitted=1", got.EvidenceSummary)
	}
	if !strings.Contains(got.EvidenceSummary, "rejected=0") {
		t.Fatalf("Handle().EvidenceSummary = %q, want rejected=0", got.EvidenceSummary)
	}
}

func TestDeployableUnitCorrelationHandleFiltersByEntityKeys(t *testing.T) {
	t.Parallel()

	handler := DeployableUnitCorrelationHandler{
		FactLoader: &stubDeployableUnitFactLoader{
			envelopes: append(
				deployableUnitCorrelationEnvelopes(
					"repo-edge-api",
					"edge-api",
					[]map[string]any{
						{
							"repo_id":       "repo-edge-api",
							"language":      "dockerfile",
							"relative_path": "Dockerfile",
							"parsed_file_data": map[string]any{
								"dockerfile_stages": []any{
									map[string]any{"name": "runtime"},
								},
							},
						},
					},
				),
				deployableUnitCorrelationEnvelopes(
					"repo-worker",
					"background-worker",
					[]map[string]any{
						{
							"repo_id": "repo-worker",
							"parsed_file_data": map[string]any{
								"argocd_applications": []any{
									map[string]any{"name": "background-worker"},
								},
							},
						},
					},
				)...,
			),
		},
	}

	got, err := handler.Handle(context.Background(), deployableUnitIntent("edge-api"))
	if err != nil {
		t.Fatalf("Handle() error = %v, want nil", err)
	}
	if !strings.Contains(got.EvidenceSummary, "evaluated 1 deployable unit candidate") {
		t.Fatalf("Handle().EvidenceSummary = %q, want one evaluated candidate", got.EvidenceSummary)
	}
}

func TestDeployableUnitCorrelationHandleSplitsMultipleDockerfilesConservatively(t *testing.T) {
	t.Parallel()

	handler := DeployableUnitCorrelationHandler{
		FactLoader: &stubDeployableUnitFactLoader{
			envelopes: deployableUnitCorrelationEnvelopes(
				"repo-monolith",
				"monolith",
				[]map[string]any{
					{
						"repo_id":       "repo-monolith",
						"language":      "dockerfile",
						"relative_path": "docker/api.Dockerfile",
						"parsed_file_data": map[string]any{
							"dockerfile_stages": []any{
								map[string]any{"name": "runtime"},
							},
						},
					},
					{
						"repo_id":       "repo-monolith",
						"language":      "dockerfile",
						"relative_path": "docker/worker.Dockerfile",
						"parsed_file_data": map[string]any{
							"dockerfile_stages": []any{
								map[string]any{"name": "runtime"},
							},
						},
					},
				},
			),
		},
		ResolvedLoader: &stubDeployableUnitResolvedLoader{
			resolved: []relationships.ResolvedRelationship{
				{
					SourceRepoID:     "repo-monolith",
					TargetRepoID:     "repo-deployments",
					RelationshipType: relationships.RelDeploysFrom,
					Confidence:       0.94,
					Details: map[string]any{
						"evidence_kinds": []string{
							string(relationships.EvidenceKindArgoCDAppSource),
						},
					},
				},
			},
		},
	}

	got, err := handler.Handle(context.Background(), deployableUnitIntent("monolith"))
	if err != nil {
		t.Fatalf("Handle() error = %v, want nil", err)
	}
	if !strings.Contains(got.EvidenceSummary, "evaluated 2 deployable unit candidate") {
		t.Fatalf("Handle().EvidenceSummary = %q, want two evaluated candidates", got.EvidenceSummary)
	}
	if !strings.Contains(got.EvidenceSummary, "admitted=0") {
		t.Fatalf("Handle().EvidenceSummary = %q, want admitted=0 for ambiguous repo-level deploy evidence", got.EvidenceSummary)
	}
	if !strings.Contains(got.EvidenceSummary, "rejected=2") {
		t.Fatalf("Handle().EvidenceSummary = %q, want rejected=2", got.EvidenceSummary)
	}
}

func TestDeployableUnitCorrelationHandleFactLoaderError(t *testing.T) {
	t.Parallel()

	handler := DeployableUnitCorrelationHandler{
		FactLoader: &stubDeployableUnitFactLoader{err: fmt.Errorf("facts unavailable")},
	}

	_, err := handler.Handle(context.Background(), deployableUnitIntent("edge-api"))
	if err == nil {
		t.Fatal("Handle() error = nil, want non-nil")
	}
}

func deployableUnitIntent(entityKeys ...string) Intent {
	return Intent{
		IntentID:        "intent-1",
		ScopeID:         "repository:test-scope",
		GenerationID:    "generation-1",
		SourceSystem:    "git",
		Domain:          DomainDeployableUnitCorrelation,
		Cause:           "facts committed",
		EntityKeys:      entityKeys,
		RelatedScopeIDs: []string{"repository:deploy-repo"},
	}
}

func deployableUnitCorrelationEnvelopes(
	repoID string,
	repoName string,
	filePayloads []map[string]any,
) []facts.Envelope {
	now := time.Now().UTC()
	envelopes := []facts.Envelope{
		{
			FactID:   "fact-repo-" + repoID,
			FactKind: "repository",
			Payload: map[string]any{
				"graph_id": repoID,
				"name":     repoName,
			},
			ObservedAt: now,
		},
	}

	for idx, payload := range filePayloads {
		envelopes = append(envelopes, facts.Envelope{
			FactID:     fmt.Sprintf("fact-file-%s-%d", repoID, idx),
			FactKind:   "file",
			Payload:    payload,
			ObservedAt: now,
		})
	}

	return envelopes
}
