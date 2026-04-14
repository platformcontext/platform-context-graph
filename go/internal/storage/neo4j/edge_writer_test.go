package neo4j

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/reducer"
)

func TestEdgeWriterWriteEdgesPlatformInfraDispatch(t *testing.T) {
	t.Parallel()

	executor := &recordingExecutor{}
	writer := NewEdgeWriter(executor)

	rows := []reducer.SharedProjectionIntentRow{
		{
			IntentID:     "i1",
			RepositoryID: "repo-1",
			Payload: map[string]any{
				"repo_id":              "repo-1",
				"platform_id":          "platform:eks:aws:cluster-1:prod:us-east-1",
				"platform_name":        "cluster-1",
				"platform_kind":        "eks",
				"platform_provider":    "aws",
				"platform_environment": "prod",
				"platform_region":      "us-east-1",
				"platform_locator":     "arn:aws:eks:us-east-1:123:cluster/cluster-1",
			},
		},
	}

	err := writer.WriteEdges(context.Background(), reducer.DomainPlatformInfra, rows, "finalization/workloads")
	if err != nil {
		t.Fatalf("WriteEdges() error = %v", err)
	}
	if got, want := len(executor.calls), 1; got != want {
		t.Fatalf("executor calls = %d, want %d", got, want)
	}
	if executor.calls[0].Operation != OperationCanonicalUpsert {
		t.Fatalf("operation = %q, want %q", executor.calls[0].Operation, OperationCanonicalUpsert)
	}
	if !strings.Contains(executor.calls[0].Cypher, "PROVISIONS_PLATFORM") {
		t.Fatalf("cypher missing PROVISIONS_PLATFORM: %s", executor.calls[0].Cypher)
	}
}

func TestEdgeWriterWriteEdgesRepoDependencyDispatch(t *testing.T) {
	t.Parallel()

	executor := &recordingExecutor{}
	writer := NewEdgeWriter(executor)

	rows := []reducer.SharedProjectionIntentRow{
		{
			IntentID:     "i1",
			RepositoryID: "repo-a",
			Payload: map[string]any{
				"repo_id":        "repo-a",
				"target_repo_id": "repo-b",
			},
		},
	}

	err := writer.WriteEdges(context.Background(), reducer.DomainRepoDependency, rows, "finalization/workloads")
	if err != nil {
		t.Fatalf("WriteEdges() error = %v", err)
	}
	if got, want := len(executor.calls), 1; got != want {
		t.Fatalf("executor calls = %d, want %d", got, want)
	}
	if !strings.Contains(executor.calls[0].Cypher, "DEPENDS_ON") {
		t.Fatalf("cypher missing DEPENDS_ON: %s", executor.calls[0].Cypher)
	}
	if !strings.Contains(executor.calls[0].Cypher, "source_repo:Repository") {
		t.Fatalf("cypher missing Repository match: %s", executor.calls[0].Cypher)
	}
}

func TestEdgeWriterWriteEdgesWorkloadDependencyDispatch(t *testing.T) {
	t.Parallel()

	executor := &recordingExecutor{}
	writer := NewEdgeWriter(executor)

	rows := []reducer.SharedProjectionIntentRow{
		{
			IntentID:     "i1",
			RepositoryID: "repo-a",
			Payload: map[string]any{
				"workload_id":        "wl-a",
				"target_workload_id": "wl-b",
			},
		},
	}

	err := writer.WriteEdges(context.Background(), reducer.DomainWorkloadDependency, rows, "finalization/workloads")
	if err != nil {
		t.Fatalf("WriteEdges() error = %v", err)
	}
	if got, want := len(executor.calls), 1; got != want {
		t.Fatalf("executor calls = %d, want %d", got, want)
	}
	if !strings.Contains(executor.calls[0].Cypher, "DEPENDS_ON") {
		t.Fatalf("cypher missing DEPENDS_ON: %s", executor.calls[0].Cypher)
	}
	if !strings.Contains(executor.calls[0].Cypher, "source:Workload") {
		t.Fatalf("cypher missing Workload match: %s", executor.calls[0].Cypher)
	}
}

func TestEdgeWriterWriteEdgesCodeCallDispatch(t *testing.T) {
	t.Parallel()

	executor := &recordingExecutor{}
	writer := NewEdgeWriter(executor)

	rows := []reducer.SharedProjectionIntentRow{
		{
			IntentID:     "i1",
			RepositoryID: "repo-a",
			Payload: map[string]any{
				"repo_id":          "repo-a",
				"caller_entity_id": "entity:function:caller",
				"callee_entity_id": "entity:function:callee",
			},
		},
	}

	err := writer.WriteEdges(context.Background(), reducer.DomainCodeCalls, rows, "parser/code-calls")
	if err != nil {
		t.Fatalf("WriteEdges() error = %v", err)
	}
	if got, want := len(executor.calls), 1; got != want {
		t.Fatalf("executor calls = %d, want %d", got, want)
	}
	if !strings.Contains(executor.calls[0].Cypher, "CALLS") {
		t.Fatalf("cypher missing CALLS: %s", executor.calls[0].Cypher)
	}
	if got, want := executor.calls[0].Parameters["caller_entity_id"], "entity:function:caller"; got != want {
		t.Fatalf("caller_entity_id = %v, want %v", got, want)
	}
}

func TestEdgeWriterWriteEdgesMultipleRows(t *testing.T) {
	t.Parallel()

	executor := &recordingExecutor{}
	writer := NewEdgeWriter(executor)

	rows := []reducer.SharedProjectionIntentRow{
		{IntentID: "i1", RepositoryID: "repo-a", Payload: map[string]any{"repo_id": "repo-a", "target_repo_id": "repo-b"}},
		{IntentID: "i2", RepositoryID: "repo-a", Payload: map[string]any{"repo_id": "repo-a", "target_repo_id": "repo-c"}},
	}

	err := writer.WriteEdges(context.Background(), reducer.DomainRepoDependency, rows, "finalization/workloads")
	if err != nil {
		t.Fatalf("WriteEdges() error = %v", err)
	}
	if got, want := len(executor.calls), 2; got != want {
		t.Fatalf("executor calls = %d, want %d", got, want)
	}
}

func TestEdgeWriterWriteEdgesEmptyRowsIsNoop(t *testing.T) {
	t.Parallel()

	executor := &recordingExecutor{}
	writer := NewEdgeWriter(executor)

	err := writer.WriteEdges(context.Background(), reducer.DomainRepoDependency, nil, "finalization/workloads")
	if err != nil {
		t.Fatalf("WriteEdges() error = %v", err)
	}
	if len(executor.calls) != 0 {
		t.Fatalf("executor calls = %d, want 0", len(executor.calls))
	}
}

func TestEdgeWriterWriteEdgesUnknownDomainReturnsError(t *testing.T) {
	t.Parallel()

	executor := &recordingExecutor{}
	writer := NewEdgeWriter(executor)

	rows := []reducer.SharedProjectionIntentRow{
		{IntentID: "i1", Payload: map[string]any{}},
	}

	err := writer.WriteEdges(context.Background(), "unknown_domain", rows, "finalization/workloads")
	if err == nil {
		t.Fatal("WriteEdges() error = nil, want non-nil")
	}
	if !strings.Contains(err.Error(), "unsupported domain") {
		t.Fatalf("error = %q, want 'unsupported domain'", err.Error())
	}
}

func TestEdgeWriterWriteEdgesPropagatesExecutorError(t *testing.T) {
	t.Parallel()

	executor := &recordingExecutor{errAtCall: errors.New("neo4j timeout")}
	writer := NewEdgeWriter(executor)

	rows := []reducer.SharedProjectionIntentRow{
		{IntentID: "i1", RepositoryID: "repo-a", Payload: map[string]any{"repo_id": "repo-a", "target_repo_id": "repo-b"}},
	}

	err := writer.WriteEdges(context.Background(), reducer.DomainRepoDependency, rows, "finalization/workloads")
	if err == nil {
		t.Fatal("WriteEdges() error = nil, want non-nil")
	}
	if !strings.Contains(err.Error(), "neo4j timeout") {
		t.Fatalf("error = %q, want executor error propagated", err.Error())
	}
}

func TestEdgeWriterRetractEdgesPlatformInfraDispatch(t *testing.T) {
	t.Parallel()

	executor := &recordingExecutor{}
	writer := NewEdgeWriter(executor)

	rows := []reducer.SharedProjectionIntentRow{
		{IntentID: "i1", RepositoryID: "repo-1", Payload: map[string]any{"repo_id": "repo-1"}},
		{IntentID: "i2", RepositoryID: "repo-2", Payload: map[string]any{"repo_id": "repo-2"}},
	}

	err := writer.RetractEdges(context.Background(), reducer.DomainPlatformInfra, rows, "finalization/workloads")
	if err != nil {
		t.Fatalf("RetractEdges() error = %v", err)
	}
	if got, want := len(executor.calls), 1; got != want {
		t.Fatalf("executor calls = %d, want %d (retraction is batched)", got, want)
	}
	if !strings.Contains(executor.calls[0].Cypher, "PROVISIONS_PLATFORM") {
		t.Fatalf("cypher missing PROVISIONS_PLATFORM: %s", executor.calls[0].Cypher)
	}
	if !strings.Contains(executor.calls[0].Cypher, "DELETE rel") {
		t.Fatalf("cypher missing DELETE: %s", executor.calls[0].Cypher)
	}
}

func TestEdgeWriterRetractEdgesRepoDependencyDispatch(t *testing.T) {
	t.Parallel()

	executor := &recordingExecutor{}
	writer := NewEdgeWriter(executor)

	rows := []reducer.SharedProjectionIntentRow{
		{IntentID: "i1", RepositoryID: "repo-a", Payload: map[string]any{"repo_id": "repo-a"}},
	}

	err := writer.RetractEdges(context.Background(), reducer.DomainRepoDependency, rows, "finalization/workloads")
	if err != nil {
		t.Fatalf("RetractEdges() error = %v", err)
	}
	if got, want := len(executor.calls), 1; got != want {
		t.Fatalf("executor calls = %d, want %d", got, want)
	}
	if !strings.Contains(executor.calls[0].Cypher, "source_repo:Repository") {
		t.Fatalf("cypher missing Repository match: %s", executor.calls[0].Cypher)
	}
}

func TestEdgeWriterRetractEdgesWorkloadDependencyDispatch(t *testing.T) {
	t.Parallel()

	executor := &recordingExecutor{}
	writer := NewEdgeWriter(executor)

	rows := []reducer.SharedProjectionIntentRow{
		{IntentID: "i1", RepositoryID: "repo-a", Payload: map[string]any{"repo_id": "repo-a"}},
	}

	err := writer.RetractEdges(context.Background(), reducer.DomainWorkloadDependency, rows, "finalization/workloads")
	if err != nil {
		t.Fatalf("RetractEdges() error = %v", err)
	}
	if got, want := len(executor.calls), 1; got != want {
		t.Fatalf("executor calls = %d, want %d", got, want)
	}
	if !strings.Contains(executor.calls[0].Cypher, "source:Workload") {
		t.Fatalf("cypher missing Workload match: %s", executor.calls[0].Cypher)
	}
}

func TestEdgeWriterRetractEdgesCodeCallDispatch(t *testing.T) {
	t.Parallel()

	executor := &recordingExecutor{}
	writer := NewEdgeWriter(executor)

	rows := []reducer.SharedProjectionIntentRow{
		{IntentID: "i1", RepositoryID: "repo-a", Payload: map[string]any{"repo_id": "repo-a"}},
	}

	err := writer.RetractEdges(context.Background(), reducer.DomainCodeCalls, rows, "parser/code-calls")
	if err != nil {
		t.Fatalf("RetractEdges() error = %v", err)
	}
	if got, want := len(executor.calls), 1; got != want {
		t.Fatalf("executor calls = %d, want %d", got, want)
	}
	if !strings.Contains(executor.calls[0].Cypher, "CALLS") {
		t.Fatalf("cypher missing CALLS: %s", executor.calls[0].Cypher)
	}
	if !strings.Contains(executor.calls[0].Cypher, "source.repo_id IN $repo_ids") {
		t.Fatalf("cypher missing repo_id filter: %s", executor.calls[0].Cypher)
	}
}

func TestEdgeWriterRetractEdgesEmptyRowsIsNoop(t *testing.T) {
	t.Parallel()

	executor := &recordingExecutor{}
	writer := NewEdgeWriter(executor)

	err := writer.RetractEdges(context.Background(), reducer.DomainPlatformInfra, nil, "finalization/workloads")
	if err != nil {
		t.Fatalf("RetractEdges() error = %v", err)
	}
	if len(executor.calls) != 0 {
		t.Fatalf("executor calls = %d, want 0", len(executor.calls))
	}
}

func TestEdgeWriterRetractEdgesUnknownDomainReturnsError(t *testing.T) {
	t.Parallel()

	executor := &recordingExecutor{}
	writer := NewEdgeWriter(executor)

	rows := []reducer.SharedProjectionIntentRow{
		{IntentID: "i1", RepositoryID: "repo-a", Payload: map[string]any{"repo_id": "repo-a"}},
	}

	err := writer.RetractEdges(context.Background(), "unknown_domain", rows, "finalization/workloads")
	if err == nil {
		t.Fatal("RetractEdges() error = nil, want non-nil")
	}
	if !strings.Contains(err.Error(), "unsupported domain") {
		t.Fatalf("error = %q, want 'unsupported domain'", err.Error())
	}
}

func TestEdgeWriterRetractEdgesPropagatesExecutorError(t *testing.T) {
	t.Parallel()

	executor := &recordingExecutor{errAtCall: errors.New("connection refused")}
	writer := NewEdgeWriter(executor)

	rows := []reducer.SharedProjectionIntentRow{
		{IntentID: "i1", RepositoryID: "repo-a", Payload: map[string]any{"repo_id": "repo-a"}},
	}

	err := writer.RetractEdges(context.Background(), reducer.DomainRepoDependency, rows, "finalization/workloads")
	if err == nil {
		t.Fatal("RetractEdges() error = nil, want non-nil")
	}
	if !strings.Contains(err.Error(), "connection refused") {
		t.Fatalf("error = %q, want executor error propagated", err.Error())
	}
}

func TestEdgeWriterRequiresExecutor(t *testing.T) {
	t.Parallel()

	writer := NewEdgeWriter(nil)

	rows := []reducer.SharedProjectionIntentRow{
		{IntentID: "i1", RepositoryID: "repo-a", Payload: map[string]any{"repo_id": "repo-a", "target_repo_id": "repo-b"}},
	}

	err := writer.WriteEdges(context.Background(), reducer.DomainRepoDependency, rows, "finalization/workloads")
	if err == nil {
		t.Fatal("WriteEdges() error = nil, want non-nil")
	}
	if !strings.Contains(err.Error(), "executor is required") {
		t.Fatalf("error = %q, want 'executor is required'", err.Error())
	}
}

// Suppress unused import for time package used only by SharedProjectionIntentRow.
var _ = time.Now
