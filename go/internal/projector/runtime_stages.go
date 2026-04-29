package projector

import (
	"context"
	"errors"
	"fmt"
	"time"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/metric"
	"go.opentelemetry.io/otel/trace"

	"github.com/platformcontext/platform-context-graph/go/internal/content"
	"github.com/platformcontext/platform-context-graph/go/internal/facts"
	"github.com/platformcontext/platform-context-graph/go/internal/scope"
	"github.com/platformcontext/platform-context-graph/go/internal/telemetry"
)

func (r Runtime) writeContentProjection(ctx context.Context, scopeValue scope.IngestionScope, mat content.Materialization) (content.Result, error) {
	if len(mat.Records) == 0 && len(mat.Entities) == 0 {
		return content.Result{}, nil
	}
	if r.ContentWriter == nil {
		return content.Result{}, errors.New("content writer is required when content rows are present")
	}

	contentStart := time.Now()
	contentResult, err := r.ContentWriter.Write(ctx, mat)
	if err != nil {
		return content.Result{}, fmt.Errorf("write content materialization: %w", err)
	}
	if r.Instruments != nil {
		r.Instruments.ProjectorStageDuration.Record(ctx, time.Since(contentStart).Seconds(), metric.WithAttributes(
			telemetry.AttrScopeID(scopeValue.ScopeID),
			attribute.String("stage", "content_write"),
		))
	}
	r.logRuntimeStage(ctx, scopeValue, mat.GenerationID, "content_write", contentStart,
		"content_record_count", len(mat.Records),
		"content_entity_count", len(mat.Entities),
		"deleted_count", contentResult.DeletedCount,
	)

	return contentResult, nil
}

// enqueueReducerIntents publishes reducer follow-up work as soon as canonical
// graph readiness exists, allowing reducer-only graph work to overlap later
// source-local content-store writes.
func (r Runtime) enqueueReducerIntents(
	ctx context.Context,
	scopeValue scope.IngestionScope,
	generationID string,
	intents []ReducerIntent,
) (IntentResult, error) {
	if r.IntentWriter == nil {
		return IntentResult{}, errors.New("reducer intent writer is required when reducer intents are present")
	}

	enqueueStart := time.Now()
	if r.Tracer != nil {
		var enqueueSpan trace.Span
		ctx, enqueueSpan = r.Tracer.Start(ctx, telemetry.SpanReducerIntentEnqueue)
		defer enqueueSpan.End()
	}

	intentResult, err := r.IntentWriter.Enqueue(ctx, intents)
	if err != nil {
		return IntentResult{}, fmt.Errorf("enqueue reducer intents: %w", err)
	}

	if r.Instruments != nil {
		duration := time.Since(enqueueStart).Seconds()
		r.Instruments.ProjectorStageDuration.Record(ctx, duration, metric.WithAttributes(
			telemetry.AttrScopeID(scopeValue.ScopeID),
			attribute.String("stage", "intent_enqueue"),
		))
		r.Instruments.ReducerIntentsEnqueued.Add(ctx, int64(len(intents)), metric.WithAttributes(
			telemetry.AttrScopeID(scopeValue.ScopeID),
		))
	}
	r.logRuntimeStage(ctx, scopeValue, generationID, "intent_enqueue", enqueueStart,
		"reducer_intent_count", len(intents),
		"enqueued_count", intentResult.Count,
	)

	return intentResult, nil
}

func (r Runtime) writeCanonicalProjection(
	ctx context.Context,
	scopeValue scope.IngestionScope,
	generationID string,
	inputFacts []facts.Envelope,
	mat CanonicalMaterialization,
) error {
	if mat.IsEmpty() {
		return nil
	}
	if r.CanonicalWriter == nil {
		return errors.New("canonical writer is required when canonical data is present")
	}

	canonicalStart := time.Now()
	if r.Tracer != nil {
		var canonicalSpan trace.Span
		ctx, canonicalSpan = r.Tracer.Start(ctx, telemetry.SpanCanonicalProjection)
		defer canonicalSpan.End()
	}

	if err := r.CanonicalWriter.Write(ctx, mat); err != nil {
		return fmt.Errorf("write canonical projection: %w", err)
	}
	if err := r.publishCanonicalGraphPhases(ctx, generationID, inputFacts); err != nil {
		return fmt.Errorf("publish canonical graph phases: %w", err)
	}

	if r.Instruments != nil {
		canonicalDur := time.Since(canonicalStart).Seconds()
		r.Instruments.CanonicalProjectionDuration.Record(ctx, canonicalDur, metric.WithAttributes(
			telemetry.AttrScopeID(scopeValue.ScopeID),
		))
		r.Instruments.CanonicalWrites.Add(ctx, 1, metric.WithAttributes(
			telemetry.AttrScopeID(scopeValue.ScopeID),
		))
		r.Instruments.ProjectorStageDuration.Record(ctx, canonicalDur, metric.WithAttributes(
			telemetry.AttrScopeID(scopeValue.ScopeID),
			attribute.String("stage", "canonical_write"),
		))
	}
	r.logRuntimeStage(ctx, scopeValue, generationID, "canonical_write", canonicalStart,
		"repository_count", canonicalRepositoryCount(mat),
		"directory_count", len(mat.Directories),
		"file_count", len(mat.Files),
		"entity_count", len(mat.Entities),
		"module_count", len(mat.Modules),
		"import_count", len(mat.Imports),
	)

	return nil
}

func canonicalRepositoryCount(mat CanonicalMaterialization) int {
	if mat.Repository == nil {
		return 0
	}
	return 1
}
