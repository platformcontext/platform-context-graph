package graph

import (
	"context"
	"errors"
	"strings"
	"testing"
)

func TestSchemaStatementsContainsExpectedConstraints(t *testing.T) {
	t.Parallel()

	stmts := SchemaStatements()
	if len(stmts) == 0 {
		t.Fatal("SchemaStatements() returned empty slice")
	}

	expected := []string{
		"CREATE CONSTRAINT repository_id IF NOT EXISTS",
		"CREATE CONSTRAINT repository_path IF NOT EXISTS",
		"CREATE CONSTRAINT path IF NOT EXISTS FOR (f:File)",
		"CREATE CONSTRAINT directory_path IF NOT EXISTS",
		"CREATE CONSTRAINT function_unique IF NOT EXISTS",
		"CREATE CONSTRAINT class_unique IF NOT EXISTS",
		"CREATE CONSTRAINT parameter_unique IF NOT EXISTS",
		"CREATE CONSTRAINT platform_id IF NOT EXISTS",
		"CREATE CONSTRAINT source_local_record_unique IF NOT EXISTS",
	}
	for _, want := range expected {
		found := false
		for _, stmt := range stmts {
			if strings.Contains(stmt, want) {
				found = true
				break
			}
		}
		if !found {
			t.Errorf("SchemaStatements() missing constraint containing %q", want)
		}
	}
}

func TestSchemaStatementsContainsPerformanceIndexes(t *testing.T) {
	t.Parallel()

	stmts := SchemaStatements()

	expected := []string{
		"CREATE INDEX function_lang IF NOT EXISTS",
		"CREATE INDEX class_lang IF NOT EXISTS",
		"CREATE INDEX function_name IF NOT EXISTS",
		"CREATE INDEX class_name IF NOT EXISTS",
		"CREATE INDEX workload_name IF NOT EXISTS",
	}
	for _, want := range expected {
		found := false
		for _, stmt := range stmts {
			if strings.Contains(stmt, want) {
				found = true
				break
			}
		}
		if !found {
			t.Errorf("SchemaStatements() missing index containing %q", want)
		}
	}
}

func TestSchemaStatementsContainsUIDConstraints(t *testing.T) {
	t.Parallel()

	stmts := SchemaStatements()

	expected := []string{
		"function_uid_unique",
		"class_uid_unique",
		"variable_uid_unique",
		"typedef_uid_unique",
		"terraform_resource_uid_unique",
	}
	for _, want := range expected {
		found := false
		for _, stmt := range stmts {
			if strings.Contains(stmt, want) {
				found = true
				break
			}
		}
		if !found {
			t.Errorf("SchemaStatements() missing UID constraint containing %q", want)
		}
	}
}

func TestSchemaStatementsContainsFulltextIndexes(t *testing.T) {
	t.Parallel()

	stmts := SchemaStatements()

	found := false
	for _, stmt := range stmts {
		if strings.Contains(stmt, "code_search_index") {
			found = true
			break
		}
	}
	if !found {
		t.Error("SchemaStatements() missing code_search_index fulltext statement")
	}

	found = false
	for _, stmt := range stmts {
		if strings.Contains(stmt, "infra_search_index") {
			found = true
			break
		}
	}
	if !found {
		t.Error("SchemaStatements() missing infra_search_index fulltext statement")
	}
}

func TestEnsureSchemaExecutesAllStatements(t *testing.T) {
	t.Parallel()

	executor := &schemaRecordingExecutor{}
	err := EnsureSchema(context.Background(), executor, nil)
	if err != nil {
		t.Fatalf("EnsureSchema() error = %v, want nil", err)
	}

	expectedCount := len(SchemaStatements())
	if got := len(executor.calls); got != expectedCount {
		t.Fatalf("executor calls = %d, want %d", got, expectedCount)
	}
}

func TestEnsureSchemaRequiresExecutor(t *testing.T) {
	t.Parallel()

	err := EnsureSchema(context.Background(), nil, nil)
	if err == nil {
		t.Fatal("EnsureSchema() error = nil, want non-nil")
	}
	if !strings.Contains(err.Error(), "executor is required") {
		t.Fatalf("error = %q, want 'executor is required'", err.Error())
	}
}

func TestEnsureSchemaFulltextFallback(t *testing.T) {
	t.Parallel()

	// Executor that fails on procedure-based fulltext calls but succeeds on
	// CREATE FULLTEXT INDEX fallback.
	executor := &schemaRecordingExecutor{
		failOn: func(cypher string) bool {
			return strings.Contains(cypher, "db.index.fulltext.createNodeIndex")
		},
	}

	err := EnsureSchema(context.Background(), executor, nil)
	if err != nil {
		t.Fatalf("EnsureSchema() error = %v, want nil", err)
	}

	// Verify fallback statements were executed.
	var fallbackCount int
	for _, call := range executor.calls {
		if strings.Contains(call.Cypher, "CREATE FULLTEXT INDEX") {
			fallbackCount++
		}
	}
	if fallbackCount != len(schemaFulltextIndexes) {
		t.Fatalf("fallback fulltext calls = %d, want %d", fallbackCount, len(schemaFulltextIndexes))
	}
}

func TestEnsureSchemaContinuesOnFailure(t *testing.T) {
	t.Parallel()

	// Executor that fails on every call.
	executor := &schemaRecordingExecutor{
		failOn: func(_ string) bool { return true },
	}

	err := EnsureSchema(context.Background(), executor, nil)
	if err != nil {
		t.Fatalf("EnsureSchema() error = %v, want nil (warnings logged, not returned)", err)
	}

	// Should still attempt all statements.
	if len(executor.calls) == 0 {
		t.Fatal("executor should have been called at least once")
	}
}

func TestLabelToSnake(t *testing.T) {
	t.Parallel()

	tests := []struct {
		input string
		want  string
	}{
		{"Function", "function"},
		{"Class", "class"},
		{"CrossplaneXRD", "crossplane_x_r_d"},
		{"TerraformResource", "terraform_resource"},
		{"K8sResource", "k8s_resource"},
	}

	for _, tt := range tests {
		if got := labelToSnake(tt.input); got != tt.want {
			t.Errorf("labelToSnake(%q) = %q, want %q", tt.input, got, tt.want)
		}
	}
}

type schemaRecordingExecutor struct {
	calls  []CypherStatement
	failOn func(string) bool
}

func (r *schemaRecordingExecutor) ExecuteCypher(_ context.Context, stmt CypherStatement) error {
	r.calls = append(r.calls, stmt)
	if r.failOn != nil && r.failOn(stmt.Cypher) {
		return errors.New("simulated schema error")
	}
	return nil
}
