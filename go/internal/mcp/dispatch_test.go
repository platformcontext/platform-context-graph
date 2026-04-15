package mcp

import "testing"

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
