package parser

import (
	"path/filepath"
	"testing"
)

func TestDefaultEngineParsePathPython(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	filePath := filepath.Join(repoRoot, "service.py")
	writeTestFile(
		t,
		filePath,
		`import os

class Greeter:
    pass

def hello(name):
    value = os.path.join(name, "child")
    return value

hello("world")
`,
	)

	engine, err := DefaultEngine()
	if err != nil {
		t.Fatalf("DefaultEngine() error = %v, want nil", err)
	}

	got, err := engine.ParsePath(repoRoot, filePath, false, Options{VariableScope: "all"})
	if err != nil {
		t.Fatalf("ParsePath() error = %v, want nil", err)
	}

	if got["path"] != filePath {
		t.Fatalf("path = %#v, want %#v", got["path"], filePath)
	}
	if got["repo_path"] != repoRoot {
		t.Fatalf("repo_path = %#v, want %#v", got["repo_path"], repoRoot)
	}
	if got["lang"] != "python" {
		t.Fatalf("lang = %#v, want %#v", got["lang"], "python")
	}
	if got["is_dependency"] != false {
		t.Fatalf("is_dependency = %#v, want %#v", got["is_dependency"], false)
	}

	assertNamedBucketContains(t, got, "functions", "hello")
	assertNamedBucketContains(t, got, "classes", "Greeter")
	assertNamedBucketContains(t, got, "variables", "value")
	assertNamedBucketContains(t, got, "imports", "os")
	assertNamedBucketContains(t, got, "function_calls", "join")
}

func TestDefaultEngineParsePathGo(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	filePath := filepath.Join(repoRoot, "main.go")
	writeTestFile(
		t,
		filePath,
		`package main

import "fmt"

type Reader interface {
	Read(p []byte) (n int, err error)
}

type Point struct {
	X int
}

var Version = "1.0.0"

func Greet(name string) string {
	fmt.Println(name)
	return name
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

	if got["lang"] != "go" {
		t.Fatalf("lang = %#v, want %#v", got["lang"], "go")
	}

	assertNamedBucketContains(t, got, "functions", "Greet")
	assertNamedBucketContains(t, got, "interfaces", "Reader")
	assertNamedBucketContains(t, got, "structs", "Point")
	assertNamedBucketContains(t, got, "variables", "Version")
	assertNamedBucketContains(t, got, "imports", "fmt")
	assertNamedBucketContains(t, got, "function_calls", "Println")
}

func TestDefaultEngineParsePathRawText(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	filePath := filepath.Join(repoRoot, "templates", "config.cfg.j2")
	writeTestFile(
		t,
		filePath,
		`apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ .Values.name }}
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

	if got["lang"] != "config_template" {
		t.Fatalf("lang = %#v, want %#v", got["lang"], "config_template")
	}
	assertEmptyNamedBucket(t, got, "functions")
	assertEmptyNamedBucket(t, got, "classes")
	assertEmptyNamedBucket(t, got, "variables")
	assertEmptyNamedBucket(t, got, "imports")
	assertEmptyNamedBucket(t, got, "function_calls")
}

func TestDefaultEnginePreScanPaths(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	pythonPath := filepath.Join(repoRoot, "service.py")
	goPath := filepath.Join(repoRoot, "main.go")
	writeTestFile(
		t,
		pythonPath,
		`class Greeter:
    pass

def hello(name):
    return name
`,
	)
	writeTestFile(
		t,
		goPath,
		`package main

type Point struct{}

func Greet() {}
`,
	)

	engine, err := DefaultEngine()
	if err != nil {
		t.Fatalf("DefaultEngine() error = %v, want nil", err)
	}

	got, err := engine.PreScanPaths([]string{pythonPath, goPath})
	if err != nil {
		t.Fatalf("PreScanPaths() error = %v, want nil", err)
	}

	assertPrescanContains(t, got, "Greeter", pythonPath)
	assertPrescanContains(t, got, "hello", pythonPath)
	assertPrescanContains(t, got, "Point", goPath)
	assertPrescanContains(t, got, "Greet", goPath)
}

func writeTestFile(t *testing.T, path string, body string) {
	t.Helper()

	if err := ensureParentDirectory(path); err != nil {
		t.Fatalf("ensureParentDirectory(%q) error = %v, want nil", path, err)
	}
	if err := osWriteFile(path, []byte(body)); err != nil {
		t.Fatalf("osWriteFile(%q) error = %v, want nil", path, err)
	}
}

func assertNamedBucketContains(t *testing.T, payload map[string]any, key string, wantName string) {
	t.Helper()

	items, ok := payload[key].([]map[string]any)
	if !ok {
		t.Fatalf("%s = %T, want []map[string]any", key, payload[key])
	}
	for _, item := range items {
		name, _ := item["name"].(string)
		if name == wantName {
			return
		}
	}
	t.Fatalf("%s missing name %q in %#v", key, wantName, items)
}

func assertEmptyNamedBucket(t *testing.T, payload map[string]any, key string) {
	t.Helper()

	items, ok := payload[key].([]map[string]any)
	if !ok {
		t.Fatalf("%s = %T, want []map[string]any", key, payload[key])
	}
	if len(items) != 0 {
		t.Fatalf("%s = %#v, want empty bucket", key, items)
	}
}

func assertPrescanContains(t *testing.T, importsMap map[string][]string, name string, wantPath string) {
	t.Helper()

	paths, ok := importsMap[name]
	if !ok {
		t.Fatalf("imports map missing %q", name)
	}
	for _, path := range paths {
		if path == wantPath {
			return
		}
	}
	t.Fatalf("imports map[%q] = %#v, want path %q", name, paths, wantPath)
}
