package main

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	neo4jdriver "github.com/neo4j/neo4j-go-driver/v5/neo4j"

	"github.com/platformcontext/platform-context-graph/go/internal/app"
	"github.com/platformcontext/platform-context-graph/go/internal/collector"
	runtimecfg "github.com/platformcontext/platform-context-graph/go/internal/runtime"
	sourceneo4j "github.com/platformcontext/platform-context-graph/go/internal/storage/neo4j"
	"github.com/platformcontext/platform-context-graph/go/internal/storage/postgres"
)

// runnerFunc adapts a plain function into the app.Runner interface for tests.
type runnerFunc func(context.Context) error

func (f runnerFunc) Run(ctx context.Context) error { return f(ctx) }

var _ app.Runner = runnerFunc(nil)

func TestBuildIngesterServiceProducesCompositeRunner(t *testing.T) {
	t.Parallel()

	runner, err := buildIngesterService(
		postgres.SQLDB{},
		&noopCanonicalWriter{},
		func(string) string { return "" },
		func() (string, error) { return t.TempDir(), nil },
		func() []string { return []string{"PATH=/usr/bin"} },
		nil, // tracer
		nil, // instruments
		nil, // logger
	)
	if err != nil {
		t.Fatalf("buildIngesterService() error = %v, want nil", err)
	}
	if len(runner.runners) != 2 {
		t.Fatalf("buildIngesterService() runner count = %d, want 2", len(runner.runners))
	}
}

func TestBuildIngesterCollectorServiceUsesNativeSnapshotter(t *testing.T) {
	t.Parallel()

	service, err := buildIngesterCollectorService(
		postgres.SQLDB{},
		func(string) string { return "" },
		func() (string, error) { return t.TempDir(), nil },
		func() []string { return []string{"PATH=/usr/bin"} },
		nil, // tracer
		nil, // instruments
		nil, // logger
	)
	if err != nil {
		t.Fatalf("buildIngesterCollectorService() error = %v, want nil", err)
	}

	source, ok := service.Source.(*collector.GitSource)
	if !ok {
		t.Fatalf("buildIngesterCollectorService() source type = %T, want *collector.GitSource", service.Source)
	}
	if _, ok := source.Selector.(collector.NativeRepositorySelector); !ok {
		t.Fatalf("buildIngesterCollectorService() selector type = %T, want collector.NativeRepositorySelector", source.Selector)
	}
	if _, ok := source.Snapshotter.(collector.NativeRepositorySnapshotter); !ok {
		t.Fatalf("buildIngesterCollectorService() snapshotter type = %T, want collector.NativeRepositorySnapshotter", source.Snapshotter)
	}
}

func TestCompositeRunnerCancelsOnFirstError(t *testing.T) {
	t.Parallel()

	expectedErr := errors.New("runner failed")
	blocked := make(chan struct{})

	runner := compositeRunner{
		runners: []app.Runner{
			runnerFunc(func(ctx context.Context) error {
				return expectedErr
			}),
			runnerFunc(func(ctx context.Context) error {
				<-ctx.Done()
				close(blocked)
				return nil
			}),
		},
	}

	err := runner.Run(context.Background())
	if !errors.Is(err, expectedErr) {
		t.Fatalf("compositeRunner.Run() error = %v, want %v", err, expectedErr)
	}

	select {
	case <-blocked:
	case <-time.After(5 * time.Second):
		t.Fatal("compositeRunner.Run() did not cancel remaining runners")
	}
}

func TestLargeGenThresholdDefault(t *testing.T) {
	t.Parallel()

	got := largeGenThreshold(func(string) string { return "" })
	if got != 10000 {
		t.Fatalf("largeGenThreshold() = %d, want 10000", got)
	}
}

func TestLargeGenThresholdFromEnv(t *testing.T) {
	t.Parallel()

	got := largeGenThreshold(func(k string) string {
		if k == "PCG_LARGE_GEN_THRESHOLD" {
			return "5000"
		}
		return ""
	})
	if got != 5000 {
		t.Fatalf("largeGenThreshold() = %d, want 5000", got)
	}
}

func TestLargeGenMaxConcurrentDefault(t *testing.T) {
	t.Parallel()

	got := largeGenMaxConcurrent(func(string) string { return "" })
	if got != 2 {
		t.Fatalf("largeGenMaxConcurrent() = %d, want 2", got)
	}
}

func TestLargeGenMaxConcurrentFromEnv(t *testing.T) {
	t.Parallel()

	got := largeGenMaxConcurrent(func(k string) string {
		if k == "PCG_LARGE_GEN_MAX_CONCURRENT" {
			return "4"
		}
		return ""
	})
	if got != 4 {
		t.Fatalf("largeGenMaxConcurrent() = %d, want 4", got)
	}
}

func TestCompositeRunnerExitsOnContextCancel(t *testing.T) {
	t.Parallel()

	runner := compositeRunner{
		runners: []app.Runner{
			runnerFunc(func(ctx context.Context) error {
				<-ctx.Done()
				return nil
			}),
			runnerFunc(func(ctx context.Context) error {
				<-ctx.Done()
				return nil
			}),
		},
	}

	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	err := runner.Run(ctx)
	if err != nil {
		t.Fatalf("compositeRunner.Run() error = %v, want nil", err)
	}
}

func TestOpenIngesterCanonicalWriterAcceptsNornicDBOnSharedBoltPath(t *testing.T) {
	t.Parallel()

	_, closer, err := openIngesterCanonicalWriter(context.Background(), func(key string) string {
		switch key {
		case "PCG_GRAPH_BACKEND":
			return "nornicdb"
		default:
			return ""
		}
	}, nil, nil)
	if closer != nil {
		_ = closer.Close()
	}
	if err == nil {
		t.Fatal("openIngesterCanonicalWriter() error = nil, want non-nil")
	}
	if !strings.Contains(err.Error(), "PCG_NEO4J_URI") && !strings.Contains(err.Error(), "NEO4J_URI") {
		t.Fatalf("openIngesterCanonicalWriter() error = %q, want shared bolt config context", err)
	}
}

func TestCanonicalExecutorForGraphBackendKeepsNeo4jGrouped(t *testing.T) {
	t.Parallel()

	executor := canonicalExecutorForGraphBackend(&groupCapableIngesterExecutor{}, runtimecfg.GraphBackendNeo4j, 0, false, nil, nil)
	if _, ok := executor.(sourceneo4j.GroupExecutor); !ok {
		t.Fatal("Neo4j canonical executor does not implement GroupExecutor")
	}
}

func TestCanonicalExecutorForGraphBackendForcesNornicDBSequentialByDefault(t *testing.T) {
	t.Parallel()

	inner := &groupCapableIngesterExecutor{}
	executor := canonicalExecutorForGraphBackend(inner, runtimecfg.GraphBackendNornicDB, 0, false, nil, nil)
	if _, ok := executor.(sourceneo4j.GroupExecutor); ok {
		t.Fatal("NornicDB canonical executor implements GroupExecutor, want sequential execute-only surface")
	}

	err := executor.Execute(context.Background(), sourceneo4j.Statement{Cypher: "RETURN 1"})
	if err != nil {
		t.Fatalf("Execute() error = %v, want nil", err)
	}
	if inner.executeCalls != 1 {
		t.Fatalf("inner Execute calls = %d, want 1", inner.executeCalls)
	}
}

func TestCanonicalExecutorForGraphBackendAllowsNornicDBGroupedWhenConformanceEnabled(t *testing.T) {
	t.Parallel()

	inner := &groupCapableIngesterExecutor{}
	executor := canonicalExecutorForGraphBackend(inner, runtimecfg.GraphBackendNornicDB, 0, true, nil, nil)
	ge, ok := executor.(sourceneo4j.GroupExecutor)
	if !ok {
		t.Fatal("NornicDB canonical executor does not implement GroupExecutor when conformance grouped writes are enabled")
	}

	err := ge.ExecuteGroup(context.Background(), []sourceneo4j.Statement{{Cypher: "RETURN 1"}})
	if err != nil {
		t.Fatalf("ExecuteGroup() error = %v, want nil", err)
	}
	if inner.groupCalls != 1 {
		t.Fatalf("inner ExecuteGroup calls = %d, want 1", inner.groupCalls)
	}
}

func TestCanonicalExecutorForGraphBackendWrapsNornicDBWithTimeout(t *testing.T) {
	t.Parallel()

	executor := canonicalExecutorForGraphBackend(contextBlockingIngesterExecutor{}, runtimecfg.GraphBackendNornicDB, 10*time.Millisecond, false, nil, nil)

	err := executor.Execute(context.Background(), sourceneo4j.Statement{Cypher: "RETURN 1"})
	if !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("Execute() error = %v, want deadline exceeded", err)
	}
}

func TestNornicDBCanonicalGroupedWritesDefaultDisabled(t *testing.T) {
	t.Parallel()

	got, err := nornicDBCanonicalGroupedWrites(func(string) string { return "" })
	if err != nil {
		t.Fatalf("nornicDBCanonicalGroupedWrites() error = %v, want nil", err)
	}
	if got {
		t.Fatal("nornicDBCanonicalGroupedWrites() = true, want false by default")
	}
}

func TestNornicDBCanonicalGroupedWritesFromEnv(t *testing.T) {
	t.Parallel()

	got, err := nornicDBCanonicalGroupedWrites(func(key string) string {
		if key == "PCG_NORNICDB_CANONICAL_GROUPED_WRITES" {
			return "true"
		}
		return ""
	})
	if err != nil {
		t.Fatalf("nornicDBCanonicalGroupedWrites() error = %v, want nil", err)
	}
	if !got {
		t.Fatal("nornicDBCanonicalGroupedWrites() = false, want true")
	}
}

func TestNornicDBCanonicalGroupedWritesRejectsInvalidEnv(t *testing.T) {
	t.Parallel()

	_, err := nornicDBCanonicalGroupedWrites(func(key string) string {
		if key == "PCG_NORNICDB_CANONICAL_GROUPED_WRITES" {
			return "maybe"
		}
		return ""
	})
	if err == nil {
		t.Fatal("nornicDBCanonicalGroupedWrites() error = nil, want non-nil")
	}
	if !strings.Contains(err.Error(), "PCG_NORNICDB_CANONICAL_GROUPED_WRITES") {
		t.Fatalf("nornicDBCanonicalGroupedWrites() error = %q, want env name", err)
	}
}

func TestNornicDBCanonicalWriteTimeoutDefault(t *testing.T) {
	t.Parallel()

	got := nornicDBCanonicalWriteTimeout(func(string) string { return "" })
	if got != defaultNornicDBCanonicalWriteTimeout {
		t.Fatalf("nornicDBCanonicalWriteTimeout() = %s, want %s", got, defaultNornicDBCanonicalWriteTimeout)
	}
}

func TestNornicDBCanonicalWriteTimeoutFromEnv(t *testing.T) {
	t.Parallel()

	got := nornicDBCanonicalWriteTimeout(func(key string) string {
		if key == "PCG_CANONICAL_WRITE_TIMEOUT" {
			return "2s"
		}
		return ""
	})
	if got != 2*time.Second {
		t.Fatalf("nornicDBCanonicalWriteTimeout() = %s, want 2s", got)
	}
}

func TestIngesterContentBeforeCanonicalOnlyLocalAuthoritative(t *testing.T) {
	t.Parallel()

	if !ingesterContentBeforeCanonical(func(key string) string {
		if key == "PCG_QUERY_PROFILE" {
			return "local_authoritative"
		}
		return ""
	}) {
		t.Fatal("ingesterContentBeforeCanonical(local_authoritative) = false, want true")
	}
	if ingesterContentBeforeCanonical(func(key string) string {
		if key == "PCG_QUERY_PROFILE" {
			return "production"
		}
		return ""
	}) {
		t.Fatal("ingesterContentBeforeCanonical(production) = true, want false")
	}
}

func TestCanonicalTransactionTimeoutOnlyAppliesToNornicDB(t *testing.T) {
	t.Parallel()

	getenv := func(key string) string {
		if key == "PCG_CANONICAL_WRITE_TIMEOUT" {
			return "3s"
		}
		return ""
	}
	if got := canonicalTransactionTimeout(runtimecfg.GraphBackendNeo4j, getenv); got != 0 {
		t.Fatalf("canonicalTransactionTimeout(neo4j) = %s, want 0", got)
	}
	if got := canonicalTransactionTimeout(runtimecfg.GraphBackendNornicDB, getenv); got != 3*time.Second {
		t.Fatalf("canonicalTransactionTimeout(nornicdb) = %s, want 3s", got)
	}
}

func TestIngesterNeo4jExecutorTransactionConfigurersSetTimeout(t *testing.T) {
	t.Parallel()

	executor := ingesterNeo4jExecutor{TxTimeout: 4 * time.Second}
	configurers := executor.transactionConfigurers()
	if len(configurers) != 1 {
		t.Fatalf("transactionConfigurers count = %d, want 1", len(configurers))
	}
	var config neo4jdriver.TransactionConfig
	configurers[0](&config)
	if got := config.Timeout; got != 4*time.Second {
		t.Fatalf("transaction timeout = %s, want 4s", got)
	}
}

type groupCapableIngesterExecutor struct {
	executeCalls int
	groupCalls   int
}

func (g *groupCapableIngesterExecutor) Execute(context.Context, sourceneo4j.Statement) error {
	g.executeCalls++
	return nil
}

func (g *groupCapableIngesterExecutor) ExecuteGroup(context.Context, []sourceneo4j.Statement) error {
	g.groupCalls++
	return nil
}

type contextBlockingIngesterExecutor struct{}

func (contextBlockingIngesterExecutor) Execute(ctx context.Context, _ sourceneo4j.Statement) error {
	<-ctx.Done()
	return ctx.Err()
}
