package collector

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"time"

	"go.opentelemetry.io/otel/metric"
	"go.opentelemetry.io/otel/trace"

	"github.com/platformcontext/platform-context-graph/go/internal/facts"
	"github.com/platformcontext/platform-context-graph/go/internal/scope"
	"github.com/platformcontext/platform-context-graph/go/internal/telemetry"
)

// Source yields one collected scope generation at a time for durable commit.
type Source interface {
	Next(context.Context) (CollectedGeneration, bool, error)
}

// CollectedGeneration is one repo-scoped source generation gathered by the
// collector boundary.
type CollectedGeneration struct {
	Scope      scope.IngestionScope
	Generation scope.ScopeGeneration
	Facts      []facts.Envelope
}

// Committer owns the collector durable write boundary.
type Committer interface {
	CommitScopeGeneration(
		context.Context,
		scope.IngestionScope,
		scope.ScopeGeneration,
		[]facts.Envelope,
	) error
}

// Service coordinates collector-owned collection with the durable commit seam.
type Service struct {
	Source       Source
	Committer    Committer
	PollInterval time.Duration
	Tracer       trace.Tracer           // optional — nil means no tracing
	Instruments  *telemetry.Instruments // optional — nil means no metrics
	Logger       *slog.Logger           // optional — nil means no structured logging
}

// Run polls the source and commits each collected generation atomically.
func (s Service) Run(ctx context.Context) error {
	if s.Source == nil {
		return errors.New("collector source is required")
	}
	if s.Committer == nil {
		return errors.New("collector committer is required")
	}
	if s.PollInterval <= 0 {
		return errors.New("collector poll interval must be positive")
	}

	for {
		collected, ok, err := s.Source.Next(ctx)
		if err != nil {
			if ctx.Err() != nil && errors.Is(err, ctx.Err()) {
				return nil
			}
			return fmt.Errorf("collect scope generation: %w", err)
		}
		if !ok {
			if err := waitForNextPoll(ctx, s.PollInterval); err != nil {
				return nil
			}
			continue
		}

		if err := s.commitWithTelemetry(ctx, collected); err != nil {
			return err
		}
	}
}

func (s Service) commitWithTelemetry(ctx context.Context, collected CollectedGeneration) error {
	start := time.Now()

	// Start span if tracer is available
	if s.Tracer != nil {
		var span trace.Span
		ctx, span = s.Tracer.Start(ctx, telemetry.SpanCollectorObserve)
		defer span.End()
	}

	err := s.Committer.CommitScopeGeneration(
		ctx,
		collected.Scope,
		collected.Generation,
		collected.Facts,
	)

	duration := time.Since(start).Seconds()

	if s.Instruments != nil {
		attrs := metric.WithAttributes(
			telemetry.AttrScopeID(collected.Scope.ScopeID),
			telemetry.AttrSourceSystem(collected.Scope.SourceSystem),
			telemetry.AttrCollectorKind("git"),
		)
		s.Instruments.CollectorObserveDuration.Record(ctx, duration, attrs)
		s.Instruments.FactsEmitted.Add(ctx, int64(len(collected.Facts)), attrs)
		if err == nil {
			s.Instruments.FactsCommitted.Add(ctx, int64(len(collected.Facts)), attrs)
		}
	}

	if s.Logger != nil {
		scopeAttrs := telemetry.ScopeAttrs(
			collected.Scope.ScopeID,
			collected.Generation.GenerationID,
			collected.Scope.SourceSystem,
		)
		logAttrs := make([]any, 0, len(scopeAttrs)+2)
		for _, a := range scopeAttrs {
			logAttrs = append(logAttrs, a)
		}
		logAttrs = append(logAttrs, slog.Int("fact_count", len(collected.Facts)))
		logAttrs = append(logAttrs, slog.Float64("duration_seconds", duration))

		logAttrs = append(logAttrs, telemetry.PhaseAttr(telemetry.PhaseEmission))
		if err != nil {
			logAttrs = append(logAttrs, slog.String("error", err.Error()))
			logAttrs = append(logAttrs, telemetry.FailureClassAttr("commit_failure"))
			s.Logger.ErrorContext(ctx, "collector commit failed", logAttrs...)
		} else {
			s.Logger.InfoContext(ctx, "collector commit succeeded", logAttrs...)
		}
	}

	if err != nil {
		return fmt.Errorf("commit scope generation: %w", err)
	}
	return nil
}

func waitForNextPoll(ctx context.Context, pollInterval time.Duration) error {
	timer := time.NewTimer(pollInterval)
	defer timer.Stop()

	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-timer.C:
		return nil
	}
}
