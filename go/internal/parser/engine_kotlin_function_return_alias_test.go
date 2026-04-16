package parser

import (
	"path/filepath"
	"testing"
)

func TestDefaultEngineParsePathKotlinInfersSameFileFunctionReturnTypeAliasCalls(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	filePath := filepath.Join(repoRoot, "Usage.kt")
	writeTestFile(
		t,
		filePath,
		`package comprehensive

class Service {
    fun info(): String = "ok"
}

fun createService(): Service = Service()

fun usage(): String {
    val provider = createService()
    return provider.info()
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

	for _, item := range items {
		fullName, _ := item["full_name"].(string)
		if fullName != "provider.info" {
			continue
		}
		assertStringFieldValue(t, item, "inferred_obj_type", "Service")
		return
	}
	t.Fatalf("function_calls missing full_name=%q in %#v", "provider.info", items)
}

func TestDefaultEngineParsePathKotlinInfersFunctionReturnReceiverChainsForDotCalls(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	filePath := filepath.Join(repoRoot, "Usage.kt")
	writeTestFile(
		t,
		filePath,
		`package comprehensive

class Service {
    fun info(): String = "ok"
}

class Factory {
    fun createService(): Service = Service()
}

fun usage(): String {
    val factory = Factory()
    return factory.createService().info()
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

	for _, item := range items {
		fullName, _ := item["full_name"].(string)
		if fullName != "factory.createService().info" {
			continue
		}
		assertStringFieldValue(t, item, "inferred_obj_type", "Service")
		return
	}
	t.Fatalf("function_calls missing full_name=%q in %#v", "factory.createService().info", items)
}

func TestDefaultEngineParsePathKotlinInfersNestedFunctionReturnAssignmentReceiverCallsForDotCalls(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	filePath := filepath.Join(repoRoot, "Usage.kt")
	writeTestFile(
		t,
		filePath,
		`package comprehensive

class Service {
    fun info(): String = "ok"
}

class Factory {
    fun createService(): Service = Service()
}

fun createFactory(): Factory = Factory()

fun usage(): String {
    val service = createFactory().createService()
    return service.info()
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
		"createFactory().createService": "Factory",
		"service.info":                  "Service",
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
}

func TestDefaultEngineParsePathKotlinInfersSiblingFileFunctionReturnTypeAliasCalls(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	apiPath := filepath.Join(repoRoot, "Api.kt")
	usagePath := filepath.Join(repoRoot, "Usage.kt")
	writeTestFile(
		t,
		apiPath,
		`package comprehensive

class Service {
    fun info(): String = "ok"
}

class Factory {
    fun createService(): Service = Service()
}

fun createFactory(): Factory = Factory()
`,
	)
	writeTestFile(
		t,
		usagePath,
		`package comprehensive

fun usage(): String {
    val service = createFactory().createService()
    return service.info()
}
`,
	)

	engine, err := DefaultEngine()
	if err != nil {
		t.Fatalf("DefaultEngine() error = %v, want nil", err)
	}

	got, err := engine.ParsePath(repoRoot, usagePath, false, Options{})
	if err != nil {
		t.Fatalf("ParsePath() error = %v, want nil", err)
	}

	items, ok := got["function_calls"].([]map[string]any)
	if !ok {
		t.Fatalf("function_calls = %T, want []map[string]any", got["function_calls"])
	}

	want := map[string]string{
		"createFactory().createService": "Factory",
		"service.info":                  "Service",
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
}

func TestDefaultEngineParsePathKotlinPrefersPackageAwareSiblingFunctionReturnTypesForDotCalls(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	apiPath := filepath.Join(repoRoot, "Api.kt")
	otherPath := filepath.Join(repoRoot, "Other.kt")
	usagePath := filepath.Join(repoRoot, "Usage.kt")
	writeTestFile(
		t,
		apiPath,
		`package comprehensive

class Service {
    fun info(): String = "ok"
}

class Factory {
    fun createService(): Service = Service()
}

fun createFactory(): Factory = Factory()
`,
	)
	writeTestFile(
		t,
		otherPath,
		`package otherpkg

class OtherFactory {
    fun createService(): String = "wrong"
}

fun createFactory(): OtherFactory = OtherFactory()
`,
	)
	writeTestFile(
		t,
		usagePath,
		`package comprehensive

fun usage(): String {
    val service = createFactory().createService()
    return service.info()
}
`,
	)

	engine, err := DefaultEngine()
	if err != nil {
		t.Fatalf("DefaultEngine() error = %v, want nil", err)
	}

	got, err := engine.ParsePath(repoRoot, usagePath, false, Options{})
	if err != nil {
		t.Fatalf("ParsePath() error = %v, want nil", err)
	}

	items, ok := got["function_calls"].([]map[string]any)
	if !ok {
		t.Fatalf("function_calls = %T, want []map[string]any", got["function_calls"])
	}

	want := map[string]string{
		"createFactory().createService": "Factory",
		"service.info":                  "Service",
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
}
