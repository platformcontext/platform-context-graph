package main

import (
	"context"
	"errors"
	"reflect"
	"strings"
	"testing"

	"github.com/platformcontext/platform-context-graph/go/internal/runtime"
	sourceneo4j "github.com/platformcontext/platform-context-graph/go/internal/storage/neo4j"
)

func TestBootstrapCanonicalExecutorUsesNornicDBPhaseGroupsByDefault(t *testing.T) {
	t.Parallel()

	raw := &recordingBootstrapGroupExecutor{}
	executor, err := bootstrapCanonicalExecutorForGraphBackend(
		raw,
		runtime.GraphBackendNornicDB,
		func(key string) string {
			if key == nornicDBFilePhaseGroupStatementsEnv {
				return "2"
			}
			return ""
		},
		nil,
		nil,
	)
	if err != nil {
		t.Fatalf("bootstrapCanonicalExecutorForGraphBackend() error = %v, want nil", err)
	}
	if _, ok := executor.(sourceneo4j.GroupExecutor); ok {
		t.Fatal("NornicDB bootstrap executor exposes GroupExecutor, want bounded PhaseGroupExecutor only")
	}
	phaseExecutor, ok := executor.(sourceneo4j.PhaseGroupExecutor)
	if !ok {
		t.Fatal("NornicDB bootstrap executor does not implement PhaseGroupExecutor")
	}

	stmts := []sourceneo4j.Statement{
		bootstrapTestStatement("phase=files rows=1 chunk=1/6"),
		bootstrapTestStatement("phase=files rows=1 chunk=2/6"),
		bootstrapTestStatement("phase=files rows=1 chunk=3/6"),
		bootstrapTestStatement("phase=files rows=1 chunk=4/6"),
		bootstrapTestStatement("phase=files rows=1 chunk=5/6"),
		bootstrapTestStatement("phase=files rows=1 chunk=6/6"),
	}
	if err := phaseExecutor.ExecutePhaseGroup(context.Background(), stmts); err != nil {
		t.Fatalf("ExecutePhaseGroup() error = %v, want nil", err)
	}

	if got, want := raw.groupSizes, []int{2, 2, 2}; !reflect.DeepEqual(got, want) {
		t.Fatalf("group sizes = %v, want %v", got, want)
	}
}

func TestBootstrapNornicDBPhaseGroupExecutorWrapsChunkFailure(t *testing.T) {
	t.Parallel()

	rawErr := errors.New("txn too large")
	raw := &recordingBootstrapGroupExecutor{err: rawErr}
	executor := bootstrapNornicDBPhaseGroupExecutor{
		inner:             raw,
		maxStatements:     500,
		fileMaxStatements: 2,
	}

	err := executor.ExecutePhaseGroup(context.Background(), []sourceneo4j.Statement{
		bootstrapTestStatement("phase=files rows=1 chunk=1/3"),
		bootstrapTestStatement("phase=files rows=1 chunk=2/3"),
		bootstrapTestStatement("phase=files rows=1 chunk=3/3"),
	})
	if err == nil {
		t.Fatal("ExecutePhaseGroup() error = nil, want failure")
	}
	for _, want := range []string{
		"phase-group chunk 1/1",
		"statements 1-2 of 2",
		`first_statement="phase=files rows=1 chunk=1/3"`,
		rawErr.Error(),
	} {
		if !strings.Contains(err.Error(), want) {
			t.Fatalf("ExecutePhaseGroup() error = %q, want %q", err.Error(), want)
		}
	}
}

func bootstrapTestStatement(summary string) sourceneo4j.Statement {
	return sourceneo4j.Statement{
		Cypher: "RETURN $value",
		Parameters: map[string]any{
			"value":                                 1,
			sourceneo4j.StatementMetadataPhaseKey:   sourceneo4j.CanonicalPhaseFiles,
			sourceneo4j.StatementMetadataSummaryKey: summary,
		},
	}
}

type recordingBootstrapGroupExecutor struct {
	groupSizes []int
	err        error
}

func (r *recordingBootstrapGroupExecutor) Execute(context.Context, sourceneo4j.Statement) error {
	return nil
}

func (r *recordingBootstrapGroupExecutor) ExecuteGroup(_ context.Context, stmts []sourceneo4j.Statement) error {
	r.groupSizes = append(r.groupSizes, len(stmts))
	return r.err
}
