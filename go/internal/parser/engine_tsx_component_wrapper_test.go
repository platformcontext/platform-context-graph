package parser

import "path/filepath"
import "testing"

func TestDefaultEngineParsePathTSXCapturesReactFCComponentTypeAssertion(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	filePath := filepath.Join(repoRoot, "src", "Screen.tsx")
	writeTestFile(
		t,
		filePath,
		`import type { FC } from "react";

const Dynamic = component as React.FC<{ title: string }>;
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

	dynamicVar := findNamedBucketItem(t, got, "variables", "Dynamic")
	assertStringFieldValue(t, dynamicVar, "component_type_assertion", "React.FC")
}
