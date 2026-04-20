package collector

import (
	"context"
	"errors"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/parser"
)

func TestNativeRepositorySnapshotterUsesSCIPWhenEnabled(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	callerPath := filepath.Join(repoRoot, "caller.py")
	calleePath := filepath.Join(repoRoot, "callee.py")
	writeCollectorTestFile(
		t,
		callerPath,
		"from callee import callee\n\ndef handle():\n    return callee(1)\n",
	)
	writeCollectorTestFile(
		t,
		calleePath,
		"def callee(x):\n    return x\n",
	)

	engine, err := parser.DefaultEngine()
	if err != nil {
		t.Fatalf("DefaultEngine() error = %v, want nil", err)
	}
	resolvedCallerPath, err := filepath.EvalSymlinks(callerPath)
	if err != nil {
		resolvedCallerPath = callerPath
	}
	resolvedCalleePath, err := filepath.EvalSymlinks(calleePath)
	if err != nil {
		resolvedCalleePath = calleePath
	}

	indexer := &stubSCIPIndexer{available: map[string]bool{"python": true}}
	scipParser := &stubSCIPResultParser{
		result: parser.SCIPParseResult{
			Files: map[string]map[string]any{
				resolvedCallerPath: {
					"path":                resolvedCallerPath,
					"lang":                "python",
					"is_dependency":       false,
					"functions":           []map[string]any{{"name": "handle", "line_number": 3, "end_line": 3, "args": []string{}, "return_type": "int"}},
					"classes":             []map[string]any{},
					"variables":           []map[string]any{},
					"imports":             []map[string]any{},
					"function_calls_scip": []map[string]any{{"caller_symbol": "pkg/caller#handle().", "caller_file": resolvedCallerPath, "caller_line": 3, "callee_symbol": "pkg/callee#callee().", "callee_file": resolvedCalleePath, "callee_line": 1, "callee_name": "callee", "ref_line": 4}},
				},
				resolvedCalleePath: {
					"path":                resolvedCalleePath,
					"lang":                "python",
					"is_dependency":       false,
					"functions":           []map[string]any{{"name": "callee", "line_number": 1, "end_line": 1, "args": []string{"x"}, "return_type": "int"}},
					"classes":             []map[string]any{},
					"variables":           []map[string]any{},
					"imports":             []map[string]any{},
					"function_calls_scip": []map[string]any{},
				},
			},
			SymbolTable: map[string]map[string]any{},
		},
	}

	snapshotter := NativeRepositorySnapshotter{
		Engine: engine,
		SCIP: SnapshotSCIPConfig{
			Enabled:   true,
			Languages: []string{"python"},
			Indexer:   indexer,
			Parser:    scipParser,
		},
		Now: func() time.Time {
			return time.Date(2026, time.April, 13, 12, 0, 0, 0, time.UTC)
		},
	}

	got, err := snapshotter.SnapshotRepository(
		context.Background(),
		SelectedRepository{RepoPath: repoRoot},
	)
	if err != nil {
		t.Fatalf("SnapshotRepository() error = %v, want nil", err)
	}

	if indexer.runCalls != 1 {
		t.Fatalf("SCIP indexer run calls = %d, want 1", indexer.runCalls)
	}
	if scipParser.parseCalls != 1 {
		t.Fatalf("SCIP parser calls = %d, want 1", scipParser.parseCalls)
	}

	callerFile := collectorFileByBaseName(t, got.FileData, "caller.py")
	functions, _ := callerFile["functions"].([]map[string]any)
	if len(functions) != 1 {
		t.Fatalf("len(functions) = %d, want 1", len(functions))
	}
	if source, _ := functions[0]["source"].(string); !strings.Contains(source, "def handle()") {
		t.Fatalf("functions[0].source = %#v, want python source body", functions[0]["source"])
	}
	callEdges, _ := callerFile["function_calls_scip"].([]map[string]any)
	if len(callEdges) != 1 {
		t.Fatalf(
			"len(function_calls_scip) = %d, want 1 (indexer calls=%d parser calls=%d file=%#v)",
			len(callEdges),
			indexer.runCalls,
			scipParser.parseCalls,
			callerFile["function_calls_scip"],
		)
	}
}

func TestNativeRepositorySnapshotterFallsBackWhenSCIPParserFails(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	writeCollectorTestFile(
		t,
		filepath.Join(repoRoot, "app.py"),
		"def handler():\n    return 1\n",
	)

	engine, err := parser.DefaultEngine()
	if err != nil {
		t.Fatalf("DefaultEngine() error = %v, want nil", err)
	}

	snapshotter := NativeRepositorySnapshotter{
		Engine: engine,
		SCIP: SnapshotSCIPConfig{
			Enabled:   true,
			Languages: []string{"python"},
			Indexer:   &stubSCIPIndexer{available: map[string]bool{"python": true}},
			Parser:    &stubSCIPResultParser{err: errors.New("boom")},
		},
	}

	got, err := snapshotter.SnapshotRepository(
		context.Background(),
		SelectedRepository{RepoPath: repoRoot},
	)
	if err != nil {
		t.Fatalf("SnapshotRepository() error = %v, want nil", err)
	}

	if len(got.FileData) != 1 {
		t.Fatalf("len(FileData) = %d, want 1", len(got.FileData))
	}
	parsed := got.FileData[0]
	functions, _ := parsed["functions"].([]map[string]any)
	if len(functions) != 1 || functions[0]["name"] != "handler" {
		t.Fatalf("functions = %#v, want tree-sitter fallback output", functions)
	}
	if _, ok := parsed["function_calls_scip"]; ok {
		t.Fatalf("function_calls_scip present after fallback: %#v", parsed["function_calls_scip"])
	}
}

type stubSCIPIndexer struct {
	available map[string]bool
	runCalls  int
}

func (s *stubSCIPIndexer) IsAvailable(lang string) bool {
	return s.available[lang]
}

func (s *stubSCIPIndexer) Run(_ context.Context, _ string, _ string, outputDir string) (string, error) {
	s.runCalls++
	return filepath.Join(outputDir, "index.scip"), nil
}

type stubSCIPResultParser struct {
	result     parser.SCIPParseResult
	err        error
	parseCalls int
}

func (s *stubSCIPResultParser) Parse(_, _ string) (parser.SCIPParseResult, error) {
	s.parseCalls++
	if s.err != nil {
		return parser.SCIPParseResult{}, s.err
	}
	return s.result, nil
}

func collectorFileByBaseName(t *testing.T, files []map[string]any, baseName string) map[string]any {
	t.Helper()

	for _, file := range files {
		path, _ := file["path"].(string)
		if filepath.Base(path) == baseName {
			return file
		}
	}
	t.Fatalf("no parsed file found for %q in %#v", baseName, files)
	return nil
}
