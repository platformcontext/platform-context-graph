package reducer

import (
	"testing"
)

func TestInferWorkloadKindCronJob(t *testing.T) {
	t.Parallel()
	if got := InferWorkloadKind("my-cron-job", nil); got != "cronjob" {
		t.Fatalf("InferWorkloadKind() = %q, want cronjob", got)
	}
}

func TestInferWorkloadKindWorker(t *testing.T) {
	t.Parallel()
	if got := InferWorkloadKind("data-worker", nil); got != "worker" {
		t.Fatalf("InferWorkloadKind() = %q, want worker", got)
	}
}

func TestInferWorkloadKindConsumer(t *testing.T) {
	t.Parallel()
	if got := InferWorkloadKind("event-consumer", nil); got != "consumer" {
		t.Fatalf("InferWorkloadKind() = %q, want consumer", got)
	}
}

func TestInferWorkloadKindBatch(t *testing.T) {
	t.Parallel()
	if got := InferWorkloadKind("nightly-batch", nil); got != "batch" {
		t.Fatalf("InferWorkloadKind() = %q, want batch", got)
	}
}

func TestInferWorkloadKindServiceFromResourceKinds(t *testing.T) {
	t.Parallel()
	if got := InferWorkloadKind("my-api", []string{"Deployment", "Service"}); got != "service" {
		t.Fatalf("InferWorkloadKind() = %q, want service", got)
	}
}

func TestInferWorkloadKindDefaultService(t *testing.T) {
	t.Parallel()
	if got := InferWorkloadKind("my-app", nil); got != "service" {
		t.Fatalf("InferWorkloadKind() = %q, want service", got)
	}
}

func TestInferWorkloadKindNameTakesPrecedenceOverResourceKinds(t *testing.T) {
	t.Parallel()
	// Name-based inference ("cron") takes precedence over resource kinds.
	if got := InferWorkloadKind("my-cron-task", []string{"Deployment"}); got != "cronjob" {
		t.Fatalf("InferWorkloadKind() = %q, want cronjob", got)
	}
}

func TestInferWorkloadClassificationService(t *testing.T) {
	t.Parallel()

	candidate := WorkloadCandidate{
		RepoName:      "edge-api",
		ResourceKinds: []string{"deployment", "service"},
		Provenance:    []string{"k8s_resource"},
	}

	if got := InferWorkloadClassification(candidate); got != "service" {
		t.Fatalf("InferWorkloadClassification() = %q, want service", got)
	}
}

func TestInferWorkloadClassificationJob(t *testing.T) {
	t.Parallel()

	candidate := WorkloadCandidate{
		RepoName:      "nightly-batch",
		ResourceKinds: []string{"job"},
		Provenance:    []string{"k8s_resource"},
	}

	if got := InferWorkloadClassification(candidate); got != "job" {
		t.Fatalf("InferWorkloadClassification() = %q, want job", got)
	}
}

func TestInferWorkloadClassificationUtility(t *testing.T) {
	t.Parallel()

	candidate := WorkloadCandidate{
		RepoName:   "automation-shared",
		Provenance: []string{"jenkins_pipeline"},
		Confidence: 0.42,
		Namespaces: nil,
	}

	if got := InferWorkloadClassification(candidate); got != "utility" {
		t.Fatalf("InferWorkloadClassification() = %q, want utility", got)
	}
}

func TestInferWorkloadClassificationInfrastructure(t *testing.T) {
	t.Parallel()

	candidate := WorkloadCandidate{
		RepoName:   "network-stack",
		Provenance: []string{"cloudformation_template"},
	}

	if got := InferWorkloadClassification(candidate); got != "infrastructure" {
		t.Fatalf("InferWorkloadClassification() = %q, want infrastructure", got)
	}
}

func TestExtractOverlayEnvironmentsBasic(t *testing.T) {
	t.Parallel()
	paths := []string{
		"deploy/overlays/production/kustomization.yaml",
		"deploy/overlays/staging/kustomization.yaml",
		"deploy/base/deployment.yaml",
	}
	got := ExtractOverlayEnvironments(paths)
	if len(got) != 2 {
		t.Fatalf("ExtractOverlayEnvironments() len = %d, want 2", len(got))
	}
	if got[0] != "production" {
		t.Fatalf("got[0] = %q, want production", got[0])
	}
	if got[1] != "staging" {
		t.Fatalf("got[1] = %q, want staging", got[1])
	}
}

func TestExtractOverlayEnvironmentsDeduplicates(t *testing.T) {
	t.Parallel()
	paths := []string{
		"deploy/overlays/prod/a.yaml",
		"deploy/overlays/prod/b.yaml",
	}
	got := ExtractOverlayEnvironments(paths)
	if len(got) != 1 {
		t.Fatalf("ExtractOverlayEnvironments() len = %d, want 1", len(got))
	}
	if got[0] != "prod" {
		t.Fatalf("got[0] = %q, want prod", got[0])
	}
}

func TestExtractOverlayEnvironmentsSupportsJenkinsAndTerraformPathConventions(t *testing.T) {
	t.Parallel()
	paths := []string{
		"inventory/staging.ini",
		"group_vars/monitoring.yml",
		"env/prod/main.tf",
	}
	got := ExtractOverlayEnvironments(paths)
	if len(got) != 3 {
		t.Fatalf("ExtractOverlayEnvironments() len = %d, want 3", len(got))
	}
	if got[0] != "staging" {
		t.Fatalf("got[0] = %q, want staging", got[0])
	}
	if got[1] != "monitoring" {
		t.Fatalf("got[1] = %q, want monitoring", got[1])
	}
	if got[2] != "prod" {
		t.Fatalf("got[2] = %q, want prod", got[2])
	}
}

func TestExtractOverlayEnvironmentsNoMatch(t *testing.T) {
	t.Parallel()
	paths := []string{"src/main.go", "README.md"}
	got := ExtractOverlayEnvironments(paths)
	if len(got) != 0 {
		t.Fatalf("ExtractOverlayEnvironments() len = %d, want 0", len(got))
	}
}

func TestBuildProjectionRowsEmptyCandidates(t *testing.T) {
	t.Parallel()
	result := BuildProjectionRows(nil, nil)
	if result.Stats.Workloads != 0 {
		t.Fatalf("Stats.Workloads = %d, want 0", result.Stats.Workloads)
	}
	if len(result.WorkloadRows) != 0 {
		t.Fatalf("WorkloadRows len = %d, want 0", len(result.WorkloadRows))
	}
}

func TestBuildProjectionRowsSkipsMissingRepoID(t *testing.T) {
	t.Parallel()
	candidates := []WorkloadCandidate{
		{RepoName: "my-service"},
	}
	result := BuildProjectionRows(candidates, nil)
	if result.Stats.Workloads != 0 {
		t.Fatalf("Stats.Workloads = %d, want 0", result.Stats.Workloads)
	}
}

func TestBuildProjectionRowsSkipsMissingRepoName(t *testing.T) {
	t.Parallel()
	candidates := []WorkloadCandidate{
		{RepoID: "repo-1"},
	}
	result := BuildProjectionRows(candidates, nil)
	if result.Stats.Workloads != 0 {
		t.Fatalf("Stats.Workloads = %d, want 0", result.Stats.Workloads)
	}
}

func TestBuildProjectionRowsSingleCandidate(t *testing.T) {
	t.Parallel()
	candidates := []WorkloadCandidate{
		{
			RepoID:           "repo-1",
			RepoName:         "my-api",
			ResourceKinds:    []string{"Deployment", "Service"},
			Namespaces:       []string{"production"},
			DeploymentRepoID: "",
			Confidence:       0.98,
			Provenance:       []string{"k8s_resource"},
		},
	}
	result := BuildProjectionRows(candidates, nil)

	if result.Stats.Workloads != 1 {
		t.Fatalf("Stats.Workloads = %d, want 1", result.Stats.Workloads)
	}
	if len(result.WorkloadRows) != 1 {
		t.Fatalf("WorkloadRows len = %d, want 1", len(result.WorkloadRows))
	}
	wl := result.WorkloadRows[0]
	if wl.RepoID != "repo-1" {
		t.Fatalf("RepoID = %q, want repo-1", wl.RepoID)
	}
	if wl.WorkloadID != "workload:my-api" {
		t.Fatalf("WorkloadID = %q, want workload:my-api", wl.WorkloadID)
	}
	if wl.WorkloadKind != "service" {
		t.Fatalf("WorkloadKind = %q, want service", wl.WorkloadKind)
	}
	if wl.WorkloadName != "my-api" {
		t.Fatalf("WorkloadName = %q, want my-api", wl.WorkloadName)
	}

	// Instance from namespace fallback.
	if result.Stats.Instances != 1 {
		t.Fatalf("Stats.Instances = %d, want 1", result.Stats.Instances)
	}
	inst := result.InstanceRows[0]
	if inst.InstanceID != "workload-instance:my-api:production" {
		t.Fatalf("InstanceID = %q", inst.InstanceID)
	}
	if inst.Environment != "production" {
		t.Fatalf("Environment = %q", inst.Environment)
	}

	// Repo descriptor.
	if len(result.RepoDescriptors) != 1 {
		t.Fatalf("RepoDescriptors len = %d, want 1", len(result.RepoDescriptors))
	}
	if result.RepoDescriptors[0].WorkloadID != "workload:my-api" {
		t.Fatalf("RepoDescriptor WorkloadID = %q", result.RepoDescriptors[0].WorkloadID)
	}
}

func TestBuildProjectionRowsUsesExplicitWorkloadName(t *testing.T) {
	t.Parallel()

	candidates := []WorkloadCandidate{
		{
			RepoID:           "repo-1",
			RepoName:         "monolith-repo",
			WorkloadName:     "api",
			ResourceKinds:    []string{"Deployment"},
			Namespaces:       []string{"production"},
			DeploymentRepoID: "deploy-repo-1",
			Classification:   "service",
			Confidence:       0.96,
			Provenance:       []string{"argocd_application_source"},
		},
	}
	deploymentEnvs := map[string][]string{
		"deploy-repo-1": {"production"},
	}

	result := BuildProjectionRows(candidates, deploymentEnvs)
	if len(result.WorkloadRows) != 1 {
		t.Fatalf("len(WorkloadRows) = %d, want 1", len(result.WorkloadRows))
	}
	if got, want := result.WorkloadRows[0].WorkloadID, "workload:api"; got != want {
		t.Fatalf("WorkloadID = %q, want %q", got, want)
	}
	if got, want := result.WorkloadRows[0].WorkloadName, "api"; got != want {
		t.Fatalf("WorkloadName = %q, want %q", got, want)
	}
	if len(result.InstanceRows) != 1 {
		t.Fatalf("len(InstanceRows) = %d, want 1", len(result.InstanceRows))
	}
	if got, want := result.InstanceRows[0].InstanceID, "workload-instance:api:production"; got != want {
		t.Fatalf("InstanceID = %q, want %q", got, want)
	}
}

func TestBuildProjectionRowsWithDeploymentEnvironments(t *testing.T) {
	t.Parallel()
	candidates := []WorkloadCandidate{
		{
			RepoID:           "repo-1",
			RepoName:         "my-api",
			ResourceKinds:    []string{"Deployment"},
			DeploymentRepoID: "deploy-repo-1",
			Confidence:       0.95,
			Provenance:       []string{"argocd_application_source"},
		},
	}
	deploymentEnvs := map[string][]string{
		"deploy-repo-1": {"staging", "production"},
	}
	result := BuildProjectionRows(candidates, deploymentEnvs)

	if result.Stats.Instances != 2 {
		t.Fatalf("Stats.Instances = %d, want 2", result.Stats.Instances)
	}
	if result.Stats.DeploymentSources != 2 {
		t.Fatalf("Stats.DeploymentSources = %d, want 2", result.Stats.DeploymentSources)
	}

	// Check deployment source rows.
	if len(result.DeploymentSourceRows) != 2 {
		t.Fatalf("DeploymentSourceRows len = %d, want 2", len(result.DeploymentSourceRows))
	}
	if result.DeploymentSourceRows[0].DeploymentRepoID != "deploy-repo-1" {
		t.Fatalf("DeploymentRepoID = %q", result.DeploymentSourceRows[0].DeploymentRepoID)
	}
}

func TestBuildProjectionRowsUsesRepoIDOverlaysWhenNoDeploymentRepo(t *testing.T) {
	t.Parallel()
	candidates := []WorkloadCandidate{
		{
			RepoID:         "repo-self-deploy",
			RepoName:       "self-deploy-api",
			ResourceKinds:  []string{"Deployment"},
			Classification: "service",
			Confidence:     0.98,
			Provenance:     []string{"k8s_resource"},
		},
	}
	deploymentEnvs := map[string][]string{
		"repo-self-deploy": {"staging", "production"},
	}
	result := BuildProjectionRows(candidates, deploymentEnvs)

	if result.Stats.Instances != 2 {
		t.Fatalf("Stats.Instances = %d, want 2", result.Stats.Instances)
	}
	if result.InstanceRows[0].Environment != "staging" {
		t.Fatalf("InstanceRows[0].Environment = %q, want staging", result.InstanceRows[0].Environment)
	}
	if result.InstanceRows[1].Environment != "production" {
		t.Fatalf("InstanceRows[1].Environment = %q, want production", result.InstanceRows[1].Environment)
	}
}

func TestBuildProjectionRowsRuntimePlatformFromResourceKinds(t *testing.T) {
	t.Parallel()
	candidates := []WorkloadCandidate{
		{
			RepoID:        "repo-1",
			RepoName:      "my-api",
			ResourceKinds: []string{"Deployment", "Service"},
			Namespaces:    []string{"production"},
			Confidence:    0.98,
			Provenance:    []string{"k8s_resource"},
		},
	}
	result := BuildProjectionRows(candidates, nil)

	if len(result.RuntimePlatformRows) != 1 {
		t.Fatalf("RuntimePlatformRows len = %d, want 1", len(result.RuntimePlatformRows))
	}
	plat := result.RuntimePlatformRows[0]
	if plat.PlatformKind != "kubernetes" {
		t.Fatalf("PlatformKind = %q, want kubernetes", plat.PlatformKind)
	}
	if plat.InstanceID != "workload-instance:my-api:production" {
		t.Fatalf("InstanceID = %q", plat.InstanceID)
	}
	if plat.PlatformName != "production" {
		t.Fatalf("PlatformName = %q, want production", plat.PlatformName)
	}
}

func TestBuildProjectionRowsDeduplicatesWorkloads(t *testing.T) {
	t.Parallel()
	candidates := []WorkloadCandidate{
		{RepoID: "repo-1", RepoName: "my-api", Namespaces: []string{"prod"}, Confidence: 0.98},
		{RepoID: "repo-1", RepoName: "my-api", Namespaces: []string{"staging"}, Confidence: 0.98},
	}
	result := BuildProjectionRows(candidates, nil)

	if result.Stats.Workloads != 1 {
		t.Fatalf("Stats.Workloads = %d, want 1 (deduplicated)", result.Stats.Workloads)
	}
	if result.Stats.Instances != 2 {
		t.Fatalf("Stats.Instances = %d, want 2", result.Stats.Instances)
	}
}

func TestBuildProjectionRowsDeduplicatesInstances(t *testing.T) {
	t.Parallel()
	candidates := []WorkloadCandidate{
		{RepoID: "repo-1", RepoName: "my-api", Namespaces: []string{"prod"}, Confidence: 0.98},
		{RepoID: "repo-1", RepoName: "my-api", Namespaces: []string{"prod"}, Confidence: 0.98},
	}
	result := BuildProjectionRows(candidates, nil)

	if result.Stats.Instances != 1 {
		t.Fatalf("Stats.Instances = %d, want 1 (deduplicated)", result.Stats.Instances)
	}
}

func TestBuildProjectionRowsNoRuntimePlatformWithoutKubernetesKinds(t *testing.T) {
	t.Parallel()
	candidates := []WorkloadCandidate{
		{
			RepoID:        "repo-1",
			RepoName:      "my-lib",
			ResourceKinds: []string{},
			Namespaces:    []string{"production"},
			Confidence:    0.85,
			Provenance:    []string{"dockerfile_runtime"},
		},
	}
	result := BuildProjectionRows(candidates, nil)

	if len(result.RuntimePlatformRows) != 0 {
		t.Fatalf("RuntimePlatformRows len = %d, want 0", len(result.RuntimePlatformRows))
	}
}

func TestBuildProjectionRowsSkipsUtilityCandidates(t *testing.T) {
	t.Parallel()

	result := BuildProjectionRows([]WorkloadCandidate{
		{
			RepoID:         "repo-utility",
			RepoName:       "automation-shared",
			Classification: "utility",
			Confidence:     0.42,
			Provenance:     []string{"jenkins_pipeline"},
		},
	}, nil)

	if got := len(result.WorkloadRows); got != 0 {
		t.Fatalf("len(WorkloadRows) = %d, want 0 for utility candidate", got)
	}
	if got := len(result.InstanceRows); got != 0 {
		t.Fatalf("len(InstanceRows) = %d, want 0 for utility candidate", got)
	}
}

func TestBuildProjectionRowsSkipsCandidatesWithoutConfidence(t *testing.T) {
	t.Parallel()

	result := BuildProjectionRows([]WorkloadCandidate{
		{
			RepoID:         "repo-missing-confidence",
			RepoName:       "missing-confidence-api",
			Classification: "service",
			ResourceKinds:  []string{"deployment"},
			Namespaces:     []string{"production"},
		},
	}, nil)

	if got := len(result.WorkloadRows); got != 0 {
		t.Fatalf("len(WorkloadRows) = %d, want 0 for missing-confidence candidate", got)
	}
	if got := len(result.InstanceRows); got != 0 {
		t.Fatalf("len(InstanceRows) = %d, want 0 for missing-confidence candidate", got)
	}
}

func TestBuildProjectionRowsSkipsCandidatesBelowMaterializationConfidenceFloor(t *testing.T) {
	t.Parallel()

	result := BuildProjectionRows([]WorkloadCandidate{
		{
			RepoID:         "repo-low-confidence",
			RepoName:       "dockerfile-only-api",
			Classification: "service",
			Confidence:     0.80,
			Provenance:     []string{"dockerfile_runtime"},
			ResourceKinds:  []string{"deployment"},
			Namespaces:     []string{"production"},
		},
	}, nil)

	if got := len(result.WorkloadRows); got != 0 {
		t.Fatalf("len(WorkloadRows) = %d, want 0 for below-threshold candidate", got)
	}
	if got := len(result.InstanceRows); got != 0 {
		t.Fatalf("len(InstanceRows) = %d, want 0 for below-threshold candidate", got)
	}
}

func TestBuildProjectionRowsCarriesClassificationConfidenceAndProvenance(t *testing.T) {
	t.Parallel()

	candidates := []WorkloadCandidate{
		{
			RepoID:           "repo-edge-api",
			RepoName:         "edge-api",
			DeploymentRepoID: "repo-platform-deploy",
			Classification:   "service",
			Confidence:       0.96,
			Provenance:       []string{"argocd_application_source", "dockerfile_runtime"},
			ResourceKinds:    []string{"deployment"},
		},
	}
	deploymentEnvs := map[string][]string{
		"repo-platform-deploy": {"production"},
	}

	result := BuildProjectionRows(candidates, deploymentEnvs)
	if got := len(result.WorkloadRows); got != 1 {
		t.Fatalf("len(WorkloadRows) = %d, want 1", got)
	}
	workload := result.WorkloadRows[0]
	if got, want := workload.Classification, "service"; got != want {
		t.Fatalf("Classification = %q, want %q", got, want)
	}
	if got, want := workload.Confidence, 0.96; got != want {
		t.Fatalf("Confidence = %f, want %f", got, want)
	}
	if got, want := workload.Provenance, []string{"argocd_application_source", "dockerfile_runtime"}; len(got) != len(want) || got[0] != want[0] || got[1] != want[1] {
		t.Fatalf("Provenance = %v, want %v", got, want)
	}
	if got := len(result.DeploymentSourceRows); got != 1 {
		t.Fatalf("len(DeploymentSourceRows) = %d, want 1", got)
	}
	if got, want := result.DeploymentSourceRows[0].Confidence, 0.96; got != want {
		t.Fatalf("Deployment source confidence = %f, want %f", got, want)
	}
}

func TestBuildProjectionRowsDoesNotInventDefaultEnvironmentInstance(t *testing.T) {
	t.Parallel()

	candidates := []WorkloadCandidate{
		{
			RepoID:         "repo-boattrader",
			RepoName:       "api-node-boattrader",
			Classification: "service",
			Confidence:     0.85,
			Provenance:     []string{"dockerfile_runtime", "jenkins_pipeline"},
		},
	}

	result := BuildProjectionRows(candidates, nil)

	if got := result.Stats.Workloads; got != 1 {
		t.Fatalf("Stats.Workloads = %d, want 1", got)
	}
	if got := result.Stats.Instances; got != 0 {
		t.Fatalf("Stats.Instances = %d, want 0 when no environment evidence exists", got)
	}
	if got := len(result.InstanceRows); got != 0 {
		t.Fatalf("len(InstanceRows) = %d, want 0 when no environment evidence exists", got)
	}
	if got := len(result.RuntimePlatformRows); got != 0 {
		t.Fatalf("len(RuntimePlatformRows) = %d, want 0 when no environment evidence exists", got)
	}
	if got := len(result.DeploymentSourceRows); got != 0 {
		t.Fatalf("len(DeploymentSourceRows) = %d, want 0 when no runtime instance exists", got)
	}
}

func TestBuildProjectionRowsSkipsNamespaceFallbackForNonEnvironmentNamespace(t *testing.T) {
	t.Parallel()

	candidates := []WorkloadCandidate{
		{
			RepoID:         "repo-service-gha",
			RepoName:       "service-gha",
			Classification: "service",
			Confidence:     0.98,
			Namespaces:     []string{"service-gha"},
			Provenance:     []string{"k8s_resource", "dockerfile_runtime"},
		},
	}

	result := BuildProjectionRows(candidates, nil)

	if got := result.Stats.Workloads; got != 1 {
		t.Fatalf("Stats.Workloads = %d, want 1", got)
	}
	if got := result.Stats.Instances; got != 0 {
		t.Fatalf("Stats.Instances = %d, want 0 for non-environment namespace fallback", got)
	}
	if got := len(result.InstanceRows); got != 0 {
		t.Fatalf("len(InstanceRows) = %d, want 0 for non-environment namespace fallback", got)
	}
	if got := len(result.RuntimePlatformRows); got != 0 {
		t.Fatalf("len(RuntimePlatformRows) = %d, want 0 for non-environment namespace fallback", got)
	}
}
