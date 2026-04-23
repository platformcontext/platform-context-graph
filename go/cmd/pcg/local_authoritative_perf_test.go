package main

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"runtime"
	"strings"
	"testing"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/pcglocal"
	"github.com/platformcontext/platform-context-graph/go/internal/query"
)

const localAuthoritativePerfGateEnv = "PCG_LOCAL_AUTHORITATIVE_PERF"

func TestLocalAuthoritativeStartupEnvelope(t *testing.T) {
	if testing.Short() {
		t.Skip("local-authoritative perf smoke is skipped in short mode")
	}
	if !perfGateEnabled(localAuthoritativePerfGateEnv) {
		t.Skipf("set %s=true to run the local-authoritative startup perf smoke", localAuthoritativePerfGateEnv)
	}
	if strings.TrimSpace(os.Getenv("PCG_NORNICDB_BINARY")) == "" {
		t.Skip("set PCG_NORNICDB_BINARY to run the local-authoritative startup perf smoke")
	}
	if runtime.GOOS == "windows" {
		t.Skip("local-authoritative perf smoke is Unix-only in this slice")
	}

	t.Setenv("PCG_QUERY_PROFILE", string(query.ProfileLocalAuthoritative))
	t.Setenv("PCG_GRAPH_BACKEND", string(query.GraphBackendNornicDB))
	t.Setenv("PCG_HOME", t.TempDir())

	workspaceRoot := t.TempDir()
	layout, err := pcglocal.BuildLayout(os.Getenv, os.UserHomeDir, runtime.GOOS, workspaceRoot)
	if err != nil {
		t.Fatalf("BuildLayout() error = %v, want nil", err)
	}

	coldStart, err := measureLocalAuthoritativeStartup(layout)
	if err != nil {
		t.Fatalf("measureLocalAuthoritativeStartup(cold) error = %v, want nil", err)
	}
	t.Logf("local_authoritative cold start = %s", coldStart)
	if coldStart > 15*time.Second {
		t.Fatalf("local_authoritative cold start = %s, want <= %s", coldStart, 15*time.Second)
	}
	assertLocalAuthoritativeOwnerLockReleased(t, layout)

	warmRestart, err := measureLocalAuthoritativeStartup(layout)
	if err != nil {
		t.Fatalf("measureLocalAuthoritativeStartup(warm) error = %v, want nil", err)
	}
	t.Logf("local_authoritative warm restart = %s", warmRestart)
	if warmRestart > 5*time.Second {
		t.Fatalf("local_authoritative warm restart = %s, want <= %s", warmRestart, 5*time.Second)
	}
}

func assertLocalAuthoritativeOwnerLockReleased(t *testing.T, layout pcglocal.Layout) {
	t.Helper()

	lock, err := pcglocal.AcquireOwnerLock(layout.OwnerLockPath)
	if err != nil {
		t.Fatalf("AcquireOwnerLock(%q) error = %v, want nil after host shutdown", layout.OwnerLockPath, err)
	}
	if err := lock.Close(); err != nil {
		t.Fatalf("OwnerLock.Close() error = %v, want nil", err)
	}
}

func measureLocalAuthoritativeStartup(layout pcglocal.Layout) (time.Duration, error) {
	originalStartChild := localHostStartChildProcess
	originalWaitChild := localHostWaitChildProcess
	defer func() {
		localHostStartChildProcess = originalStartChild
		localHostWaitChildProcess = originalWaitChild
	}()

	ctx, cancel := context.WithTimeout(context.Background(), 90*time.Second)
	defer cancel()

	startedAt := time.Now()
	var readyAt time.Duration
	localHostStartChildProcess = func(name string, args []string, env []string) (*exec.Cmd, error) {
		if name != "pcg-ingester" {
			return nil, fmt.Errorf("unexpected child process %q", name)
		}
		record, err := pcglocal.ReadOwnerRecord(layout.OwnerRecordPath)
		if err != nil {
			return nil, fmt.Errorf("read owner record during startup: %w", err)
		}
		if record.Profile != string(query.ProfileLocalAuthoritative) {
			return nil, fmt.Errorf("owner record profile = %q, want %q", record.Profile, query.ProfileLocalAuthoritative)
		}
		if record.GraphBackend != string(query.GraphBackendNornicDB) {
			return nil, fmt.Errorf("owner record graph backend = %q, want %q", record.GraphBackend, query.GraphBackendNornicDB)
		}
		if record.PostgresPort <= 0 {
			return nil, fmt.Errorf("owner record postgres port = %d, want > 0", record.PostgresPort)
		}
		if record.GraphBoltPort <= 0 || record.GraphHTTPPort <= 0 {
			return nil, fmt.Errorf("owner record graph ports = bolt:%d http:%d, want > 0", record.GraphBoltPort, record.GraphHTTPPort)
		}
		readyAt = time.Since(startedAt)
		return &exec.Cmd{}, nil
	}
	localHostWaitChildProcess = func(ctx context.Context, cmd *exec.Cmd) error {
		return nil
	}

	if err := runOwnedLocalHostWithLayout(ctx, layout, localHostModeWatch); err != nil {
		return 0, err
	}
	if readyAt <= 0 {
		return 0, fmt.Errorf("local-authoritative host never reached ingester startup")
	}
	return readyAt, nil
}

func perfGateEnabled(name string) bool {
	value := strings.TrimSpace(strings.ToLower(os.Getenv(name)))
	switch value {
	case "1", "true", "yes", "on":
		return true
	default:
		return false
	}
}
