package query

import (
	"context"
	"database/sql/driver"
	"reflect"
	"strings"
	"testing"
)

func TestEnrichServiceQueryContextAddsServiceAndRelationshipSignals(t *testing.T) {
	t.Parallel()

	db := openContentReaderTestDB(t, []contentReaderQueryResult{
		{
			columns: []string{"repo_id", "relative_path", "commit_sha", "content", "content_hash", "line_count", "language", "artifact_type"},
			rows: [][]driver.Value{
				{"repo-api-node-boats", "deploy/qa/ingress.yaml", "sha-1", "", "hash-1", int64(8), "yaml", "yaml"},
				{"repo-api-node-boats", "specs/index.yaml", "sha-2", "", "hash-2", int64(15), "yaml", "yaml"},
			},
		},
		{
			columns: []string{"repo_id", "relative_path", "commit_sha", "content", "content_hash", "line_count", "language", "artifact_type"},
			rows: [][]driver.Value{
				{"repo-api-node-boats", "deploy/qa/ingress.yaml", "sha-1", "spec:\n  rules:\n    - host: api-node-boats.qa.bgrp.io\n", "hash-1", int64(8), "yaml", "yaml"},
			},
		},
		{
			columns: []string{"repo_id", "relative_path", "commit_sha", "content", "content_hash", "line_count", "language", "artifact_type"},
			rows: [][]driver.Value{
				{"repo-api-node-boats", "specs/index.yaml", "sha-2", "openapi: 3.0.3\ninfo:\n  version: v1\nservers:\n  - url: https://api-node-boats.qa.bgrp.io\npaths:\n  /boats:\n    get:\n      operationId: listBoats\n", "hash-2", int64(15), "yaml", "yaml"},
			},
		},
		{
			columns: []string{"repo_id", "relative_path", "commit_sha", "content", "content_hash", "line_count", "language", "artifact_type"},
			rows: [][]driver.Value{
				{"repo-consumer-9", "configs/service.json", "sha-3", "", "hash-3", int64(3), "json", "json"},
			},
		},
		{
			columns: []string{"repo_id", "relative_path", "commit_sha", "content", "content_hash", "line_count", "language", "artifact_type"},
			rows: [][]driver.Value{
				{"repo-consumer-9", "deploy/values.yaml", "sha-4", "", "hash-4", int64(5), "yaml", "yaml"},
			},
		},
		{
			columns: []string{
				"entity_id", "repo_id", "relative_path", "entity_type", "entity_name",
				"start_line", "end_line", "language", "source_cache", "metadata",
			},
			rows: [][]driver.Value{
				{
					"terraform-module-1", "repo-terraform-stack", "env/qa/main.tf", "TerraformModule", "service_module",
					int64(1), int64(10), "hcl", `module "service" { source = "../../modules/service" }`,
					[]byte(`{"source":"../../modules/service"}`),
				},
			},
		},
	})

	workloadContext := map[string]any{
		"id":        "workload:api-node-boats",
		"name":      "api-node-boats",
		"kind":      "Deployment",
		"repo_id":   "repo-api-node-boats",
		"repo_name": "api-node-boats",
		"instances": []map[string]any{
			{
				"instance_id":   "instance:qa",
				"platform_name": "qa-eks",
				"platform_kind": "eks",
				"environment":   "qa",
			},
		},
		"dependencies": []map[string]any{
			{"type": "DEPENDS_ON", "target_name": "shared-lib"},
		},
	}

	err := enrichServiceQueryContext(context.Background(), fakeGraphReader{
		run: func(_ context.Context, cypher string, params map[string]any) ([]map[string]any, error) {
			if strings.Contains(cypher, "PROVISIONS_DEPENDENCY_FOR|DEPLOYS_FROM|USES_MODULE|DISCOVERS_CONFIG_IN") {
				if got, want := params["repo_id"], "repo-api-node-boats"; got != want {
					t.Fatalf("params[repo_id] = %#v, want %#v", got, want)
				}
				return []map[string]any{
					{
						"repo_id":            "repo-terraform-stack",
						"repo_name":          "terraform-stack-qa",
						"relationship_type":  "PROVISIONS_DEPENDENCY_FOR",
						"relationship_reason": "terraform_provider_reference",
					},
				}, nil
			}
			return nil, nil
		},
		runSingle: func(_ context.Context, cypher string, params map[string]any) (map[string]any, error) {
			if strings.Contains(cypher, "MATCH (r:Repository {id: $repo_id}) RETURN") {
				if got, want := params["repo_id"], "repo-api-node-boats"; got != want {
					t.Fatalf("repo params[repo_id] = %#v, want %#v", got, want)
				}
				return map[string]any{
					"id":         "repo-api-node-boats",
					"name":       "api-node-boats",
					"path":       "/repos/api-node-boats",
					"local_path": "/repos/api-node-boats",
					"remote_url": "https://github.com/acme/api-node-boats",
					"repo_slug":  "acme/api-node-boats",
					"has_remote": true,
				}, nil
			}
			return nil, nil
		},
	}, NewContentReader(db), workloadContext)
	if err != nil {
		t.Fatalf("enrichServiceQueryContext() error = %v, want nil", err)
	}

	if got := len(mapSliceValue(workloadContext, "hostnames")); got != 1 {
		t.Fatalf("len(hostnames) = %d, want 1", got)
	}
	if got, want := StringSliceVal(workloadContext, "observed_config_environments"), []string{"qa"}; !reflect.DeepEqual(got, want) {
		t.Fatalf("observed_config_environments = %#v, want %#v", got, want)
	}

	apiSurface := mapValue(workloadContext, "api_surface")
	if got, want := IntVal(apiSurface, "endpoint_count"), 1; got != want {
		t.Fatalf("api_surface.endpoint_count = %d, want %d", got, want)
	}
	if got, want := IntVal(apiSurface, "spec_count"), 1; got != want {
		t.Fatalf("api_surface.spec_count = %d, want %d", got, want)
	}

	consumers := mapSliceValue(workloadContext, "consumer_repositories")
	if len(consumers) != 2 {
		t.Fatalf("len(consumer_repositories) = %d, want 2", len(consumers))
	}
	if got, want := StringVal(consumers[0], "repository"), "repo-consumer-9"; got != want {
		t.Fatalf("consumer_repositories[0].repository = %q, want %q", got, want)
	}

	provisioningChains := mapSliceValue(workloadContext, "provisioning_source_chains")
	if len(provisioningChains) != 1 {
		t.Fatalf("len(provisioning_source_chains) = %d, want 1", len(provisioningChains))
	}
	if got, want := StringVal(provisioningChains[0], "repository"), "terraform-stack-qa"; got != want {
		t.Fatalf("provisioning_source_chains[0].repository = %q, want %q", got, want)
	}

	documentationOverview := mapValue(workloadContext, "documentation_overview")
	if got, want := documentationOverview["repo_slug"], "acme/api-node-boats"; got != want {
		t.Fatalf("documentation_overview.repo_slug = %#v, want %#v", got, want)
	}

	supportOverview := mapValue(workloadContext, "support_overview")
	if got, want := supportOverview["consumer_repository_count"], 2; got != want {
		t.Fatalf("support_overview.consumer_repository_count = %#v, want %#v", got, want)
	}
}
