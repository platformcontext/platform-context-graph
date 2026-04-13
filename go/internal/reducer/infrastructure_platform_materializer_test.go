package reducer

import (
	"context"
	"errors"
	"strings"
	"testing"
)

func TestInfrastructurePlatformMaterializerWritesProvisionsPlatformEdges(t *testing.T) {
	t.Parallel()

	executor := &recordingCypherExecutor{}
	materializer := NewInfrastructurePlatformMaterializer(executor)

	rows := []InfrastructurePlatformRow{
		{
			RepoID:           "repo:infra-eks",
			PlatformID:       "platform:kubernetes:aws:cluster/prod-cluster:none:none",
			PlatformName:     "prod-cluster",
			PlatformKind:     "kubernetes",
			PlatformProvider: "aws",
			PlatformLocator:  "cluster/prod-cluster",
		},
	}

	result, err := materializer.Materialize(context.Background(), rows)
	if err != nil {
		t.Fatalf("Materialize() error = %v", err)
	}
	if result.PlatformEdgesWritten != 1 {
		t.Fatalf("PlatformEdgesWritten = %d, want 1", result.PlatformEdgesWritten)
	}
	if len(executor.calls) != 1 {
		t.Fatalf("executor calls = %d, want 1", len(executor.calls))
	}
	if !strings.Contains(executor.calls[0].cypher, "PROVISIONS_PLATFORM") {
		t.Fatalf("cypher missing PROVISIONS_PLATFORM: %s", executor.calls[0].cypher)
	}
	if !strings.Contains(executor.calls[0].cypher, "MERGE (p:Platform {id: $platform_id})") {
		t.Fatalf("cypher missing Platform MERGE: %s", executor.calls[0].cypher)
	}
	if executor.calls[0].params["repo_id"] != "repo:infra-eks" {
		t.Fatalf("repo_id = %v, want repo:infra-eks", executor.calls[0].params["repo_id"])
	}
	if executor.calls[0].params["platform_kind"] != "kubernetes" {
		t.Fatalf("platform_kind = %v, want kubernetes", executor.calls[0].params["platform_kind"])
	}
	if executor.calls[0].params["platform_provider"] != "aws" {
		t.Fatalf("platform_provider = %v, want aws", executor.calls[0].params["platform_provider"])
	}
	if executor.calls[0].params["platform_locator"] != "cluster/prod-cluster" {
		t.Fatalf("platform_locator = %v, want cluster/prod-cluster", executor.calls[0].params["platform_locator"])
	}
}

func TestInfrastructurePlatformMaterializerMultipleRows(t *testing.T) {
	t.Parallel()

	executor := &recordingCypherExecutor{}
	materializer := NewInfrastructurePlatformMaterializer(executor)

	rows := []InfrastructurePlatformRow{
		{
			RepoID:           "repo:infra-eks",
			PlatformID:       "platform:kubernetes:aws:cluster/prod:none:none",
			PlatformName:     "prod",
			PlatformKind:     "kubernetes",
			PlatformProvider: "aws",
			PlatformLocator:  "cluster/prod",
		},
		{
			RepoID:           "repo:infra-ecs",
			PlatformID:       "platform:ecs:aws:cluster/payments:none:none",
			PlatformName:     "payments",
			PlatformKind:     "ecs",
			PlatformProvider: "aws",
			PlatformLocator:  "cluster/payments",
		},
	}

	result, err := materializer.Materialize(context.Background(), rows)
	if err != nil {
		t.Fatalf("Materialize() error = %v", err)
	}
	if result.PlatformEdgesWritten != 2 {
		t.Fatalf("PlatformEdgesWritten = %d, want 2", result.PlatformEdgesWritten)
	}
	if len(executor.calls) != 2 {
		t.Fatalf("executor calls = %d, want 2", len(executor.calls))
	}
}

func TestInfrastructurePlatformMaterializerIdempotent(t *testing.T) {
	t.Parallel()

	executor := &recordingCypherExecutor{}
	materializer := NewInfrastructurePlatformMaterializer(executor)

	rows := []InfrastructurePlatformRow{
		{
			RepoID:           "repo:infra-eks",
			PlatformID:       "platform:kubernetes:aws:cluster/prod:none:none",
			PlatformName:     "prod",
			PlatformKind:     "kubernetes",
			PlatformProvider: "aws",
			PlatformLocator:  "cluster/prod",
		},
	}

	result1, err := materializer.Materialize(context.Background(), rows)
	if err != nil {
		t.Fatalf("first Materialize() error = %v", err)
	}

	result2, err := materializer.Materialize(context.Background(), rows)
	if err != nil {
		t.Fatalf("second Materialize() error = %v", err)
	}

	if result1.PlatformEdgesWritten != result2.PlatformEdgesWritten {
		t.Fatalf("idempotency violated: first=%d, second=%d",
			result1.PlatformEdgesWritten, result2.PlatformEdgesWritten)
	}

	// Both calls should produce identical Cypher statements.
	if len(executor.calls) != 2 {
		t.Fatalf("executor calls = %d, want 2", len(executor.calls))
	}
	if executor.calls[0].cypher != executor.calls[1].cypher {
		t.Fatal("Cypher statements differ between runs")
	}
}

func TestInfrastructurePlatformMaterializerRetractsStaleEdges(t *testing.T) {
	t.Parallel()

	executor := &recordingCypherExecutor{}
	materializer := NewInfrastructurePlatformMaterializer(executor)

	err := materializer.RetractStale(
		context.Background(),
		[]string{"repo:old-infra", "repo:deprecated"},
	)
	if err != nil {
		t.Fatalf("RetractStale() error = %v", err)
	}
	if len(executor.calls) != 1 {
		t.Fatalf("executor calls = %d, want 1", len(executor.calls))
	}
	if !strings.Contains(executor.calls[0].cypher, "PROVISIONS_PLATFORM") {
		t.Fatalf("cypher missing PROVISIONS_PLATFORM: %s", executor.calls[0].cypher)
	}
	if !strings.Contains(executor.calls[0].cypher, "DELETE rel") {
		t.Fatalf("cypher missing DELETE: %s", executor.calls[0].cypher)
	}
	repoIDs, ok := executor.calls[0].params["repo_ids"].([]string)
	if !ok {
		t.Fatalf("repo_ids type = %T, want []string", executor.calls[0].params["repo_ids"])
	}
	if len(repoIDs) != 2 {
		t.Fatalf("repo_ids len = %d, want 2", len(repoIDs))
	}
}

func TestInfrastructurePlatformMaterializerRetractStaleEmptyRepoIDs(t *testing.T) {
	t.Parallel()

	executor := &recordingCypherExecutor{}
	materializer := NewInfrastructurePlatformMaterializer(executor)

	err := materializer.RetractStale(context.Background(), nil)
	if err != nil {
		t.Fatalf("RetractStale(nil) error = %v", err)
	}
	if len(executor.calls) != 0 {
		t.Fatalf("executor calls = %d, want 0 (no-op for empty repo IDs)", len(executor.calls))
	}
}

func TestInfrastructurePlatformMaterializerEmptyRows(t *testing.T) {
	t.Parallel()

	executor := &recordingCypherExecutor{}
	materializer := NewInfrastructurePlatformMaterializer(executor)

	result, err := materializer.Materialize(context.Background(), nil)
	if err != nil {
		t.Fatalf("Materialize(nil) error = %v", err)
	}
	if result.PlatformEdgesWritten != 0 {
		t.Fatalf("PlatformEdgesWritten = %d, want 0", result.PlatformEdgesWritten)
	}
	if len(executor.calls) != 0 {
		t.Fatalf("executor calls = %d, want 0", len(executor.calls))
	}
}

func TestInfrastructurePlatformMaterializerNilExecutor(t *testing.T) {
	t.Parallel()

	materializer := NewInfrastructurePlatformMaterializer(nil)

	_, err := materializer.Materialize(context.Background(), []InfrastructurePlatformRow{
		{RepoID: "repo:test", PlatformID: "platform:test"},
	})
	if err == nil {
		t.Fatal("Materialize() error = nil, want non-nil")
	}
	if !strings.Contains(err.Error(), "executor is required") {
		t.Fatalf("error = %q, want 'executor is required'", err.Error())
	}
}

func TestInfrastructurePlatformMaterializerPropagatesExecutorError(t *testing.T) {
	t.Parallel()

	executor := &errorCypherExecutor{err: errors.New("neo4j connection refused")}
	materializer := NewInfrastructurePlatformMaterializer(executor)

	_, err := materializer.Materialize(context.Background(), []InfrastructurePlatformRow{
		{
			RepoID:       "repo:infra-eks",
			PlatformID:   "platform:kubernetes:aws:cluster/prod:none:none",
			PlatformName: "prod",
			PlatformKind: "kubernetes",
		},
	})
	if err == nil {
		t.Fatal("Materialize() error = nil, want non-nil")
	}
	if !strings.Contains(err.Error(), "neo4j connection refused") {
		t.Fatalf("error = %q, want to contain 'neo4j connection refused'", err.Error())
	}
}

type errorCypherExecutor struct {
	err error
}

func (e *errorCypherExecutor) ExecuteCypher(_ context.Context, _ string, _ map[string]any) error {
	return e.err
}
