package parser

import (
	"path/filepath"
	"testing"
)

func TestDefaultEngineParsePathPythonEmitsMetaclassMetadata(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	filePath := filepath.Join(repoRoot, "metaclass.py")
	writeTestFile(
		t,
		filePath,
		`class MetaLogger(type):
    pass

class Logged(metaclass=MetaLogger):
    pass
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

	logged := assertBucketItemByName(t, got, "classes", "Logged")
	assertStringFieldValue(t, logged, "metaclass", "MetaLogger")
}
