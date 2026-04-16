package neo4j

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"testing"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/reducer"
)

func TestEdgeWriterWriteEdgesPlatformInfraDispatch(t *testing.T) {
	t.Parallel()

	executor := &recordingExecutor{}
	writer := NewEdgeWriter(executor, 0)

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
	writer := NewEdgeWriter(executor, 0)

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
	writer := NewEdgeWriter(executor, 0)

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
	writer := NewEdgeWriter(executor, 0)

	rows := []reducer.SharedProjectionIntentRow{
		{
			IntentID:     "i1",
			RepositoryID: "repo-a",
			Payload: map[string]any{
				"repo_id":          "repo-a",
				"caller_entity_id": "entity:function:caller",
				"callee_entity_id": "entity:function:callee",
				"call_kind":        "jsx_component",
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
	if !strings.Contains(executor.calls[0].Cypher, "REFERENCES") {
		t.Fatalf("cypher missing REFERENCES branch: %s", executor.calls[0].Cypher)
	}
	if !strings.Contains(executor.calls[0].Cypher, "CALLS") {
		t.Fatalf("cypher missing CALLS branch: %s", executor.calls[0].Cypher)
	}
	if !strings.Contains(executor.calls[0].Cypher, "UNWIND") {
		t.Fatalf("cypher missing UNWIND: %s", executor.calls[0].Cypher)
	}
	batchRows, ok := executor.calls[0].Parameters["rows"].([]map[string]any)
	if !ok || len(batchRows) != 1 {
		t.Fatalf("expected 1 row in batch, got %v", executor.calls[0].Parameters["rows"])
	}
	if got, want := batchRows[0]["caller_entity_id"], "entity:function:caller"; got != want {
		t.Fatalf("caller_entity_id = %v, want %v", got, want)
	}
	if got, want := batchRows[0]["call_kind"], "jsx_component"; got != want {
		t.Fatalf("call_kind = %v, want %v", got, want)
	}
}

func TestEdgeWriterWriteEdgesPythonMetaclassDispatch(t *testing.T) {
	t.Parallel()

	executor := &recordingExecutor{}
	writer := NewEdgeWriter(executor, 0)

	rows := []reducer.SharedProjectionIntentRow{
		{
			IntentID:     "i1",
			RepositoryID: "repo-a",
			Payload: map[string]any{
				"repo_id":           "repo-a",
				"source_entity_id":  "entity:class:logged",
				"target_entity_id":  "entity:class:meta",
				"relationship_type": "USES_METACLASS",
			},
		},
	}

	err := writer.WriteEdges(context.Background(), reducer.DomainCodeCalls, rows, "parser/python-metaclass")
	if err != nil {
		t.Fatalf("WriteEdges() error = %v", err)
	}
	if got, want := len(executor.calls), 1; got != want {
		t.Fatalf("executor calls = %d, want %d", got, want)
	}
	if !strings.Contains(executor.calls[0].Cypher, "USES_METACLASS") {
		t.Fatalf("cypher missing USES_METACLASS branch: %s", executor.calls[0].Cypher)
	}
	batchRows, ok := executor.calls[0].Parameters["rows"].([]map[string]any)
	if !ok || len(batchRows) != 1 {
		t.Fatalf("expected 1 row in batch, got %v", executor.calls[0].Parameters["rows"])
	}
	if got, want := batchRows[0]["source_entity_id"], "entity:class:logged"; got != want {
		t.Fatalf("source_entity_id = %v, want %v", got, want)
	}
	if got, want := batchRows[0]["target_entity_id"], "entity:class:meta"; got != want {
		t.Fatalf("target_entity_id = %v, want %v", got, want)
	}
	if got, want := batchRows[0]["relationship_type"], "USES_METACLASS"; got != want {
		t.Fatalf("relationship_type = %v, want %v", got, want)
	}
}

func TestEdgeWriterWriteEdgesMultipleRowsBatched(t *testing.T) {
	t.Parallel()

	executor := &recordingExecutor{}
	writer := NewEdgeWriter(executor, 0)

	rows := []reducer.SharedProjectionIntentRow{
		{IntentID: "i1", RepositoryID: "repo-a", Payload: map[string]any{"repo_id": "repo-a", "target_repo_id": "repo-b"}},
		{IntentID: "i2", RepositoryID: "repo-a", Payload: map[string]any{"repo_id": "repo-a", "target_repo_id": "repo-c"}},
	}

	err := writer.WriteEdges(context.Background(), reducer.DomainRepoDependency, rows, "finalization/workloads")
	if err != nil {
		t.Fatalf("WriteEdges() error = %v", err)
	}
	if got, want := len(executor.calls), 1; got != want {
		t.Fatalf("executor calls = %d, want %d (batched)", got, want)
	}
	batchRows, ok := executor.calls[0].Parameters["rows"].([]map[string]any)
	if !ok {
		t.Fatal("expected rows parameter to be []map[string]any")
	}
	if got, want := len(batchRows), 2; got != want {
		t.Fatalf("batch rows = %d, want %d", got, want)
	}
}

func TestEdgeWriterWriteEdgesEmptyRowsIsNoop(t *testing.T) {
	t.Parallel()

	executor := &recordingExecutor{}
	writer := NewEdgeWriter(executor, 0)

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
	writer := NewEdgeWriter(executor, 0)

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
	writer := NewEdgeWriter(executor, 0)

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
	writer := NewEdgeWriter(executor, 0)

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
	writer := NewEdgeWriter(executor, 0)

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
	writer := NewEdgeWriter(executor, 0)

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
	writer := NewEdgeWriter(executor, 0)

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
	if !strings.Contains(executor.calls[0].Cypher, "CALLS|REFERENCES") {
		t.Fatalf("cypher missing CALLS|REFERENCES retract: %s", executor.calls[0].Cypher)
	}
	if !strings.Contains(executor.calls[0].Cypher, "source.repo_id IN $repo_ids") {
		t.Fatalf("cypher missing repo_id filter: %s", executor.calls[0].Cypher)
	}
}

func TestEdgeWriterRetractEdgesEmptyRowsIsNoop(t *testing.T) {
	t.Parallel()

	executor := &recordingExecutor{}
	writer := NewEdgeWriter(executor, 0)

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
	writer := NewEdgeWriter(executor, 0)

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
	writer := NewEdgeWriter(executor, 0)

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

	writer := NewEdgeWriter(nil, 0)

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

func TestBatchedWriteEdgesRespectsBatchSize(t *testing.T) {
	t.Parallel()

	executor := &recordingExecutor{}
	writer := NewEdgeWriter(executor, 2) // batch size = 2

	rows := []reducer.SharedProjectionIntentRow{
		{IntentID: "i1", RepositoryID: "r1", Payload: map[string]any{"repo_id": "r1", "target_repo_id": "r2"}},
		{IntentID: "i2", RepositoryID: "r1", Payload: map[string]any{"repo_id": "r1", "target_repo_id": "r3"}},
		{IntentID: "i3", RepositoryID: "r1", Payload: map[string]any{"repo_id": "r1", "target_repo_id": "r4"}},
		{IntentID: "i4", RepositoryID: "r1", Payload: map[string]any{"repo_id": "r1", "target_repo_id": "r5"}},
		{IntentID: "i5", RepositoryID: "r1", Payload: map[string]any{"repo_id": "r1", "target_repo_id": "r6"}},
	}

	err := writer.WriteEdges(context.Background(), reducer.DomainRepoDependency, rows, "finalization/workloads")
	if err != nil {
		t.Fatalf("WriteEdges() error = %v", err)
	}
	// 5 rows at batch_size=2 → 3 batches (2, 2, 1)
	if got, want := len(executor.calls), 3; got != want {
		t.Fatalf("executor calls = %d, want %d", got, want)
	}
	// First two batches have 2 rows each
	for i := 0; i < 2; i++ {
		batchRows := executor.calls[i].Parameters["rows"].([]map[string]any)
		if got, want := len(batchRows), 2; got != want {
			t.Fatalf("batch %d rows = %d, want %d", i, got, want)
		}
	}
	// Last batch has 1 row
	lastRows := executor.calls[2].Parameters["rows"].([]map[string]any)
	if got, want := len(lastRows), 1; got != want {
		t.Fatalf("last batch rows = %d, want %d", got, want)
	}
}

func TestBatchedWriteEdgesDefaultBatchSize(t *testing.T) {
	t.Parallel()

	executor := &recordingExecutor{}
	writer := NewEdgeWriter(executor, 0) // uses DefaultBatchSize (500)

	// Create 1000 rows — should produce 2 batches of 500
	rows := make([]reducer.SharedProjectionIntentRow, 1000)
	for i := range rows {
		rows[i] = reducer.SharedProjectionIntentRow{
			IntentID:     fmt.Sprintf("i%d", i),
			RepositoryID: "r1",
			Payload:      map[string]any{"repo_id": "r1", "target_repo_id": fmt.Sprintf("r%d", i+2)},
		}
	}

	err := writer.WriteEdges(context.Background(), reducer.DomainRepoDependency, rows, "finalization/workloads")
	if err != nil {
		t.Fatalf("WriteEdges() error = %v", err)
	}
	if got, want := len(executor.calls), 2; got != want {
		t.Fatalf("executor calls = %d, want %d", got, want)
	}
}

func TestBatchedWriteEdgesSkipsEmptyRequiredFields(t *testing.T) {
	t.Parallel()

	executor := &recordingExecutor{}
	writer := NewEdgeWriter(executor, 0)

	rows := []reducer.SharedProjectionIntentRow{
		// Valid row
		{IntentID: "i1", RepositoryID: "r1", Payload: map[string]any{"repo_id": "r1", "target_repo_id": "r2"}},
		// Missing repo_id — should be skipped
		{IntentID: "i2", RepositoryID: "r1", Payload: map[string]any{"repo_id": "", "target_repo_id": "r3"}},
		// Missing target_repo_id — should be skipped
		{IntentID: "i3", RepositoryID: "r1", Payload: map[string]any{"repo_id": "r1", "target_repo_id": ""}},
		// Valid row
		{IntentID: "i4", RepositoryID: "r1", Payload: map[string]any{"repo_id": "r1", "target_repo_id": "r4"}},
	}

	err := writer.WriteEdges(context.Background(), reducer.DomainRepoDependency, rows, "finalization/workloads")
	if err != nil {
		t.Fatalf("WriteEdges() error = %v", err)
	}
	if got, want := len(executor.calls), 1; got != want {
		t.Fatalf("executor calls = %d, want %d", got, want)
	}
	batchRows := executor.calls[0].Parameters["rows"].([]map[string]any)
	if got, want := len(batchRows), 2; got != want {
		t.Fatalf("batch rows = %d, want %d (invalid rows filtered)", got, want)
	}
}

func TestBatchedWriteEdgesAllRowsInvalidIsNoop(t *testing.T) {
	t.Parallel()

	executor := &recordingExecutor{}
	writer := NewEdgeWriter(executor, 0)

	rows := []reducer.SharedProjectionIntentRow{
		{IntentID: "i1", RepositoryID: "r1", Payload: map[string]any{"repo_id": "", "target_repo_id": ""}},
		{IntentID: "i2", RepositoryID: "r1", Payload: map[string]any{}},
	}

	err := writer.WriteEdges(context.Background(), reducer.DomainRepoDependency, rows, "finalization/workloads")
	if err != nil {
		t.Fatalf("WriteEdges() error = %v", err)
	}
	if got := len(executor.calls); got != 0 {
		t.Fatalf("executor calls = %d, want 0 (all rows filtered)", got)
	}
}

func TestBatchedWriteEdgesParameterFidelity(t *testing.T) {
	t.Parallel()

	executor := &recordingExecutor{}
	writer := NewEdgeWriter(executor, 0)

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

	err := writer.WriteEdges(context.Background(), reducer.DomainPlatformInfra, rows, "test-evidence")
	if err != nil {
		t.Fatalf("WriteEdges() error = %v", err)
	}

	batchRows := executor.calls[0].Parameters["rows"].([]map[string]any)
	row := batchRows[0]

	expectedKeys := []string{
		"repo_id", "platform_id", "platform_name", "platform_kind",
		"platform_provider", "platform_environment", "platform_region",
		"platform_locator", "evidence_source",
	}
	for _, key := range expectedKeys {
		if _, ok := row[key]; !ok {
			t.Errorf("missing key %q in row map", key)
		}
	}
	if got, want := row["evidence_source"], "test-evidence"; got != want {
		t.Errorf("evidence_source = %v, want %v", got, want)
	}
	if got, want := row["platform_name"], "cluster-1"; got != want {
		t.Errorf("platform_name = %v, want %v", got, want)
	}
}

func TestBatchedWriteEdgesUsesUNWINDCypher(t *testing.T) {
	t.Parallel()

	domains := []struct {
		domain   string
		payload  map[string]any
		contains string
	}{
		{
			domain:   reducer.DomainPlatformInfra,
			payload:  map[string]any{"repo_id": "r1", "platform_id": "p1"},
			contains: "UNWIND $rows AS row",
		},
		{
			domain:   reducer.DomainRepoDependency,
			payload:  map[string]any{"repo_id": "r1", "target_repo_id": "r2"},
			contains: "UNWIND $rows AS row",
		},
		{
			domain:   reducer.DomainWorkloadDependency,
			payload:  map[string]any{"workload_id": "w1", "target_workload_id": "w2"},
			contains: "UNWIND $rows AS row",
		},
		{
			domain:   reducer.DomainCodeCalls,
			payload:  map[string]any{"caller_entity_id": "c1", "callee_entity_id": "c2"},
			contains: "UNWIND $rows AS row",
		},
	}

	for _, tc := range domains {
		t.Run(tc.domain, func(t *testing.T) {
			t.Parallel()
			executor := &recordingExecutor{}
			writer := NewEdgeWriter(executor, 0)

			rows := []reducer.SharedProjectionIntentRow{
				{IntentID: "i1", RepositoryID: "r1", Payload: tc.payload},
			}
			err := writer.WriteEdges(context.Background(), tc.domain, rows, "test")
			if err != nil {
				t.Fatalf("WriteEdges(%s) error = %v", tc.domain, err)
			}
			if !strings.Contains(executor.calls[0].Cypher, tc.contains) {
				t.Fatalf("cypher missing %q: %s", tc.contains, executor.calls[0].Cypher)
			}
		})
	}
}

func TestEdgeWriterWriteEdgesInheritanceDispatch(t *testing.T) {
	t.Parallel()

	executor := &recordingExecutor{}
	writer := NewEdgeWriter(executor, 0)

	rows := []reducer.SharedProjectionIntentRow{
		{
			IntentID:     "i1",
			RepositoryID: "repo-a",
			Payload: map[string]any{
				"child_entity_id":   "entity:class:child",
				"parent_entity_id":  "entity:class:parent",
				"repo_id":           "repo-a",
				"relationship_type": "INHERITS",
			},
		},
	}

	err := writer.WriteEdges(context.Background(), reducer.DomainInheritanceEdges, rows, "reducer/inheritance")
	if err != nil {
		t.Fatalf("WriteEdges() error = %v", err)
	}
	if got, want := len(executor.calls), 1; got != want {
		t.Fatalf("executor calls = %d, want %d", got, want)
	}
	if !strings.Contains(executor.calls[0].Cypher, "INHERITS") {
		t.Fatalf("cypher missing INHERITS: %s", executor.calls[0].Cypher)
	}
	if !strings.Contains(executor.calls[0].Cypher, "UNWIND") {
		t.Fatalf("cypher missing UNWIND: %s", executor.calls[0].Cypher)
	}
	batchRows, ok := executor.calls[0].Parameters["rows"].([]map[string]any)
	if !ok || len(batchRows) != 1 {
		t.Fatalf("expected 1 row in batch, got %v", executor.calls[0].Parameters["rows"])
	}
	if got, want := batchRows[0]["child_entity_id"], "entity:class:child"; got != want {
		t.Fatalf("child_entity_id = %v, want %v", got, want)
	}
	if got, want := batchRows[0]["parent_entity_id"], "entity:class:parent"; got != want {
		t.Fatalf("parent_entity_id = %v, want %v", got, want)
	}
	if got, want := batchRows[0]["evidence_source"], "reducer/inheritance"; got != want {
		t.Fatalf("evidence_source = %v, want %v", got, want)
	}
}

func TestEdgeWriterWriteEdgesInheritanceSkipsEmptyFields(t *testing.T) {
	t.Parallel()

	executor := &recordingExecutor{}
	writer := NewEdgeWriter(executor, 0)

	rows := []reducer.SharedProjectionIntentRow{
		{IntentID: "i1", RepositoryID: "r1", Payload: map[string]any{"child_entity_id": "", "parent_entity_id": "p1"}},
		{IntentID: "i2", RepositoryID: "r1", Payload: map[string]any{"child_entity_id": "c1", "parent_entity_id": ""}},
	}

	err := writer.WriteEdges(context.Background(), reducer.DomainInheritanceEdges, rows, "reducer/inheritance")
	if err != nil {
		t.Fatalf("WriteEdges() error = %v", err)
	}
	if got := len(executor.calls); got != 0 {
		t.Fatalf("executor calls = %d, want 0 (all rows filtered)", got)
	}
}

func TestEdgeWriterWriteEdgesSQLRelationshipDispatch(t *testing.T) {
	t.Parallel()

	executor := &recordingExecutor{}
	writer := NewEdgeWriter(executor, 0)

	rows := []reducer.SharedProjectionIntentRow{
		{
			IntentID:     "i1",
			RepositoryID: "repo-a",
			Payload: map[string]any{
				"source_entity_id":  "entity:sql_view:my_view",
				"target_entity_id":  "entity:sql_table:users",
				"repo_id":           "repo-a",
				"relationship_type": "REFERENCES_TABLE",
			},
		},
	}

	err := writer.WriteEdges(context.Background(), reducer.DomainSQLRelationships, rows, "reducer/sql-relationships")
	if err != nil {
		t.Fatalf("WriteEdges() error = %v", err)
	}
	if got, want := len(executor.calls), 1; got != want {
		t.Fatalf("executor calls = %d, want %d", got, want)
	}
	if !strings.Contains(executor.calls[0].Cypher, "REFERENCES_TABLE") {
		t.Fatalf("cypher missing REFERENCES_TABLE: %s", executor.calls[0].Cypher)
	}
	if !strings.Contains(executor.calls[0].Cypher, "HAS_COLUMN") {
		t.Fatalf("cypher missing HAS_COLUMN branch: %s", executor.calls[0].Cypher)
	}
	if !strings.Contains(executor.calls[0].Cypher, "TRIGGERS") {
		t.Fatalf("cypher missing TRIGGERS branch: %s", executor.calls[0].Cypher)
	}
	batchRows, ok := executor.calls[0].Parameters["rows"].([]map[string]any)
	if !ok || len(batchRows) != 1 {
		t.Fatalf("expected 1 row in batch, got %v", executor.calls[0].Parameters["rows"])
	}
	if got, want := batchRows[0]["source_entity_id"], "entity:sql_view:my_view"; got != want {
		t.Fatalf("source_entity_id = %v, want %v", got, want)
	}
	if got, want := batchRows[0]["relationship_type"], "REFERENCES_TABLE"; got != want {
		t.Fatalf("relationship_type = %v, want %v", got, want)
	}
}

func TestEdgeWriterWriteEdgesSQLRelationshipSkipsEmptyFields(t *testing.T) {
	t.Parallel()

	executor := &recordingExecutor{}
	writer := NewEdgeWriter(executor, 0)

	rows := []reducer.SharedProjectionIntentRow{
		{IntentID: "i1", RepositoryID: "r1", Payload: map[string]any{"source_entity_id": "", "target_entity_id": "t1"}},
		{IntentID: "i2", RepositoryID: "r1", Payload: map[string]any{"source_entity_id": "s1", "target_entity_id": ""}},
	}

	err := writer.WriteEdges(context.Background(), reducer.DomainSQLRelationships, rows, "reducer/sql-relationships")
	if err != nil {
		t.Fatalf("WriteEdges() error = %v", err)
	}
	if got := len(executor.calls); got != 0 {
		t.Fatalf("executor calls = %d, want 0 (all rows filtered)", got)
	}
}

func TestEdgeWriterRetractEdgesInheritanceDispatch(t *testing.T) {
	t.Parallel()

	executor := &recordingExecutor{}
	writer := NewEdgeWriter(executor, 0)

	rows := []reducer.SharedProjectionIntentRow{
		{IntentID: "i1", RepositoryID: "repo-a", Payload: map[string]any{"repo_id": "repo-a"}},
	}

	err := writer.RetractEdges(context.Background(), reducer.DomainInheritanceEdges, rows, "reducer/inheritance")
	if err != nil {
		t.Fatalf("RetractEdges() error = %v", err)
	}
	if got, want := len(executor.calls), 1; got != want {
		t.Fatalf("executor calls = %d, want %d", got, want)
	}
	if !strings.Contains(executor.calls[0].Cypher, "INHERITS") {
		t.Fatalf("cypher missing INHERITS: %s", executor.calls[0].Cypher)
	}
	if !strings.Contains(executor.calls[0].Cypher, "DELETE rel") {
		t.Fatalf("cypher missing DELETE: %s", executor.calls[0].Cypher)
	}
}

func TestEdgeWriterRetractEdgesSQLRelationshipDispatch(t *testing.T) {
	t.Parallel()

	executor := &recordingExecutor{}
	writer := NewEdgeWriter(executor, 0)

	rows := []reducer.SharedProjectionIntentRow{
		{IntentID: "i1", RepositoryID: "repo-a", Payload: map[string]any{"repo_id": "repo-a"}},
	}

	err := writer.RetractEdges(context.Background(), reducer.DomainSQLRelationships, rows, "reducer/sql-relationships")
	if err != nil {
		t.Fatalf("RetractEdges() error = %v", err)
	}
	if got, want := len(executor.calls), 1; got != want {
		t.Fatalf("executor calls = %d, want %d", got, want)
	}
	if !strings.Contains(executor.calls[0].Cypher, "REFERENCES_TABLE") {
		t.Fatalf("cypher missing REFERENCES_TABLE: %s", executor.calls[0].Cypher)
	}
	if !strings.Contains(executor.calls[0].Cypher, "HAS_COLUMN") {
		t.Fatalf("cypher missing HAS_COLUMN: %s", executor.calls[0].Cypher)
	}
	if !strings.Contains(executor.calls[0].Cypher, "TRIGGERS") {
		t.Fatalf("cypher missing TRIGGERS: %s", executor.calls[0].Cypher)
	}
	if !strings.Contains(executor.calls[0].Cypher, "DELETE rel") {
		t.Fatalf("cypher missing DELETE: %s", executor.calls[0].Cypher)
	}
}

func TestBatchedWriteEdgesUsesUNWINDCypherIncludesNewDomains(t *testing.T) {
	t.Parallel()

	domains := []struct {
		domain   string
		payload  map[string]any
		contains string
	}{
		{
			domain:   reducer.DomainInheritanceEdges,
			payload:  map[string]any{"child_entity_id": "c1", "parent_entity_id": "p1"},
			contains: "UNWIND $rows AS row",
		},
		{
			domain:   reducer.DomainSQLRelationships,
			payload:  map[string]any{"source_entity_id": "s1", "target_entity_id": "t1"},
			contains: "UNWIND $rows AS row",
		},
	}

	for _, tc := range domains {
		t.Run(tc.domain, func(t *testing.T) {
			t.Parallel()
			executor := &recordingExecutor{}
			writer := NewEdgeWriter(executor, 0)

			rows := []reducer.SharedProjectionIntentRow{
				{IntentID: "i1", RepositoryID: "r1", Payload: tc.payload},
			}
			err := writer.WriteEdges(context.Background(), tc.domain, rows, "test")
			if err != nil {
				t.Fatalf("WriteEdges(%s) error = %v", tc.domain, err)
			}
			if !strings.Contains(executor.calls[0].Cypher, tc.contains) {
				t.Fatalf("cypher missing %q: %s", tc.contains, executor.calls[0].Cypher)
			}
		})
	}
}

// Suppress unused import for time package used only by SharedProjectionIntentRow.
var _ = time.Now
