package parser

import (
	"path/filepath"
	"testing"
)

func TestDefaultEngineParsePathRubyFixtures(t *testing.T) {
	t.Parallel()

	repoRoot := repoFixturePath("ecosystems", "ruby_comprehensive")
	engine, err := DefaultEngine()
	if err != nil {
		t.Fatalf("DefaultEngine() error = %v, want nil", err)
	}

	basicPath := filepath.Join(repoRoot, "basic.rb")
	basicPayload, err := engine.ParsePath(repoRoot, basicPath, false, Options{})
	if err != nil {
		t.Fatalf("ParsePath(%q) error = %v, want nil", basicPath, err)
	}
	assertNamedBucketContains(t, basicPayload, "functions", "greet")
	assertNamedBucketContains(t, basicPayload, "classes", "Application")
	assertNamedBucketContains(t, basicPayload, "modules", "Comprehensive")
	assertNamedBucketContains(t, basicPayload, "variables", "@config")
	assertNamedBucketContains(t, basicPayload, "function_calls", "Comprehensive.greet")

	mixinsPath := filepath.Join(repoRoot, "modules_mixins.rb")
	mixinsPayload, err := engine.ParsePath(repoRoot, mixinsPath, false, Options{})
	if err != nil {
		t.Fatalf("ParsePath(%q) error = %v, want nil", mixinsPath, err)
	}
	assertNamedBucketContains(t, mixinsPayload, "classes", "Service")
	assertNamedBucketContains(t, mixinsPayload, "functions", "expensive_operation")
	assertModuleInclusion(t, mixinsPayload, "Service", "Printable")
}

func TestDefaultEngineParsePathPHPFixtures(t *testing.T) {
	t.Parallel()

	repoRoot := repoFixturePath("ecosystems", "php_comprehensive")
	engine, err := DefaultEngine()
	if err != nil {
		t.Fatalf("DefaultEngine() error = %v, want nil", err)
	}

	importsPath := filepath.Join(repoRoot, "imports.php")
	importsPayload, err := engine.ParsePath(repoRoot, importsPath, false, Options{})
	if err != nil {
		t.Fatalf("ParsePath(%q) error = %v, want nil", importsPath, err)
	}
	assertNamedBucketContains(t, importsPayload, "functions", "run")
	assertNamedBucketContains(t, importsPayload, "classes", "Application")
	assertBucketContainsFieldValue(t, importsPayload, "imports", "name", "Comprehensive\\Config")
	assertNamedBucketContains(t, importsPayload, "variables", "$config")
	assertNamedBucketContains(t, importsPayload, "function_calls", "$this->service.info")

	traitsPath := filepath.Join(repoRoot, "traits.php")
	traitsPayload, err := engine.ParsePath(repoRoot, traitsPath, false, Options{})
	if err != nil {
		t.Fatalf("ParsePath(%q) error = %v, want nil", traitsPath, err)
	}
	assertNamedBucketContains(t, traitsPayload, "traits", "Loggable")
	assertNamedBucketContains(t, traitsPayload, "functions", "info")
}

func TestDefaultEngineParsePathKotlinFixtures(t *testing.T) {
	t.Parallel()

	repoRoot := repoFixturePath("ecosystems", "kotlin_comprehensive")
	engine, err := DefaultEngine()
	if err != nil {
		t.Fatalf("DefaultEngine() error = %v, want nil", err)
	}

	basicPath := filepath.Join(repoRoot, "Basic.kt")
	basicPayload, err := engine.ParsePath(repoRoot, basicPath, false, Options{})
	if err != nil {
		t.Fatalf("ParsePath(%q) error = %v, want nil", basicPath, err)
	}
	assertNamedBucketContains(t, basicPayload, "functions", "greet")
	assertNamedBucketContains(t, basicPayload, "classes", "AppConfig")
	assertNamedBucketContains(t, basicPayload, "variables", "VERSION")

	classesPath := filepath.Join(repoRoot, "Classes.kt")
	classesPayload, err := engine.ParsePath(repoRoot, classesPath, false, Options{})
	if err != nil {
		t.Fatalf("ParsePath(%q) error = %v, want nil", classesPath, err)
	}
	assertNamedBucketContains(t, classesPayload, "classes", "Point")
	assertNamedBucketContains(t, classesPayload, "classes", "Companion")
	assertFunctionWithClassContext(t, classesPayload, "create", "Companion")
}

func TestDefaultEngineParsePathSwiftFixtures(t *testing.T) {
	t.Parallel()

	repoRoot := repoFixturePath("ecosystems", "swift_comprehensive")
	engine, err := DefaultEngine()
	if err != nil {
		t.Fatalf("DefaultEngine() error = %v, want nil", err)
	}

	structsPath := filepath.Join(repoRoot, "Structs.swift")
	structsPayload, err := engine.ParsePath(repoRoot, structsPath, false, Options{})
	if err != nil {
		t.Fatalf("ParsePath(%q) error = %v, want nil", structsPath, err)
	}
	assertNamedBucketContains(t, structsPayload, "structs", "Point")
	assertNamedBucketContains(t, structsPayload, "variables", "host")
	assertNamedBucketContains(t, structsPayload, "imports", "Foundation")

	enumsPath := filepath.Join(repoRoot, "Enums.swift")
	enumsPayload, err := engine.ParsePath(repoRoot, enumsPath, false, Options{})
	if err != nil {
		t.Fatalf("ParsePath(%q) error = %v, want nil", enumsPath, err)
	}
	assertNamedBucketContains(t, enumsPayload, "enums", "Direction")
	assertNamedBucketContains(t, enumsPayload, "functions", "map")
	assertNamedBucketContains(t, enumsPayload, "function_calls", "transform")
}

func TestDefaultEngineParsePathElixirFixtures(t *testing.T) {
	t.Parallel()

	repoRoot := repoFixturePath("ecosystems", "elixir_comprehensive")
	engine, err := DefaultEngine()
	if err != nil {
		t.Fatalf("DefaultEngine() error = %v, want nil", err)
	}

	basicPath := filepath.Join(repoRoot, "basic.ex")
	basicPayload, err := engine.ParsePath(repoRoot, basicPath, false, Options{})
	if err != nil {
		t.Fatalf("ParsePath(%q) error = %v, want nil", basicPath, err)
	}
	assertNamedBucketContains(t, basicPayload, "functions", "greet")
	assertNamedBucketContains(t, basicPayload, "modules", "Comprehensive.Basic")

	importsPath := filepath.Join(repoRoot, "imports.ex")
	importsPayload, err := engine.ParsePath(repoRoot, importsPath, false, Options{})
	if err != nil {
		t.Fatalf("ParsePath(%q) error = %v, want nil", importsPath, err)
	}
	assertBucketContainsFieldValue(t, importsPayload, "imports", "name", "Logger")
	assertNamedBucketContains(t, importsPayload, "functions", "start")
	assertEmptyNamedBucket(t, importsPayload, "variables")
}

func TestDefaultEngineParsePathDartFixtures(t *testing.T) {
	t.Parallel()

	repoRoot := repoFixturePath("ecosystems", "dart_comprehensive")
	engine, err := DefaultEngine()
	if err != nil {
		t.Fatalf("DefaultEngine() error = %v, want nil", err)
	}

	asyncPath := filepath.Join(repoRoot, "async.dart")
	asyncPayload, err := engine.ParsePath(repoRoot, asyncPath, false, Options{})
	if err != nil {
		t.Fatalf("ParsePath(%q) error = %v, want nil", asyncPath, err)
	}
	assertNamedBucketContains(t, asyncPayload, "functions", "fetchData")
	assertNamedBucketContains(t, asyncPayload, "classes", "AsyncWorker")
	assertNamedBucketContains(t, asyncPayload, "imports", "dart:async")
	assertNamedBucketContains(t, asyncPayload, "function_calls", "fetchData")

	extensionsPath := filepath.Join(repoRoot, "extensions.dart")
	extensionsPayload, err := engine.ParsePath(repoRoot, extensionsPath, false, Options{})
	if err != nil {
		t.Fatalf("ParsePath(%q) error = %v, want nil", extensionsPath, err)
	}
	assertNamedBucketContains(t, extensionsPayload, "classes", "StringTools")
}

func TestDefaultEngineParsePathPerlFixtures(t *testing.T) {
	t.Parallel()

	repoRoot := repoFixturePath("ecosystems", "perl_comprehensive")
	engine, err := DefaultEngine()
	if err != nil {
		t.Fatalf("DefaultEngine() error = %v, want nil", err)
	}

	modulesPath := filepath.Join(repoRoot, "modules.pl")
	payload, err := engine.ParsePath(repoRoot, modulesPath, false, Options{})
	if err != nil {
		t.Fatalf("ParsePath(%q) error = %v, want nil", modulesPath, err)
	}
	assertNamedBucketContains(t, payload, "classes", "Utilities")
	assertNamedBucketContains(t, payload, "functions", "format_path")
	assertBucketContainsFieldValue(t, payload, "imports", "name", "File::Basename")
}

func TestDefaultEngineParsePathHaskellFixtures(t *testing.T) {
	t.Parallel()

	repoRoot := repoFixturePath("ecosystems", "haskell_comprehensive")
	engine, err := DefaultEngine()
	if err != nil {
		t.Fatalf("DefaultEngine() error = %v, want nil", err)
	}

	basicPath := filepath.Join(repoRoot, "Basic.hs")
	basicPayload, err := engine.ParsePath(repoRoot, basicPath, false, Options{})
	if err != nil {
		t.Fatalf("ParsePath(%q) error = %v, want nil", basicPath, err)
	}
	assertNamedBucketContains(t, basicPayload, "functions", "greet")
	assertNamedBucketContains(t, basicPayload, "functions", "processNames")
	assertBucketContainsFieldValue(t, basicPayload, "imports", "name", "Data.List")
	assertNamedBucketContains(t, basicPayload, "variables", "category")
}

func assertFunctionWithClassContext(
	t *testing.T,
	payload map[string]any,
	name string,
	classContext string,
) {
	t.Helper()

	items, ok := payload["functions"].([]map[string]any)
	if !ok {
		t.Fatalf("functions = %T, want []map[string]any", payload["functions"])
	}
	for _, item := range items {
		itemName, _ := item["name"].(string)
		itemContext, _ := item["class_context"].(string)
		if itemName == name && itemContext == classContext {
			return
		}
	}
	t.Fatalf("functions missing name=%q class_context=%q in %#v", name, classContext, items)
}

func assertModuleInclusion(t *testing.T, payload map[string]any, className string, moduleName string) {
	t.Helper()

	items, ok := payload["module_inclusions"].([]map[string]any)
	if !ok {
		t.Fatalf("module_inclusions = %T, want []map[string]any", payload["module_inclusions"])
	}
	for _, item := range items {
		itemClass, _ := item["class"].(string)
		itemModule, _ := item["module"].(string)
		if itemClass == className && itemModule == moduleName {
			return
		}
	}
	t.Fatalf(
		"module_inclusions missing class=%q module=%q in %#v",
		className,
		moduleName,
		items,
	)
}
