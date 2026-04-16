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

func TestDefaultEngineParsePathTSXCapturesMemoAndForwardRefWrappers(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	filePath := filepath.Join(repoRoot, "src", "Screen.tsx")
	writeTestFile(
		t,
		filePath,
		`import { forwardRef, memo } from "react";

const MemoButton = memo(() => <button type="button" />);

const ForwardedButton = forwardRef(function ForwardedButton(_props, ref) {
  return <button ref={ref} type="button" />;
});
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

	memoButton := findNamedBucketItem(t, got, "components", "MemoButton")
	assertStringFieldValue(t, memoButton, "component_wrapper_kind", "memo")

	forwardedButton := findNamedBucketItem(t, got, "components", "ForwardedButton")
	assertStringFieldValue(t, forwardedButton, "component_wrapper_kind", "forwardRef")
}
