package main

import (
	"context"
	"os/exec"
	"strings"
	"testing"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/pcglocal"
	"github.com/platformcontext/platform-context-graph/go/internal/query"
	statuspkg "github.com/platformcontext/platform-context-graph/go/internal/status"
)

func TestRenderLocalHostProgressSnapshotIncludesOwnerFlowAndQueue(t *testing.T) {
	t.Parallel()

	rendered := renderLocalHostProgressSnapshot(
		"/workspace/repo",
		localHostRuntimeConfig{
			Profile:      query.ProfileLocalAuthoritative,
			GraphBackend: query.GraphBackendNornicDB,
		},
		statuspkg.Report{
			AsOf: time.Date(2026, time.April, 23, 21, 15, 0, 0, time.UTC),
			Health: statuspkg.HealthSummary{
				State: "progressing",
			},
			FlowSummaries: []statuspkg.FlowSummary{
				{Lane: "collector", Progress: "scopes active=1", Backlog: "generations pending=1"},
				{Lane: "projector", Progress: "stage running=2", Backlog: "queue outstanding=6"},
				{Lane: "reducer", Progress: "stage retrying=1", Backlog: "top domain code_call_materialization outstanding=4"},
			},
			Queue: statuspkg.QueueSnapshot{
				Pending:              3,
				InFlight:             2,
				Retrying:             1,
				DeadLetter:           0,
				Failed:               0,
				OldestOutstandingAge: 5*time.Minute + 2*time.Second,
			},
		},
	)

	for _, want := range []string{
		"Local progress 2026-04-23T21:15:00Z",
		"Owner: running | profile=local_authoritative | backend=nornicdb | workspace=/workspace/repo",
		"Health: progressing",
		"Collector: progress=scopes active=1 | backlog=generations pending=1",
		"Projector: progress=stage running=2 | backlog=queue outstanding=6",
		"Reducer: progress=stage retrying=1 | backlog=top domain code_call_materialization outstanding=4",
		"Queue: pending=3 in_flight=2 retrying=1 dead_letter=0 failed=0 oldest=5m2s",
	} {
		if !strings.Contains(rendered, want) {
			t.Fatalf("rendered progress missing %q in %q", want, rendered)
		}
	}
}

func TestRunOwnedLocalHostWithLayoutWatchStartsAndStopsProgressReporter(t *testing.T) {
	t.Setenv("PCG_QUERY_PROFILE", string(query.ProfileLocalAuthoritative))

	originalPrepareWorkspace := localHostPrepareWorkspace
	originalStartEmbeddedPostgres := localHostStartEmbeddedPostgres
	originalStartManagedGraph := localHostStartManagedGraph
	originalWriteOwnerRecord := localHostWriteOwnerRecord
	originalHostname := localHostHostname
	originalStartChild := localHostStartChildProcess
	originalWaitManagedChildren := localHostWaitManagedChildren
	originalApplyBootstrap := localHostApplyBootstrap
	originalStartProgressReporter := localHostStartProgressReporter
	t.Cleanup(func() {
		localHostPrepareWorkspace = originalPrepareWorkspace
		localHostStartEmbeddedPostgres = originalStartEmbeddedPostgres
		localHostStartManagedGraph = originalStartManagedGraph
		localHostWriteOwnerRecord = originalWriteOwnerRecord
		localHostHostname = originalHostname
		localHostStartChildProcess = originalStartChild
		localHostWaitManagedChildren = originalWaitManagedChildren
		localHostApplyBootstrap = originalApplyBootstrap
		localHostStartProgressReporter = originalStartProgressReporter
	})

	localHostPrepareWorkspace = func(layout pcglocal.Layout) (*pcglocal.OwnerLock, error) {
		return &pcglocal.OwnerLock{}, nil
	}
	localHostStartEmbeddedPostgres = func(ctx context.Context, layout pcglocal.Layout) (*pcglocal.ManagedPostgres, error) {
		return &pcglocal.ManagedPostgres{
			DSN:        "host=127.0.0.1 port=15439 user=pcg password=change-me dbname=postgres sslmode=disable",
			Port:       15439,
			DataDir:    "/workspace/postgres/data",
			SocketDir:  "/tmp/pcg",
			SocketPath: "/tmp/pcg/.s.PGSQL.15439",
			PID:        21,
		}, nil
	}
	localHostStartManagedGraph = func(ctx context.Context, layout pcglocal.Layout, runtimeConfig localHostRuntimeConfig) (*managedLocalGraph, error) {
		return &managedLocalGraph{
			Backend:  query.GraphBackendNornicDB,
			Address:  "127.0.0.1",
			BoltPort: 17687,
			HTTPPort: 17474,
			Username: "admin",
			Password: "workspace-secret",
			PID:      88,
			Cmd:      &exec.Cmd{},
		}, nil
	}
	localHostWriteOwnerRecord = func(path string, record pcglocal.OwnerRecord) error {
		return nil
	}
	localHostHostname = func() (string, error) {
		return "local-test", nil
	}
	localHostApplyBootstrap = func(ctx context.Context, dsn string) error {
		return nil
	}
	localHostStartChildProcess = func(name string, args []string, env []string) (*exec.Cmd, error) {
		return &exec.Cmd{}, nil
	}

	progressStarts := 0
	progressStops := 0
	localHostStartProgressReporter = func(
		ctx context.Context,
		workspaceRoot string,
		dsn string,
		runtimeConfig localHostRuntimeConfig,
	) (localHostProgressStop, error) {
		progressStarts++
		if workspaceRoot != "/workspace/repo" {
			t.Fatalf("progress reporter workspace root = %q, want /workspace/repo", workspaceRoot)
		}
		if runtimeConfig.Profile != query.ProfileLocalAuthoritative {
			t.Fatalf("progress reporter profile = %q, want %q", runtimeConfig.Profile, query.ProfileLocalAuthoritative)
		}
		return func() error {
			progressStops++
			return nil
		}, nil
	}

	localHostWaitManagedChildren = func(ctx context.Context, children []localHostChild, allowCleanExit string) error {
		return nil
	}

	err := runOwnedLocalHostWithLayout(context.Background(), pcglocal.Layout{
		WorkspaceID:     "workspace-id",
		WorkspaceRoot:   "/workspace/repo",
		OwnerRecordPath: "/workspace/owner.json",
		CacheDir:        "/workspace/cache",
		LogsDir:         "/workspace/logs",
		GraphDir:        "/workspace/graph",
	}, localHostModeWatch)
	if err != nil {
		t.Fatalf("runOwnedLocalHostWithLayout() error = %v, want nil", err)
	}

	if got, want := progressStarts, 1; got != want {
		t.Fatalf("progress reporter starts = %d, want %d", got, want)
	}
	if got, want := progressStops, 1; got != want {
		t.Fatalf("progress reporter stops = %d, want %d", got, want)
	}
}
