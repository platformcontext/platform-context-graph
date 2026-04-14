package reducer

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/platformcontext/platform-context-graph/go/internal/facts"
	"github.com/platformcontext/platform-context-graph/go/internal/parser"
)

func TestExtractCodeCallRowsResolvesKotlinThisReceiverCallsUsingClassContext(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	callerPath := filepath.Join(repoRoot, "Worker.kt")

	writeFile := func(path string, contents string) {
		t.Helper()
		if err := os.WriteFile(path, []byte(contents), 0o600); err != nil {
			t.Fatalf("WriteFile(%q) error = %v, want nil", path, err)
		}
	}

	writeFile(callerPath, `package comprehensive

class Worker {
    fun helper(): String = "ok"

    fun run(): String {
        return this.helper()
    }
}

fun helper(): String = "top-level"
`)

	engine, err := parser.DefaultEngine()
	if err != nil {
		t.Fatalf("DefaultEngine() error = %v, want nil", err)
	}

	callerPayload, err := engine.ParsePath(repoRoot, callerPath, false, parser.Options{})
	if err != nil {
		t.Fatalf("ParsePath(%q) error = %v, want nil", callerPath, err)
	}
	if functions, ok := callerPayload["functions"].([]map[string]any); ok {
		for _, function := range functions {
			name, _ := function["name"].(string)
			classContext, _ := function["class_context"].(string)
			switch {
			case name == "run":
				function["end_line"] = 7
				function["uid"] = "content-entity:kotlin-run"
			case name == "helper" && classContext == "Worker":
				function["uid"] = "content-entity:kotlin-worker-helper"
			case name == "helper":
				function["uid"] = "content-entity:kotlin-top-level-helper"
			}
		}
	}
	envelopes := []facts.Envelope{
		{
			FactKind: "repository",
			Payload: map[string]any{
				"repo_id": "repo-kotlin",
			},
		},
		{
			FactKind: "file",
			Payload: map[string]any{
				"repo_id":          "repo-kotlin",
				"relative_path":    "Worker.kt",
				"parsed_file_data": callerPayload,
			},
		},
	}

	entityIndex := buildCodeEntityIndex(envelopes)
	calls, ok := callerPayload["function_calls"].([]map[string]any)
	if !ok || len(calls) != 1 {
		t.Fatalf("function_calls = %#v, want exactly one Kotlin call", callerPayload["function_calls"])
	}
	if got := resolveSameFileCalleeEntityID(entityIndex, callerPath, "Worker.kt", calls[0]); got == "" {
		t.Fatalf(
			"resolved same-file callee: %q (candidates=%v, names=%v)",
			got,
			entityIndex.uniqueNameByPath,
			codeCallExactCandidateNames(calls[0], "kotlin"),
		)
	}

	_, rows := ExtractCodeCallRows(envelopes)
	if len(rows) != 1 {
		t.Fatalf("len(rows) = %d, want 1", len(rows))
	}
	if got, want := rows[0]["callee_entity_id"], "content-entity:kotlin-worker-helper"; got != want {
		t.Fatalf("callee_entity_id = %#v, want %#v", got, want)
	}
}
