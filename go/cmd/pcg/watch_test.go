package main

import (
	"errors"
	"os"
	"path/filepath"
	"reflect"
	"testing"

	"github.com/spf13/cobra"
)

func TestRunWatchExecsIngesterWithResolvedWorkspaceRoot(t *testing.T) {
	base := t.TempDir()
	repoRoot := filepath.Join(base, "repo")
	startPath := filepath.Join(repoRoot, "pkg")
	if err := os.MkdirAll(startPath, 0o755); err != nil {
		t.Fatalf("MkdirAll() error = %v, want nil", err)
	}
	if err := os.Mkdir(filepath.Join(repoRoot, ".git"), 0o755); err != nil {
		t.Fatalf("Mkdir(.git) error = %v, want nil", err)
	}

	restore, calls := stubWatchRuntime()
	defer restore()

	wantExecErr := errors.New("exec sentinel")
	calls.lookPath = func(file string) (string, error) {
		if file != "pcg-ingester" {
			t.Fatalf("LookPath() file = %q, want %q", file, "pcg-ingester")
		}
		return "/tmp/pcg-ingester", nil
	}
	calls.exec = func(binary string, args []string, env []string) error {
		calls.binary = binary
		calls.args = append([]string(nil), args...)
		calls.env = append([]string(nil), env...)
		return wantExecErr
	}

	err := runWatch(&cobra.Command{}, []string{startPath})
	if !errors.Is(err, wantExecErr) {
		t.Fatalf("runWatch() error = %v, want %v", err, wantExecErr)
	}

	if calls.binary != "/tmp/pcg-ingester" {
		t.Fatalf("exec binary = %q, want %q", calls.binary, "/tmp/pcg-ingester")
	}
	wantWorkspaceRoot := mustEvalSymlinks(t, repoRoot)
	wantArgs := []string{"pcg-ingester", "--watch", wantWorkspaceRoot}
	if !reflect.DeepEqual(calls.args, wantArgs) {
		t.Fatalf("exec args = %#v, want %#v", calls.args, wantArgs)
	}
	if got := calls.setenv["PCG_WATCH_PATH"]; got != wantWorkspaceRoot {
		t.Fatalf("PCG_WATCH_PATH = %q, want %q", got, wantWorkspaceRoot)
	}
}

func TestRunWatchUsesExplicitWorkspaceRootFlag(t *testing.T) {
	base := t.TempDir()
	workspaceRoot := filepath.Join(base, "monofolder")
	startPath := filepath.Join(workspaceRoot, "repo", "pkg")
	if err := os.MkdirAll(startPath, 0o755); err != nil {
		t.Fatalf("MkdirAll() error = %v, want nil", err)
	}

	restore, calls := stubWatchRuntime()
	defer restore()

	wantExecErr := errors.New("exec sentinel")
	calls.lookPath = func(string) (string, error) { return "/tmp/pcg-ingester", nil }
	calls.exec = func(binary string, args []string, env []string) error {
		calls.binary = binary
		calls.args = append([]string(nil), args...)
		return wantExecErr
	}

	cmd := &cobra.Command{}
	cmd.Flags().String("workspace-root", "", "")
	if err := cmd.Flags().Set("workspace-root", workspaceRoot); err != nil {
		t.Fatalf("Set(workspace-root) error = %v, want nil", err)
	}

	err := runWatch(cmd, []string{startPath})
	if !errors.Is(err, wantExecErr) {
		t.Fatalf("runWatch() error = %v, want %v", err, wantExecErr)
	}

	wantWorkspaceRoot := mustEvalSymlinks(t, workspaceRoot)
	wantArgs := []string{"pcg-ingester", "--watch", wantWorkspaceRoot}
	if !reflect.DeepEqual(calls.args, wantArgs) {
		t.Fatalf("exec args = %#v, want %#v", calls.args, wantArgs)
	}
}

func TestRunWorkspaceWatchUsesWorkspaceArgumentAsExplicitRoot(t *testing.T) {
	workspaceRoot := t.TempDir()

	restore, calls := stubWatchRuntime()
	defer restore()

	wantExecErr := errors.New("exec sentinel")
	calls.lookPath = func(string) (string, error) { return "/tmp/pcg-ingester", nil }
	calls.exec = func(binary string, args []string, env []string) error {
		calls.binary = binary
		calls.args = append([]string(nil), args...)
		return wantExecErr
	}

	cmd := &cobra.Command{}
	cmd.Flags().String("workspace-root", "", "")
	err := runWorkspaceWatch(cmd, []string{workspaceRoot})
	if !errors.Is(err, wantExecErr) {
		t.Fatalf("runWorkspaceWatch() error = %v, want %v", err, wantExecErr)
	}

	wantWorkspaceRoot := mustEvalSymlinks(t, workspaceRoot)
	wantArgs := []string{"pcg-ingester", "--watch", wantWorkspaceRoot}
	if !reflect.DeepEqual(calls.args, wantArgs) {
		t.Fatalf("exec args = %#v, want %#v", calls.args, wantArgs)
	}
	if got := calls.setenv["PCG_WATCH_PATH"]; got != wantWorkspaceRoot {
		t.Fatalf("PCG_WATCH_PATH = %q, want %q", got, wantWorkspaceRoot)
	}
}

func TestRunWatchReturnsFriendlyErrorWhenIngesterMissing(t *testing.T) {
	restore, calls := stubWatchRuntime()
	defer restore()

	calls.lookPath = func(string) (string, error) {
		return "", errors.New("missing")
	}

	err := runWatch(&cobra.Command{}, nil)
	if err == nil {
		t.Fatal("runWatch() error = nil, want non-nil")
	}
	if err.Error() != "pcg-ingester not found" {
		t.Fatalf("runWatch() error = %q, want %q", err.Error(), "pcg-ingester not found")
	}
}

type watchRuntimeCalls struct {
	lookPath func(string) (string, error)
	exec     func(string, []string, []string) error
	setenv   map[string]string
	binary   string
	args     []string
	env      []string
}

func stubWatchRuntime() (func(), *watchRuntimeCalls) {
	calls := &watchRuntimeCalls{
		setenv: make(map[string]string),
	}

	originalLookPath := watchLookPath
	originalExec := watchExec
	originalSetenv := watchSetenv
	originalEnviron := watchEnviron

	watchLookPath = func(file string) (string, error) {
		if calls.lookPath == nil {
			return "", errors.New("watchLookPath not stubbed")
		}
		return calls.lookPath(file)
	}
	watchExec = func(binary string, args []string, env []string) error {
		if calls.exec == nil {
			return errors.New("watchExec not stubbed")
		}
		return calls.exec(binary, args, env)
	}
	watchSetenv = func(key, value string) error {
		calls.setenv[key] = value
		return nil
	}
	watchEnviron = func() []string {
		return []string{"PATH=/tmp"}
	}

	return func() {
		watchLookPath = originalLookPath
		watchExec = originalExec
		watchSetenv = originalSetenv
		watchEnviron = originalEnviron
	}, calls
}

func mustEvalSymlinks(t *testing.T, path string) string {
	t.Helper()

	resolved, err := filepath.EvalSymlinks(path)
	if err != nil {
		t.Fatalf("EvalSymlinks(%q) error = %v, want nil", path, err)
	}
	return resolved
}
