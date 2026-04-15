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

func TestDefaultEngineParsePathKotlinInfersLocalReceiverTypesForDotCalls(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	filePath := filepath.Join(repoRoot, "Usage.kt")
	writeTestFile(
		t,
		filePath,
		`package comprehensive

class User {
    fun greet(): String = "hi"
}

class Calculator {
    fun add(a: Int, b: Int): Int = a + b
}

fun String.removeSpaces(): String = this.replace(" ", "")

fun usage(): String {
    val user = User()
    val calculator = Calculator()
    val text = "Hello World"
    calculator.add(5, 10)
    user.greet()
    return text.removeSpaces()
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

	items, ok := got["function_calls"].([]map[string]any)
	if !ok {
		t.Fatalf("function_calls = %T, want []map[string]any", got["function_calls"])
	}

	want := map[string]string{
		"calculator.add":    "Calculator",
		"user.greet":        "User",
		"text.removeSpaces": "String",
	}
	for _, item := range items {
		fullName, _ := item["full_name"].(string)
		if wantType, ok := want[fullName]; ok {
			assertStringFieldValue(t, item, "inferred_obj_type", wantType)
			delete(want, fullName)
		}
	}
	if len(want) != 0 {
		t.Fatalf("missing inferred receiver calls: %#v in %#v", want, items)
	}

	extension := assertBucketItemByName(t, got, "functions", "removeSpaces")
	assertStringFieldValue(t, extension, "class_context", "String")
}
