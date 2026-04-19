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
	if got, want := c.Classification, "service"; got != want {
		t.Errorf("Classification = %q, want %q", got, want)
	}
	if got, want := c.Confidence, 0.95; got < want {
		t.Errorf("Confidence = %f, want >= %f", got, want)
	}
	if len(c.Provenance) == 0 || c.Provenance[0] != "argocd_application" {
		t.Errorf("Provenance = %v, want first entry argocd_application", c.Provenance)
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

func TestExtractWorkloadCandidatesIncludesDockerfileRuntimeSignals(t *testing.T) {
	t.Parallel()

	now := time.Now().UTC()
	envelopes := []facts.Envelope{
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
			FactID:   "fact-file-1",
			FactKind: "file",
			Payload: map[string]any{
				"repo_id":       "repo-edge-api",
				"language":      "dockerfile",
				"relative_path": "Dockerfile",
				"parsed_file_data": map[string]any{
					"dockerfile_stages": []any{
						map[string]any{"name": "runtime"},
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

	candidate := candidates[0]
	if got, want := candidate.Classification, "service"; got != want {
		t.Fatalf("Classification = %q, want %q", got, want)
	}
	if got, want := candidate.Confidence, 0.75; got < want {
		t.Fatalf("Confidence = %f, want >= %f", got, want)
	}
	if len(candidate.Provenance) == 0 || candidate.Provenance[0] != "dockerfile_runtime" {
		t.Fatalf("Provenance = %v, want first entry dockerfile_runtime", candidate.Provenance)
	}
}

func TestExtractWorkloadCandidatesClassifiesJenkinsOnlyRepoAsUtility(t *testing.T) {
	t.Parallel()

	now := time.Now().UTC()
	envelopes := []facts.Envelope{
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
			FactID:   "fact-file-1",
			FactKind: "file",
			Payload: map[string]any{
				"repo_id":       "repo-automation",
				"language":      "groovy",
				"relative_path": "Jenkinsfile",
				"parsed_file_data": map[string]any{
					"jenkins_pipeline_calls": []any{"deployShared"},
				},
			},
			ObservedAt: now,
		},
	}

	candidates, _ := ExtractWorkloadCandidates(envelopes)
	if len(candidates) != 1 {
		t.Fatalf("len(candidates) = %d, want 1", len(candidates))
	}

	candidate := candidates[0]
	if got, want := candidate.Classification, "utility"; got != want {
		t.Fatalf("Classification = %q, want %q", got, want)
	}
	if got, want := candidate.Confidence, 0.60; got >= want {
		t.Fatalf("Confidence = %f, want < %f for utility-only candidate", got, want)
	}
	if len(candidate.Provenance) == 0 || candidate.Provenance[0] != "jenkins_pipeline" {
		t.Fatalf("Provenance = %v, want first entry jenkins_pipeline", candidate.Provenance)
	}
}
