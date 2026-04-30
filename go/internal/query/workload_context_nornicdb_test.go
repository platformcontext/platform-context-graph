package query

import (
	"context"
	"strings"
	"testing"
)

func TestFetchWorkloadContextUsesScalarQueriesForNornicDBOptionalProjectionSafety(t *testing.T) {
	t.Parallel()

	handler := &EntityHandler{
		Neo4j: fakeWorkloadGraphReader{
			runSingle: func(_ context.Context, cypher string, params map[string]any) (map[string]any, error) {
				if strings.Contains(cypher, "OPTIONAL MATCH") || strings.Contains(cypher, "collect(DISTINCT {") {
					t.Fatalf("cypher = %q, want scalar queries without optional map projection", cypher)
				}
				if !strings.Contains(cypher, "RETURN w.id as id, w.name as name, w.kind as kind") {
					t.Fatalf("unexpected RunSingle cypher: %q", cypher)
				}
				if got, want := params["service_name"], "api-node-datax"; got != want {
					t.Fatalf("params[service_name] = %#v, want %#v", got, want)
				}
				return map[string]any{
					"id":   "workload:api-node-datax",
					"name": "api-node-datax",
					"kind": "service",
				}, nil
			},
			run: func(_ context.Context, cypher string, _ map[string]any) ([]map[string]any, error) {
				if strings.Contains(cypher, "OPTIONAL MATCH") || strings.Contains(cypher, "collect(DISTINCT {") {
					t.Fatalf("cypher = %q, want scalar queries without optional map projection", cypher)
				}
				if strings.Contains(cypher, "(i:WorkloadInstance)-[runsOn:RUNS_ON]->") {
					t.Fatalf("cypher = %q, want RUNS_ON traversal in a separate MATCH", cypher)
				}
				switch {
				case strings.Contains(cypher, "MATCH (r:Repository)-[:DEFINES]->(w)"):
					return []map[string]any{{
						"repo_id":   "repository:datax",
						"repo_name": "api-node-datax",
					}}, nil
				case strings.Contains(cypher, "-[runsOn:RUNS_ON]->(p:Platform)"):
					return []map[string]any{
						{
							"instance_id":         "workload-instance:api-node-datax:bg-prod",
							"platform_name":       "bg-prod",
							"platform_kind":       "kubernetes",
							"platform_confidence": 0.95,
							"platform_reason":     "resolved_deployment_evidence",
						},
						{
							"instance_id":         "workload-instance:api-node-datax:bg-prod",
							"platform_name":       "ecs-prod",
							"platform_kind":       "ecs",
							"platform_confidence": 0.91,
							"platform_reason":     "terraform_service_evidence",
						},
						{
							"instance_id":         "workload-instance:api-node-datax:ops-qa",
							"platform_name":       "ops-qa",
							"platform_kind":       "kubernetes",
							"platform_confidence": 0.95,
							"platform_reason":     "resolved_deployment_evidence",
						},
					}, nil
				case strings.Contains(cypher, "MATCH (w)<-[:INSTANCE_OF]-(i:WorkloadInstance)"):
					return []map[string]any{
						{
							"instance_id":                "workload-instance:api-node-datax:bg-prod",
							"environment":                "bg-prod",
							"materialization_confidence": 0.91,
							"materialization_provenance": []any{"helm_values_reference"},
						},
						{
							"instance_id":                "workload-instance:api-node-datax:ops-qa",
							"environment":                "ops-qa",
							"materialization_confidence": 0.91,
							"materialization_provenance": []any{"kustomize_resource_reference"},
						},
					}, nil
				case strings.Contains(cypher, "DEPENDS_ON|USES_MODULE|DEPLOYS_FROM"):
					return nil, nil
				case strings.Contains(cypher, "K8sResource OR"):
					return nil, nil
				case strings.Contains(cypher, "fn.name IN"):
					return nil, nil
				default:
					t.Fatalf("unexpected Run cypher: %q", cypher)
				}
				return nil, nil
			},
		},
	}

	ctx, err := handler.fetchWorkloadContext(
		context.Background(),
		"w.name = $service_name OR w.id = $service_name",
		map[string]any{"service_name": "api-node-datax"},
	)
	if err != nil {
		t.Fatalf("fetchWorkloadContext() error = %v", err)
	}

	if got, want := ctx["repo_name"], "api-node-datax"; got != want {
		t.Fatalf("repo_name = %#v, want %#v", got, want)
	}
	instances, ok := ctx["instances"].([]map[string]any)
	if !ok {
		t.Fatalf("instances type = %T, want []map[string]any", ctx["instances"])
	}
	if got, want := len(instances), 2; got != want {
		t.Fatalf("len(instances) = %d, want %d", got, want)
	}
	if got, want := instances[0]["environment"], "bg-prod"; got != want {
		t.Fatalf("instances[0].environment = %#v, want %#v", got, want)
	}
	if got, want := instances[0]["platform_name"], "bg-prod"; got != want {
		t.Fatalf("instances[0].platform_name = %#v, want %#v", got, want)
	}
	bgProdPlatforms := mapSliceValue(instances[0], "platforms")
	if got, want := len(bgProdPlatforms), 2; got != want {
		t.Fatalf("len(instances[0].platforms) = %d, want %d", got, want)
	}
	if got, want := bgProdPlatforms[1]["platform_name"], "ecs-prod"; got != want {
		t.Fatalf("instances[0].platforms[1].platform_name = %#v, want %#v", got, want)
	}
	overview := buildServiceDeploymentOverview(ctx)
	if got, want := overview["platform_count"], 3; got != want {
		t.Fatalf("deployment_overview.platform_count = %#v, want %#v", got, want)
	}
	story := buildWorkloadStory(ctx)
	if !strings.Contains(story, "bg-prod on bg-prod (kubernetes), ecs-prod (ecs)") {
		t.Fatalf("story = %q, want both platform targets for bg-prod", story)
	}
}
