package projector

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"time"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/metric"
	"go.opentelemetry.io/otel/trace"

	"github.com/platformcontext/platform-context-graph/go/internal/facts"
	"github.com/platformcontext/platform-context-graph/go/internal/scope"
	"github.com/platformcontext/platform-context-graph/go/internal/telemetry"
)

const defaultPollInterval = time.Second

// ScopeGenerationWork captures one claimed scope generation for projection.
type ScopeGenerationWork struct {
	Scope      scope.IngestionScope
	Generation scope.ScopeGeneration
	// AttemptCount is the durable number of claims already consumed for this
	// scope generation work item.
	AttemptCount int
}

// ProjectorWorkSource claims one scope generation at a time.
type ProjectorWorkSource interface {
	Claim(context.Context) (ScopeGenerationWork, bool, error)
}

// FactStore loads source-local facts for a claimed scope generation.
type FactStore interface {
	LoadFacts(context.Context, ScopeGenerationWork) ([]facts.Envelope, error)
}

// ProjectionRunner projects one scope generation worth of facts.
type ProjectionRunner interface {
	Project(context.Context, scope.IngestionScope, scope.ScopeGeneration, []facts.Envelope) (Result, error)
}

// ProjectorWorkSink acknowledges or fails claimed projector work.
type ProjectorWorkSink interface {
	Ack(context.Context, ScopeGenerationWork, Result) error
	Fail(context.Context, ScopeGenerationWork, error) error
}

// Service coordinates the projector work loop without owning projection logic.
type Service struct {
	PollInterval time.Duration
	WorkSource   ProjectorWorkSource
	FactStore    FactStore
	Runner       ProjectionRunner
	WorkSink     ProjectorWorkSink
	Wait         func(context.Context, time.Duration) error
	Tracer       trace.Tracer           // optional
	Instruments  *telemetry.Instruments // optional
	Logger       *slog.Logger           // optional
}

// Run polls for projector work until the context is canceled.
func (s Service) Run(ctx context.Context) error {
	if err := s.validate(); err != nil {
		return err
	}

	for {
		claimStart := time.Now()
		work, ok, err := s.WorkSource.Claim(ctx)
		if err != nil {
			return fmt.Errorf("claim projector work: %w", err)
		}

		if s.Instruments != nil {
			s.Instruments.QueueClaimDuration.Record(ctx, time.Since(claimStart).Seconds(), metric.WithAttributes(
				attribute.String("queue", "projector"),
			))
		}

		if !ok {
			if err := s.wait(ctx, s.pollInterval()); err != nil {
				if errors.Is(err, context.Canceled) || errors.Is(err, context.DeadlineExceeded) || ctx.Err() != nil {
					return nil
				}
				return fmt.Errorf("wait for projector work: %w", err)
			}
			continue
		}

		if err := s.processWork(ctx, work); err != nil {
			return err
		}
	}
}

func (s Service) processWork(ctx context.Context, work ScopeGenerationWork) error {
	start := time.Now()

	if s.Tracer != nil {
		var span trace.Span
		ctx, span = s.Tracer.Start(ctx, telemetry.SpanProjectorRun)
		defer span.End()
	}

	factsForGeneration, err := s.FactStore.LoadFacts(ctx, work)
	if err != nil {
		s.recordProjectionResult(ctx, work, start, "failed", 0, err)
		if failErr := s.WorkSink.Fail(ctx, work, err); failErr != nil {
			return errors.Join(err, fmt.Errorf("fail projector work: %w", failErr))
		}
		return nil
	}

	result, err := s.Runner.Project(ctx, work.Scope, work.Generation, factsForGeneration)
	if err != nil {
		s.recordProjectionResult(ctx, work, start, "failed", len(factsForGeneration), err)
		if failErr := s.WorkSink.Fail(ctx, work, err); failErr != nil {
			return errors.Join(err, fmt.Errorf("fail projector work: %w", failErr))
		}
		return nil
	}

	if err := s.WorkSink.Ack(ctx, work, result); err != nil {
		return fmt.Errorf("ack projector work: %w", err)
	}

	s.recordProjectionResult(ctx, work, start, "succeeded", len(factsForGeneration), nil)
	return nil
}

func (s Service) recordProjectionResult(ctx context.Context, work ScopeGenerationWork, start time.Time, status string, factCount int, err error) {
	duration := time.Since(start).Seconds()

	if s.Instruments != nil {
		s.Instruments.ProjectorRunDuration.Record(ctx, duration, metric.WithAttributes(
			telemetry.AttrScopeID(work.Scope.ScopeID),
		))
		s.Instruments.ProjectionsCompleted.Add(ctx, 1, metric.WithAttributes(
			telemetry.AttrScopeID(work.Scope.ScopeID),
			attribute.String("status", status),
		))
	}

	if s.Logger != nil {
		scopeAttrs := telemetry.ScopeAttrs(work.Scope.ScopeID, work.Generation.GenerationID, work.Scope.SourceSystem)
		logAttrs := make([]any, 0, len(scopeAttrs)+3)
		for _, a := range scopeAttrs {
			logAttrs = append(logAttrs, a)
		}
		logAttrs = append(logAttrs, slog.String("status", status))
		logAttrs = append(logAttrs, slog.Int("fact_count", factCount))
		logAttrs = append(logAttrs, slog.Float64("duration_seconds", duration))
		logAttrs = append(logAttrs, telemetry.PhaseAttr(telemetry.PhaseProjection))
		if err != nil {
			logAttrs = append(logAttrs, slog.String("error", err.Error()))
			logAttrs = append(logAttrs, telemetry.FailureClassAttr("projection_failure"))
			s.Logger.ErrorContext(ctx, "projection failed", logAttrs...)
		} else {
			s.Logger.InfoContext(ctx, "projection succeeded", logAttrs...)
		}
	}
}

func (s Service) validate() error {
	if s.WorkSource == nil {
		return errors.New("work source is required")
	}
	if s.FactStore == nil {
		return errors.New("fact store is required")
	}
	if s.Runner == nil {
		return errors.New("runner is required")
	}
	if s.WorkSink == nil {
		return errors.New("work sink is required")
	}

	return nil
}

func (s Service) pollInterval() time.Duration {
	if s.PollInterval <= 0 {
		return defaultPollInterval
	}

	return s.PollInterval
}

func (s Service) wait(ctx context.Context, interval time.Duration) error {
	if s.Wait != nil {
		return s.Wait(ctx, interval)
	}

	timer := time.NewTimer(interval)
	defer timer.Stop()

	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-timer.C:
		return nil
	}
}
