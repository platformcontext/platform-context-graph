package parser

import "path/filepath"
import "testing"

func TestDefaultEngineParsePathTypeScriptCapturesAdvancedTypeSemantics(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	filePath := filepath.Join(repoRoot, "src", "types.ts")
	writeTestFile(
		t,
		filePath,
		`namespace API {
  export type ReadonlyMap<T> = {
    readonly [K in keyof T]: T[K];
  };

  export type Response<T> = T extends string
    ? { ok: true; value: T }
    : { ok: false };
}
`,
	)

	engine, err := DefaultEngine()
	if err != nil {
		t.Fatalf("DefaultEngine() error = %v, want nil", err)
	}

	got, err := engine.ParsePath(repoRoot, filePath, false, Options{})
	if err != nil {
		t.Fatalf("ParsePath() error = %v, want nil", err)
	}

	namespace := findNamedBucketItem(t, got, "modules", "API")
	assertStringFieldValue(t, namespace, "module_kind", "namespace")

	mappedAlias := findNamedBucketItem(t, got, "type_aliases", "ReadonlyMap")
	assertStringFieldValue(t, mappedAlias, "type_alias_kind", "mapped_type")
	assertStringSliceFieldValue(t, mappedAlias, "type_parameters", []string{"T"})

	conditionalAlias := findNamedBucketItem(t, got, "type_aliases", "Response")
	assertStringFieldValue(t, conditionalAlias, "type_alias_kind", "conditional_type")
	assertStringSliceFieldValue(t, conditionalAlias, "type_parameters", []string{"T"})
}
