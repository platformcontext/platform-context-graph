package mcp

import "testing"

func TestResolveRouteMapsResolveEntityQueryToName(t *testing.T) {
	t.Parallel()

	route, err := resolveRoute("resolve_entity", map[string]any{
		"query":       "api-node-boats",
		"types":       []any{"workload"},
		"environment": "qa",
		"limit":       float64(5),
	})
	if err != nil {
		t.Fatalf("resolveRoute() error = %v, want nil", err)
	}
	if route.path != "/api/v0/entities/resolve" {
		t.Fatalf("route.path = %q, want /api/v0/entities/resolve", route.path)
	}
	body, ok := route.body.(map[string]any)
	if !ok {
		t.Fatalf("route.body type = %T, want map[string]any", route.body)
	}
	if got, want := body["name"], "api-node-boats"; got != want {
		t.Fatalf("body[name] = %#v, want %#v", got, want)
	}
	if got, want := body["type"], "workload"; got != want {
		t.Fatalf("body[type] = %#v, want %#v", got, want)
	}
	if _, exists := body["query"]; exists {
		t.Fatalf("body should not contain query, got %#v", body["query"])
	}
	if _, exists := body["types"]; exists {
		t.Fatalf("body should not contain types, got %#v", body["types"])
	}
}

func TestResolveRouteMapsQualifiedServiceIDToServicePath(t *testing.T) {
	t.Parallel()

	route, err := resolveRoute("get_service_context", map[string]any{
		"workload_id": "workload:api-node-boats",
		"environment": "prod",
	})
	if err != nil {
		t.Fatalf("resolveRoute() error = %v, want nil", err)
	}
	if got, want := route.path, "/api/v0/services/api-node-boats/context"; got != want {
		t.Fatalf("route.path = %q, want %q", got, want)
	}
	if got, want := route.query["environment"], "prod"; got != want {
		t.Fatalf("route.query[environment] = %#v, want %#v", got, want)
	}
}

func TestResolveRouteMapsSearchFileContentPatternAndRepoIDs(t *testing.T) {
	t.Parallel()

	route, err := resolveRoute("search_file_content", map[string]any{
		"pattern":  "api-node-boats",
		"repo_ids": []any{"repo://boats", "repo://shared"},
		"limit":    float64(25),
	})
	if err != nil {
		t.Fatalf("resolveRoute() error = %v, want nil", err)
	}
	if got, want := route.path, "/api/v0/content/files/search"; got != want {
		t.Fatalf("route.path = %q, want %q", got, want)
	}
	body, ok := route.body.(map[string]any)
	if !ok {
		t.Fatalf("route.body type = %T, want map[string]any", route.body)
	}
	if got, want := body["query"], "api-node-boats"; got != want {
		t.Fatalf("body[query] = %#v, want %#v", got, want)
	}
	repoIDs, ok := body["repo_ids"].([]any)
	if !ok {
		t.Fatalf("body[repo_ids] type = %T, want []any", body["repo_ids"])
	}
	if got, want := len(repoIDs), 2; got != want {
		t.Fatalf("len(body[repo_ids]) = %d, want %d", got, want)
	}
	if _, exists := body["pattern"]; exists {
		t.Fatalf("body should not contain pattern, got %#v", body["pattern"])
	}
}

func TestResolveRouteMapsSearchEntityContentSingleRepoID(t *testing.T) {
	t.Parallel()

	route, err := resolveRoute("search_entity_content", map[string]any{
		"pattern":  "api-node-boats",
		"repo_ids": []any{"repo://boats"},
		"limit":    float64(10),
	})
	if err != nil {
		t.Fatalf("resolveRoute() error = %v, want nil", err)
	}
	body, ok := route.body.(map[string]any)
	if !ok {
		t.Fatalf("route.body type = %T, want map[string]any", route.body)
	}
	if got, want := body["query"], "api-node-boats"; got != want {
		t.Fatalf("body[query] = %#v, want %#v", got, want)
	}
	if got, want := body["repo_id"], "repo://boats"; got != want {
		t.Fatalf("body[repo_id] = %#v, want %#v", got, want)
	}
	if _, exists := body["repo_ids"]; exists {
		t.Fatalf("body should not contain repo_ids, got %#v", body["repo_ids"])
	}
}

func TestResolveRouteMapsAnalyzeCodeRelationshipsCallers(t *testing.T) {
	t.Parallel()

	route, err := resolveRoute("analyze_code_relationships", map[string]any{
		"query_type": "find_callers",
		"target":     "helper",
	})
	if err != nil {
		t.Fatalf("resolveRoute() error = %v, want nil", err)
	}
	if route.path != "/api/v0/code/relationships" {
		t.Fatalf("route.path = %q, want /api/v0/code/relationships", route.path)
	}
	body, ok := route.body.(map[string]any)
	if !ok {
		t.Fatalf("route.body type = %T, want map[string]any", route.body)
	}
	if got, want := body["name"], "helper"; got != want {
		t.Fatalf("body[name] = %#v, want %#v", got, want)
	}
	if got, want := body["direction"], "incoming"; got != want {
		t.Fatalf("body[direction] = %#v, want %#v", got, want)
	}
	if got, want := body["relationship_type"], "CALLS"; got != want {
		t.Fatalf("body[relationship_type] = %#v, want %#v", got, want)
	}
}

func TestResolveRouteMapsAnalyzeCodeRelationshipsImporters(t *testing.T) {
	t.Parallel()

	route, err := resolveRoute("analyze_code_relationships", map[string]any{
		"query_type": "find_importers",
		"target":     "payments",
	})
	if err != nil {
		t.Fatalf("resolveRoute() error = %v, want nil", err)
	}
	body, ok := route.body.(map[string]any)
	if !ok {
		t.Fatalf("route.body type = %T, want map[string]any", route.body)
	}
	if got, want := body["name"], "payments"; got != want {
		t.Fatalf("body[name] = %#v, want %#v", got, want)
	}
	if got, want := body["direction"], "incoming"; got != want {
		t.Fatalf("body[direction] = %#v, want %#v", got, want)
	}
	if got, want := body["relationship_type"], "IMPORTS"; got != want {
		t.Fatalf("body[relationship_type] = %#v, want %#v", got, want)
	}
}

func TestResolveRouteKeepsGenericAnalyzeCodeRelationshipsFallback(t *testing.T) {
	t.Parallel()

	route, err := resolveRoute("analyze_code_relationships", map[string]any{
		"query_type": "class_hierarchy",
		"target":     "PaymentProcessor",
	})
	if err != nil {
		t.Fatalf("resolveRoute() error = %v, want nil", err)
	}
	body, ok := route.body.(map[string]any)
	if !ok {
		t.Fatalf("route.body type = %T, want map[string]any", route.body)
	}
	if got, want := body["entity_id"], "PaymentProcessor"; got != want {
		t.Fatalf("body[entity_id] = %#v, want %#v", got, want)
	}
	if got, want := body["query_type"], "class_hierarchy"; got != want {
		t.Fatalf("body[query_type] = %#v, want %#v", got, want)
	}
}

func TestResolveRouteMapsAnalyzeCodeRelationshipsCallChain(t *testing.T) {
	t.Parallel()

	route, err := resolveRoute("analyze_code_relationships", map[string]any{
		"query_type": "call_chain",
		"target":     "wrapper->helper",
		"context":    "7",
	})
	if err != nil {
		t.Fatalf("resolveRoute() error = %v, want nil", err)
	}
	if route.path != "/api/v0/code/call-chain" {
		t.Fatalf("route.path = %q, want /api/v0/code/call-chain", route.path)
	}
	body, ok := route.body.(map[string]any)
	if !ok {
		t.Fatalf("route.body type = %T, want map[string]any", route.body)
	}
	if got, want := body["start"], "wrapper"; got != want {
		t.Fatalf("body[start] = %#v, want %#v", got, want)
	}
	if got, want := body["end"], "helper"; got != want {
		t.Fatalf("body[end] = %#v, want %#v", got, want)
	}
	if got, want := body["max_depth"], 7; got != want {
		t.Fatalf("body[max_depth] = %#v, want %#v", got, want)
	}
}

func TestResolveRouteMapsFindDeadCodeExclusions(t *testing.T) {
	t.Parallel()

	route, err := resolveRoute("find_dead_code", map[string]any{
		"repo_id":                "repo-1",
		"exclude_decorated_with": []any{"@route", "@app.route"},
	})
	if err != nil {
		t.Fatalf("resolveRoute() error = %v, want nil", err)
	}
	if route.path != "/api/v0/code/dead-code" {
		t.Fatalf("route.path = %q, want /api/v0/code/dead-code", route.path)
	}
	body, ok := route.body.(map[string]any)
	if !ok {
		t.Fatalf("route.body type = %T, want map[string]any", route.body)
	}
	if got, want := body["repo_id"], "repo-1"; got != want {
		t.Fatalf("body[repo_id] = %#v, want %#v", got, want)
	}
	exclusions, ok := body["exclude_decorated_with"].([]any)
	if !ok {
		t.Fatalf("body[exclude_decorated_with] type = %T, want []any", body["exclude_decorated_with"])
	}
	if len(exclusions) != 2 {
		t.Fatalf("len(body[exclude_decorated_with]) = %d, want 2", len(exclusions))
	}
}

func TestResolveRouteMapsTraceDeploymentChain(t *testing.T) {
	t.Parallel()

	route, err := resolveRoute("trace_deployment_chain", map[string]any{
		"service_name":                 "payments-api",
		"direct_only":                  true,
		"max_depth":                    float64(6),
		"include_related_module_usage": true,
	})
	if err != nil {
		t.Fatalf("resolveRoute() error = %v, want nil", err)
	}
	if route.path != "/api/v0/impact/trace-deployment-chain" {
		t.Fatalf("route.path = %q, want /api/v0/impact/trace-deployment-chain", route.path)
	}
	body, ok := route.body.(map[string]any)
	if !ok {
		t.Fatalf("route.body type = %T, want map[string]any", route.body)
	}
	if got, want := body["service_name"], "payments-api"; got != want {
		t.Fatalf("body[service_name] = %#v, want %#v", got, want)
	}
	if got, want := body["direct_only"], true; got != want {
		t.Fatalf("body[direct_only] = %#v, want %#v", got, want)
	}
	if got, want := body["max_depth"], 6; got != want {
		t.Fatalf("body[max_depth] = %#v, want %#v", got, want)
	}
	if got, want := body["include_related_module_usage"], true; got != want {
		t.Fatalf("body[include_related_module_usage] = %#v, want %#v", got, want)
	}
}
