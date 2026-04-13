package reducer

import (
	"testing"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/facts"
)

func TestExtractWorkloadCandidatesFromK8sResourceFacts(t *testing.T) {
	t.Parallel()

	now := time.Now().UTC()
	envelopes := []facts.Envelope{
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
			FactID:   "fact-file-1",
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
	}

	candidates, _ := ExtractWorkloadCandidates(envelopes)
	if len(candidates) != 1 {
		t.Fatalf("len(candidates) = %d, want 1", len(candidates))
	}
	c := candidates[0]
	if c.RepoID != "repo-payments" {
		t.Errorf("RepoID = %q, want repo-payments", c.RepoID)
	}
	if c.RepoName != "payments" {
		t.Errorf("RepoName = %q, want payments", c.RepoName)
	}
	if len(c.ResourceKinds) != 1 || c.ResourceKinds[0] != "deployment" {
		t.Errorf("ResourceKinds = %v, want [deployment]", c.ResourceKinds)
	}
	if len(c.Namespaces) != 1 || c.Namespaces[0] != "production" {
		t.Errorf("Namespaces = %v, want [production]", c.Namespaces)
	}
}

func TestExtractWorkloadCandidatesFromArgoCDApplicationFacts(t *testing.T) {
	t.Parallel()

	now := time.Now().UTC()
	envelopes := []facts.Envelope{
		{
			FactID:   "fact-repo",
			FactKind: "repository",
			Payload: map[string]any{
				"graph_id": "repo-api",
				"name":     "api-service",
			},
			ObservedAt: now,
		},
		{
			FactID:   "fact-file-1",
			FactKind: "file",
			Payload: map[string]any{
				"repo_id": "repo-api",
				"parsed_file_data": map[string]any{
					"argocd_applications": []any{
						map[string]any{
							"name":        "api-service",
							"source_repo": "https://github.com/org/deploy-manifests",
							"source_path": "apps/api-service",
						},
					},
				},
			},
			ObservedAt: now,
		},
	}

	candidates, _ := ExtractWorkloadCandidates(envelopes)
	if len(candidates) != 1 {
		t.Fatalf("len(candidates) = %d, want 1", len(candidates))
	}
	c := candidates[0]
	if c.RepoID != "repo-api" {
		t.Errorf("RepoID = %q, want repo-api", c.RepoID)
	}
	if c.RepoName != "api-service" {
		t.Errorf("RepoName = %q, want api-service", c.RepoName)
	}
}

func TestExtractWorkloadCandidatesSkipsRepoWithoutWorkloadSignals(t *testing.T) {
	t.Parallel()

	now := time.Now().UTC()
	envelopes := []facts.Envelope{
		{
			FactID:   "fact-repo",
			FactKind: "repository",
			Payload: map[string]any{
				"graph_id": "repo-docs",
				"name":     "documentation",
			},
			ObservedAt: now,
		},
		{
			FactID:   "fact-file-1",
			FactKind: "file",
			Payload: map[string]any{
				"repo_id": "repo-docs",
				"parsed_file_data": map[string]any{
					"k8s_resources":       []any{},
					"argocd_applications": []any{},
				},
			},
			ObservedAt: now,
		},
	}

	candidates, _ := ExtractWorkloadCandidates(envelopes)
	if len(candidates) != 0 {
		t.Fatalf("len(candidates) = %d, want 0 (no workload signals)", len(candidates))
	}
}

func TestExtractWorkloadCandidatesDeduplicatesKindsAndNamespaces(t *testing.T) {
	t.Parallel()

	now := time.Now().UTC()
	envelopes := []facts.Envelope{
		{
			FactID:   "fact-repo",
			FactKind: "repository",
			Payload: map[string]any{
				"graph_id": "repo-svc",
				"name":     "svc",
			},
			ObservedAt: now,
		},
		{
			FactID:   "fact-file-1",
			FactKind: "file",
			Payload: map[string]any{
				"repo_id": "repo-svc",
				"parsed_file_data": map[string]any{
					"k8s_resources": []any{
						map[string]any{"name": "svc", "kind": "Deployment", "namespace": "prod"},
						map[string]any{"name": "svc-worker", "kind": "Deployment", "namespace": "prod"},
						map[string]any{"name": "svc-cron", "kind": "CronJob", "namespace": "staging"},
					},
				},
			},
			ObservedAt: now,
		},
	}

	candidates, _ := ExtractWorkloadCandidates(envelopes)
	if len(candidates) != 1 {
		t.Fatalf("len(candidates) = %d, want 1", len(candidates))
	}
	c := candidates[0]
	if len(c.ResourceKinds) != 2 {
		t.Fatalf("ResourceKinds = %v, want 2 unique kinds", c.ResourceKinds)
	}
	if len(c.Namespaces) != 2 {
		t.Fatalf("Namespaces = %v, want 2 unique namespaces", c.Namespaces)
	}
}

func TestExtractWorkloadCandidatesEmptyEnvelopes(t *testing.T) {
	t.Parallel()

	candidates, envs := ExtractWorkloadCandidates(nil)
	if len(candidates) != 0 {
		t.Fatalf("len(candidates) = %d, want 0", len(candidates))
	}
	if len(envs) != 0 {
		t.Fatalf("len(envs) = %d, want 0", len(envs))
	}
}

func TestExtractWorkloadCandidatesOverlayEnvironments(t *testing.T) {
	t.Parallel()

	now := time.Now().UTC()
	envelopes := []facts.Envelope{
		{
			FactID:   "fact-repo",
			FactKind: "repository",
			Payload: map[string]any{
				"graph_id": "repo-app",
				"name":     "app",
			},
			ObservedAt: now,
		},
		{
			FactID:   "fact-file-1",
			FactKind: "file",
			Payload: map[string]any{
				"repo_id": "repo-app",
				"parsed_file_data": map[string]any{
					"k8s_resources": []any{
						map[string]any{"name": "app", "kind": "Deployment", "namespace": "default"},
					},
				},
				"relative_path": "overlays/production/deployment.yaml",
			},
			ObservedAt: now,
		},
		{
			FactID:   "fact-file-2",
			FactKind: "file",
			Payload: map[string]any{
				"repo_id": "repo-app",
				"parsed_file_data": map[string]any{
					"k8s_resources": []any{
						map[string]any{"name": "app", "kind": "Deployment", "namespace": "default"},
					},
				},
				"relative_path": "overlays/staging/deployment.yaml",
			},
			ObservedAt: now,
		},
	}

	_, deploymentEnvs := ExtractWorkloadCandidates(envelopes)
	envs := deploymentEnvs["repo-app"]
	if len(envs) != 2 {
		t.Fatalf("deployment environments for repo-app = %v, want 2 entries", envs)
	}
}
