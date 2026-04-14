package parser

import (
	"path/filepath"
	"reflect"
	"strings"
	"testing"
)

func TestDefaultEngineParsePathPHPEmitsFunctionParametersSourceAndContext(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	filePath := filepath.Join(repoRoot, "functions.php")
	writeTestFile(
		t,
		filePath,
		`<?php
namespace Demo;

function greet(string $name, int $count): string {
    $prefix = "Hello";
    return $prefix . $name;
}

class Application {
    public function run(string $message): void {
        greet($message, 1);
    }
}
`,
	)

	engine, err := DefaultEngine()
	if err != nil {
		t.Fatalf("DefaultEngine() error = %v, want nil", err)
	}

	got, err := engine.ParsePath(repoRoot, filePath, false, Options{IndexSource: true})
	if err != nil {
		t.Fatalf("ParsePath() error = %v, want nil", err)
	}

	functionItem := assertBucketItemByName(t, got, "functions", "greet")
	phpAssertStringSliceFieldValue(t, functionItem, "parameters", []string{"$name", "$count"})
	phpAssertStringFieldContains(t, functionItem, "source", "return $prefix . $name;")

	methodItem := assertBucketItemByName(t, got, "functions", "run")
	phpAssertStringFieldValue(t, methodItem, "class_context", "Application")
	phpAssertStringFieldContains(t, methodItem, "source", "greet($message, 1);")
}

func TestDefaultEngineParsePathPHPEmitsInheritanceAndImportMetadata(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	filePath := filepath.Join(repoRoot, "types.php")
	writeTestFile(
		t,
		filePath,
		`<?php
namespace Demo;

use Demo\Library\Config as AppConfig;
use Demo\Library\Service;

class Child extends ParentClass implements Runnable, JsonSerializable {
}

interface Repository extends Identifiable, Countable {
}

trait Loggable {
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

	classItem := assertBucketItemByName(t, got, "classes", "Child")
	phpAssertStringSliceFieldValue(t, classItem, "bases", []string{"ParentClass", "Runnable", "JsonSerializable"})

	interfaceItem := assertBucketItemByName(t, got, "interfaces", "Repository")
	phpAssertStringSliceFieldValue(t, interfaceItem, "bases", []string{"Identifiable", "Countable"})

	importItem := assertBucketItemByName(t, got, "imports", "Demo\\Library\\Config")
	phpAssertStringFieldValue(t, importItem, "full_import_name", "use Demo\\Library\\Config as AppConfig;")
	phpAssertStringFieldValue(t, importItem, "alias", "AppConfig")
	phpAssertBoolFieldValue(t, importItem, "is_dependency", false)

	secondImport := assertBucketItemByName(t, got, "imports", "Demo\\Library\\Service")
	phpAssertStringFieldValue(t, secondImport, "full_import_name", "use Demo\\Library\\Service;")
	if alias, ok := secondImport["alias"]; ok && alias != nil && alias != "" {
		t.Fatalf("alias = %#v, want nil or empty", alias)
	}
}

func TestDefaultEngineParsePathPHPEmitsVariableAndCallMetadata(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	filePath := filepath.Join(repoRoot, "calls.php")
	writeTestFile(
		t,
		filePath,
		`<?php
namespace Demo;

class Config {
    private string $env;
    private bool $debug;

    public function run(string $message): void {
        $service = new Service("main");
        $greeting = greet($message);
        $service->info($greeting);
        Logger::warn("warn");
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

	envItem := assertBucketItemByName(t, got, "variables", "$env")
	phpAssertStringFieldValue(t, envItem, "context", "Config")
	phpAssertStringFieldValue(t, envItem, "class_context", "Config")

	serviceItem := assertBucketItemByName(t, got, "variables", "$service")
	phpAssertStringFieldValue(t, serviceItem, "type", "Service")
	phpAssertStringFieldValue(t, serviceItem, "context", "run")
	phpAssertNilField(t, serviceItem, "class_context")

	infoCall := assertBucketItemByName(t, got, "function_calls", "info")
	phpAssertStringFieldValue(t, infoCall, "full_name", "$service.info")
	phpAssertStringSliceFieldValue(t, infoCall, "args", []string{"$greeting"})
	assertCallContextTuple(t, infoCall, "run", "method_declaration", 8)
	phpAssertAnySliceFieldValue(t, infoCall, "class_context", []any{nil, nil})

	warnCall := assertBucketItemByName(t, got, "function_calls", "warn")
	phpAssertStringFieldValue(t, warnCall, "full_name", "Logger.warn")
	phpAssertStringSliceFieldValue(t, warnCall, "args", []string{"\"warn\""})
	phpAssertStringFieldValue(t, warnCall, "inferred_obj_type", "Logger")
	assertCallContextTuple(t, warnCall, "run", "method_declaration", 8)
	phpAssertAnySliceFieldValue(t, warnCall, "class_context", []any{nil, nil})

	newCall := assertBucketItemByName(t, got, "function_calls", "Service")
	phpAssertStringFieldValue(t, newCall, "full_name", "Service")
	phpAssertStringSliceFieldValue(t, newCall, "args", []string{"\"main\""})
	assertCallContextTuple(t, newCall, "run", "method_declaration", 8)
	phpAssertAnySliceFieldValue(t, newCall, "class_context", []any{nil, nil})
}

func TestDefaultEngineParsePathPHPEmitsStaticMethodReceiverMetadata(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	filePath := filepath.Join(repoRoot, "static_calls.php")
	writeTestFile(
		t,
		filePath,
		`<?php
namespace Demo;

class Logger {
    public static function warn(string $message): void {}
}

class Config {
    public function run(): void {
        Logger::warn("warn");
        \Demo\Logger::warn("namespaced");
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

	warnCall := assertBucketItemByName(t, got, "function_calls", "warn")
	phpAssertStringFieldValue(t, warnCall, "full_name", "Logger.warn")
	phpAssertStringFieldValue(t, warnCall, "inferred_obj_type", "Logger")

	namespacedCall := assertBucketItemByFieldValue(t, got, "function_calls", "full_name", "Demo\\Logger.warn")
	phpAssertStringFieldValue(t, namespacedCall, "name", "warn")
	phpAssertStringFieldValue(t, namespacedCall, "inferred_obj_type", "Demo\\Logger")
}

func TestDefaultEngineParsePathPHPEmitsPropertyTypeInferenceFromDeclaration(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	filePath := filepath.Join(repoRoot, "typed_properties.php")
	writeTestFile(
		t,
		filePath,
		`<?php
class Config {
    private string $env;
    private ?Service $service = null;
    private bool $debug = false;
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

	envItem := assertBucketItemByName(t, got, "variables", "$env")
	phpAssertStringFieldValue(t, envItem, "type", "string")

	serviceItem := assertBucketItemByName(t, got, "variables", "$service")
	phpAssertStringFieldValue(t, serviceItem, "type", "Service")

	debugItem := assertBucketItemByName(t, got, "variables", "$debug")
	phpAssertStringFieldValue(t, debugItem, "type", "bool")
}

func TestDefaultEngineParsePathPHPEmitsCallContextLineMetadata(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	filePath := filepath.Join(repoRoot, "context.php")
	writeTestFile(
		t,
		filePath,
		`<?php
class Demo {
    public function run(string $message): void {
        greet($message);
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

	greetCall := assertBucketItemByName(t, got, "function_calls", "greet")
	assertCallContextTuple(t, greetCall, "run", "method_declaration", 3)
}

func TestDefaultEngineParsePathPHPMultilineArgumentsAndContextLineMetadata(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	filePath := filepath.Join(repoRoot, "multiline.php")
	writeTestFile(
		t,
		filePath,
		`<?php

class Demo {
    public function build(
        string $name,
        array $options = [
            'flags' => ['cache' => true, 'retry' => false],
        ],
    ): void {
        render(
            title: "Hello",
            options: [
                'greeting' => greet($name),
                'service' => $this->service,
            ],
        );
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

	functionItem := assertBucketItemByName(t, got, "functions", "build")
	phpAssertStringSliceFieldValue(t, functionItem, "parameters", []string{"$name", "$options"})

	renderCall := assertBucketItemByName(t, got, "function_calls", "render")
	phpAssertStringSliceFieldValue(
		t,
		renderCall,
		"args",
		[]string{
			`title: "Hello"`,
			`options: [
                'greeting' => greet($name),
                'service' => $this->service,
            ]`,
		},
	)
	assertCallContextTuple(t, renderCall, "build", "method_declaration", 4)
}

func phpAssertStringFieldValue(t *testing.T, item map[string]any, field string, want string) {
	t.Helper()

	got, _ := item[field].(string)
	if got != want {
		t.Fatalf("%s = %#v, want %#v", field, got, want)
	}
}

func phpAssertStringFieldContains(t *testing.T, item map[string]any, field string, want string) {
	t.Helper()

	got, _ := item[field].(string)
	if !strings.Contains(got, want) {
		t.Fatalf("%s = %#v, want to contain %#v", field, got, want)
	}
}

func phpAssertBoolFieldValue(t *testing.T, item map[string]any, field string, want bool) {
	t.Helper()

	got, ok := item[field].(bool)
	if !ok {
		t.Fatalf("%s = %T, want bool", field, item[field])
	}
	if got != want {
		t.Fatalf("%s = %#v, want %#v", field, got, want)
	}
}

func phpAssertStringSliceFieldValue(t *testing.T, item map[string]any, field string, want []string) {
	t.Helper()

	got, ok := item[field].([]string)
	if !ok {
		t.Fatalf("%s = %T, want []string", field, item[field])
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("%s = %#v, want %#v", field, got, want)
	}
}

func phpAssertAnySliceFieldValue(t *testing.T, item map[string]any, field string, want []any) {
	t.Helper()

	got, ok := item[field].([]any)
	if !ok {
		t.Fatalf("%s = %T, want []any", field, item[field])
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("%s = %#v, want %#v", field, got, want)
	}
}

func phpAssertNilField(t *testing.T, item map[string]any, field string) {
	t.Helper()

	if value, ok := item[field]; ok && value != nil {
		t.Fatalf("%s = %#v, want nil", field, value)
	}
}

func assertBucketItemByFieldValue(
	t *testing.T,
	payload map[string]any,
	bucket string,
	field string,
	want string,
) map[string]any {
	t.Helper()

	items, ok := payload[bucket].([]map[string]any)
	if !ok {
		t.Fatalf("%s = %T, want []map[string]any", bucket, payload[bucket])
	}
	for _, item := range items {
		value, _ := item[field].(string)
		if value == want {
			return item
		}
	}
	t.Fatalf("%s missing %s=%q in %#v", bucket, field, want, items)
	return nil
}

func assertCallContextTuple(
	t *testing.T,
	item map[string]any,
	wantName string,
	wantType string,
	wantLine int,
) {
	t.Helper()

	context, ok := item["context"].([]any)
	if !ok {
		t.Fatalf("context = %T, want []any", item["context"])
	}
	if len(context) < 3 {
		t.Fatalf("context = %#v, want at least 3 items", context)
	}
	if got, _ := context[0].(string); got != wantName {
		t.Fatalf("context[0] = %#v, want %#v", got, wantName)
	}
	if got, _ := context[1].(string); got != wantType {
		t.Fatalf("context[1] = %#v, want %#v", got, wantType)
	}
	if got, ok := context[2].(int); !ok || got != wantLine {
		t.Fatalf("context[2] = %#v, want %#v", context[2], wantLine)
	}
}
