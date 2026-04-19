package main

import (
	"context"
	"errors"
	"testing"

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
