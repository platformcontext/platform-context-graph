package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"io"
	"os"
	"testing"
	"time"

	"github.com/spf13/cobra"

	"github.com/platformcontext/platform-context-graph/go/internal/pcglocal"
	"github.com/platformcontext/platform-context-graph/go/internal/query"
)

func TestGraphStatusForLayoutWithoutOwnerRecord(t *testing.T) {
	originalReadOwnerRecord := graphReadOwnerRecord
	originalResolveBinary := graphResolveBinary
	t.Cleanup(func() {
		graphReadOwnerRecord = originalReadOwnerRecord
		graphResolveBinary = originalResolveBinary
	})

	graphReadOwnerRecord = func(path string) (pcglocal.OwnerRecord, error) {
		return pcglocal.OwnerRecord{}, os.ErrNotExist
	}
	graphResolveBinary = func() (string, error) {
		return "", errors.New("not installed")
	}

	got, err := graphStatusForLayout(pcglocal.Layout{
		WorkspaceRoot:   "/workspace/repo",
		WorkspaceID:     "workspace-id",
		OwnerRecordPath: "/workspace/owner.json",
	})
	if err != nil {
		t.Fatalf("graphStatusForLayout() error = %v, want nil", err)
	}
	if got.OwnerPresent {
		t.Fatal("OwnerPresent = true, want false")
	}
	if got.GraphRunning {
		t.Fatal("GraphRunning = true, want false")
	}
	if got.WorkspaceRoot != "/workspace/repo" {
		t.Fatalf("WorkspaceRoot = %q, want %q", got.WorkspaceRoot, "/workspace/repo")
	}
}

func TestGraphStatusForLayoutReportsRunningAuthoritativeBackend(t *testing.T) {
	originalReadOwnerRecord := graphReadOwnerRecord
	originalResolveBinary := graphResolveBinary
	originalReadVersion := graphReadVersion
	originalProcessAlive := localHostProcessAlive
	originalGraphHTTPHealthy := localGraphHTTPHealthy
	originalGraphBoltHealthy := localGraphBoltHealthy
	t.Cleanup(func() {
		graphReadOwnerRecord = originalReadOwnerRecord
		graphResolveBinary = originalResolveBinary
		graphReadVersion = originalReadVersion
		localHostProcessAlive = originalProcessAlive
		localGraphHTTPHealthy = originalGraphHTTPHealthy
		localGraphBoltHealthy = originalGraphBoltHealthy
	})

	record := pcglocal.OwnerRecord{
		PID:           100,
		StartedAt:     "2026-04-22T20:00:00Z",
		Profile:       string(query.ProfileLocalAuthoritative),
		GraphBackend:  string(query.GraphBackendNornicDB),
		GraphAddress:  "127.0.0.1",
		GraphPID:      200,
		GraphBoltPort: 17687,
		GraphHTTPPort: 17474,
		GraphDataDir:  "/workspace/graph/nornicdb",
		GraphVersion:  "1.0.42",
	}
	graphReadOwnerRecord = func(path string) (pcglocal.OwnerRecord, error) {
		return record, nil
	}
	graphResolveBinary = func() (string, error) {
		return "/tmp/nornicdb", nil
	}
	graphReadVersion = func(binaryPath string) (string, error) {
		return "1.0.42", nil
	}
	localHostProcessAlive = func(pid int) bool {
		return pid == record.GraphPID
	}
	localGraphHTTPHealthy = func(address string, port int, timeout time.Duration) bool {
		return address == record.GraphAddress && port == record.GraphHTTPPort
	}
	localGraphBoltHealthy = func(address string, port int, timeout time.Duration) bool {
		return address == record.GraphAddress && port == record.GraphBoltPort
	}

	got, err := graphStatusForLayout(pcglocal.Layout{
		WorkspaceRoot:   "/workspace/repo",
		WorkspaceID:     "workspace-id",
		OwnerRecordPath: "/workspace/owner.json",
	})
	if err != nil {
		t.Fatalf("graphStatusForLayout() error = %v, want nil", err)
	}
	if !got.OwnerPresent {
		t.Fatal("OwnerPresent = false, want true")
	}
	if got.Profile != string(query.ProfileLocalAuthoritative) {
		t.Fatalf("Profile = %q, want %q", got.Profile, query.ProfileLocalAuthoritative)
	}
	if got.GraphBackend != string(query.GraphBackendNornicDB) {
		t.Fatalf("GraphBackend = %q, want %q", got.GraphBackend, query.GraphBackendNornicDB)
	}
	if !got.GraphInstalled {
		t.Fatal("GraphInstalled = false, want true")
	}
	if got.GraphBinaryPath != "/tmp/nornicdb" {
		t.Fatalf("GraphBinaryPath = %q, want %q", got.GraphBinaryPath, "/tmp/nornicdb")
	}
	if !got.GraphRunning {
		t.Fatal("GraphRunning = false, want true")
	}
	if got.GraphBoltPort != 17687 {
		t.Fatalf("GraphBoltPort = %d, want %d", got.GraphBoltPort, 17687)
	}
	if got.GraphHTTPPort != 17474 {
		t.Fatalf("GraphHTTPPort = %d, want %d", got.GraphHTTPPort, 17474)
	}
}

func TestRunGraphStatusPrintsJSON(t *testing.T) {
	originalGetwd := graphGetwd
	originalBuildLayout := graphBuildLayout
	originalReadOwnerRecord := graphReadOwnerRecord
	t.Cleanup(func() {
		graphGetwd = originalGetwd
		graphBuildLayout = originalBuildLayout
		graphReadOwnerRecord = originalReadOwnerRecord
	})

	workspaceRoot := t.TempDir()
	graphGetwd = func() (string, error) {
		return workspaceRoot, nil
	}
	graphBuildLayout = func(workspaceRoot string) (pcglocal.Layout, error) {
		return pcglocal.Layout{
			WorkspaceRoot:   workspaceRoot,
			WorkspaceID:     "workspace-id",
			OwnerRecordPath: "/workspace/owner.json",
		}, nil
	}
	graphReadOwnerRecord = func(path string) (pcglocal.OwnerRecord, error) {
		return pcglocal.OwnerRecord{}, os.ErrNotExist
	}

	cmd := &cobra.Command{}
	cmd.Flags().String("workspace-root", "", "")

	output := captureStdout(t, func() {
		if err := runGraphStatus(cmd, nil); err != nil {
			t.Fatalf("runGraphStatus() error = %v, want nil", err)
		}
	})

	var got graphStatusOutput
	if err := json.Unmarshal([]byte(output), &got); err != nil {
		t.Fatalf("json.Unmarshal(output) error = %v, output=%q", err, output)
	}
	if got.WorkspaceID != "workspace-id" {
		t.Fatalf("WorkspaceID = %q, want %q", got.WorkspaceID, "workspace-id")
	}
}

func TestGraphLifecycleNotWiredReturnsActionableError(t *testing.T) {
	err := graphLifecycleNotWired("pcg graph start")
	if err == nil {
		t.Fatal("graphLifecycleNotWired() error = nil, want non-nil")
	}
	if err.Error() != "pcg graph start not wired yet" {
		t.Fatalf("graphLifecycleNotWired() error = %q, want %q", err.Error(), "pcg graph start not wired yet")
	}
}

func TestRunInstallNornicDBReturnsNotWiredError(t *testing.T) {
	err := graphLifecycleNotWired("pcg install nornicdb")
	if err == nil {
		t.Fatal("graphLifecycleNotWired() error = nil, want non-nil")
	}
	if err.Error() != "pcg install nornicdb not wired yet" {
		t.Fatalf("graphLifecycleNotWired() error = %q, want %q", err.Error(), "pcg install nornicdb not wired yet")
	}
}

func TestResolveNornicDBBinaryPrefersHeadlessBinary(t *testing.T) {
	originalLookPath := localGraphLookPath
	t.Cleanup(func() {
		localGraphLookPath = originalLookPath
	})
	t.Setenv("PCG_NORNICDB_BINARY", "")

	localGraphLookPath = func(file string) (string, error) {
		switch file {
		case "nornicdb-headless":
			return "/pcg/bin/nornicdb-headless", nil
		case "nornicdb":
			return "/pcg/bin/nornicdb", nil
		default:
			return "", errors.New("unexpected binary lookup")
		}
	}

	got, err := resolveNornicDBBinary()
	if err != nil {
		t.Fatalf("resolveNornicDBBinary() error = %v, want nil", err)
	}
	if got != "/pcg/bin/nornicdb-headless" {
		t.Fatalf("resolveNornicDBBinary() = %q, want headless path", got)
	}
}

func TestResolveNornicDBBinaryAllowsExplicitFullBinary(t *testing.T) {
	t.Setenv("PCG_NORNICDB_BINARY", "/opt/nornicdb")

	got, err := resolveNornicDBBinary()
	if err != nil {
		t.Fatalf("resolveNornicDBBinary() error = %v, want nil", err)
	}
	if got != "/opt/nornicdb" {
		t.Fatalf("resolveNornicDBBinary() = %q, want explicit path", got)
	}
}

func captureStdout(t *testing.T, fn func()) string {
	t.Helper()

	originalStdout := os.Stdout
	reader, writer, err := os.Pipe()
	if err != nil {
		t.Fatalf("os.Pipe() error = %v, want nil", err)
	}
	os.Stdout = writer
	t.Cleanup(func() {
		os.Stdout = originalStdout
	})

	done := make(chan string, 1)
	go func() {
		var buffer bytes.Buffer
		_, _ = io.Copy(&buffer, reader)
		done <- buffer.String()
	}()

	fn()

	_ = writer.Close()
	got := <-done
	return got
}

func TestRunGraphStatusReturnsBuildLayoutError(t *testing.T) {
	originalGetwd := graphGetwd
	originalBuildLayout := graphBuildLayout
	t.Cleanup(func() {
		graphGetwd = originalGetwd
		graphBuildLayout = originalBuildLayout
	})

	workspaceRoot := t.TempDir()
	graphGetwd = func() (string, error) {
		return workspaceRoot, nil
	}
	graphBuildLayout = func(workspaceRoot string) (pcglocal.Layout, error) {
		return pcglocal.Layout{}, errors.New("layout failed")
	}

	cmd := &cobra.Command{}
	cmd.Flags().String("workspace-root", "", "")

	err := runGraphStatus(cmd, nil)
	if err == nil || err.Error() != "layout failed" {
		t.Fatalf("runGraphStatus() error = %v, want %q", err, "layout failed")
	}
}
