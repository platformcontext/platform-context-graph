package neo4j

import (
	"context"
	"testing"

	"github.com/platformcontext/platform-context-graph/go/internal/reducer"
	"github.com/platformcontext/platform-context-graph/go/internal/telemetry"
	"go.opentelemetry.io/otel/attribute"
	sdkmetric "go.opentelemetry.io/otel/sdk/metric"
	"go.opentelemetry.io/otel/sdk/metric/metricdata"
)

func TestEdgeWriterWriteEdgesCodeCallIsolationRecordsBatchTelemetry(t *testing.T) {
	t.Parallel()

	metricReader := sdkmetric.NewManualReader()
	meterProvider := sdkmetric.NewMeterProvider(sdkmetric.WithReader(metricReader))
	instruments, err := telemetry.NewInstruments(meterProvider.Meter("test"))
	if err != nil {
		t.Fatalf("NewInstruments() error = %v", err)
	}

	executor := &recordingGroupExecutor{}
	writer := NewEdgeWriter(executor, 500)
	writer.Instruments = instruments
	writer.CodeCallBatchSize = 2
	writer.CodeCallGroupBatchSize = 1

	rows := []reducer.SharedProjectionIntentRow{
		{IntentID: "i1", RepositoryID: "repo-a", Payload: map[string]any{"caller_entity_id": "entity:function:a", "callee_entity_id": "entity:function:b"}},
		{IntentID: "i2", RepositoryID: "repo-a", Payload: map[string]any{"caller_entity_id": "entity:function:c", "callee_entity_id": "entity:function:d"}},
		{IntentID: "i3", RepositoryID: "repo-a", Payload: map[string]any{"caller_entity_id": "entity:function:e", "callee_entity_id": "entity:function:f"}},
	}

	if err := writer.WriteEdges(context.Background(), reducer.DomainCodeCalls, rows, "parser/code-calls"); err != nil {
		t.Fatalf("WriteEdges() error = %v", err)
	}

	var rm metricdata.ResourceMetrics
	if err := metricReader.Collect(context.Background(), &rm); err != nil {
		t.Fatalf("Collect() error = %v", err)
	}

	if got, want := int64(len(executor.groupCalls)), int64(2); got != want {
		t.Fatalf("isolated group calls = %d, want %d", got, want)
	}
	wantAttrs := map[string]string{"domain": reducer.DomainCodeCalls}
	assertInt64CounterValue(t, rm, "pcg_dp_code_call_edge_batches_total", wantAttrs, 2)
	assertHistogramCount(t, rm, "pcg_dp_code_call_edge_batch_duration_seconds", wantAttrs, 2)
}

func TestEdgeWriterWriteEdgesNonCodeCallDoesNotRecordCodeCallBatchTelemetry(t *testing.T) {
	t.Parallel()

	metricReader := sdkmetric.NewManualReader()
	meterProvider := sdkmetric.NewMeterProvider(sdkmetric.WithReader(metricReader))
	instruments, err := telemetry.NewInstruments(meterProvider.Meter("test"))
	if err != nil {
		t.Fatalf("NewInstruments() error = %v", err)
	}

	executor := &recordingGroupExecutor{}
	writer := NewEdgeWriter(executor, 2)
	writer.Instruments = instruments
	writer.CodeCallBatchSize = 2
	writer.CodeCallGroupBatchSize = 1

	rows := []reducer.SharedProjectionIntentRow{
		{IntentID: "i1", RepositoryID: "repo-a", Payload: map[string]any{"repo_id": "repo-a", "target_repo_id": "repo-b"}},
		{IntentID: "i2", RepositoryID: "repo-a", Payload: map[string]any{"repo_id": "repo-a", "target_repo_id": "repo-c"}},
		{IntentID: "i3", RepositoryID: "repo-a", Payload: map[string]any{"repo_id": "repo-a", "target_repo_id": "repo-d"}},
	}

	if err := writer.WriteEdges(context.Background(), reducer.DomainRepoDependency, rows, "finalization/workloads"); err != nil {
		t.Fatalf("WriteEdges() error = %v", err)
	}

	var rm metricdata.ResourceMetrics
	if err := metricReader.Collect(context.Background(), &rm); err != nil {
		t.Fatalf("Collect() error = %v", err)
	}

	assertMetricMissing(t, rm, "pcg_dp_code_call_edge_batches_total")
	assertMetricMissing(t, rm, "pcg_dp_code_call_edge_batch_duration_seconds")
}

func assertInt64CounterValue(
	t *testing.T,
	rm metricdata.ResourceMetrics,
	metricName string,
	wantAttrs map[string]string,
	wantValue int64,
) {
	t.Helper()

	for _, scopeMetric := range rm.ScopeMetrics {
		for _, metricRecord := range scopeMetric.Metrics {
			if metricRecord.Name != metricName {
				continue
			}
			sum, ok := metricRecord.Data.(metricdata.Sum[int64])
			if !ok {
				t.Fatalf("metric %s data = %T, want metricdata.Sum[int64]", metricName, metricRecord.Data)
			}
			for _, point := range sum.DataPoints {
				if attributesMatch(point.Attributes, wantAttrs) {
					if got := point.Value; got != wantValue {
						t.Fatalf("metric %s value = %d, want %d", metricName, got, wantValue)
					}
					return
				}
			}
		}
	}

	t.Fatalf("metric %s with attrs %v not found", metricName, wantAttrs)
}

func assertHistogramCount(
	t *testing.T,
	rm metricdata.ResourceMetrics,
	metricName string,
	wantAttrs map[string]string,
	wantCount uint64,
) {
	t.Helper()

	for _, scopeMetric := range rm.ScopeMetrics {
		for _, metricRecord := range scopeMetric.Metrics {
			if metricRecord.Name != metricName {
				continue
			}
			histogram, ok := metricRecord.Data.(metricdata.Histogram[float64])
			if !ok {
				t.Fatalf("metric %s data = %T, want metricdata.Histogram[float64]", metricName, metricRecord.Data)
			}
			for _, point := range histogram.DataPoints {
				if attributesMatch(point.Attributes, wantAttrs) {
					if got := point.Count; got != wantCount {
						t.Fatalf("metric %s count = %d, want %d", metricName, got, wantCount)
					}
					return
				}
			}
		}
	}

	t.Fatalf("metric %s with attrs %v not found", metricName, wantAttrs)
}

func assertMetricMissing(t *testing.T, rm metricdata.ResourceMetrics, metricName string) {
	t.Helper()

	for _, scopeMetric := range rm.ScopeMetrics {
		for _, metricRecord := range scopeMetric.Metrics {
			if metricRecord.Name == metricName {
				t.Fatalf("metric %s unexpectedly recorded", metricName)
			}
		}
	}
}

func attributesMatch(attrs attribute.Set, want map[string]string) bool {
	if len(want) == 0 {
		return len(attrs.ToSlice()) == 0
	}

	gotAttrs := attrs.ToSlice()
	if len(gotAttrs) != len(want) {
		return false
	}
	for _, attr := range gotAttrs {
		wantValue, ok := want[string(attr.Key)]
		if !ok || attr.Value.AsString() != wantValue {
			return false
		}
	}
	return true
}
