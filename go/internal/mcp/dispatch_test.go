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
