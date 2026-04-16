package parser

import (
	"path/filepath"
	"testing"
)

func TestDefaultEngineParsePathJavaScriptComputedClassMemberNames(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	filePath := filepath.Join(repoRoot, "computed.js")
	writeTestFile(
		t,
		filePath,
		`class Greeter {
  ["sayHello"]() {
    return "hi";
  }
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

	assertNamedBucketContains(t, got, "classes", "Greeter")
	assertNamedBucketContains(t, got, "functions", "sayHello")
}

func TestDefaultEngineParsePathJavaScriptComputedClassMemberConcatenation(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	filePath := filepath.Join(repoRoot, "computed_concat.js")
	writeTestFile(
		t,
		filePath,
		`class Greeter {
  ["say" + "Hello"]() {
    return "hi";
  }
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

	assertNamedBucketContains(t, got, "classes", "Greeter")
	assertNamedBucketContains(t, got, "functions", "sayHello")
}
