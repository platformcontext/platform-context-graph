package query

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestGetRepositoryContextIncludesGraphDeploymentEvidence(t *testing.T) {
	t.Parallel()

	handler := &RepositoryHandler{
		Neo4j: fakeRepoGraphReader{
			runSingleByMatch: map[string]map[string]any{
				"INSTANCE_OF": {
					"id":               "repo-service",
					"name":             "checkout-service",
					"path":             "/repos/checkout-service",
					"local_path":       "/repos/checkout-service",
					"remote_url":       "https://github.com/acme/checkout-service",
					"repo_slug":        "acme/checkout-service",
					"has_remote":       true,
					"file_count":       int64(42),
					"workload_count":   int64(1),
					"platform_count":   int64(2),
					"dependency_count": int64(3),
				},
			},
			runByMatch: map[string][]map[string]any{
				"EVIDENCES_REPOSITORY_RELATIONSHIP]->(r:Repository": {
					{
						"direction":             "incoming",
						"artifact_id":           "evidence-artifact:helm:1",
						"name":                  "HELM_VALUES_REFERENCE:charts/checkout/values-prod.yaml",
						"domain":                "deployment",
						"path":                  "charts/checkout/values-prod.yaml",
						"evidence_kind":         "HELM_VALUES_REFERENCE",
						"artifact_family":       "helm",
						"extractor":             "helm",
						"relationship_type":     "DEPLOYS_FROM",
						"resolved_id":           "resolved-1",
						"generation_id":         "gen-1",
						"confidence":            0.91,
						"environment":           "prod",
						"runtime_platform_kind": "kubernetes",
						"matched_alias":         "checkout-service",
						"matched_value":         "registry.example.test/checkout-service",
						"evidence_source":       "resolver/cross-repo",
						"source_repo_id":        "repo-deploy",
						"source_repo_name":      "platform-deployments",
						"target_repo_id":        "repo-service",
						"target_repo_name":      "checkout-service",
					},
				},
				"(r:Repository {id: $repo_id})-[source_rel:HAS_DEPLOYMENT_EVIDENCE]->": {
					{
						"direction":         "outgoing",
						"artifact_id":       "evidence-artifact:gha:1",
						"name":              "GITHUB_ACTIONS_REUSABLE_WORKFLOW_REF:.github/workflows/deploy.yaml",
						"domain":            "deployment",
						"path":              ".github/workflows/deploy.yaml",
						"evidence_kind":     "GITHUB_ACTIONS_REUSABLE_WORKFLOW_REF",
						"artifact_family":   "github_actions",
						"extractor":         "github_actions",
						"relationship_type": "DEPLOYS_FROM",
						"resolved_id":       "resolved-2",
						"generation_id":     "gen-1",
						"confidence":        0.82,
						"matched_alias":     "deploy.yaml",
						"matched_value":     ".github/workflows/deploy.yaml",
						"evidence_source":   "resolver/cross-repo",
						"source_repo_id":    "repo-service",
						"source_repo_name":  "checkout-service",
						"target_repo_id":    "repo-workflows",
						"target_repo_name":  "shared-workflows",
					},
				},
			},
		},
	}

	mux := http.NewServeMux()
	handler.Mount(mux)

	req := httptest.NewRequest(http.MethodGet, "/api/v0/repositories/repo-service/context", nil)
	req.SetPathValue("repo_id", "repo-service")
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if got, want := w.Code, http.StatusOK; got != want {
		t.Fatalf("status = %d, want %d; body = %s", got, want, w.Body.String())
	}

	var resp map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("json.Unmarshal() error = %v", err)
	}

	surface, ok := resp["deployment_evidence"].(map[string]any)
	if !ok {
		t.Fatalf("deployment_evidence type = %T, want map[string]any", resp["deployment_evidence"])
	}
	if got, want := surface["truth_basis"], "graph"; got != want {
		t.Fatalf("deployment_evidence.truth_basis = %#v, want %#v", got, want)
	}
	if got, want := surface["artifact_count"], float64(2); got != want {
		t.Fatalf("deployment_evidence.artifact_count = %#v, want %#v", got, want)
	}

	for _, want := range []string{"helm", "github_actions"} {
		if !containsStringAny(surface["artifact_families"].([]any), want) {
			t.Fatalf("artifact_families missing %q: %#v", want, surface["artifact_families"])
		}
	}
	for _, want := range []string{"HELM_VALUES_REFERENCE", "GITHUB_ACTIONS_REUSABLE_WORKFLOW_REF"} {
		if !containsStringAny(surface["evidence_kinds"].([]any), want) {
			t.Fatalf("evidence_kinds missing %q: %#v", want, surface["evidence_kinds"])
		}
	}
	if !containsStringAny(surface["environments"].([]any), "prod") {
		t.Fatalf("environments missing prod: %#v", surface["environments"])
	}

	artifacts, ok := surface["artifacts"].([]any)
	if !ok || len(artifacts) != 2 {
		t.Fatalf("deployment_evidence.artifacts = %#v, want two artifacts", surface["artifacts"])
	}
	first, ok := artifacts[0].(map[string]any)
	if !ok {
		t.Fatalf("deployment_evidence.artifacts[0] type = %T, want map[string]any", artifacts[0])
	}
	for key, want := range map[string]any{
		"id":                    "evidence-artifact:gha:1",
		"direction":             "outgoing",
		"artifact_family":       "github_actions",
		"relationship_type":     "DEPLOYS_FROM",
		"resolved_id":           "resolved-2",
		"generation_id":         "gen-1",
		"source_repo_id":        "repo-service",
		"target_repo_id":        "repo-workflows",
		"postgres_lookup_basis": "resolved_id",
	} {
		if got := first[key]; got != want {
			t.Fatalf("artifact[0].%s = %#v, want %#v; artifact=%#v", key, got, want, first)
		}
	}
}

func TestQueryRepoDeploymentEvidenceIncomingUsesArtifactFirstBoundary(t *testing.T) {
	t.Parallel()

	reader := &recordingDeploymentEvidenceGraphReader{}
	queryRepoDeploymentEvidence(context.Background(), reader, map[string]any{"repo_id": "repo-service"})

	if len(reader.cypherCalls) != 2 {
		t.Fatalf("len(cypherCalls) = %d, want 2", len(reader.cypherCalls))
	}
	incoming := reader.cypherCalls[1]
	for _, want := range []string{
		"MATCH (artifact:EvidenceArtifact)-[:EVIDENCES_REPOSITORY_RELATIONSHIP]->(r:Repository {id: $repo_id})",
		"WITH artifact, r",
		"MATCH (source:Repository)-[:HAS_DEPLOYMENT_EVIDENCE]->(artifact)",
	} {
		if !strings.Contains(incoming, want) {
			t.Fatalf("incoming query missing %q:\n%s", want, incoming)
		}
	}
	oldShape := "MATCH (source:Repository)-[:HAS_DEPLOYMENT_EVIDENCE]->(artifact:EvidenceArtifact)-[:EVIDENCES_REPOSITORY_RELATIONSHIP]->(r:Repository {id: $repo_id})"
	if strings.Contains(incoming, oldShape) {
		t.Fatalf("incoming query still uses source-first NornicDB-slow shape:\n%s", incoming)
	}
}

type recordingDeploymentEvidenceGraphReader struct {
	cypherCalls []string
}

func (r *recordingDeploymentEvidenceGraphReader) Run(_ context.Context, cypher string, _ map[string]any) ([]map[string]any, error) {
	r.cypherCalls = append(r.cypherCalls, cypher)
	return nil, nil
}

func (r *recordingDeploymentEvidenceGraphReader) RunSingle(context.Context, string, map[string]any) (map[string]any, error) {
	return nil, nil
}
