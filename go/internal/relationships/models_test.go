package relationships

import "testing"

func TestEntityIdentity(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name     string
		entityID string
		repoID   string
		want     string
	}{
		{
			name:     "entity ID takes precedence",
			entityID: "platform:aws:eks:us-east-1:prod",
			repoID:   "repo-123",
			want:     "platform:aws:eks:us-east-1:prod",
		},
		{
			name:     "falls back to repo ID",
			entityID: "",
			repoID:   "repo-456",
			want:     "repo-456",
		},
		{
			name:     "both empty returns empty",
			entityID: "",
			repoID:   "",
			want:     "",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			got := entityIdentity(tt.entityID, tt.repoID)
			if got != tt.want {
				t.Errorf("entityIdentity(%q, %q) = %q, want %q",
					tt.entityID, tt.repoID, got, tt.want)
			}
		})
	}
}

func TestEvidenceKindConstants(t *testing.T) {
	t.Parallel()

	// Verify key constants have expected string values.
	checks := map[EvidenceKind]string{
		EvidenceKindTerraformAppRepo:               "TERRAFORM_APP_REPO",
		EvidenceKindTerraformModuleSource:          "TERRAFORM_MODULE_SOURCE",
		EvidenceKindTerragruntDependencyConfigPath: "TERRAGRUNT_DEPENDENCY_CONFIG_PATH",
		EvidenceKindHelmChart:                      "HELM_CHART_REFERENCE",
		EvidenceKindArgoCDAppSource:                "ARGOCD_APPLICATION_SOURCE",
		EvidenceKindKustomizeResource:              "KUSTOMIZE_RESOURCE_REFERENCE",
		EvidenceKindKustomizeHelmChart:             "KUSTOMIZE_HELM_CHART_REFERENCE",
		EvidenceKindKustomizeImage:                 "KUSTOMIZE_IMAGE_REFERENCE",
	}
	for kind, want := range checks {
		if string(kind) != want {
			t.Errorf("EvidenceKind %v = %q, want %q", kind, string(kind), want)
		}
	}
}

func TestRelationshipTypeConstants(t *testing.T) {
	t.Parallel()

	if string(RelDeploysFrom) != "DEPLOYS_FROM" {
		t.Errorf("RelDeploysFrom = %q", string(RelDeploysFrom))
	}
	if string(RelProvisionsDependencyFor) != "PROVISIONS_DEPENDENCY_FOR" {
		t.Errorf("RelProvisionsDependencyFor = %q", string(RelProvisionsDependencyFor))
	}
	if string(RelDependsOn) != "DEPENDS_ON" {
		t.Errorf("RelDependsOn = %q", string(RelDependsOn))
	}
}

func TestResolutionSourceConstants(t *testing.T) {
	t.Parallel()

	if string(ResolutionSourceInferred) != "inferred" {
		t.Errorf("ResolutionSourceInferred = %q", string(ResolutionSourceInferred))
	}
	if string(ResolutionSourceAssertion) != "assertion" {
		t.Errorf("ResolutionSourceAssertion = %q", string(ResolutionSourceAssertion))
	}
}
