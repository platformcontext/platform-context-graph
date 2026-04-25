package main

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"testing"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/reducer"
	runtimecfg "github.com/platformcontext/platform-context-graph/go/internal/runtime"
	sourceneo4j "github.com/platformcontext/platform-context-graph/go/internal/storage/neo4j"
)

// fakeNeo4jSession records cypher calls for assertion.
type fakeNeo4jSession struct {
	calls []fakeCypherCall
	err   error
	errs  []error
}

type fakeCypherCall struct {
	Cypher     string
	Parameters map[string]any
}

func (s *fakeNeo4jSession) RunCypher(ctx context.Context, cypher string, params map[string]any) error {
	s.calls = append(s.calls, fakeCypherCall{Cypher: cypher, Parameters: params})
	if len(s.errs) > 0 {
		err := s.errs[0]
		s.errs = s.errs[1:]
		return err
	}
	return s.err
}

func (s *fakeNeo4jSession) RunCypherGroup(ctx context.Context, stmts []sourceneo4j.Statement) error {
	for _, stmt := range stmts {
		if err := s.RunCypher(ctx, stmt.Cypher, stmt.Parameters); err != nil {
			return err
		}
	}
	return nil
}

func TestReducerNeo4jExecutorExecutesStatement(t *testing.T) {
	t.Parallel()

	session := &fakeNeo4jSession{}
	executor := reducerNeo4jExecutor{session: session}

	stmt := sourceneo4j.Statement{
		Operation:  sourceneo4j.OperationCanonicalUpsert,
		Cypher:     "MERGE (w:Workload {id: $workload_id})",
		Parameters: map[string]any{"workload_id": "workload:my-api"},
	}

	err := executor.Execute(context.Background(), stmt)
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if len(session.calls) != 1 {
		t.Fatalf("session calls = %d, want 1", len(session.calls))
	}
	if session.calls[0].Cypher != stmt.Cypher {
		t.Fatalf("cypher = %q, want %q", session.calls[0].Cypher, stmt.Cypher)
	}
	if session.calls[0].Parameters["workload_id"] != "workload:my-api" {
		t.Fatalf("workload_id = %v", session.calls[0].Parameters["workload_id"])
	}
}

func TestReducerNeo4jExecutorPropagatesError(t *testing.T) {
	t.Parallel()

	session := &fakeNeo4jSession{err: errors.New("neo4j timeout")}
	executor := reducerNeo4jExecutor{session: session}

	err := executor.Execute(context.Background(), sourceneo4j.Statement{
		Cypher: "MERGE (w:Workload {id: $id})",
	})
	if err == nil {
		t.Fatal("Execute() error = nil, want non-nil")
	}
}

func TestReducerCypherExecutorExecutesCypher(t *testing.T) {
	t.Parallel()

	session := &fakeNeo4jSession{}
	executor := reducerCypherExecutor{session: session}

	err := executor.ExecuteCypher(context.Background(),
		"MERGE (w:Workload {id: $workload_id})",
		map[string]any{"workload_id": "workload:my-api"},
	)
	if err != nil {
		t.Fatalf("ExecuteCypher() error = %v", err)
	}
	if len(session.calls) != 1 {
		t.Fatalf("session calls = %d, want 1", len(session.calls))
	}
	if session.calls[0].Cypher != "MERGE (w:Workload {id: $workload_id})" {
		t.Fatalf("cypher = %q", session.calls[0].Cypher)
	}
}

func TestReducerCypherExecutorPropagatesError(t *testing.T) {
	t.Parallel()

	session := &fakeNeo4jSession{err: errors.New("connection refused")}
	executor := reducerCypherExecutor{session: session}

	err := executor.ExecuteCypher(context.Background(), "MERGE (w:Workload)", nil)
	if err == nil {
		t.Fatal("ExecuteCypher() error = nil, want non-nil")
	}
}

func TestReducerCypherExecutorRetriesTransientDeadlock(t *testing.T) {
	t.Parallel()

	session := &fakeNeo4jSession{
		errs: []error{
			errors.New("Neo4jError: Neo.TransientError.Transaction.DeadlockDetected (deadlock cycle)"),
			nil,
		},
	}
	executor := reducerCypherExecutor{session: session}

	err := executor.ExecuteCypher(context.Background(), "MERGE (w:Workload {id: $id})", map[string]any{"id": "workload:retry"})
	if err != nil {
		t.Fatalf("ExecuteCypher() error = %v, want nil after retry", err)
	}
	if got, want := len(session.calls), 2; got != want {
		t.Fatalf("session calls = %d, want %d", got, want)
	}
}

type groupCapableReducerExecutor struct {
	groupCalls int
}

func (e *groupCapableReducerExecutor) Execute(context.Context, sourceneo4j.Statement) error {
	return nil
}

func (e *groupCapableReducerExecutor) ExecuteGroup(context.Context, []sourceneo4j.Statement) error {
	e.groupCalls++
	return nil
}

type contextBlockingReducerExecutor struct{}

func (contextBlockingReducerExecutor) Execute(ctx context.Context, _ sourceneo4j.Statement) error {
	<-ctx.Done()
	return ctx.Err()
}

func (contextBlockingReducerExecutor) ExecuteGroup(ctx context.Context, _ []sourceneo4j.Statement) error {
	<-ctx.Done()
	return ctx.Err()
}

func TestSemanticEntityExecutorForGraphBackendKeepsNeo4jGroupedExecutor(t *testing.T) {
	t.Parallel()

	executor := semanticEntityExecutorForGraphBackend(&groupCapableReducerExecutor{}, runtimecfg.GraphBackendNeo4j, 0, false)
	if _, ok := executor.(sourceneo4j.GroupExecutor); !ok {
		t.Fatal("Neo4j semantic entity executor does not implement GroupExecutor")
	}
}

func TestSemanticEntityExecutorForGraphBackendHidesGroupExecutorForNornicDB(t *testing.T) {
	t.Parallel()

	inner := &groupCapableReducerExecutor{}
	executor := semanticEntityExecutorForGraphBackend(inner, runtimecfg.GraphBackendNornicDB, 0, false)
	if _, ok := executor.(sourceneo4j.GroupExecutor); ok {
		t.Fatal("NornicDB semantic entity executor implements GroupExecutor, want execute-only surface")
	}
}

func TestSemanticEntityExecutorForGraphBackendPreservesGroupedWritesForConformance(t *testing.T) {
	t.Parallel()

	inner := &groupCapableReducerExecutor{}
	executor := semanticEntityExecutorForGraphBackend(inner, runtimecfg.GraphBackendNornicDB, 0, true)
	ge, ok := executor.(sourceneo4j.GroupExecutor)
	if !ok {
		t.Fatal("NornicDB semantic entity executor does not implement GroupExecutor when conformance grouped writes are enabled")
	}
	if err := ge.ExecuteGroup(context.Background(), []sourceneo4j.Statement{{Cypher: "RETURN 1"}}); err != nil {
		t.Fatalf("ExecuteGroup() error = %v, want nil", err)
	}
	if got, want := inner.groupCalls, 1; got != want {
		t.Fatalf("inner groupCalls = %d, want %d", got, want)
	}
}

func TestSemanticEntityExecutorForGraphBackendTimesOutGroupedWrites(t *testing.T) {
	t.Parallel()

	executor := semanticEntityExecutorForGraphBackend(contextBlockingReducerExecutor{}, runtimecfg.GraphBackendNornicDB, 10*time.Millisecond, true)
	ge, ok := executor.(sourceneo4j.GroupExecutor)
	if !ok {
		t.Fatal("NornicDB grouped semantic entity executor does not implement GroupExecutor")
	}
	err := ge.ExecuteGroup(context.Background(), []sourceneo4j.Statement{{Cypher: "RETURN 1"}})
	if !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("ExecuteGroup() error = %v, want deadline exceeded", err)
	}
}

type recordingReducerStatementExecutor struct {
	calls []sourceneo4j.Statement
}

func (e *recordingReducerStatementExecutor) Execute(_ context.Context, stmt sourceneo4j.Statement) error {
	e.calls = append(e.calls, stmt)
	return nil
}

func TestSemanticEntityWriterForGraphBackendUsesBatchedRowsForNornicDB(t *testing.T) {
	t.Parallel()

	executor := &recordingReducerStatementExecutor{}
	writer, err := semanticEntityWriterForGraphBackend(executor, 100, runtimecfg.GraphBackendNornicDB, func(string) string { return "" })
	if err != nil {
		t.Fatalf("semanticEntityWriterForGraphBackend() error = %v", err)
	}

	const docstring = "buildCallChainCypher uses shortestPath((start)-[*]->(end)) for graph traversal."
	result, err := writer.WriteSemanticEntities(context.Background(), reducer.SemanticEntityWrite{
		RepoIDs: []string{"repo-1"},
		Rows: []reducer.SemanticEntityRow{
			{
				RepoID:       "repo-1",
				EntityID:     "function-go-1",
				EntityType:   "Function",
				EntityName:   "buildCallChainCypher",
				FilePath:     "/repo/go/internal/query/code_call_chain.go",
				RelativePath: "go/internal/query/code_call_chain.go",
				Language:     "go",
				StartLine:    22,
				EndLine:      178,
				Metadata: map[string]any{
					"docstring":     docstring,
					"class_context": "CodeHandler",
				},
			},
		},
	})
	if err != nil {
		t.Fatalf("WriteSemanticEntities() error = %v", err)
	}
	if got, want := result.CanonicalWrites, 1; got != want {
		t.Fatalf("CanonicalWrites = %d, want %d", got, want)
	}
	if got, want := len(executor.calls), 2; got != want {
		t.Fatalf("executor calls = %d, want %d", got, want)
	}

	stmt := executor.calls[1]
	if !strings.Contains(stmt.Cypher, "UNWIND $rows AS row") {
		t.Fatalf("upsert cypher = %q, want batched UNWIND rows", stmt.Cypher)
	}
	if !strings.Contains(stmt.Cypher, "SET n += row.properties") {
		t.Fatalf("upsert cypher = %q, want row property map merge", stmt.Cypher)
	}
	if strings.Contains(stmt.Cypher, "shortestPath") {
		t.Fatalf("upsert cypher inlined docstring metadata: %s", stmt.Cypher)
	}
	rows, ok := stmt.Parameters["rows"].([]map[string]any)
	if !ok {
		t.Fatalf("rows parameter type = %T, want []map[string]any", stmt.Parameters["rows"])
	}
	properties, ok := rows[0]["properties"].(map[string]any)
	if !ok {
		t.Fatalf("rows[0][properties] type = %T, want map[string]any", rows[0]["properties"])
	}
	if got, want := properties["docstring"], docstring; got != want {
		t.Fatalf("properties[docstring] = %#v, want %#v", got, want)
	}
}

func TestSemanticEntityWriterForGraphBackendAppliesNornicDBLabelBatchCaps(t *testing.T) {
	t.Parallel()

	executor := &recordingReducerStatementExecutor{}
	writer, err := semanticEntityWriterForGraphBackend(executor, 100, runtimecfg.GraphBackendNornicDB, func(key string) string {
		if key == nornicDBSemanticEntityLabelBatchEnv {
			return "Function=2,Variable=3"
		}
		return ""
	})
	if err != nil {
		t.Fatalf("semanticEntityWriterForGraphBackend() error = %v", err)
	}

	result, err := writer.WriteSemanticEntities(context.Background(), reducer.SemanticEntityWrite{
		RepoIDs: []string{"repo-1"},
		Rows: []reducer.SemanticEntityRow{
			semanticFunctionRow("function-go-1"),
			semanticFunctionRow("function-go-2"),
			semanticFunctionRow("function-go-3"),
			semanticVariableRow("variable-go-1"),
			semanticVariableRow("variable-go-2"),
			semanticVariableRow("variable-go-3"),
			semanticVariableRow("variable-go-4"),
		},
	})
	if err != nil {
		t.Fatalf("WriteSemanticEntities() error = %v", err)
	}
	if got, want := result.CanonicalWrites, 7; got != want {
		t.Fatalf("CanonicalWrites = %d, want %d", got, want)
	}

	var functionBatches, variableBatches []int
	for _, call := range executor.calls {
		label, _ := call.Parameters[sourceneo4j.StatementMetadataEntityLabelKey].(string)
		rows, _ := call.Parameters["rows"].([]map[string]any)
		switch label {
		case "Function":
			functionBatches = append(functionBatches, len(rows))
		case "Variable":
			variableBatches = append(variableBatches, len(rows))
		}
	}
	if got, want := intsString(functionBatches), "[2 1]"; got != want {
		t.Fatalf("Function batch sizes = %s, want %s", got, want)
	}
	if got, want := intsString(variableBatches), "[3 1]"; got != want {
		t.Fatalf("Variable batch sizes = %s, want %s", got, want)
	}
}

func TestSemanticEntityWriterForGraphBackendAppliesDefaultNornicDBModuleCap(t *testing.T) {
	t.Parallel()

	executor := &recordingReducerStatementExecutor{}
	writer, err := semanticEntityWriterForGraphBackend(executor, 100, runtimecfg.GraphBackendNornicDB, func(string) string {
		return ""
	})
	if err != nil {
		t.Fatalf("semanticEntityWriterForGraphBackend() error = %v", err)
	}

	rows := make([]reducer.SemanticEntityRow, 0, 11)
	for i := 0; i < 11; i++ {
		rows = append(rows, semanticModuleRow(fmt.Sprintf("module-ts-%02d", i)))
	}
	result, err := writer.WriteSemanticEntities(context.Background(), reducer.SemanticEntityWrite{
		RepoIDs: []string{"repo-1"},
		Rows:    rows,
	})
	if err != nil {
		t.Fatalf("WriteSemanticEntities() error = %v", err)
	}
	if got, want := result.CanonicalWrites, 11; got != want {
		t.Fatalf("CanonicalWrites = %d, want %d", got, want)
	}

	var moduleBatches []int
	for _, call := range executor.calls {
		label, _ := call.Parameters[sourceneo4j.StatementMetadataEntityLabelKey].(string)
		if label != "Module" {
			continue
		}
		rows, _ := call.Parameters["rows"].([]map[string]any)
		moduleBatches = append(moduleBatches, len(rows))
	}
	if got, want := intsString(moduleBatches), "[10 1]"; got != want {
		t.Fatalf("Module batch sizes = %s, want %s", got, want)
	}
}

func TestSemanticEntityWriterForGraphBackendRejectsInvalidNornicDBLabelBatchCaps(t *testing.T) {
	t.Parallel()

	_, err := semanticEntityWriterForGraphBackend(&recordingReducerStatementExecutor{}, 100, runtimecfg.GraphBackendNornicDB, func(key string) string {
		if key == nornicDBSemanticEntityLabelBatchEnv {
			return "Function=0"
		}
		return ""
	})
	if err == nil {
		t.Fatal("semanticEntityWriterForGraphBackend() error = nil, want non-nil")
	}
	if !strings.Contains(err.Error(), nornicDBSemanticEntityLabelBatchEnv) {
		t.Fatalf("semanticEntityWriterForGraphBackend() error = %q, want env name", err)
	}
}

func semanticFunctionRow(id string) reducer.SemanticEntityRow {
	return reducer.SemanticEntityRow{
		RepoID:       "repo-1",
		EntityID:     id,
		EntityType:   "Function",
		EntityName:   id,
		FilePath:     "/repo/main.go",
		RelativePath: "main.go",
		Language:     "go",
		StartLine:    1,
		EndLine:      2,
	}
}

func semanticVariableRow(id string) reducer.SemanticEntityRow {
	return reducer.SemanticEntityRow{
		RepoID:       "repo-1",
		EntityID:     id,
		EntityType:   "Variable",
		EntityName:   id,
		FilePath:     "/repo/main.go",
		RelativePath: "main.go",
		Language:     "go",
		StartLine:    1,
		EndLine:      1,
	}
}

func semanticModuleRow(id string) reducer.SemanticEntityRow {
	return reducer.SemanticEntityRow{
		RepoID:       "repo-1",
		EntityID:     id,
		EntityType:   "Module",
		EntityName:   id,
		FilePath:     "/repo/main.ts",
		RelativePath: "main.ts",
		Language:     "typescript",
		StartLine:    1,
		EndLine:      1,
	}
}

func intsString(values []int) string {
	return fmt.Sprint(values)
}
