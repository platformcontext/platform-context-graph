package query

import "testing"

func TestBuildEntitySemanticSummaryTypeScriptClass(t *testing.T) {
	t.Parallel()

	entity := map[string]any{
		"labels": []string{"Class"},
		"name":   "Demo",
		"metadata": map[string]any{
			"decorators":      []any{"@sealed"},
			"type_parameters": []any{"T"},
		},
	}

	got := buildEntitySemanticSummary(entity)
	want := "Class Demo uses decorators @sealed and declares type parameters T."
	if got != want {
		t.Fatalf("buildEntitySemanticSummary() = %q, want %q", got, want)
	}
}

func TestBuildEntitySemanticSummaryPythonFunction(t *testing.T) {
	t.Parallel()

	entity := map[string]any{
		"labels": []string{"Function"},
		"name":   "handler",
		"metadata": map[string]any{
			"decorators": []any{"@route"},
			"async":      true,
			"docstring":  "Handles incoming requests.",
		},
	}

	got := buildEntitySemanticSummary(entity)
	want := "Function handler is async, uses decorators @route, and is documented as \"Handles incoming requests.\"."
	if got != want {
		t.Fatalf("buildEntitySemanticSummary() = %q, want %q", got, want)
	}
}

func TestBuildEntitySemanticSummaryTypeAnnotation(t *testing.T) {
	t.Parallel()

	entity := map[string]any{
		"labels": []string{"TypeAnnotation"},
		"name":   "user_id",
		"metadata": map[string]any{
			"type": "UUID",
		},
	}

	got := buildEntitySemanticSummary(entity)
	want := "TypeAnnotation user_id is annotated as UUID."
	if got != want {
		t.Fatalf("buildEntitySemanticSummary() = %q, want %q", got, want)
	}
}

func TestBuildEntitySemanticSummaryComponent(t *testing.T) {
	t.Parallel()

	entity := map[string]any{
		"labels": []string{"Component"},
		"name":   "Button",
		"metadata": map[string]any{
			"framework": "react",
		},
	}

	got := buildEntitySemanticSummary(entity)
	want := "Component Button is associated with the react framework."
	if got != want {
		t.Fatalf("buildEntitySemanticSummary() = %q, want %q", got, want)
	}
}

func TestBuildEntitySemanticSummaryJavaScriptFunction(t *testing.T) {
	t.Parallel()

	entity := map[string]any{
		"labels": []string{"Function"},
		"name":   "getTab",
		"metadata": map[string]any{
			"docstring":   "Returns the active tab.",
			"method_kind": "getter",
		},
	}

	got := buildEntitySemanticSummary(entity)
	want := "Function getTab has method kind getter and is documented as \"Returns the active tab.\"."
	if got != want {
		t.Fatalf("buildEntitySemanticSummary() = %q, want %q", got, want)
	}
}

func TestBuildEntitySemanticSummaryEmptyWhenNoUsefulMetadata(t *testing.T) {
	t.Parallel()

	entity := map[string]any{
		"labels": []string{"Function"},
		"name":   "noop",
	}

	if got := buildEntitySemanticSummary(entity); got != "" {
		t.Fatalf("buildEntitySemanticSummary() = %q, want empty", got)
	}
}
