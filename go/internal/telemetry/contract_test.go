package telemetry

import (
	"slices"
	"testing"
)

func TestMetricDimensionKeys(t *testing.T) {
	t.Parallel()

	want := []string{
		"scope_id",
		"scope_kind",
		"source_system",
		"generation_id",
		"collector_kind",
		"domain",
		"partition_key",
	}

	got := MetricDimensionKeys()
	if !slices.Equal(got, want) {
		t.Fatalf("MetricDimensionKeys() = %v, want %v", got, want)
	}

	got[0] = "mutated"
	if slices.Equal(MetricDimensionKeys(), got) {
		t.Fatalf("MetricDimensionKeys() returned shared storage")
	}
}

func TestSpanNames(t *testing.T) {
	t.Parallel()

	want := []string{
		"collector.observe",
		"scope.assign",
		"fact.emit",
		"projector.run",
		"reducer_intent.enqueue",
		"reducer.run",
		"canonical.write",
	}

	got := SpanNames()
	if !slices.Equal(got, want) {
		t.Fatalf("SpanNames() = %v, want %v", got, want)
	}
}

func TestLogKeys(t *testing.T) {
	t.Parallel()

	want := []string{
		"scope_id",
		"scope_kind",
		"source_system",
		"generation_id",
		"collector_kind",
		"domain",
		"partition_key",
		"request_id",
		"failure_class",
		"refresh_skipped",
	}

	got := LogKeys()
	if !slices.Equal(got, want) {
		t.Fatalf("LogKeys() = %v, want %v", got, want)
	}
}
