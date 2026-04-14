package query

import "testing"

func TestExtractJavaScriptSemantics(t *testing.T) {
	t.Parallel()

	semantics := ExtractJavaScriptSemantics(map[string]any{
		"docstring":   "Returns the active tab.",
		"method_kind": "getter",
	})

	if got, want := semantics.Docstring, "Returns the active tab."; got != want {
		t.Fatalf("Docstring = %q, want %q", got, want)
	}
	if got, want := semantics.MethodKind, "getter"; got != want {
		t.Fatalf("MethodKind = %q, want %q", got, want)
	}
	if !semantics.Present() {
		t.Fatal("Present() = false, want true")
	}
}

func TestExtractJavaScriptSemanticsSkipsMissingValues(t *testing.T) {
	t.Parallel()

	semantics := ExtractJavaScriptSemantics(map[string]any{
		"docstring":   "",
		"method_kind": nil,
	})

	if semantics.Present() {
		t.Fatal("Present() = true, want false")
	}
	if got := semantics.Fields(); len(got) != 0 {
		t.Fatalf("Fields() = %#v, want empty map", got)
	}
}

func TestAttachJavaScriptSemanticsClonesResult(t *testing.T) {
	t.Parallel()

	result := map[string]any{
		"entity_id": "graph-1",
		"name":      "getTab",
	}

	got := AttachJavaScriptSemantics(result, map[string]any{
		"docstring":   "Returns the active tab.",
		"method_kind": "getter",
	})

	if _, ok := result["javascript_semantics"]; ok {
		t.Fatal("result was mutated, want original map unchanged")
	}

	semantics, ok := got["javascript_semantics"].(map[string]any)
	if !ok {
		t.Fatalf("javascript_semantics type = %T, want map[string]any", got["javascript_semantics"])
	}
	if got, want := semantics["docstring"], "Returns the active tab."; got != want {
		t.Fatalf("javascript_semantics[docstring] = %#v, want %#v", got, want)
	}
	if got, want := semantics["method_kind"], "getter"; got != want {
		t.Fatalf("javascript_semantics[method_kind] = %#v, want %#v", got, want)
	}
}

func TestAttachJavaScriptSemanticsReturnsOriginalWhenEmpty(t *testing.T) {
	t.Parallel()

	result := map[string]any{
		"entity_id": "graph-1",
	}

	got := AttachJavaScriptSemantics(result, map[string]any{})

	if _, ok := got["javascript_semantics"]; ok {
		t.Fatal("javascript_semantics present, want absent")
	}
	if got["entity_id"] != "graph-1" {
		t.Fatalf("entity_id = %#v, want graph-1", got["entity_id"])
	}
}
