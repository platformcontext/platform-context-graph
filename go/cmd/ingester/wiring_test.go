package main

import (
	"context"
	"errors"
	"reflect"
	"strings"
	"testing"
	"time"

	neo4jdriver "github.com/neo4j/neo4j-go-driver/v5/neo4j"

	"github.com/platformcontext/platform-context-graph/go/internal/app"
	"github.com/platformcontext/platform-context-graph/go/internal/collector"
	"github.com/platformcontext/platform-context-graph/go/internal/projector"
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

func TestBuildIngesterProjectorRuntimeWiresPhasePublisherAndRepairQueue(t *testing.T) {
	t.Parallel()

	runtime := buildIngesterProjectorRuntime(
		postgres.SQLDB{},
		&noopCanonicalWriter{},
		nil,
		nil,
		func(string) string { return "" },
		nil,
		nil,
	)

	if runtime.PhasePublisher == nil {
		t.Fatal("buildIngesterProjectorRuntime() PhasePublisher = nil, want non-nil")
	}
	if runtime.RepairQueue == nil {
		t.Fatal("buildIngesterProjectorRuntime() RepairQueue = nil, want non-nil")
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

	executor := canonicalExecutorForGraphBackend(
		&groupCapableIngesterExecutor{},
		runtimecfg.GraphBackendNeo4j,
		0,
		false,
		defaultNornicDBPhaseGroupStatements,
		defaultNornicDBEntityPhaseStatements,
		nil,
		nil,
	)
	if _, ok := executor.(sourceneo4j.GroupExecutor); !ok {
		t.Fatal("Neo4j canonical executor does not implement GroupExecutor")
	}
}

func TestCanonicalExecutorForGraphBackendUsesNornicDBPhaseGroupsByDefault(t *testing.T) {
	t.Parallel()

	inner := &groupCapableIngesterExecutor{}
	executor := canonicalExecutorForGraphBackend(
		inner,
		runtimecfg.GraphBackendNornicDB,
		0,
		false,
		defaultNornicDBPhaseGroupStatements,
		defaultNornicDBEntityPhaseStatements,
		nil,
		nil,
	)
	if _, ok := executor.(sourceneo4j.GroupExecutor); ok {
		t.Fatal("NornicDB canonical executor implements GroupExecutor, want non-atomic phase-group surface")
	}
	pge, ok := executor.(sourceneo4j.PhaseGroupExecutor)
	if !ok {
		t.Fatal("NornicDB canonical executor does not implement PhaseGroupExecutor by default")
	}

	err := executor.Execute(context.Background(), sourceneo4j.Statement{Cypher: "RETURN 1"})
	if err != nil {
		t.Fatalf("Execute() error = %v, want nil", err)
	}
	if inner.executeCalls != 1 {
		t.Fatalf("inner Execute calls = %d, want 1", inner.executeCalls)
	}
	if err := pge.ExecutePhaseGroup(context.Background(), []sourceneo4j.Statement{{Cypher: "RETURN 2"}}); err != nil {
		t.Fatalf("ExecutePhaseGroup() error = %v, want nil", err)
	}
	if inner.groupCalls != 1 {
		t.Fatalf("inner ExecuteGroup calls = %d, want 1", inner.groupCalls)
	}
}

func TestCanonicalExecutorForGraphBackendUsesConfiguredNornicDBPhaseGroupStatements(t *testing.T) {
	t.Parallel()

	inner := &groupCapableIngesterExecutor{}
	executor := canonicalExecutorForGraphBackend(
		inner,
		runtimecfg.GraphBackendNornicDB,
		0,
		false,
		777,
		defaultNornicDBEntityPhaseStatements,
		nil,
		nil,
	)
	pge, ok := executor.(nornicDBPhaseGroupExecutor)
	if !ok {
		t.Fatalf("executor type = %T, want nornicDBPhaseGroupExecutor", executor)
	}
	if got, want := pge.maxStatements, 777; got != want {
		t.Fatalf("phase-group max statements = %d, want %d", got, want)
	}
}

func TestCanonicalExecutorForGraphBackendUsesConfiguredNornicDBEntityPhaseStatements(t *testing.T) {
	t.Parallel()

	inner := &groupCapableIngesterExecutor{}
	executor := canonicalExecutorForGraphBackend(
		inner,
		runtimecfg.GraphBackendNornicDB,
		0,
		false,
		defaultNornicDBPhaseGroupStatements,
		17,
		nil,
		nil,
	)
	pge, ok := executor.(nornicDBPhaseGroupExecutor)
	if !ok {
		t.Fatalf("executor type = %T, want nornicDBPhaseGroupExecutor", executor)
	}
	if got, want := pge.entityMaxStatements, 17; got != want {
		t.Fatalf("entity phase max statements = %d, want %d", got, want)
	}
}

func TestNornicDBPhaseGroupExecutorSplitsChunksByConfiguredStatementLimit(t *testing.T) {
	t.Parallel()

	inner := &recordingGroupChunkExecutor{}
	executor := nornicDBPhaseGroupExecutor{
		inner:         inner,
		maxStatements: 2,
	}

	stmts := []sourceneo4j.Statement{
		{Cypher: "RETURN 1"},
		{Cypher: "RETURN 2"},
		{Cypher: "RETURN 3"},
		{Cypher: "RETURN 4"},
		{Cypher: "RETURN 5"},
	}

	if err := executor.ExecutePhaseGroup(context.Background(), stmts); err != nil {
		t.Fatalf("ExecutePhaseGroup() error = %v, want nil", err)
	}
	if got, want := len(inner.groupSizes), 3; got != want {
		t.Fatalf("group call count = %d, want %d", got, want)
	}
	if got, want := inner.groupSizes, []int{2, 2, 1}; !equalIntSlices(got, want) {
		t.Fatalf("group sizes = %v, want %v", got, want)
	}
}

func TestNornicDBPhaseGroupExecutorUsesEntitySpecificStatementLimit(t *testing.T) {
	t.Parallel()

	inner := &recordingGroupChunkExecutor{}
	executor := nornicDBPhaseGroupExecutor{
		inner:               inner,
		maxStatements:       5,
		entityMaxStatements: 2,
	}

	stmts := []sourceneo4j.Statement{
		{Cypher: "RETURN 1", Parameters: map[string]any{"_pcg_phase": "entities"}},
		{Cypher: "RETURN 2", Parameters: map[string]any{"_pcg_phase": "entities"}},
		{Cypher: "RETURN 3", Parameters: map[string]any{"_pcg_phase": "entities"}},
		{Cypher: "RETURN 4", Parameters: map[string]any{"_pcg_phase": "entities"}},
		{Cypher: "RETURN 5", Parameters: map[string]any{"_pcg_phase": "entities"}},
	}

	if err := executor.ExecutePhaseGroup(context.Background(), stmts); err != nil {
		t.Fatalf("ExecutePhaseGroup() error = %v, want nil", err)
	}
	if got, want := inner.groupSizes, []int{2, 2, 1}; !equalIntSlices(got, want) {
		t.Fatalf("entity group sizes = %v, want %v", got, want)
	}
}

func TestNornicDBPhaseGroupExecutorExecutesEntitySingletonFallbackOutsideGroup(t *testing.T) {
	t.Parallel()

	inner := &recordingGroupChunkExecutor{}
	executor := nornicDBPhaseGroupExecutor{
		inner:               inner,
		maxStatements:       5,
		entityMaxStatements: 2,
	}

	stmts := []sourceneo4j.Statement{
		{
			Cypher: "RETURN grouped1",
			Parameters: map[string]any{
				"_pcg_phase": "entities",
				"rows":       []map[string]any{{"entity_id": "one"}},
			},
		},
		{
			Cypher: "RETURN fallback",
			Parameters: map[string]any{
				"_pcg_phase":             "entities",
				"_pcg_phase_group_mode":  "execute_only",
				"_pcg_statement_summary": "label=Function rows=1 entity_id=fallback fallback=singleton_parameterized",
				"entity_id":              "fallback",
				"props":                  map[string]any{"name": "fallback"},
			},
		},
		{
			Cypher: "RETURN grouped2",
			Parameters: map[string]any{
				"_pcg_phase": "entities",
				"rows":       []map[string]any{{"entity_id": "two"}},
			},
		},
	}

	if err := executor.ExecutePhaseGroup(context.Background(), stmts); err != nil {
		t.Fatalf("ExecutePhaseGroup() error = %v, want nil", err)
	}
	if got, want := inner.groupSizes, []int{1, 1}; !equalIntSlices(got, want) {
		t.Fatalf("group sizes = %v, want %v", got, want)
	}
	if got, want := len(inner.executeParams), 1; got != want {
		t.Fatalf("execute params count = %d, want %d", got, want)
	}
	if _, ok := inner.executeParams[0]["_pcg_phase_group_mode"]; ok {
		t.Fatalf("execute params include group-mode diagnostic: %#v", inner.executeParams[0])
	}
	if got, want := inner.executeParams[0]["entity_id"], "fallback"; got != want {
		t.Fatalf("execute entity_id = %#v, want %#v", got, want)
	}
}

func TestNornicDBPhaseGroupExecutorWrapsChunkFailureDetails(t *testing.T) {
	t.Parallel()

	inner := &recordingGroupChunkExecutor{
		failAtCall: 2,
		err:        errors.New("context canceled"),
	}
	executor := nornicDBPhaseGroupExecutor{
		inner:         inner,
		maxStatements: 2,
	}

	stmts := []sourceneo4j.Statement{
		{Cypher: "RETURN 1"},
		{Cypher: "RETURN 2"},
		{Cypher: "RETURN 3"},
	}

	err := executor.ExecutePhaseGroup(context.Background(), stmts)
	if err == nil {
		t.Fatal("ExecutePhaseGroup() error = nil, want non-nil")
	}
	if !strings.Contains(err.Error(), "phase-group chunk 2/2") {
		t.Fatalf("ExecutePhaseGroup() error = %q, want chunk ordinal context", err.Error())
	}
	if !strings.Contains(err.Error(), "statements 3-3 of 3") {
		t.Fatalf("ExecutePhaseGroup() error = %q, want statement range context", err.Error())
	}
	if !strings.Contains(err.Error(), `first_statement="RETURN 3"`) {
		t.Fatalf("ExecutePhaseGroup() error = %q, want first statement summary", err.Error())
	}
	if !strings.Contains(err.Error(), "context canceled") {
		t.Fatalf("ExecutePhaseGroup() error = %q, want inner error context", err.Error())
	}
}

func TestNornicDBPhaseGroupExecutorStripsDiagnosticStatementParamsBeforeDriver(t *testing.T) {
	t.Parallel()

	inner := &recordingGroupChunkExecutor{}
	executor := nornicDBPhaseGroupExecutor{
		inner:         inner,
		maxStatements: 2,
	}

	stmts := []sourceneo4j.Statement{
		{
			Cypher: "RETURN 1",
			Parameters: map[string]any{
				"rows":                   []map[string]any{{"entity_id": "one"}},
				"_pcg_phase":             "entities",
				"_pcg_statement_summary": "label=Function rows=1 entity_id=one",
			},
		},
	}

	if err := executor.ExecutePhaseGroup(context.Background(), stmts); err != nil {
		t.Fatalf("ExecutePhaseGroup() error = %v, want nil", err)
	}
	if got, want := len(inner.groupParams), 1; got != want {
		t.Fatalf("group params count = %d, want %d", got, want)
	}
	if _, ok := inner.groupParams[0]["_pcg_statement_summary"]; ok {
		t.Fatalf("group params include diagnostic summary: %#v", inner.groupParams[0])
	}
	if _, ok := inner.groupParams[0]["_pcg_phase"]; ok {
		t.Fatalf("group params include phase diagnostic: %#v", inner.groupParams[0])
	}
	if got, want := inner.groupParams[0]["rows"], stmts[0].Parameters["rows"]; !reflect.DeepEqual(got, want) {
		t.Fatalf("group rows param = %#v, want %#v", got, want)
	}
}

func TestCanonicalExecutorForGraphBackendAllowsNornicDBGroupedWhenConformanceEnabled(t *testing.T) {
	t.Parallel()

	inner := &groupCapableIngesterExecutor{}
	executor := canonicalExecutorForGraphBackend(
		inner,
		runtimecfg.GraphBackendNornicDB,
		0,
		true,
		defaultNornicDBPhaseGroupStatements,
		defaultNornicDBEntityPhaseStatements,
		nil,
		nil,
	)
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

func TestCanonicalExecutorForGraphBackendNornicDBGroupedFullStackReachesRawExecutor(t *testing.T) {
	t.Parallel()

	inner := &groupCapableIngesterExecutor{}
	executor := canonicalExecutorForGraphBackend(
		inner,
		runtimecfg.GraphBackendNornicDB,
		0,
		true,
		defaultNornicDBPhaseGroupStatements,
		defaultNornicDBEntityPhaseStatements,
		nil,
		nil,
	)
	if _, ok := executor.(sourceneo4j.GroupExecutor); !ok {
		t.Fatal("NornicDB grouped executor stack does not implement GroupExecutor")
	}

	writer := sourceneo4j.NewCanonicalNodeWriter(executor, 0, nil)
	err := writer.Write(context.Background(), minimalCanonicalMaterialization())
	if err != nil {
		t.Fatalf("CanonicalNodeWriter.Write() error = %v, want nil", err)
	}
	if inner.groupCalls != 1 {
		t.Fatalf("raw ExecuteGroup calls = %d, want 1", inner.groupCalls)
	}
	if inner.executeCalls != 0 {
		t.Fatalf("raw Execute calls = %d, want 0 for grouped path", inner.executeCalls)
	}
}

func TestCanonicalExecutorForGraphBackendNornicDBDefaultFullStackUsesPhaseGroups(t *testing.T) {
	t.Parallel()

	inner := &groupCapableIngesterExecutor{}
	executor := canonicalExecutorForGraphBackend(
		inner,
		runtimecfg.GraphBackendNornicDB,
		0,
		false,
		defaultNornicDBPhaseGroupStatements,
		defaultNornicDBEntityPhaseStatements,
		nil,
		nil,
	)
	if _, ok := executor.(sourceneo4j.PhaseGroupExecutor); !ok {
		t.Fatal("NornicDB default executor stack does not implement PhaseGroupExecutor")
	}

	writer := sourceneo4j.NewCanonicalNodeWriter(executor, 0, nil)
	err := writer.Write(context.Background(), minimalCanonicalMaterialization())
	if err != nil {
		t.Fatalf("CanonicalNodeWriter.Write() error = %v, want nil", err)
	}
	if inner.groupCalls == 0 {
		t.Fatal("raw ExecuteGroup calls = 0, want phase-group usage")
	}
	if inner.executeCalls != 0 {
		t.Fatalf("raw Execute calls = %d, want 0 for phase-group path", inner.executeCalls)
	}
}

func TestCanonicalExecutorForGraphBackendWrapsNornicDBWithTimeout(t *testing.T) {
	t.Parallel()

	executor := canonicalExecutorForGraphBackend(
		contextBlockingIngesterExecutor{},
		runtimecfg.GraphBackendNornicDB,
		10*time.Millisecond,
		false,
		defaultNornicDBPhaseGroupStatements,
		defaultNornicDBEntityPhaseStatements,
		nil,
		nil,
	)

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
		if key == canonicalWriteTimeoutEnv {
			return "2s"
		}
		return ""
	})
	if got != 2*time.Second {
		t.Fatalf("nornicDBCanonicalWriteTimeout() = %s, want 2s", got)
	}
}

func TestNornicDBPhaseGroupStatementsDefault(t *testing.T) {
	t.Parallel()

	got, err := nornicDBPhaseGroupStatements(func(string) string { return "" })
	if err != nil {
		t.Fatalf("nornicDBPhaseGroupStatements() error = %v, want nil", err)
	}
	if got != defaultNornicDBPhaseGroupStatements {
		t.Fatalf("nornicDBPhaseGroupStatements() = %d, want %d", got, defaultNornicDBPhaseGroupStatements)
	}
}

func TestNornicDBPhaseGroupStatementsFromEnv(t *testing.T) {
	t.Parallel()

	got, err := nornicDBPhaseGroupStatements(func(key string) string {
		if key == nornicDBPhaseGroupStatementsEnv {
			return "750"
		}
		return ""
	})
	if err != nil {
		t.Fatalf("nornicDBPhaseGroupStatements() error = %v, want nil", err)
	}
	if got != 750 {
		t.Fatalf("nornicDBPhaseGroupStatements() = %d, want 750", got)
	}
}

func TestNornicDBPhaseGroupStatementsRejectsInvalidEnv(t *testing.T) {
	t.Parallel()

	_, err := nornicDBPhaseGroupStatements(func(key string) string {
		if key == nornicDBPhaseGroupStatementsEnv {
			return "nope"
		}
		return ""
	})
	if err == nil {
		t.Fatal("nornicDBPhaseGroupStatements() error = nil, want non-nil")
	}
	if !strings.Contains(err.Error(), nornicDBPhaseGroupStatementsEnv) {
		t.Fatalf("nornicDBPhaseGroupStatements() error = %q, want env name", err)
	}
}

func TestNornicDBEntityPhaseGroupStatementsDefault(t *testing.T) {
	t.Parallel()

	got, err := nornicDBEntityPhaseGroupStatements(func(string) string { return "" })
	if err != nil {
		t.Fatalf("nornicDBEntityPhaseGroupStatements() error = %v, want nil", err)
	}
	if got != defaultNornicDBEntityPhaseStatements {
		t.Fatalf("nornicDBEntityPhaseGroupStatements() = %d, want %d", got, defaultNornicDBEntityPhaseStatements)
	}
}

func TestNornicDBEntityPhaseGroupStatementsFromEnv(t *testing.T) {
	t.Parallel()

	got, err := nornicDBEntityPhaseGroupStatements(func(key string) string {
		if key == nornicDBEntityPhaseStatementsEnv {
			return "33"
		}
		return ""
	})
	if err != nil {
		t.Fatalf("nornicDBEntityPhaseGroupStatements() error = %v, want nil", err)
	}
	if got != 33 {
		t.Fatalf("nornicDBEntityPhaseGroupStatements() = %d, want 33", got)
	}
}

func TestNornicDBEntityPhaseGroupStatementsRejectsInvalidEnv(t *testing.T) {
	t.Parallel()

	_, err := nornicDBEntityPhaseGroupStatements(func(key string) string {
		if key == nornicDBEntityPhaseStatementsEnv {
			return "nope"
		}
		return ""
	})
	if err == nil {
		t.Fatal("nornicDBEntityPhaseGroupStatements() error = nil, want non-nil")
	}
	if !strings.Contains(err.Error(), nornicDBEntityPhaseStatementsEnv) {
		t.Fatalf("nornicDBEntityPhaseGroupStatements() error = %q, want env name", err)
	}
}

func TestNornicDBEntityBatchSizeDefault(t *testing.T) {
	t.Parallel()

	got, err := nornicDBEntityBatchSize(func(string) string { return "" })
	if err != nil {
		t.Fatalf("nornicDBEntityBatchSize() error = %v, want nil", err)
	}
	if got != defaultNornicDBEntityBatchSize {
		t.Fatalf("nornicDBEntityBatchSize() = %d, want %d", got, defaultNornicDBEntityBatchSize)
	}
}

func TestNornicDBEntityBatchSizeFromEnv(t *testing.T) {
	t.Parallel()

	got, err := nornicDBEntityBatchSize(func(key string) string {
		if key == nornicDBEntityBatchSizeEnv {
			return "100"
		}
		return ""
	})
	if err != nil {
		t.Fatalf("nornicDBEntityBatchSize() error = %v, want nil", err)
	}
	if got != 100 {
		t.Fatalf("nornicDBEntityBatchSize() = %d, want 100", got)
	}
}

func TestNornicDBEntityBatchSizeRejectsInvalidEnv(t *testing.T) {
	t.Parallel()

	_, err := nornicDBEntityBatchSize(func(key string) string {
		if key == nornicDBEntityBatchSizeEnv {
			return "nope"
		}
		return ""
	})
	if err == nil {
		t.Fatal("nornicDBEntityBatchSize() error = nil, want non-nil")
	}
	if !strings.Contains(err.Error(), nornicDBEntityBatchSizeEnv) {
		t.Fatalf("nornicDBEntityBatchSize() error = %q, want env name", err)
	}
}

func TestNornicDBEntityLabelBatchSizes(t *testing.T) {
	t.Parallel()

	got, err := nornicDBEntityLabelBatchSizes(func(string) string { return "" }, 100)
	if err != nil {
		t.Fatalf("nornicDBEntityLabelBatchSizes() error = %v, want nil", err)
	}
	if got["Function"] != defaultNornicDBFunctionEntityBatchSize {
		t.Fatalf("Function batch size = %d, want %d", got["Function"], defaultNornicDBFunctionEntityBatchSize)
	}
	if got["Struct"] != defaultNornicDBStructEntityBatchSize {
		t.Fatalf("Struct batch size = %d, want %d", got["Struct"], defaultNornicDBStructEntityBatchSize)
	}
}

func TestNornicDBEntityLabelBatchSizesClampToEntityBatchSize(t *testing.T) {
	t.Parallel()

	got, err := nornicDBEntityLabelBatchSizes(func(string) string { return "" }, 40)
	if err != nil {
		t.Fatalf("nornicDBEntityLabelBatchSizes() error = %v, want nil", err)
	}
	if got["Function"] != defaultNornicDBFunctionEntityBatchSize {
		t.Fatalf("Function batch size = %d, want %d", got["Function"], defaultNornicDBFunctionEntityBatchSize)
	}
	if got["Struct"] != 40 {
		t.Fatalf("Struct batch size = %d, want 40", got["Struct"])
	}
}

func TestNornicDBEntityLabelBatchSizesDefault(t *testing.T) {
	t.Parallel()

	got, err := nornicDBEntityLabelBatchSizes(func(string) string { return "" }, 100)
	if err != nil {
		t.Fatalf("nornicDBEntityLabelBatchSizes() error = %v, want nil", err)
	}
	if got["Function"] != defaultNornicDBFunctionEntityBatchSize {
		t.Fatalf("Function batch size = %d, want %d", got["Function"], defaultNornicDBFunctionEntityBatchSize)
	}
	if got["Struct"] != defaultNornicDBStructEntityBatchSize {
		t.Fatalf("Struct batch size = %d, want %d", got["Struct"], defaultNornicDBStructEntityBatchSize)
	}
}

func TestNornicDBEntityLabelBatchSizesFromEnv(t *testing.T) {
	t.Parallel()

	got, err := nornicDBEntityLabelBatchSizes(func(key string) string {
		if key == nornicDBEntityLabelBatchSizesEnv {
			return "Function=30,Struct=40,Class=75"
		}
		return ""
	}, 100)
	if err != nil {
		t.Fatalf("nornicDBEntityLabelBatchSizes() error = %v, want nil", err)
	}
	if got["Function"] != 30 {
		t.Fatalf("Function batch size = %d, want 30", got["Function"])
	}
	if got["Struct"] != 40 {
		t.Fatalf("Struct batch size = %d, want 40", got["Struct"])
	}
	if got["Class"] != 75 {
		t.Fatalf("Class batch size = %d, want 75", got["Class"])
	}
}

func TestNornicDBEntityLabelBatchSizesCapsEnvByEntityBatchSize(t *testing.T) {
	t.Parallel()

	got, err := nornicDBEntityLabelBatchSizes(func(key string) string {
		if key == nornicDBEntityLabelBatchSizesEnv {
			return "Function=30,Struct=80"
		}
		return ""
	}, 50)
	if err != nil {
		t.Fatalf("nornicDBEntityLabelBatchSizes() error = %v, want nil", err)
	}
	if got["Function"] != 30 {
		t.Fatalf("Function batch size = %d, want 30", got["Function"])
	}
	if got["Struct"] != 50 {
		t.Fatalf("Struct batch size = %d, want 50", got["Struct"])
	}
}

func TestNornicDBEntityLabelBatchSizesRejectsInvalidEnv(t *testing.T) {
	t.Parallel()

	_, err := nornicDBEntityLabelBatchSizes(func(key string) string {
		if key == nornicDBEntityLabelBatchSizesEnv {
			return "Function=nope"
		}
		return ""
	}, 100)
	if err == nil {
		t.Fatal("nornicDBEntityLabelBatchSizes() error = nil, want non-nil")
	}
	if !strings.Contains(err.Error(), nornicDBEntityLabelBatchSizesEnv) {
		t.Fatalf("nornicDBEntityLabelBatchSizes() error = %q, want env name", err)
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

type recordingGroupChunkExecutor struct {
	groupSizes    []int
	groupParams   []map[string]any
	executeParams []map[string]any
	callCount     int
	failAtCall    int
	err           error
}

func (r *recordingGroupChunkExecutor) Execute(_ context.Context, stmt sourceneo4j.Statement) error {
	r.executeParams = append(r.executeParams, stmt.Parameters)
	return nil
}

func (r *recordingGroupChunkExecutor) ExecuteGroup(_ context.Context, stmts []sourceneo4j.Statement) error {
	r.callCount++
	r.groupSizes = append(r.groupSizes, len(stmts))
	if len(stmts) > 0 {
		r.groupParams = append(r.groupParams, stmts[0].Parameters)
	}
	if r.failAtCall > 0 && r.callCount == r.failAtCall {
		return r.err
	}
	return nil
}

func equalIntSlices(got []int, want []int) bool {
	if len(got) != len(want) {
		return false
	}
	for i := range got {
		if got[i] != want[i] {
			return false
		}
	}
	return true
}

func minimalCanonicalMaterialization() projector.CanonicalMaterialization {
	return projector.CanonicalMaterialization{
		ScopeID:      "scope-1",
		GenerationID: "gen-1",
		RepoID:       "repo-1",
		RepoPath:     "/repos/my-repo",
		Repository: &projector.RepositoryRow{
			RepoID:    "repo-1",
			Name:      "my-repo",
			Path:      "/repos/my-repo",
			LocalPath: "/repos/my-repo",
		},
		Directories: []projector.DirectoryRow{
			{Path: "/repos/my-repo/src", Name: "src", ParentPath: "/repos/my-repo", RepoID: "repo-1", Depth: 0},
		},
		Files: []projector.FileRow{
			{Path: "/repos/my-repo/src/main.go", RelativePath: "src/main.go", Name: "main.go", Language: "go", RepoID: "repo-1", DirPath: "/repos/my-repo/src"},
		},
		Entities: []projector.EntityRow{
			{EntityID: "e1", Label: "Function", EntityName: "main", FilePath: "/repos/my-repo/src/main.go", RelativePath: "src/main.go", StartLine: 1, EndLine: 5, Language: "go", RepoID: "repo-1"},
		},
	}
}
