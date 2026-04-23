package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"io"
	"os"
	"testing"

	"github.com/spf13/cobra"

	"github.com/platformcontext/platform-context-graph/go/internal/pcglocal"
	"github.com/platformcontext/platform-context-graph/go/internal/query"
)

func TestGraphStatusForLayoutWithoutOwnerRecord(t *testing.T) {
	originalReadOwnerRecord := graphReadOwnerRecord
	t.Cleanup(func() {
		graphReadOwnerRecord = originalReadOwnerRecord
	})

	graphReadOwnerRecord = func(path string) (pcglocal.OwnerRecord, error) {
		return pcglocal.OwnerRecord{}, os.ErrNotExist
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
	originalProcessAlive := graphProcessAlive
	originalSocketHealthy := graphSocketHealthy
	t.Cleanup(func() {
		graphReadOwnerRecord = originalReadOwnerRecord
		graphProcessAlive = originalProcessAlive
		graphSocketHealthy = originalSocketHealthy
	})

	record := pcglocal.OwnerRecord{
		PID:             100,
		StartedAt:       "2026-04-22T20:00:00Z",
		Profile:         string(query.ProfileLocalAuthoritative),
		GraphBackend:    string(query.GraphBackendNornicDB),
		GraphPID:        200,
		GraphDataDir:    "/workspace/graph/nornicdb",
		GraphSocketPath: "/tmp/graph.sock",
		GraphVersion:    "v0.1.0",
	}
	graphReadOwnerRecord = func(path string) (pcglocal.OwnerRecord, error) {
		return record, nil
	}
	graphProcessAlive = func(pid int) bool {
		return pid == record.GraphPID
	}
	graphSocketHealthy = func(path string) bool {
		return path == record.GraphSocketPath
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
	if !got.GraphRunning {
		t.Fatal("GraphRunning = false, want true")
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
