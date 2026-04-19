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

func TestWorkloadMaterializationHandlerMaterializesFromFacts(t *testing.T) {
	t.Parallel()

	now := time.Now().UTC()
	loader := &stubFactLoader{
		envelopes: []facts.Envelope{
			{
				FactID:   "fact-repo",
				FactKind: "repository",
				Payload: map[string]any{
					"graph_id": "repo-payments",
					"name":     "payments",
				},
				ObservedAt: now,
			},
			{
				FactID:   "fact-file",
				FactKind: "file",
				Payload: map[string]any{
					"repo_id": "repo-payments",
					"parsed_file_data": map[string]any{
						"k8s_resources": []any{
							map[string]any{
								"name":      "payments",
								"kind":      "Deployment",
								"namespace": "production",
							},
						},
					},
				},
				ObservedAt: now,
			},
		},
	}

	executor := &recordingCypherExecutor{}
	materializer := NewWorkloadMaterializer(executor)

	handler := WorkloadMaterializationHandler{
		FactLoader:   loader,
		Materializer: materializer,
	}

	intent := Intent{
		IntentID:        "intent-wm-1",
		ScopeID:         "scope-payments",
		GenerationID:    "gen-1",
		SourceSystem:    "git",
		Domain:          DomainWorkloadMaterialization,
		Cause:           "facts projected",
		EntityKeys:      []string{"repo-payments"},
		RelatedScopeIDs: []string{"scope-payments"},
		EnqueuedAt:      now,
		AvailableAt:     now,
		Status:          IntentStatusPending,
	}

	result, err := handler.Handle(context.Background(), intent)
	if err != nil {
		t.Fatalf("Handle() error = %v", err)
	}
	if result.Status != ResultStatusSucceeded {
		t.Fatalf("Status = %q, want succeeded", result.Status)
	}
	if result.CanonicalWrites == 0 {
		t.Fatal("CanonicalWrites = 0, want > 0")
	}
	if loader.calls != 1 {
		t.Fatalf("FactLoader.ListFacts calls = %d, want 1", loader.calls)
	}
	if len(executor.calls) == 0 {
		t.Fatal("CypherExecutor calls = 0, want > 0")
	}
}

func TestWorkloadMaterializationHandlerNoCandidatesSucceeds(t *testing.T) {
	t.Parallel()

	now := time.Now().UTC()
	loader := &stubFactLoader{
		envelopes: []facts.Envelope{
			{
				FactID:   "fact-repo",
				FactKind: "repository",
				Payload: map[string]any{
					"graph_id": "repo-docs",
					"name":     "docs",
				},
				ObservedAt: now,
			},
		},
	}

	handler := WorkloadMaterializationHandler{
		FactLoader:   loader,
		Materializer: NewWorkloadMaterializer(&recordingCypherExecutor{}),
	}

	intent := Intent{
		IntentID:        "intent-wm-2",
		ScopeID:         "scope-docs",
		GenerationID:    "gen-1",
		SourceSystem:    "git",
		Domain:          DomainWorkloadMaterialization,
		Cause:           "facts projected",
		EntityKeys:      []string{"repo-docs"},
		RelatedScopeIDs: []string{"scope-docs"},
		EnqueuedAt:      now,
		AvailableAt:     now,
		Status:          IntentStatusPending,
	}

	result, err := handler.Handle(context.Background(), intent)
	if err != nil {
		t.Fatalf("Handle() error = %v", err)
	}
	if result.Status != ResultStatusSucceeded {
		t.Fatalf("Status = %q, want succeeded", result.Status)
	}
	if result.CanonicalWrites != 0 {
		t.Fatalf("CanonicalWrites = %d, want 0 (no candidates)", result.CanonicalWrites)
	}
}

func TestWorkloadMaterializationHandlerUsesArgoDeploymentSourceRelationships(t *testing.T) {
	t.Parallel()

	now := time.Now().UTC()
	loader := &stubFactLoader{
		envelopes: []facts.Envelope{
			{
				FactID:   "fact-repo",
				FactKind: "repository",
				Payload: map[string]any{
					"graph_id": "repo-service-edge-api",
					"name":     "service-edge-api",
				},
				ObservedAt: now,
			},
			{
				FactID:   "fact-file",
				FactKind: "file",
				Payload: map[string]any{
					"repo_id": "repo-service-edge-api",
					"parsed_file_data": map[string]any{
						"k8s_resources": []any{
							map[string]any{
								"name":      "service-edge-api",
								"kind":      "Deployment",
								"namespace": "modern",
							},
						},
					},
				},
				ObservedAt: now,
			},
		},
	}
	relationshipLoader := &stubResolvedRelationshipLoader{
		resolved: []relationships.ResolvedRelationship{
			{
				SourceRepoID:     "repo-service-edge-api",
				TargetRepoID:     "repo-deployment-kustomize",
				RelationshipType: relationships.RelDeploysFrom,
				Details: map[string]any{
					"evidence_kinds": []any{
						string(relationships.EvidenceKindArgoCDApplicationSetDeploySource),
					},
				},
			},
		},
	}

	executor := &recordingCypherExecutor{}
	materializer := NewWorkloadMaterializer(executor)

	handler := WorkloadMaterializationHandler{
		FactLoader:     loader,
		ResolvedLoader: relationshipLoader,
		Materializer:   materializer,
	}

	intent := Intent{
		IntentID:        "intent-wm-deploy-source",
		ScopeID:         "scope-service-edge-api",
		GenerationID:    "gen-1",
		SourceSystem:    "git",
		Domain:          DomainWorkloadMaterialization,
		Cause:           "facts projected",
		EntityKeys:      []string{"repo-service-edge-api"},
		RelatedScopeIDs: []string{"scope-service-edge-api"},
		EnqueuedAt:      now,
		AvailableAt:     now,
		Status:          IntentStatusPending,
	}

	result, err := handler.Handle(context.Background(), intent)
	if err != nil {
		t.Fatalf("Handle() error = %v", err)
	}
	if result.CanonicalWrites == 0 {
		t.Fatal("CanonicalWrites = 0, want > 0")
	}
	if relationshipLoader.calls != 1 {
		t.Fatalf("ResolvedLoader.GetResolvedRelationships calls = %d, want 1", relationshipLoader.calls)
	}
	if !containsRecordedCypher(executor.calls, "MERGE (i)-[rel:DEPLOYMENT_SOURCE]->(deployment_repo)") {
		t.Fatal("missing DEPLOYMENT_SOURCE MERGE cypher")
	}
	if !recordedCallContainsParam(executor.calls, "deployment_repo_id", "repo-deployment-kustomize") {
		t.Fatal("missing deployment_repo_id row for repo-deployment-kustomize")
	}
}

func TestWorkloadMaterializationHandlerSeedsRuntimeCandidateFromArgoDeploymentSource(t *testing.T) {
	t.Parallel()

	now := time.Now().UTC()
	loader := &stubFactLoader{
		envelopes: []facts.Envelope{
			{
				FactID:   "fact-repo",
				FactKind: "repository",
				Payload: map[string]any{
					"graph_id": "repo-edge-api",
					"name":     "edge-api",
				},
				ObservedAt: now,
			},
			{
				FactID:   "fact-repo-deploy",
				FactKind: "repository",
				Payload: map[string]any{
					"graph_id": "repo-platform-deploy",
					"name":     "platform-deploy",
				},
				ObservedAt: now,
			},
			{
				FactID:   "fact-file",
				FactKind: "file",
				Payload: map[string]any{
					"repo_id":       "repo-edge-api",
					"artifact_type": "dockerfile",
					"relative_path": "Dockerfile",
					"parsed_file_data": map[string]any{
						"dockerfile_stages": []any{
							map[string]any{"name": "runtime"},
						},
					},
				},
				ObservedAt: now,
			},
			{
				FactID:   "fact-file-deploy",
				FactKind: "file",
				Payload: map[string]any{
					"repo_id":       "repo-platform-deploy",
					"artifact_type": "argocd",
					"relative_path": "overlays/production/application.yaml",
					"parsed_file_data": map[string]any{
						"argocd_applications": []any{
							map[string]any{"name": "edge-api"},
						},
					},
				},
				ObservedAt: now,
			},
		},
	}
	relationshipLoader := &stubResolvedRelationshipLoader{
		resolved: []relationships.ResolvedRelationship{
			{
				SourceRepoID:     "repo-edge-api",
				TargetRepoID:     "repo-platform-deploy",
				RelationshipType: relationships.RelDeploysFrom,
				Confidence:       0.96,
				Details: map[string]any{
					"evidence_kinds": []any{
						string(relationships.EvidenceKindArgoCDAppSource),
					},
				},
			},
		},
	}

	executor := &recordingCypherExecutor{}
	handler := WorkloadMaterializationHandler{
		FactLoader:     loader,
		ResolvedLoader: relationshipLoader,
		Materializer:   NewWorkloadMaterializer(executor),
	}

	candidates, deploymentEnvironments := ExtractWorkloadCandidates(loader.envelopes)
	if got, want := deploymentEnvironments["repo-platform-deploy"], []string{"production"}; len(got) != len(want) || got[0] != want[0] {
		t.Fatalf("deploymentEnvironments[repo-platform-deploy] = %v, want %v", got, want)
	}
	candidates = applyResolvedDeploymentSources(candidates, relationshipLoader.resolved)
	if got, want := candidates[0].DeploymentRepoID, "repo-platform-deploy"; got != want {
		t.Fatalf("candidates[0].DeploymentRepoID = %q, want %q", got, want)
	}
	projection := BuildProjectionRows(candidates, deploymentEnvironments)
	if got := len(projection.InstanceRows); got != 1 {
		t.Fatalf("len(projection.InstanceRows) = %d, want 1", got)
	}
	if got := len(projection.DeploymentSourceRows); got != 1 {
		t.Fatalf("len(projection.DeploymentSourceRows) = %d, want 1", got)
	}

	intent := Intent{
		IntentID:        "intent-wm-runtime-argo",
		ScopeID:         "scope-edge-api",
		GenerationID:    "gen-1",
		SourceSystem:    "git",
		Domain:          DomainWorkloadMaterialization,
		Cause:           "facts projected",
		EntityKeys:      []string{"repo-edge-api"},
		RelatedScopeIDs: []string{"scope-edge-api"},
		EnqueuedAt:      now,
		AvailableAt:     now,
		Status:          IntentStatusPending,
	}

	result, err := handler.Handle(context.Background(), intent)
	if err != nil {
		t.Fatalf("Handle() error = %v", err)
	}
	if got := result.CanonicalWrites; got == 0 {
		t.Fatal("CanonicalWrites = 0, want > 0")
	}
	if !recordedCallContainsParam(executor.calls, "deployment_repo_id", "repo-platform-deploy") {
		t.Fatalf("missing deployment_repo_id row for repo-platform-deploy; calls=%#v", executor.calls)
	}
	if !recordedCallContainsParam(executor.calls, "materialization_confidence", "0.96") {
		t.Fatal("missing materialization_confidence row for seeded runtime candidate")
	}
}

func TestWorkloadMaterializationHandlerSkipsUtilityOnlyCandidate(t *testing.T) {
	t.Parallel()

	now := time.Now().UTC()
	loader := &stubFactLoader{
		envelopes: []facts.Envelope{
			{
				FactID:   "fact-repo",
				FactKind: "repository",
				Payload: map[string]any{
					"graph_id": "repo-automation",
					"name":     "automation-shared",
				},
				ObservedAt: now,
			},
			{
				FactID:   "fact-file",
				FactKind: "file",
				Payload: map[string]any{
					"repo_id":       "repo-automation",
					"artifact_type": "groovy",
					"relative_path": "Jenkinsfile",
					"parsed_file_data": map[string]any{
						"jenkins_pipeline_calls": []any{"deployShared"},
					},
				},
				ObservedAt: now,
			},
		},
	}
	executor := &recordingCypherExecutor{}
	handler := WorkloadMaterializationHandler{
		FactLoader:   loader,
		Materializer: NewWorkloadMaterializer(executor),
	}

	intent := Intent{
		IntentID:        "intent-wm-utility",
		ScopeID:         "scope-automation",
		GenerationID:    "gen-1",
		SourceSystem:    "git",
		Domain:          DomainWorkloadMaterialization,
		Cause:           "facts projected",
		EntityKeys:      []string{"repo-automation"},
		RelatedScopeIDs: []string{"scope-automation"},
		EnqueuedAt:      now,
		AvailableAt:     now,
		Status:          IntentStatusPending,
	}

	result, err := handler.Handle(context.Background(), intent)
	if err != nil {
		t.Fatalf("Handle() error = %v", err)
	}
	if got := result.CanonicalWrites; got != 0 {
		t.Fatalf("CanonicalWrites = %d, want 0 for utility-only candidate", got)
	}
	if got := len(executor.calls); got != 0 {
		t.Fatalf("len(executor.calls) = %d, want 0", got)
	}
}

func TestWorkloadMaterializationHandlerRejectsMissingDomain(t *testing.T) {
	t.Parallel()

	handler := WorkloadMaterializationHandler{
		FactLoader:   &stubFactLoader{},
		Materializer: NewWorkloadMaterializer(&recordingCypherExecutor{}),
	}

	intent := Intent{
		IntentID:        "intent-wm-3",
		ScopeID:         "scope-1",
		GenerationID:    "gen-1",
		SourceSystem:    "git",
		Domain:          DomainWorkloadIdentity,
		Cause:           "wrong domain",
		EntityKeys:      []string{"repo-a"},
		RelatedScopeIDs: []string{"scope-1"},
		EnqueuedAt:      time.Now().UTC(),
		AvailableAt:     time.Now().UTC(),
		Status:          IntentStatusPending,
	}

	_, err := handler.Handle(context.Background(), intent)
	if err == nil {
		t.Fatal("Handle() expected error for wrong domain")
	}
}

func TestWorkloadMaterializationHandlerRequiresFactLoader(t *testing.T) {
	t.Parallel()

	handler := WorkloadMaterializationHandler{
		Materializer: NewWorkloadMaterializer(&recordingCypherExecutor{}),
	}

	intent := Intent{
		IntentID:        "intent-wm-4",
		ScopeID:         "scope-1",
		GenerationID:    "gen-1",
		SourceSystem:    "git",
		Domain:          DomainWorkloadMaterialization,
		Cause:           "test",
		EntityKeys:      []string{"repo-a"},
		RelatedScopeIDs: []string{"scope-1"},
		EnqueuedAt:      time.Now().UTC(),
		AvailableAt:     time.Now().UTC(),
		Status:          IntentStatusPending,
	}

	_, err := handler.Handle(context.Background(), intent)
	if err == nil {
		t.Fatal("Handle() expected error for missing FactLoader")
	}
}

// -- test fakes --

type stubFactLoader struct {
	envelopes []facts.Envelope
	calls     int
}

func (f *stubFactLoader) ListFacts(_ context.Context, _, _ string) ([]facts.Envelope, error) {
	f.calls++
	return f.envelopes, nil
}

type stubResolvedRelationshipLoader struct {
	resolved []relationships.ResolvedRelationship
	calls    int
}

func (f *stubResolvedRelationshipLoader) GetResolvedRelationships(
	_ context.Context,
	_ string,
) ([]relationships.ResolvedRelationship, error) {
	f.calls++
	return f.resolved, nil
}

type recordingCypherExecutor struct {
	calls []recordedCypherCall
}

type recordedCypherCall struct {
	cypher string
	params map[string]any
}

func (r *recordingCypherExecutor) ExecuteCypher(_ context.Context, cypher string, params map[string]any) error {
	r.calls = append(r.calls, recordedCypherCall{cypher: cypher, params: params})
	return nil
}

func TestWorkloadMaterializationHandlerFactLoaderError(t *testing.T) {
	t.Parallel()

	loader := &errorFactLoader{err: fmt.Errorf("db connection failed")}
	handler := WorkloadMaterializationHandler{
		FactLoader:   loader,
		Materializer: NewWorkloadMaterializer(&recordingCypherExecutor{}),
	}

	intent := Intent{
		IntentID:        "intent-wm-5",
		ScopeID:         "scope-1",
		GenerationID:    "gen-1",
		SourceSystem:    "git",
		Domain:          DomainWorkloadMaterialization,
		Cause:           "test",
		EntityKeys:      []string{"repo-a"},
		RelatedScopeIDs: []string{"scope-1"},
		EnqueuedAt:      time.Now().UTC(),
		AvailableAt:     time.Now().UTC(),
		Status:          IntentStatusPending,
	}

	_, err := handler.Handle(context.Background(), intent)
	if err == nil {
		t.Fatal("Handle() expected error from FactLoader")
	}
}

type errorFactLoader struct {
	err error
}

func (f *errorFactLoader) ListFacts(context.Context, string, string) ([]facts.Envelope, error) {
	return nil, f.err
}

func containsRecordedCypher(calls []recordedCypherCall, fragment string) bool {
	for _, call := range calls {
		if strings.Contains(call.cypher, fragment) {
			return true
		}
	}
	return false
}

func recordedCallContainsParam(calls []recordedCypherCall, key, want string) bool {
	for _, call := range calls {
		rows, ok := call.params["rows"].([]map[string]any)
		if !ok {
			continue
		}
		for _, row := range rows {
			if fmt.Sprint(row[key]) == want {
				return true
			}
		}
	}
	return false
}
