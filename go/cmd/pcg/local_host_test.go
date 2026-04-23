package main

import (
	"context"
	"errors"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/pcglocal"
	"github.com/platformcontext/platform-context-graph/go/internal/query"
)

func TestRunAttachedLocalMCPStdioUsesRecordedPostgresPort(t *testing.T) {
	layout := pcglocal.Layout{
		WorkspaceID:     "workspace-id",
		OwnerRecordPath: "/tmp/owner.json",
	}
	record := pcglocal.OwnerRecord{
		PID:                42,
		WorkspaceID:        layout.WorkspaceID,
		PostgresPort:       15439,
		PostgresSocketPath: "/tmp/.s.PGSQL.15439",
	}

	originalReadOwnerRecord := localHostReadOwnerRecord
	originalProcessAlive := localHostProcessAlive
	originalSocketHealthy := localHostSocketHealthy
	originalStartChild := localHostStartChildProcess
	originalWaitChild := localHostWaitChildProcess
	t.Cleanup(func() {
		localHostReadOwnerRecord = originalReadOwnerRecord
		localHostProcessAlive = originalProcessAlive
		localHostSocketHealthy = originalSocketHealthy
		localHostStartChildProcess = originalStartChild
		localHostWaitChildProcess = originalWaitChild
	})

	localHostReadOwnerRecord = func(path string) (pcglocal.OwnerRecord, error) {
		return record, nil
	}
	localHostProcessAlive = func(pid int) bool {
		return pid == record.PID
	}
	localHostSocketHealthy = func(path string) bool {
		return path == record.PostgresSocketPath
	}

	var gotEnv []string
	localHostStartChildProcess = func(name string, args []string, env []string) (*exec.Cmd, error) {
		gotEnv = append([]string(nil), env...)
		return &exec.Cmd{}, nil
	}
	localHostWaitChildProcess = func(ctx context.Context, cmd *exec.Cmd) error {
		return nil
	}

	attached, err := runAttachedLocalMCPStdio(context.Background(), layout)
	if err != nil {
		t.Fatalf("runAttachedLocalMCPStdio() error = %v, want nil", err)
	}
	if !attached {
		t.Fatal("runAttachedLocalMCPStdio() attached = false, want true")
	}

	dsn := envValue(gotEnv, "PCG_POSTGRES_DSN")
	if !strings.Contains(dsn, "host=127.0.0.1") || !strings.Contains(dsn, "port=15439") {
		t.Fatalf("PCG_POSTGRES_DSN = %q, want loopback DSN with recorded port", dsn)
	}
}

func TestRunAttachedLocalMCPStdioRejectsRequestedProfileMismatch(t *testing.T) {
	t.Setenv("PCG_QUERY_PROFILE", string(query.ProfileLocalAuthoritative))

	layout := pcglocal.Layout{
		WorkspaceID:     "workspace-id",
		OwnerRecordPath: "/tmp/owner.json",
	}
	record := pcglocal.OwnerRecord{
		PID:                42,
		WorkspaceID:        layout.WorkspaceID,
		PostgresPort:       15439,
		PostgresSocketPath: "/tmp/.s.PGSQL.15439",
		Profile:            string(query.ProfileLocalLightweight),
	}

	originalReadOwnerRecord := localHostReadOwnerRecord
	originalProcessAlive := localHostProcessAlive
	originalSocketHealthy := localHostSocketHealthy
	originalStartChild := localHostStartChildProcess
	t.Cleanup(func() {
		localHostReadOwnerRecord = originalReadOwnerRecord
		localHostProcessAlive = originalProcessAlive
		localHostSocketHealthy = originalSocketHealthy
		localHostStartChildProcess = originalStartChild
	})

	localHostReadOwnerRecord = func(path string) (pcglocal.OwnerRecord, error) {
		return record, nil
	}
	localHostProcessAlive = func(pid int) bool {
		return pid == record.PID
	}
	localHostSocketHealthy = func(path string) bool {
		return path == record.PostgresSocketPath
	}

	startCalled := false
	localHostStartChildProcess = func(name string, args []string, env []string) (*exec.Cmd, error) {
		startCalled = true
		return &exec.Cmd{}, nil
	}

	attached, err := runAttachedLocalMCPStdio(context.Background(), layout)
	if err == nil || !strings.Contains(err.Error(), "requested profile") {
		t.Fatalf("runAttachedLocalMCPStdio() error = %v, want profile mismatch error", err)
	}
	if !attached {
		t.Fatal("runAttachedLocalMCPStdio() attached = false, want true on owner mismatch failure")
	}
	if startCalled {
		t.Fatal("runAttachedLocalMCPStdio() started child process despite owner/profile mismatch")
	}
}

func TestRunAttachedLocalMCPStdioRejectsUnhealthyAuthoritativeGraph(t *testing.T) {
	layout := pcglocal.Layout{
		WorkspaceID:     "workspace-id",
		OwnerRecordPath: "/tmp/owner.json",
	}
	record := pcglocal.OwnerRecord{
		PID:                42,
		WorkspaceID:        layout.WorkspaceID,
		PostgresPort:       15439,
		PostgresSocketPath: "/tmp/.s.PGSQL.15439",
		Profile:            string(query.ProfileLocalAuthoritative),
		GraphBackend:       string(query.GraphBackendNornicDB),
		GraphPID:           77,
		GraphBoltPort:      17687,
		GraphHTTPPort:      17474,
	}

	originalReadOwnerRecord := localHostReadOwnerRecord
	originalProcessAlive := localHostProcessAlive
	originalSocketHealthy := localHostSocketHealthy
	originalGraphHealthy := localHostGraphHealthy
	originalStartChild := localHostStartChildProcess
	t.Cleanup(func() {
		localHostReadOwnerRecord = originalReadOwnerRecord
		localHostProcessAlive = originalProcessAlive
		localHostSocketHealthy = originalSocketHealthy
		localHostGraphHealthy = originalGraphHealthy
		localHostStartChildProcess = originalStartChild
	})

	localHostReadOwnerRecord = func(path string) (pcglocal.OwnerRecord, error) {
		return record, nil
	}
	localHostProcessAlive = func(pid int) bool {
		return pid == record.PID
	}
	localHostSocketHealthy = func(path string) bool {
		return path == record.PostgresSocketPath
	}
	localHostGraphHealthy = func(record pcglocal.OwnerRecord) bool {
		return false
	}

	startCalled := false
	localHostStartChildProcess = func(name string, args []string, env []string) (*exec.Cmd, error) {
		startCalled = true
		return &exec.Cmd{}, nil
	}

	attached, err := runAttachedLocalMCPStdio(context.Background(), layout)
	if err == nil || !strings.Contains(err.Error(), "graph backend") {
		t.Fatalf("runAttachedLocalMCPStdio() error = %v, want graph backend health error", err)
	}
	if !attached {
		t.Fatal("runAttachedLocalMCPStdio() attached = false, want true when owner exists but graph is unhealthy")
	}
	if startCalled {
		t.Fatal("runAttachedLocalMCPStdio() started MCP child despite unhealthy authoritative graph")
	}
}

func TestLocalHostIngesterOverridesUseFilesystemDirectMode(t *testing.T) {
	layout := pcglocal.Layout{
		WorkspaceRoot: "/workspace/repo",
		CacheDir:      "/pcg/cache",
	}

	got := localHostIngesterOverrides(layout, localHostModeWatch, localHostRuntimeConfig{Profile: query.ProfileLocalLightweight})
	if got["PCG_REPO_SOURCE_MODE"] != "filesystem" {
		t.Fatalf("PCG_REPO_SOURCE_MODE = %q, want %q", got["PCG_REPO_SOURCE_MODE"], "filesystem")
	}
	if got["PCG_FILESYSTEM_ROOT"] != layout.WorkspaceRoot {
		t.Fatalf("PCG_FILESYSTEM_ROOT = %q, want %q", got["PCG_FILESYSTEM_ROOT"], layout.WorkspaceRoot)
	}
	if got["PCG_FILESYSTEM_DIRECT"] != "true" {
		t.Fatalf("PCG_FILESYSTEM_DIRECT = %q, want %q", got["PCG_FILESYSTEM_DIRECT"], "true")
	}
	wantReposDir := filepath.Join(layout.CacheDir, "repos")
	if got["PCG_REPOS_DIR"] != wantReposDir {
		t.Fatalf("PCG_REPOS_DIR = %q, want %q", got["PCG_REPOS_DIR"], wantReposDir)
	}
}

func TestResolveLocalHostRuntimeConfig(t *testing.T) {
	t.Run("defaults to lightweight profile", func(t *testing.T) {
		got, err := resolveLocalHostRuntimeConfig(func(string) string { return "" })
		if err != nil {
			t.Fatalf("resolveLocalHostRuntimeConfig() error = %v, want nil", err)
		}
		if got.Profile != query.ProfileLocalLightweight {
			t.Fatalf("Profile = %q, want %q", got.Profile, query.ProfileLocalLightweight)
		}
		if got.GraphBackend != "" {
			t.Fatalf("GraphBackend = %q, want empty", got.GraphBackend)
		}
	})

	t.Run("authoritative defaults to nornicdb", func(t *testing.T) {
		got, err := resolveLocalHostRuntimeConfig(func(key string) string {
			if key == "PCG_QUERY_PROFILE" {
				return string(query.ProfileLocalAuthoritative)
			}
			return ""
		})
		if err != nil {
			t.Fatalf("resolveLocalHostRuntimeConfig() error = %v, want nil", err)
		}
		if got.Profile != query.ProfileLocalAuthoritative {
			t.Fatalf("Profile = %q, want %q", got.Profile, query.ProfileLocalAuthoritative)
		}
		if got.GraphBackend != query.GraphBackendNornicDB {
			t.Fatalf("GraphBackend = %q, want %q", got.GraphBackend, query.GraphBackendNornicDB)
		}
	})

	t.Run("rejects unsupported profiles", func(t *testing.T) {
		_, err := resolveLocalHostRuntimeConfig(func(key string) string {
			if key == "PCG_QUERY_PROFILE" {
				return string(query.ProfileProduction)
			}
			return ""
		})
		if err == nil || !strings.Contains(err.Error(), "local host supports only") {
			t.Fatalf("resolveLocalHostRuntimeConfig() error = %v, want unsupported profile error", err)
		}
	})

	t.Run("rejects graph backend override in lightweight mode", func(t *testing.T) {
		_, err := resolveLocalHostRuntimeConfig(func(key string) string {
			if key == "PCG_GRAPH_BACKEND" {
				return string(query.GraphBackendNornicDB)
			}
			return ""
		})
		if err == nil || !strings.Contains(err.Error(), "PCG_GRAPH_BACKEND") {
			t.Fatalf("resolveLocalHostRuntimeConfig() error = %v, want graph-backend override error", err)
		}
	})
}

func TestLocalHostEnvHonorsRuntimeConfig(t *testing.T) {
	t.Run("lightweight disables neo4j", func(t *testing.T) {
		got := localHostEnv("dsn", localHostRuntimeConfig{Profile: query.ProfileLocalLightweight}, nil, nil)
		if envValue(got, "PCG_QUERY_PROFILE") != string(query.ProfileLocalLightweight) {
			t.Fatalf("PCG_QUERY_PROFILE = %q, want %q", envValue(got, "PCG_QUERY_PROFILE"), query.ProfileLocalLightweight)
		}
		if envValue(got, "PCG_DISABLE_NEO4J") != "true" {
			t.Fatalf("PCG_DISABLE_NEO4J = %q, want %q", envValue(got, "PCG_DISABLE_NEO4J"), "true")
		}
		if envValue(got, "PCG_GRAPH_BACKEND") != "" {
			t.Fatalf("PCG_GRAPH_BACKEND = %q, want empty", envValue(got, "PCG_GRAPH_BACKEND"))
		}
	})

	t.Run("authoritative sets graph backend", func(t *testing.T) {
		originalEnviron := pcgEnviron
		pcgEnviron = func() []string {
			return []string{"PCG_DISABLE_NEO4J=true"}
		}
		t.Cleanup(func() {
			pcgEnviron = originalEnviron
		})

		got := localHostEnv("dsn", localHostRuntimeConfig{
			Profile:      query.ProfileLocalAuthoritative,
			GraphBackend: query.GraphBackendNornicDB,
		}, nil, nil)
		if envValue(got, "PCG_QUERY_PROFILE") != string(query.ProfileLocalAuthoritative) {
			t.Fatalf("PCG_QUERY_PROFILE = %q, want %q", envValue(got, "PCG_QUERY_PROFILE"), query.ProfileLocalAuthoritative)
		}
		if envValue(got, "PCG_GRAPH_BACKEND") != string(query.GraphBackendNornicDB) {
			t.Fatalf("PCG_GRAPH_BACKEND = %q, want %q", envValue(got, "PCG_GRAPH_BACKEND"), query.GraphBackendNornicDB)
		}
		if envValue(got, "PCG_DISABLE_NEO4J") != "" {
			t.Fatalf("PCG_DISABLE_NEO4J = %q, want empty override", envValue(got, "PCG_DISABLE_NEO4J"))
		}
	})

	t.Run("authoritative injects graph bolt connection", func(t *testing.T) {
		got := localHostEnv(
			"dsn",
			localHostRuntimeConfig{
				Profile:      query.ProfileLocalAuthoritative,
				GraphBackend: query.GraphBackendNornicDB,
			},
			&managedLocalGraph{
				Backend:  query.GraphBackendNornicDB,
				Address:  "127.0.0.1",
				BoltPort: 17687,
			},
			nil,
		)
		if envValue(got, "PCG_NEO4J_URI") != "bolt://127.0.0.1:17687" {
			t.Fatalf("PCG_NEO4J_URI = %q, want %q", envValue(got, "PCG_NEO4J_URI"), "bolt://127.0.0.1:17687")
		}
		if envValue(got, "PCG_NEO4J_USERNAME") != localNornicDBAdminUsername {
			t.Fatalf("PCG_NEO4J_USERNAME = %q, want %q", envValue(got, "PCG_NEO4J_USERNAME"), localNornicDBAdminUsername)
		}
		if envValue(got, "PCG_NEO4J_PASSWORD") != localNornicDBAdminPassword {
			t.Fatalf("PCG_NEO4J_PASSWORD = %q, want %q", envValue(got, "PCG_NEO4J_PASSWORD"), localNornicDBAdminPassword)
		}
		if envValue(got, "DEFAULT_DATABASE") != localNornicDBDefaultDatabase {
			t.Fatalf("DEFAULT_DATABASE = %q, want %q", envValue(got, "DEFAULT_DATABASE"), localNornicDBDefaultDatabase)
		}
	})
}

func TestRunOwnedLocalHostWithLayoutAuthoritativeStartsManagedGraph(t *testing.T) {
	t.Setenv("PCG_QUERY_PROFILE", string(query.ProfileLocalAuthoritative))

	originalPrepareWorkspace := localHostPrepareWorkspace
	originalStartEmbeddedPostgres := localHostStartEmbeddedPostgres
	originalStartManagedGraph := localHostStartManagedGraph
	originalWriteOwnerRecord := localHostWriteOwnerRecord
	originalHostname := localHostHostname
	originalStartChild := localHostStartChildProcess
	originalWaitChild := localHostWaitChildProcess
	originalApplyBootstrap := localHostApplyBootstrap
	t.Cleanup(func() {
		localHostPrepareWorkspace = originalPrepareWorkspace
		localHostStartEmbeddedPostgres = originalStartEmbeddedPostgres
		localHostStartManagedGraph = originalStartManagedGraph
		localHostWriteOwnerRecord = originalWriteOwnerRecord
		localHostHostname = originalHostname
		localHostStartChildProcess = originalStartChild
		localHostWaitChildProcess = originalWaitChild
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
	localHostStartManagedGraph = func(ctx context.Context, layout pcglocal.Layout, runtimeConfig localHostRuntimeConfig) (*managedLocalGraph, error) {
		if runtimeConfig.GraphBackend != query.GraphBackendNornicDB {
			t.Fatalf("runtimeConfig.GraphBackend = %q, want %q", runtimeConfig.GraphBackend, query.GraphBackendNornicDB)
		}
		return &managedLocalGraph{
			Backend:    query.GraphBackendNornicDB,
			Version:    "1.0.42",
			BinaryPath: "/tmp/nornicdb",
			Address:    "127.0.0.1",
			BoltPort:   17687,
			HTTPPort:   17474,
			DataDir:    "/workspace/graph/nornicdb",
			LogPath:    "/workspace/logs/graph-nornicdb.log",
			PID:        88,
			Cmd:        &exec.Cmd{},
		}, nil
	}
	localHostHostname = func() (string, error) {
		return "local-test", nil
	}
	localHostApplyBootstrap = func(ctx context.Context, dsn string) error {
		return nil
	}
	var written pcglocal.OwnerRecord
	localHostWriteOwnerRecord = func(path string, record pcglocal.OwnerRecord) error {
		written = record
		return nil
	}
	localHostStartChildProcess = func(name string, args []string, env []string) (*exec.Cmd, error) {
		if envValue(env, "PCG_NEO4J_URI") != "bolt://127.0.0.1:17687" {
			t.Fatalf("PCG_NEO4J_URI = %q, want %q", envValue(env, "PCG_NEO4J_URI"), "bolt://127.0.0.1:17687")
		}
		return &exec.Cmd{}, nil
	}
	localHostWaitChildProcess = func(ctx context.Context, cmd *exec.Cmd) error {
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
	if written.GraphPID != 88 {
		t.Fatalf("written.GraphPID = %d, want %d", written.GraphPID, 88)
	}
	if written.GraphBackend != string(query.GraphBackendNornicDB) {
		t.Fatalf("written.GraphBackend = %q, want %q", written.GraphBackend, query.GraphBackendNornicDB)
	}
	if written.GraphBoltPort != 17687 {
		t.Fatalf("written.GraphBoltPort = %d, want %d", written.GraphBoltPort, 17687)
	}
	if written.GraphHTTPPort != 17474 {
		t.Fatalf("written.GraphHTTPPort = %d, want %d", written.GraphHTTPPort, 17474)
	}
	if written.GraphVersion != "1.0.42" {
		t.Fatalf("written.GraphVersion = %q, want %q", written.GraphVersion, "1.0.42")
	}
}

func TestRuntimeConfigFromOwnerRecordDefaultsAuthoritativeBackendToNornicDB(t *testing.T) {
	got, err := runtimeConfigFromOwnerRecord(pcglocal.OwnerRecord{
		Profile: string(query.ProfileLocalAuthoritative),
	})
	if err != nil {
		t.Fatalf("runtimeConfigFromOwnerRecord() error = %v, want nil", err)
	}
	if got.Profile != query.ProfileLocalAuthoritative {
		t.Fatalf("Profile = %q, want %q", got.Profile, query.ProfileLocalAuthoritative)
	}
	if got.GraphBackend != query.GraphBackendNornicDB {
		t.Fatalf("GraphBackend = %q, want %q", got.GraphBackend, query.GraphBackendNornicDB)
	}
}

func TestGraphHealthyFromOwnerRecord(t *testing.T) {
	originalProcessAlive := localHostProcessAlive
	originalGraphHTTPHealthy := localGraphHTTPHealthy
	originalGraphBoltHealthy := localGraphBoltHealthy
	t.Cleanup(func() {
		localHostProcessAlive = originalProcessAlive
		localGraphHTTPHealthy = originalGraphHTTPHealthy
		localGraphBoltHealthy = originalGraphBoltHealthy
	})

	record := pcglocal.OwnerRecord{
		GraphPID:      88,
		GraphAddress:  "127.0.0.1",
		GraphBoltPort: 17687,
		GraphHTTPPort: 17474,
	}
	localHostProcessAlive = func(pid int) bool {
		return pid == 88
	}
	localGraphHTTPHealthy = func(address string, port int, timeout time.Duration) bool {
		return address == "127.0.0.1" && port == 17474
	}
	localGraphBoltHealthy = func(address string, port int, timeout time.Duration) bool {
		return address == "127.0.0.1" && port == 17687
	}

	if !graphHealthyFromOwnerRecord(record) {
		t.Fatal("graphHealthyFromOwnerRecord() = false, want true")
	}
}

func TestWaitLocalChildProcessCancelUsesSingleWaiter(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("local child signal semantics are Unix-only in this slice")
	}

	cmd := exec.Command("/bin/sh", "-c", "trap 'exit 0' INT TERM; while :; do sleep 1; done")
	if err := cmd.Start(); err != nil {
		t.Fatalf("Start() error = %v, want nil", err)
	}
	t.Cleanup(func() {
		_ = cmd.Process.Kill()
		_, _ = cmd.Process.Wait()
	})

	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan error, 1)
	go func() {
		done <- waitLocalChildProcess(ctx, cmd)
	}()
	cancel()

	select {
	case err := <-done:
		if err != nil {
			t.Fatalf("waitLocalChildProcess() error = %v, want nil", err)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("waitLocalChildProcess() timed out after cancel")
	}
}

func TestNormalizeLocalChildExitTreatsAlreadyWaitedAsClean(t *testing.T) {
	err := normalizeLocalChildExit(exec.ErrWaitDelay)
	if err == nil {
		t.Fatal("normalizeLocalChildExit(exec.ErrWaitDelay) = nil, want non-nil")
	}

	err = normalizeLocalChildExit(&exec.Error{Name: "child", Err: errors.New("Wait was already called")})
	if err != nil {
		t.Fatalf("normalizeLocalChildExit(already waited) error = %v, want nil", err)
	}
}

func envValue(env []string, key string) string {
	prefix := key + "="
	for _, entry := range env {
		if strings.HasPrefix(entry, prefix) {
			return strings.TrimPrefix(entry, prefix)
		}
	}
	return ""
}
