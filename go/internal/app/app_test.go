package app

import (
	"testing"

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

	if got.Lifecycle.ServiceName != "collector-git" {
		t.Fatalf("Lifecycle.ServiceName = %q, want %q", got.Lifecycle.ServiceName, "collector-git")
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
