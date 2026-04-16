// Package relationships implements evidence-backed relationship resolution
// for cross-repository and cross-entity dependency discovery.
package relationships

// EvidenceKind classifies the origin of one piece of relationship evidence.
type EvidenceKind string

const (
	// EvidenceKindTerraformAppRepo is a Terraform app_repo reference.
	EvidenceKindTerraformAppRepo EvidenceKind = "TERRAFORM_APP_REPO"
	// EvidenceKindTerraformAppName is a Terraform app_name reference.
	EvidenceKindTerraformAppName EvidenceKind = "TERRAFORM_APP_NAME"
	// EvidenceKindTerraformGitHubRepo is a Terraform GitHub repository reference.
	EvidenceKindTerraformGitHubRepo EvidenceKind = "TERRAFORM_GITHUB_REPOSITORY"
	// EvidenceKindTerraformGitHubActions is a Terraform GitHub Actions subject reference.
	EvidenceKindTerraformGitHubActions EvidenceKind = "TERRAFORM_GITHUB_ACTIONS_REPOSITORY"
	// EvidenceKindTerraformConfigPath is a Terraform config path reference.
	EvidenceKindTerraformConfigPath EvidenceKind = "TERRAFORM_CONFIG_PATH"
	// EvidenceKindHelmChart is a Helm Chart.yaml reference.
	EvidenceKindHelmChart EvidenceKind = "HELM_CHART_REFERENCE"
	// EvidenceKindHelmValues is a Helm values reference.
	EvidenceKindHelmValues EvidenceKind = "HELM_VALUES_REFERENCE"
	// EvidenceKindArgoCDAppSource is an ArgoCD Application source reference.
	EvidenceKindArgoCDAppSource EvidenceKind = "ARGOCD_APPLICATION_SOURCE"
	// EvidenceKindArgoCDApplicationSetDiscovery is an ApplicationSet discovery reference.
	EvidenceKindArgoCDApplicationSetDiscovery EvidenceKind = "ARGOCD_APPLICATIONSET_DISCOVERY"
	// EvidenceKindArgoCDApplicationSetDeploySource is an ApplicationSet deploy-source reference.
	EvidenceKindArgoCDApplicationSetDeploySource EvidenceKind = "ARGOCD_APPLICATIONSET_DEPLOY_SOURCE"
	// EvidenceKindArgoCDDestinationPlatform is an ApplicationSet destination-platform reference.
	EvidenceKindArgoCDDestinationPlatform EvidenceKind = "ARGOCD_DESTINATION_PLATFORM"
	// EvidenceKindGitHubActionsReusableWorkflow is a reusable workflow repo reference.
	EvidenceKindGitHubActionsReusableWorkflow EvidenceKind = "GITHUB_ACTIONS_REUSABLE_WORKFLOW"
	// EvidenceKindGitHubActionsCheckoutRepository is an explicit checkout repo reference.
	EvidenceKindGitHubActionsCheckoutRepository EvidenceKind = "GITHUB_ACTIONS_CHECKOUT_REPOSITORY"
	// EvidenceKindDockerComposeBuildContext is a Compose build context repo reference.
	EvidenceKindDockerComposeBuildContext EvidenceKind = "DOCKER_COMPOSE_BUILD_CONTEXT"
	// EvidenceKindDockerComposeImage is a Compose image repo reference.
	EvidenceKindDockerComposeImage EvidenceKind = "DOCKER_COMPOSE_IMAGE"
	// EvidenceKindKustomizeResource is a Kustomize resource reference.
	EvidenceKindKustomizeResource EvidenceKind = "KUSTOMIZE_RESOURCE_REFERENCE"
	// EvidenceKindKustomizeHelmChart is a Kustomize Helm chart reference.
	EvidenceKindKustomizeHelmChart EvidenceKind = "KUSTOMIZE_HELM_CHART_REFERENCE"
	// EvidenceKindKustomizeImage is a Kustomize image reference.
	EvidenceKindKustomizeImage EvidenceKind = "KUSTOMIZE_IMAGE_REFERENCE"
)

// RelationshipType classifies the kind of link between two entities.
type RelationshipType string

const (
	// RelDeploysFrom indicates the source deploys artifacts from the target.
	RelDeploysFrom RelationshipType = "DEPLOYS_FROM"
	// RelDiscoversConfigIn indicates the source discovers config in the target.
	RelDiscoversConfigIn RelationshipType = "DISCOVERS_CONFIG_IN"
	// RelRunsOn indicates the source runs on the target platform.
	RelRunsOn RelationshipType = "RUNS_ON"
	// RelProvisionsDependencyFor indicates the source provisions infra for the target.
	RelProvisionsDependencyFor RelationshipType = "PROVISIONS_DEPENDENCY_FOR"
	// RelDependsOn is a generic dependency relationship.
	RelDependsOn RelationshipType = "DEPENDS_ON"
)

// ResolutionSource classifies how a resolved relationship was determined.
type ResolutionSource string

const (
	// ResolutionSourceInferred means the relationship was resolved from evidence.
	ResolutionSourceInferred ResolutionSource = "inferred"
	// ResolutionSourceAssertion means the relationship was explicitly asserted.
	ResolutionSourceAssertion ResolutionSource = "assertion"
)

// EvidenceFact is one raw observed fact supporting a relationship candidate.
type EvidenceFact struct {
	EvidenceKind     EvidenceKind
	RelationshipType RelationshipType
	SourceRepoID     string
	TargetRepoID     string
	SourceEntityID   string
	TargetEntityID   string
	Confidence       float64
	Rationale        string
	Details          map[string]any
}

// Assertion is one explicit human or control-plane assertion about a relationship.
type Assertion struct {
	SourceRepoID     string
	TargetRepoID     string
	SourceEntityID   string
	TargetEntityID   string
	RelationshipType RelationshipType
	Decision         string // "assert" or "reject"
	Reason           string
	Actor            string
}

// Candidate is one machine-generated relationship candidate built from evidence.
type Candidate struct {
	SourceRepoID     string
	TargetRepoID     string
	SourceEntityID   string
	TargetEntityID   string
	RelationshipType RelationshipType
	Confidence       float64
	EvidenceCount    int
	Rationale        string
	Details          map[string]any
}

// ResolvedRelationship is one canonical relationship emitted by the resolver.
type ResolvedRelationship struct {
	SourceRepoID     string
	TargetRepoID     string
	SourceEntityID   string
	TargetEntityID   string
	RelationshipType RelationshipType
	Confidence       float64
	EvidenceCount    int
	Rationale        string
	ResolutionSource ResolutionSource
	Details          map[string]any
}

// Generation tracks one resolution generation lifecycle.
type Generation struct {
	GenerationID string
	Scope        string
	RunID        string
	Status       string
}

// entityIdentity returns an entity identity from entity ID or repository ID.
func entityIdentity(entityID, repoID string) string {
	if entityID != "" {
		return entityID
	}
	return repoID
}
