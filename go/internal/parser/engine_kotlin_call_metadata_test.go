package parser

import (
	"path/filepath"
	"testing"
)

func TestDefaultEngineParsePathKotlinThisReceiverCallCarriesClassContext(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	filePath := filepath.Join(repoRoot, "Worker.kt")
	writeTestFile(
		t,
		filePath,
		`package comprehensive

class Worker {
    fun helper(): String = "ok"

    fun run(): String {
        return this.helper()
    }
}

fun helper(): String = "top-level"
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

	items, ok := got["function_calls"].([]map[string]any)
	if !ok {
		t.Fatalf("function_calls = %T, want []map[string]any", got["function_calls"])
	}
	for _, item := range items {
		fullName, _ := item["full_name"].(string)
		if fullName != "this.helper" {
			continue
		}
		assertStringFieldValue(t, item, "class_context", "Worker")
		return
	}
	t.Fatalf("function_calls missing full_name=%q in %#v", "this.helper", items)
}
