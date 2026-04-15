package parser

import (
	"path/filepath"
	"reflect"
	"strings"
	"testing"
)

func TestDefaultEngineParsePathPHPInfersAliasedNewExpressionReceiverCalls(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	filePath := filepath.Join(repoRoot, "aliased_new.php")
	writeTestFile(
		t,
		filePath,
		`<?php
class Service {
    public function info(string $message): void {}
}

class Config {
    public function run(string $message): void {
        $service = new Service();
        $logger = $service;
        $logger->info($message);
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

	loggerItem := assertBucketItemByFieldValue(t, got, "variables", "name", "$logger")
	phpAssertStringFieldValue(t, loggerItem, "type", "Service")

	infoCall := assertBucketItemByFieldValue(t, got, "function_calls", "full_name", "$logger.info")
	phpAssertStringFieldValue(t, infoCall, "inferred_obj_type", "Service")
}

func TestDefaultEngineParsePathPHPInfersAliasedThisPropertyReceiverCalls(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	filePath := filepath.Join(repoRoot, "aliased_property.php")
	writeTestFile(
		t,
		filePath,
		`<?php
class Service {
    public function info(string $message): void {}
}

class Config {
    private Service $service;

    public function run(string $message): void {
        $logger = $this->service;
        $logger->info($message);
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

	loggerItem := assertBucketItemByFieldValue(t, got, "variables", "name", "$logger")
	phpAssertStringFieldValue(t, loggerItem, "type", "Service")

	infoCall := assertBucketItemByFieldValue(t, got, "function_calls", "full_name", "$logger.info")
	phpAssertStringFieldValue(t, infoCall, "inferred_obj_type", "Service")
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
