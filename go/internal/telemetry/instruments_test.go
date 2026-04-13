package telemetry

import (
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"go.opentelemetry.io/otel/metric/noop"
)

func TestNewInstrumentsNoError(t *testing.T) {
	meter := noop.NewMeterProvider().Meter("test")
	inst, err := NewInstruments(meter)

	require.NoError(t, err, "NewInstruments should succeed with noop meter")
	require.NotNil(t, inst, "Instruments should not be nil")

	// Verify all counter fields are non-nil
	assert.NotNil(t, inst.FactsEmitted, "FactsEmitted counter should be registered")
	assert.NotNil(t, inst.FactsCommitted, "FactsCommitted counter should be registered")
	assert.NotNil(t, inst.ProjectionsCompleted, "ProjectionsCompleted counter should be registered")
	assert.NotNil(t, inst.ReducerIntentsEnqueued, "ReducerIntentsEnqueued counter should be registered")
	assert.NotNil(t, inst.ReducerExecutions, "ReducerExecutions counter should be registered")
	assert.NotNil(t, inst.CanonicalWrites, "CanonicalWrites counter should be registered")
	assert.NotNil(t, inst.SharedProjectionCycles, "SharedProjectionCycles counter should be registered")

	// Verify all histogram fields are non-nil
	assert.NotNil(t, inst.CollectorObserveDuration, "CollectorObserveDuration histogram should be registered")
	assert.NotNil(t, inst.ScopeAssignDuration, "ScopeAssignDuration histogram should be registered")
	assert.NotNil(t, inst.FactEmitDuration, "FactEmitDuration histogram should be registered")
	assert.NotNil(t, inst.ProjectorRunDuration, "ProjectorRunDuration histogram should be registered")
	assert.NotNil(t, inst.ProjectorStageDuration, "ProjectorStageDuration histogram should be registered")
	assert.NotNil(t, inst.ReducerRunDuration, "ReducerRunDuration histogram should be registered")
	assert.NotNil(t, inst.CanonicalWriteDuration, "CanonicalWriteDuration histogram should be registered")
	assert.NotNil(t, inst.QueueClaimDuration, "QueueClaimDuration histogram should be registered")
	assert.NotNil(t, inst.PostgresQueryDuration, "PostgresQueryDuration histogram should be registered")
	assert.NotNil(t, inst.Neo4jQueryDuration, "Neo4jQueryDuration histogram should be registered")
}

func TestNewInstrumentsNilMeterError(t *testing.T) {
	inst, err := NewInstruments(nil)

	require.Error(t, err, "NewInstruments should fail with nil meter")
	assert.Nil(t, inst, "Instruments should be nil on error")
	assert.Contains(t, err.Error(), "meter is required", "Error should mention meter requirement")
}

func TestAttrHelpers(t *testing.T) {
	tests := []struct {
		name     string
		attrFunc func(string) string
		wantKey  string
	}{
		{
			name:     "AttrScopeID",
			attrFunc: func(v string) string { return string(AttrScopeID(v).Key) },
			wantKey:  MetricDimensionScopeID,
		},
		{
			name:     "AttrScopeKind",
			attrFunc: func(v string) string { return string(AttrScopeKind(v).Key) },
			wantKey:  MetricDimensionScopeKind,
		},
		{
			name:     "AttrSourceSystem",
			attrFunc: func(v string) string { return string(AttrSourceSystem(v).Key) },
			wantKey:  MetricDimensionSourceSystem,
		},
		{
			name:     "AttrGenerationID",
			attrFunc: func(v string) string { return string(AttrGenerationID(v).Key) },
			wantKey:  MetricDimensionGenerationID,
		},
		{
			name:     "AttrCollectorKind",
			attrFunc: func(v string) string { return string(AttrCollectorKind(v).Key) },
			wantKey:  MetricDimensionCollectorKind,
		},
		{
			name:     "AttrDomain",
			attrFunc: func(v string) string { return string(AttrDomain(v).Key) },
			wantKey:  MetricDimensionDomain,
		},
		{
			name:     "AttrPartitionKey",
			attrFunc: func(v string) string { return string(AttrPartitionKey(v).Key) },
			wantKey:  MetricDimensionPartitionKey,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			gotKey := tt.attrFunc("test-value")
			assert.Equal(t, tt.wantKey, gotKey,
				"Attribute key should match contract constant")
		})
	}
}
