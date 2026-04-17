package query

import (
	"strings"
	"testing"
)

func TestFetchDeploymentSourcesIncludesRepositoryDeployEdges(t *testing.T) {
	t.Parallel()

	got, err := fetchDeploymentSourcesFromGraph(t.Context(), fakeRepoGraphReader{
		runByMatch: map[string][]map[string]any{
			"coalesce(rel.reason, rel.evidence_type, 'repository_deploys_from') as reason": {
				{
					"repo_id":    "repo-helm",
					"repo_name":  "deployment-helm",
					"confidence": 0.93,
					"reason":     "helm_values_reference",
				},
				{
					"repo_id":    "repo-kustomize",
					"repo_name":  "deployment-kustomize",
					"confidence": 0.91,
					"reason":     "kustomize_resource_reference",
				},
			},
		},
	}, "workload:service-edge-api", "repository:r_service_edge_api")
	if err != nil {
		t.Fatalf("fetchDeploymentSources() error = %v, want nil", err)
	}
	if len(got) != 2 {
		t.Fatalf("len(fetchDeploymentSources()) = %d, want 2", len(got))
	}
	if got[0]["repo_name"] != "deployment-helm" {
		t.Fatalf("fetchDeploymentSources()[0].repo_name = %#v, want %#v", got[0]["repo_name"], "deployment-helm")
	}
	if got[0]["reason"] != "helm_values_reference" {
		t.Fatalf("fetchDeploymentSources()[0].reason = %#v, want %#v", got[0]["reason"], "helm_values_reference")
	}
	if got[1]["repo_name"] != "deployment-kustomize" {
		t.Fatalf("fetchDeploymentSources()[1].repo_name = %#v, want %#v", got[1]["repo_name"], "deployment-kustomize")
	}
	if got[1]["reason"] != "kustomize_resource_reference" {
		t.Fatalf("fetchDeploymentSources()[1].reason = %#v, want %#v", got[1]["reason"], "kustomize_resource_reference")
	}
}

func TestBuildDeploymentTraceResponseSummarizesInstances(t *testing.T) {
	t.Parallel()

	ctx := map[string]any{
		"id":        "workload-1",
		"name":      "payments-api",
		"kind":      "service",
		"repo_id":   "repo-1",
		"repo_name": "payments",
		"instances": []map[string]any{
			{
				"instance_id":   "inst-1",
				"platform_name": "payments-argocd",
				"platform_kind": "argocd_application",
				"environment":   "prod",
			},
			{
				"instance_id":   "inst-2",
				"platform_name": "payments-argocd",
				"platform_kind": "argocd_application",
				"environment":   "stage",
			},
		},
		"deployment_sources": []map[string]any{
			{
				"repo_id":    "repo-deploy",
				"repo_name":  "payments-deploy",
				"confidence": 0.98,
				"reason":     "Deployment manifests for workload instance live in deployment repository",
			},
		},
		"cloud_resources": []map[string]any{
			{
				"id":          "cloud-1",
				"name":        "payments-db",
				"kind":        "rds_instance",
				"provider":    "aws",
				"environment": "prod",
				"confidence":  0.91,
				"reason":      "Runtime instance uses backing database",
			},
		},
		"k8s_resources": []map[string]any{
			{
				"entity_id":        "k8s-0",
				"entity_name":      "payments-api",
				"kind":             "Service",
				"qualified_name":   "payments/Service/payments-api",
				"relative_path":    "deploy/service.yaml",
				"container_images": []string{},
			},
			{
				"entity_id":        "k8s-1",
				"entity_name":      "payments-api",
				"kind":             "Deployment",
				"qualified_name":   "payments/Deployment/payments-api",
				"relative_path":    "deploy/payments.yaml",
				"container_images": []string{"ghcr.io/acme/payments-api:1.2.3"},
			},
		},
		"image_refs": []string{"ghcr.io/acme/payments-api:1.2.3"},
	}

	got := buildDeploymentTraceResponse("payments-api", ctx)

	if got["service_name"] != "payments-api" {
		t.Fatalf("service_name = %#v, want %q", got["service_name"], "payments-api")
	}
	if got["story"] == "" {
		t.Fatal("story is empty, want narrative summary")
	}
	subject, ok := got["subject"].(map[string]any)
	if !ok {
		t.Fatalf("subject type = %T, want map[string]any", got["subject"])
	}
	if subject["name"] != "payments-api" {
		t.Fatalf("subject.name = %#v, want %q", subject["name"], "payments-api")
	}
	if got["repo_id"] != "repo-1" {
		t.Fatalf("repo_id = %#v, want %q", got["repo_id"], "repo-1")
	}
	if got["repo_name"] != "payments" {
		t.Fatalf("repo_name = %#v, want %q", got["repo_name"], "payments")
	}

	overview, ok := got["deployment_overview"].(map[string]any)
	if !ok {
		t.Fatalf("deployment_overview type = %T, want map[string]any", got["deployment_overview"])
	}
	if gotCount, want := overview["instance_count"], 2; gotCount != want {
		t.Fatalf("deployment_overview.instance_count = %#v, want %#v", gotCount, want)
	}
	if gotCount, want := overview["environment_count"], 2; gotCount != want {
		t.Fatalf("deployment_overview.environment_count = %#v, want %#v", gotCount, want)
	}
	if gotCount, want := overview["platform_count"], 1; gotCount != want {
		t.Fatalf("deployment_overview.platform_count = %#v, want %#v", gotCount, want)
	}

	platforms, ok := overview["platforms"].([]string)
	if !ok {
		t.Fatalf("deployment_overview.platforms type = %T, want []string", overview["platforms"])
	}
	if len(platforms) != 1 || platforms[0] != "payments-argocd" {
		t.Fatalf("deployment_overview.platforms = %#v, want [payments-argocd]", platforms)
	}

	kinds, ok := overview["platform_kinds"].([]string)
	if !ok {
		t.Fatalf("deployment_overview.platform_kinds type = %T, want []string", overview["platform_kinds"])
	}
	if len(kinds) != 1 || kinds[0] != "argocd_application" {
		t.Fatalf("deployment_overview.platform_kinds = %#v, want [argocd_application]", kinds)
	}

	environments, ok := overview["environments"].([]string)
	if !ok {
		t.Fatalf("deployment_overview.environments type = %T, want []string", overview["environments"])
	}
	if len(environments) != 2 {
		t.Fatalf("deployment_overview.environments len = %d, want 2", len(environments))
	}

	storySections, ok := got["story_sections"].([]map[string]any)
	if !ok {
		t.Fatalf("story_sections type = %T, want []map[string]any", got["story_sections"])
	}
	if len(storySections) == 0 {
		t.Fatal("story_sections is empty, want grouped supporting context")
	}

	controllerOverview, ok := got["controller_overview"].(map[string]any)
	if !ok {
		t.Fatalf("controller_overview type = %T, want map[string]any", got["controller_overview"])
	}
	if controllerOverview["controller_count"] != 1 {
		t.Fatalf("controller_overview.controller_count = %#v, want 1", controllerOverview["controller_count"])
	}
	gitopsOverview, ok := got["gitops_overview"].(map[string]any)
	if !ok {
		t.Fatalf("gitops_overview type = %T, want map[string]any", got["gitops_overview"])
	}
	if gitopsOverview["enabled"] != true {
		t.Fatalf("gitops_overview.enabled = %#v, want true", gitopsOverview["enabled"])
	}

	runtimeOverview, ok := got["runtime_overview"].(map[string]any)
	if !ok {
		t.Fatalf("runtime_overview type = %T, want map[string]any", got["runtime_overview"])
	}
	if runtimeOverview["environment_count"] != 2 {
		t.Fatalf("runtime_overview.environment_count = %#v, want 2", runtimeOverview["environment_count"])
	}

	factSummary, ok := got["deployment_fact_summary"].(map[string]any)
	if !ok {
		t.Fatalf("deployment_fact_summary type = %T, want map[string]any", got["deployment_fact_summary"])
	}
	if factSummary["has_repository"] != true {
		t.Fatalf("deployment_fact_summary.has_repository = %#v, want true", factSummary["has_repository"])
	}
	if factSummary["mapping_mode"] != "controller" {
		t.Fatalf("deployment_fact_summary.mapping_mode = %#v, want %q", factSummary["mapping_mode"], "controller")
	}

	deploymentFacts, ok := got["deployment_facts"].([]map[string]any)
	if !ok {
		t.Fatalf("deployment_facts type = %T, want []map[string]any", got["deployment_facts"])
	}
	if len(deploymentFacts) < 3 {
		t.Fatalf("deployment_facts len = %d, want at least 3", len(deploymentFacts))
	}

	deploymentSources, ok := got["deployment_sources"].([]map[string]any)
	if !ok {
		t.Fatalf("deployment_sources type = %T, want []map[string]any", got["deployment_sources"])
	}
	if len(deploymentSources) != 1 {
		t.Fatalf("deployment_sources len = %d, want 1", len(deploymentSources))
	}

	cloudResources, ok := got["cloud_resources"].([]map[string]any)
	if !ok {
		t.Fatalf("cloud_resources type = %T, want []map[string]any", got["cloud_resources"])
	}
	if len(cloudResources) != 1 {
		t.Fatalf("cloud_resources len = %d, want 1", len(cloudResources))
	}

	k8sResources, ok := got["k8s_resources"].([]map[string]any)
	if !ok {
		t.Fatalf("k8s_resources type = %T, want []map[string]any", got["k8s_resources"])
	}
	if len(k8sResources) != 2 {
		t.Fatalf("k8s_resources len = %d, want 2", len(k8sResources))
	}

	imageRefs, ok := got["image_refs"].([]string)
	if !ok {
		t.Fatalf("image_refs type = %T, want []string", got["image_refs"])
	}
	if len(imageRefs) != 1 {
		t.Fatalf("image_refs len = %d, want 1", len(imageRefs))
	}

	k8sRelationships, ok := got["k8s_relationships"].([]map[string]any)
	if !ok {
		t.Fatalf("k8s_relationships type = %T, want []map[string]any", got["k8s_relationships"])
	}
	if len(k8sRelationships) != 2 {
		t.Fatalf("k8s_relationships len = %d, want 2", len(k8sRelationships))
	}

	controllerDrivenPaths, ok := got["controller_driven_paths"].([]map[string]any)
	if !ok {
		t.Fatalf("controller_driven_paths type = %T, want []map[string]any", got["controller_driven_paths"])
	}
	if len(controllerDrivenPaths) != 1 {
		t.Fatalf("controller_driven_paths len = %d, want 1", len(controllerDrivenPaths))
	}

	deliveryPaths, ok := got["delivery_paths"].([]map[string]any)
	if !ok {
		t.Fatalf("delivery_paths type = %T, want []map[string]any", got["delivery_paths"])
	}
	if len(deliveryPaths) != 7 {
		t.Fatalf("delivery_paths len = %d, want 7", len(deliveryPaths))
	}

	drilldowns, ok := got["drilldowns"].(map[string]any)
	if !ok {
		t.Fatalf("drilldowns type = %T, want map[string]any", got["drilldowns"])
	}
	if drilldowns["service_context_path"] == "" {
		t.Fatal("drilldowns.service_context_path is empty, want service context route")
	}
}

func TestBuildDeploymentTraceResponseNarratesTypedControllerProvenance(t *testing.T) {
	t.Parallel()

	ctx := map[string]any{
		"id":        "workload-1",
		"name":      "payments-api",
		"kind":      "service",
		"repo_id":   "repo-1",
		"repo_name": "payments",
		"instances": []map[string]any{
			{
				"instance_id":   "inst-1",
				"platform_name": "payments-argocd",
				"platform_kind": "argocd_application",
				"environment":   "prod",
			},
		},
		"deployment_sources": []map[string]any{
			{
				"repo_id":   "repo-deploy",
				"repo_name": "payments-deploy",
			},
		},
		"controller_entities": []map[string]any{
			{
				"entity_id":       "argocd-app-1",
				"entity_type":     "ArgoCDApplication",
				"entity_name":     "payments-app",
				"controller_kind": "argocd_application",
				"repo_id":         "repo-deploy",
				"relative_path":   "argocd/payments.yaml",
				"source_repo":     "https://github.com/myorg/payments-deploy.git",
				"source_path":     "deploy/overlays/prod",
				"dest_server":     "https://kubernetes.default.svc",
				"dest_namespace":  "payments",
			},
		},
	}

	got := buildDeploymentTraceResponse("payments-api", ctx)
	story, ok := got["story"].(string)
	if !ok {
		t.Fatalf("story type = %T, want string", got["story"])
	}
	if story == "" {
		t.Fatal("story is empty, want typed provenance narrative")
	}
	if !strings.Contains(story, "payments-app") {
		t.Fatalf("story = %q, want controller entity name", story)
	}
	if !strings.Contains(story, "argocd_application") {
		t.Fatalf("story = %q, want controller kind", story)
	}
	if !strings.Contains(story, "payments-deploy") {
		t.Fatalf("story = %q, want deployment source repo", story)
	}
}
