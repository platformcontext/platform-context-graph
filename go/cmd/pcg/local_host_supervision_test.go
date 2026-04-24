package main

import (
	"context"
	"errors"
	"os/exec"
	"slices"
	"strings"
	"testing"

	"github.com/platformcontext/platform-context-graph/go/internal/pcglocal"
	"github.com/platformcontext/platform-context-graph/go/internal/query"
)

func TestRunOwnedLocalHostWithLayoutAuthoritativeWatchStartsReducerAndIngester(t *testing.T) {
	t.Setenv("PCG_QUERY_PROFILE", string(query.ProfileLocalAuthoritative))

	originalPrepareWorkspace := localHostPrepareWorkspace
	originalStartEmbeddedPostgres := localHostStartEmbeddedPostgres
	originalStartManagedGraph := localHostStartManagedGraph
	originalWriteOwnerRecord := localHostWriteOwnerRecord
	originalHostname := localHostHostname
	originalStartChild := localHostStartChildProcess
	originalWaitManagedChildren := localHostWaitManagedChildren
	originalApplyBootstrap := localHostApplyBootstrap
	originalApplyGraphBootstrap := localHostApplyGraphBootstrap
	t.Cleanup(func() {
		localHostPrepareWorkspace = originalPrepareWorkspace
		localHostStartEmbeddedPostgres = originalStartEmbeddedPostgres
		localHostStartManagedGraph = originalStartManagedGraph
		localHostWriteOwnerRecord = originalWriteOwnerRecord
		localHostHostname = originalHostname
		localHostStartChildProcess = originalStartChild
		localHostWaitManagedChildren = originalWaitManagedChildren
		localHostApplyBootstrap = originalApplyBootstrap
		localHostApplyGraphBootstrap = originalApplyGraphBootstrap
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
	localHostApplyGraphBootstrap = func(ctx context.Context, runtimeConfig localHostRuntimeConfig, graph *managedLocalGraph) error {
		return nil
	}

	var started []string
	localHostStartChildProcess = func(name string, args []string, env []string) (*exec.Cmd, error) {
		started = append(started, name)
		return &exec.Cmd{}, nil
	}

	var waited []string
	var expectedCleanExit string
	localHostWaitManagedChildren = func(ctx context.Context, children []localHostChild, allowCleanExit string) error {
		for _, child := range children {
			waited = append(waited, child.name)
		}
		expectedCleanExit = allowCleanExit
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

	wantChildren := []string{"pcg-reducer", "pcg-ingester"}
	if !slices.Equal(started, wantChildren) {
		t.Fatalf("started children = %#v, want %#v", started, wantChildren)
	}
	if !slices.Equal(waited, wantChildren) {
		t.Fatalf("waited children = %#v, want %#v", waited, wantChildren)
	}
	if expectedCleanExit != "" {
		t.Fatalf("allowCleanExit = %q, want empty", expectedCleanExit)
	}
}

func TestRunOwnedLocalHostWithLayoutLightweightWatchStartsOnlyIngester(t *testing.T) {
	originalPrepareWorkspace := localHostPrepareWorkspace
	originalStartEmbeddedPostgres := localHostStartEmbeddedPostgres
	originalWriteOwnerRecord := localHostWriteOwnerRecord
	originalHostname := localHostHostname
	originalStartChild := localHostStartChildProcess
	originalWaitManagedChildren := localHostWaitManagedChildren
	originalApplyBootstrap := localHostApplyBootstrap
	t.Cleanup(func() {
		localHostPrepareWorkspace = originalPrepareWorkspace
		localHostStartEmbeddedPostgres = originalStartEmbeddedPostgres
		localHostWriteOwnerRecord = originalWriteOwnerRecord
		localHostHostname = originalHostname
		localHostStartChildProcess = originalStartChild
		localHostWaitManagedChildren = originalWaitManagedChildren
		localHostApplyBootstrap = originalApplyBootstrap
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
	localHostWriteOwnerRecord = func(path string, record pcglocal.OwnerRecord) error {
		return nil
	}
	localHostHostname = func() (string, error) {
		return "local-test", nil
	}
	localHostApplyBootstrap = func(ctx context.Context, dsn string) error {
		return nil
	}

	var started []string
	localHostStartChildProcess = func(name string, args []string, env []string) (*exec.Cmd, error) {
		started = append(started, name)
		return &exec.Cmd{}, nil
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

	wantChildren := []string{"pcg-ingester"}
	if !slices.Equal(started, wantChildren) {
		t.Fatalf("started children = %#v, want %#v", started, wantChildren)
	}
}

func TestWaitLocalHostChildrenReturnsReducerExitError(t *testing.T) {
	originalWaitChild := localHostWaitChildProcess
	t.Cleanup(func() {
		localHostWaitChildProcess = originalWaitChild
	})

	reducerCmd := &exec.Cmd{}
	ingesterCmd := &exec.Cmd{}
	reducerErr := errors.New("reducer exited")

	localHostWaitChildProcess = func(ctx context.Context, cmd *exec.Cmd) error {
		switch cmd {
		case reducerCmd:
			return reducerErr
		case ingesterCmd:
			<-ctx.Done()
			return nil
		default:
			t.Fatalf("unexpected child %p", cmd)
			return nil
		}
	}

	err := waitLocalHostChildren(context.Background(), []localHostChild{
		{name: "pcg-reducer", cmd: reducerCmd},
		{name: "pcg-ingester", cmd: ingesterCmd},
	}, "")
	if err == nil || !strings.Contains(err.Error(), "pcg-reducer exited") {
		t.Fatalf("waitLocalHostChildren() error = %v, want reducer exit error", err)
	}
}

func TestWaitLocalHostChildrenAllowsMCPCleanExit(t *testing.T) {
	originalWaitChild := localHostWaitChildProcess
	t.Cleanup(func() {
		localHostWaitChildProcess = originalWaitChild
	})

	reducerCmd := &exec.Cmd{}
	ingesterCmd := &exec.Cmd{}
	mcpCmd := &exec.Cmd{}

	localHostWaitChildProcess = func(ctx context.Context, cmd *exec.Cmd) error {
		switch cmd {
		case mcpCmd:
			return nil
		case reducerCmd, ingesterCmd:
			<-ctx.Done()
			return nil
		default:
			t.Fatalf("unexpected child %p", cmd)
			return nil
		}
	}

	err := waitLocalHostChildren(context.Background(), []localHostChild{
		{name: "pcg-reducer", cmd: reducerCmd},
		{name: "pcg-ingester", cmd: ingesterCmd},
		{name: "pcg-mcp-server", cmd: mcpCmd},
	}, "pcg-mcp-server")
	if err != nil {
		t.Fatalf("waitLocalHostChildren() error = %v, want nil", err)
	}
}
