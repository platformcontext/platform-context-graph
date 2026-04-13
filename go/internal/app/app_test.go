package app

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/runtime"
	statuspkg "github.com/platformcontext/platform-context-graph/go/internal/status"
	"github.com/platformcontext/platform-context-graph/go/internal/telemetry"
)

func TestNewWiresBootstrapForService(t *testing.T) {
	t.Parallel()

	got, err := New("collector-git")
	if err != nil {
		t.Fatalf("New() error = %v, want nil", err)
	}

	if got.Config.ServiceName != "collector-git" {
		t.Fatalf("Config.ServiceName = %q, want %q", got.Config.ServiceName, "collector-git")
	}

	if got.Config.Command != "collector-git" {
		t.Fatalf("Config.Command = %q, want %q", got.Config.Command, "collector-git")
	}

	if got.Config.ListenAddr != "0.0.0.0:8080" {
		t.Fatalf("Config.ListenAddr = %q, want %q", got.Config.ListenAddr, "0.0.0.0:8080")
	}

	if got.Config.MetricsAddr != "0.0.0.0:9464" {
		t.Fatalf("Config.MetricsAddr = %q, want %q", got.Config.MetricsAddr, "0.0.0.0:9464")
	}

	lifecycle, ok := got.Lifecycle.(runtime.Lifecycle)
	if !ok {
		t.Fatalf("Lifecycle type = %T, want runtime.Lifecycle", got.Lifecycle)
	}

	if lifecycle.ServiceName != "collector-git" {
		t.Fatalf("Lifecycle.ServiceName = %q, want %q", lifecycle.ServiceName, "collector-git")
	}

	if _, ok := got.Runner.(runtime.ContextRunner); !ok {
		t.Fatalf("Runner type = %T, want runtime.ContextRunner", got.Runner)
	}
}

func TestNewWiresObservabilityContract(t *testing.T) {
	t.Parallel()

	got, err := New("projector")
	if err != nil {
		t.Fatalf("New() error = %v, want nil", err)
	}

	if got.Observability.MetricDimensions[0] != telemetry.MetricDimensionScopeID {
		t.Fatalf("Observability.MetricDimensions[0] = %q, want %q", got.Observability.MetricDimensions[0], telemetry.MetricDimensionScopeID)
	}

	if got.Observability.SpanNames[3] != telemetry.SpanProjectorRun {
		t.Fatalf("Observability.SpanNames[3] = %q, want %q", got.Observability.SpanNames[3], telemetry.SpanProjectorRun)
	}

	if got.Observability.LogKeys[len(got.Observability.LogKeys)-1] != telemetry.LogKeyFailureClass {
		t.Fatalf("Observability.LogKeys[last] = %q, want %q", got.Observability.LogKeys[len(got.Observability.LogKeys)-1], telemetry.LogKeyFailureClass)
	}

	got.Observability.MetricDimensions[0] = "mutated"
	if telemetry.MetricDimensionKeys()[0] != telemetry.MetricDimensionScopeID {
		t.Fatalf("telemetry contract was mutated through bootstrap seam")
	}
}

func TestRunStartsLifecycleRunsServiceAndStopsLifecycle(t *testing.T) {
	t.Parallel()

	lifecycle := &stubLifecycle{}
	runner := &stubRunner{}

	app := Application{
		Lifecycle: lifecycle,
		Runner:    runner,
	}

	if err := app.Run(context.Background()); err != nil {
		t.Fatalf("Run() error = %v, want nil", err)
	}

	if got, want := lifecycle.startCalls, 1; got != want {
		t.Fatalf("lifecycle start calls = %d, want %d", got, want)
	}
	if got, want := runner.runCalls, 1; got != want {
		t.Fatalf("runner run calls = %d, want %d", got, want)
	}
	if got, want := lifecycle.stopCalls, 1; got != want {
		t.Fatalf("lifecycle stop calls = %d, want %d", got, want)
	}
}

func TestRunReturnsRunnerErrorAfterStoppingLifecycle(t *testing.T) {
	t.Parallel()

	wantErr := errors.New("runner failed")
	lifecycle := &stubLifecycle{}
	runner := &stubRunner{runErr: wantErr}

	app := Application{
		Lifecycle: lifecycle,
		Runner:    runner,
	}

	if err := app.Run(context.Background()); !errors.Is(err, wantErr) {
		t.Fatalf("Run() error = %v, want %v", err, wantErr)
	}

	if got, want := lifecycle.stopCalls, 1; got != want {
		t.Fatalf("lifecycle stop calls = %d, want %d", got, want)
	}
}

func TestComposeLifecyclesStartsAndStopsBoth(t *testing.T) {
	t.Parallel()

	first := &stubLifecycle{}
	second := &stubLifecycle{}
	lifecycle := ComposeLifecycles(first, second)
	runner := &stubRunner{}

	app := Application{
		Lifecycle: lifecycle,
		Runner:    runner,
	}

	if err := app.Run(context.Background()); err != nil {
		t.Fatalf("Run() error = %v, want nil", err)
	}

	if got, want := first.startCalls, 1; got != want {
		t.Fatalf("first start calls = %d, want %d", got, want)
	}
	if got, want := second.startCalls, 1; got != want {
		t.Fatalf("second start calls = %d, want %d", got, want)
	}
	if got, want := second.stopCalls, 1; got != want {
		t.Fatalf("second stop calls = %d, want %d", got, want)
	}
	if got, want := first.stopCalls, 1; got != want {
		t.Fatalf("first stop calls = %d, want %d", got, want)
	}
}

func TestNewHostedWithStatusServerRejectsNilReader(t *testing.T) {
	t.Parallel()

	_, err := NewHostedWithStatusServer("collector-git", runtime.ContextRunner{}, nil)
	if err == nil {
		t.Fatal("NewHostedWithStatusServer() error = nil, want non-nil")
	}
}

func TestMountStatusServerComposesRuntimeLifecycle(t *testing.T) {
	t.Setenv("PCG_LISTEN_ADDR", "127.0.0.1:0")

	base, err := NewHosted("collector-git", runtime.ContextRunner{})
	if err != nil {
		t.Fatalf("NewHosted() error = %v, want nil", err)
	}

	mounted, err := MountStatusServer(base, &fakeStatusReader{
		snapshot: statuspkg.RawSnapshot{
			AsOf: time.Date(2026, 4, 12, 16, 0, 0, 0, time.UTC),
		},
	})
	if err != nil {
		t.Fatalf("MountStatusServer() error = %v, want nil", err)
	}

	if err := mounted.Lifecycle.Start(context.Background()); err != nil {
		t.Fatalf("Lifecycle.Start() error = %v, want nil", err)
	}
	if err := mounted.Lifecycle.Stop(context.Background()); err != nil {
		t.Fatalf("Lifecycle.Stop() error = %v, want nil", err)
	}
}

type stubLifecycle struct {
	startCalls int
	stopCalls  int
}

func (l *stubLifecycle) Start(context.Context) error {
	l.startCalls++
	return nil
}

func (l *stubLifecycle) Stop(context.Context) error {
	l.stopCalls++
	return nil
}

type stubRunner struct {
	runCalls int
	runErr   error
}

func (r *stubRunner) Run(context.Context) error {
	r.runCalls++
	return r.runErr
}

type fakeStatusReader struct {
	snapshot statuspkg.RawSnapshot
	err      error
}

func (r *fakeStatusReader) ReadStatusSnapshot(context.Context, time.Time) (statuspkg.RawSnapshot, error) {
	if r.err != nil {
		return statuspkg.RawSnapshot{}, r.err
	}
	return r.snapshot, nil
}
