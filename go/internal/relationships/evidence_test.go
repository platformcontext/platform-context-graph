package relationships

import (
	"testing"

	"github.com/platformcontext/platform-context-graph/go/internal/facts"
)

func TestDiscoverEvidenceEmptyInputs(t *testing.T) {
	t.Parallel()

	if result := DiscoverEvidence(nil, nil); result != nil {
		t.Errorf("got %v, want nil", result)
	}
	if result := DiscoverEvidence([]facts.Envelope{{}}, nil); result != nil {
		t.Errorf("got %v, want nil for empty catalog", result)
	}
}

func TestDiscoverTerraformEvidence(t *testing.T) {
	t.Parallel()

	envelopes := []facts.Envelope{
		{
			ScopeID: "repo-infra",
			Payload: map[string]any{
				"artifact_type": "terraform",
				"relative_path": "main.tf",
				"content":       `app_repo = "payments-service"`,
			},
		},
	}
	catalog := []CatalogEntry{
		{RepoID: "repo-payments", Aliases: []string{"payments-service", "payments"}},
	}

	evidence := DiscoverEvidence(envelopes, catalog)

	if len(evidence) != 1 {
		t.Fatalf("len = %d, want 1", len(evidence))
	}
	if evidence[0].EvidenceKind != EvidenceKindTerraformAppRepo {
		t.Errorf("kind = %q", evidence[0].EvidenceKind)
	}
	if evidence[0].SourceRepoID != "repo-infra" {
		t.Errorf("source = %q", evidence[0].SourceRepoID)
	}
	if evidence[0].TargetRepoID != "repo-payments" {
		t.Errorf("target = %q", evidence[0].TargetRepoID)
	}
	if evidence[0].Confidence != 0.99 {
		t.Errorf("confidence = %f", evidence[0].Confidence)
	}
}

func TestDiscoverTerraformGitHubEvidence(t *testing.T) {
	t.Parallel()

	envelopes := []facts.Envelope{
		{
			ScopeID: "repo-infra",
			Payload: map[string]any{
				"artifact_type": "terraform",
				"relative_path": "modules/iam.tf",
				"content":       `source = "github.com/myorg/api-gateway.git"`,
			},
		},
	}
	catalog := []CatalogEntry{
		{RepoID: "repo-api-gw", Aliases: []string{"api-gateway"}},
	}

	evidence := DiscoverEvidence(envelopes, catalog)

	if len(evidence) != 1 {
		t.Fatalf("len = %d, want 1", len(evidence))
	}
	if evidence[0].EvidenceKind != EvidenceKindTerraformGitHubRepo {
		t.Errorf("kind = %q", evidence[0].EvidenceKind)
	}
}

func TestDiscoverHelmChartEvidence(t *testing.T) {
	t.Parallel()

	envelopes := []facts.Envelope{
		{
			ScopeID: "repo-deploy",
			Payload: map[string]any{
				"artifact_type": "helm",
				"relative_path": "charts/app/Chart.yaml",
				"content":       "name: my-app\nrepository: payments-service\n",
			},
		},
	}
	catalog := []CatalogEntry{
		{RepoID: "repo-payments", Aliases: []string{"payments-service"}},
	}

	evidence := DiscoverEvidence(envelopes, catalog)

	if len(evidence) != 1 {
		t.Fatalf("len = %d, want 1", len(evidence))
	}
	if evidence[0].EvidenceKind != EvidenceKindHelmChart {
		t.Errorf("kind = %q", evidence[0].EvidenceKind)
	}
	if evidence[0].RelationshipType != RelDeploysFrom {
		t.Errorf("type = %q", evidence[0].RelationshipType)
	}
}

func TestDiscoverHelmValuesEvidence(t *testing.T) {
	t.Parallel()

	envelopes := []facts.Envelope{
		{
			ScopeID: "repo-deploy",
			Payload: map[string]any{
				"relative_path": "charts/app/values.yaml",
				"content":       "image:\n  repository: payments-service\n",
			},
		},
	}
	catalog := []CatalogEntry{
		{RepoID: "repo-payments", Aliases: []string{"payments-service"}},
	}

	evidence := DiscoverEvidence(envelopes, catalog)

	if len(evidence) != 1 {
		t.Fatalf("len = %d, want 1", len(evidence))
	}
	if evidence[0].EvidenceKind != EvidenceKindHelmValues {
		t.Errorf("kind = %q", evidence[0].EvidenceKind)
	}
}

func TestDiscoverKustomizeEvidence(t *testing.T) {
	t.Parallel()

	envelopes := []facts.Envelope{
		{
			ScopeID: "repo-deploy",
			Payload: map[string]any{
				"relative_path": "overlays/prod/kustomization.yaml",
				"content":       "resources:\n  - ../../base\nnamePrefix: payments-service\n",
			},
		},
	}
	catalog := []CatalogEntry{
		{RepoID: "repo-payments", Aliases: []string{"payments-service"}},
	}

	evidence := DiscoverEvidence(envelopes, catalog)

	if len(evidence) < 1 {
		t.Fatalf("len = %d, want >= 1", len(evidence))
	}
	found := false
	for _, e := range evidence {
		if e.EvidenceKind == EvidenceKindKustomizeResource {
			found = true
		}
	}
	if !found {
		t.Error("expected KUSTOMIZE_RESOURCE_REFERENCE evidence")
	}
}

func TestDiscoverArgoCDEvidence(t *testing.T) {
	t.Parallel()

	envelopes := []facts.Envelope{
		{
			ScopeID: "repo-gitops",
			Payload: map[string]any{
				"artifact_type": "argocd",
				"relative_path": "apps/payments.yaml",
				"content": `apiVersion: argoproj.io/v1alpha1
kind: Application
spec:
  source:
    repoURL: 'https://github.com/myorg/payments-service.git'
    targetRevision: HEAD
`,
			},
		},
	}
	catalog := []CatalogEntry{
		{RepoID: "repo-payments", Aliases: []string{"payments-service"}},
	}

	evidence := DiscoverEvidence(envelopes, catalog)

	if len(evidence) != 1 {
		t.Fatalf("len = %d, want 1", len(evidence))
	}
	if evidence[0].EvidenceKind != EvidenceKindArgoCDAppSource {
		t.Errorf("kind = %q", evidence[0].EvidenceKind)
	}
	if evidence[0].Confidence != 0.95 {
		t.Errorf("confidence = %f", evidence[0].Confidence)
	}
}

func TestDiscoverEvidenceSelfReferenceSkipped(t *testing.T) {
	t.Parallel()

	envelopes := []facts.Envelope{
		{
			ScopeID: "repo-infra",
			Payload: map[string]any{
				"artifact_type": "terraform",
				"relative_path": "main.tf",
				"content":       `app_repo = "infra-repo"`,
			},
		},
	}
	catalog := []CatalogEntry{
		{RepoID: "repo-infra", Aliases: []string{"infra-repo"}},
	}

	evidence := DiscoverEvidence(envelopes, catalog)

	if len(evidence) != 0 {
		t.Errorf("len = %d, want 0 (self-reference)", len(evidence))
	}
}

func TestDiscoverEvidenceDeduplication(t *testing.T) {
	t.Parallel()

	envelopes := []facts.Envelope{
		{
			ScopeID: "repo-infra",
			Payload: map[string]any{
				"artifact_type": "terraform",
				"relative_path": "main.tf",
				"content":       `app_repo = "payments-service"` + "\n" + `app_repo = "payments-service"`,
			},
		},
	}
	catalog := []CatalogEntry{
		{RepoID: "repo-payments", Aliases: []string{"payments-service"}},
	}

	evidence := DiscoverEvidence(envelopes, catalog)

	// Even with two identical matches in the same file, dedup by (kind, src, tgt, path).
	if len(evidence) != 1 {
		t.Errorf("len = %d, want 1 (deduped per file)", len(evidence))
	}
}

func TestIsTerraformArtifact(t *testing.T) {
	t.Parallel()

	tests := []struct {
		artifactType string
		filePath     string
		want         bool
	}{
		{"terraform", "main.tf", true},
		{"terragrunt", "terragrunt.hcl", true},
		{"", "modules/vpc.tf", true},
		{"", "config.tf.json", true},
		{"", "data.hcl", true},
		{"", "values.yaml", false},
		{"helm", "Chart.yaml", false},
	}
	for _, tt := range tests {
		got := isTerraformArtifact(tt.artifactType, tt.filePath)
		if got != tt.want {
			t.Errorf("isTerraformArtifact(%q, %q) = %v, want %v",
				tt.artifactType, tt.filePath, got, tt.want)
		}
	}
}

func TestIsHelmArtifact(t *testing.T) {
	t.Parallel()

	tests := []struct {
		artifactType string
		filePath     string
		want         bool
	}{
		{"helm", "Chart.yaml", true},
		{"", "charts/app/Chart.yaml", true},
		{"", "charts/app/Chart.yml", true},
		{"", "values.yaml", true},
		{"", "values-prod.yaml", true},
		{"", "main.tf", false},
	}
	for _, tt := range tests {
		got := isHelmArtifact(tt.artifactType, tt.filePath)
		if got != tt.want {
			t.Errorf("isHelmArtifact(%q, %q) = %v, want %v",
				tt.artifactType, tt.filePath, got, tt.want)
		}
	}
}

func TestIsKustomizeArtifact(t *testing.T) {
	t.Parallel()

	tests := []struct {
		filePath string
		want     bool
	}{
		{"overlays/prod/kustomization.yaml", true},
		{"overlays/prod/kustomization.yml", true},
		{"main.tf", false},
		{"Chart.yaml", false},
	}
	for _, tt := range tests {
		got := isKustomizeArtifact(tt.filePath)
		if got != tt.want {
			t.Errorf("isKustomizeArtifact(%q) = %v, want %v",
				tt.filePath, got, tt.want)
		}
	}
}

func TestIsArgoCDArtifact(t *testing.T) {
	t.Parallel()

	tests := []struct {
		artifactType string
		content      string
		want         bool
	}{
		{"argocd", "", true},
		{"", "kind: Application", true},
		{"", "kind: ApplicationSet", true},
		{"", "kind: Deployment", false},
	}
	for _, tt := range tests {
		got := isArgoCDArtifact(tt.artifactType, tt.content)
		if got != tt.want {
			t.Errorf("isArgoCDArtifact(%q, %q) = %v, want %v",
				tt.artifactType, tt.content, got, tt.want)
		}
	}
}

func TestFileBaseName(t *testing.T) {
	t.Parallel()

	tests := []struct {
		path string
		want string
	}{
		{"charts/app/Chart.yaml", "Chart.yaml"},
		{"main.tf", "main.tf"},
		{"a/b/c/d.hcl", "d.hcl"},
	}
	for _, tt := range tests {
		got := fileBaseName(tt.path)
		if got != tt.want {
			t.Errorf("fileBaseName(%q) = %q, want %q", tt.path, got, tt.want)
		}
	}
}

func TestMatchesEntry(t *testing.T) {
	t.Parallel()

	entry := CatalogEntry{RepoID: "repo-1", Aliases: []string{"payments-service", "payments"}}

	if got := matchesEntry("payments-service", entry); got != "payments-service" {
		t.Errorf("got %q, want payments-service", got)
	}
	if got := matchesEntry("PAYMENTS-SERVICE", entry); got != "payments-service" {
		t.Errorf("got %q for case-insensitive match", got)
	}
	if got := matchesEntry("unrelated-repo", entry); got != "" {
		t.Errorf("got %q, want empty for no match", got)
	}
}
