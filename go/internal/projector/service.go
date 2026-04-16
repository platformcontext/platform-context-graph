package projector

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"sync"
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

// FactCounter returns the fact count for a scope generation without loading data.
// Used by the large-generation semaphore to classify repos before loading.
type FactCounter interface {
	CountFacts(ctx context.Context, scopeID, generationID string) (int, error)
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
	Workers      int                    // concurrent worker count; 0 or 1 means sequential

	// Large-generation semaphore: limits how many large repos can be
	// projected concurrently while letting small/medium repos proceed
	// without blocking. Mirrors the collector-layer pattern in GitSource.
	FactCounter           FactCounter // optional; enables large-gen semaphore
	LargeGenThreshold     int         // fact count above which semaphore is required; 0 = 10000
	LargeGenMaxConcurrent int         // max concurrent large generations; 0 = 2
	largeSem              chan struct{}
}

// Run polls for projector work until the context is canceled.
func (s Service) Run(ctx context.Context) error {
	if err := s.validate(); err != nil {
		return err
	}

	if s.Logger != nil {
		s.Logger.Info("starting projector", slog.Int("workers", s.Workers))
	}

	if s.Workers <= 1 {
		return s.runSequential(ctx)
	}
	return s.runConcurrent(ctx)
}

// runSequential processes work one at a time.
func (s Service) runSequential(ctx context.Context) error {
	for {
		claimStart := time.Now()
		work, ok, err := s.WorkSource.Claim(ctx)
		if s.Instruments != nil {
			s.Instruments.QueueClaimDuration.Record(ctx, time.Since(claimStart).Seconds(), metric.WithAttributes(
				attribute.String("queue", "projector"),
			))
		}
		if err != nil {
			return fmt.Errorf("claim projector work: %w", err)
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

		if err := s.processWork(ctx, work, 0); err != nil {
			return err
		}
	}
}

// runConcurrent spawns N worker goroutines that compete for projector work.
// Each worker independently claims, processes, and acknowledges work. On first
// fatal error (Claim or Ack failure), the shared context is canceled to drain
// siblings promptly.
func (s Service) runConcurrent(ctx context.Context) error {
	ctx, cancel := context.WithCancel(ctx)
	defer cancel()

	var (
		mu   sync.Mutex
		errs []error
		wg   sync.WaitGroup
	)

	for i := 0; i < s.Workers; i++ {
		workerID := i
		wg.Add(1)
		go func() {
			defer wg.Done()
			for {
				if ctx.Err() != nil {
					return
				}

				claimStart := time.Now()
				work, ok, err := s.WorkSource.Claim(ctx)
				if s.Instruments != nil {
					s.Instruments.QueueClaimDuration.Record(ctx, time.Since(claimStart).Seconds(), metric.WithAttributes(
						attribute.String("queue", "projector"),
					))
				}
				if err != nil {
					mu.Lock()
					errs = append(errs, fmt.Errorf("claim projector work (worker %d): %w", workerID, err))
					mu.Unlock()
					cancel()
					return
				}
				if !ok {
					if err := s.wait(ctx, s.pollInterval()); err != nil {
						if errors.Is(err, context.Canceled) || errors.Is(err, context.DeadlineExceeded) || ctx.Err() != nil {
							return
						}
						mu.Lock()
						errs = append(errs, fmt.Errorf("wait for projector work (worker %d): %w", workerID, err))
						mu.Unlock()
						cancel()
						return
					}
					continue
				}

				if err := s.processWork(ctx, work, workerID); err != nil {
					mu.Lock()
					errs = append(errs, err)
					mu.Unlock()
					cancel()
					return
				}
			}
		}()
	}

	wg.Wait()
	return errors.Join(errs...)
}

func (s Service) processWork(ctx context.Context, work ScopeGenerationWork, workerID int) error {
	start := time.Now()

	if s.Tracer != nil {
		var span trace.Span
		ctx, span = s.Tracer.Start(ctx, telemetry.SpanProjectorRun)
		defer span.End()
	}

	// Large-generation semaphore: count facts first, acquire sem if large.
	releaseSem := s.acquireLargeGenSem(ctx, work, workerID)
	if releaseSem != nil {
		defer releaseSem()
	}

	factsForGeneration, err := s.FactStore.LoadFacts(ctx, work)
	if err != nil {
		s.recordProjectionResult(ctx, work, start, "failed", 0, err, workerID)
		if failErr := s.WorkSink.Fail(ctx, work, err); failErr != nil {
			return errors.Join(err, fmt.Errorf("fail projector work: %w", failErr))
		}
		return nil
	}

	result, err := s.Runner.Project(ctx, work.Scope, work.Generation, factsForGeneration)
	if err != nil {
		s.recordProjectionResult(ctx, work, start, "failed", len(factsForGeneration), err, workerID)
		if failErr := s.WorkSink.Fail(ctx, work, err); failErr != nil {
			return errors.Join(err, fmt.Errorf("fail projector work: %w", failErr))
		}
		return nil
	}

	if err := s.WorkSink.Ack(ctx, work, result); err != nil {
		s.recordProjectionResult(ctx, work, start, "ack_failed", len(factsForGeneration), err, workerID)
		return fmt.Errorf("ack projector work: %w", err)
	}

	s.recordProjectionResult(ctx, work, start, "succeeded", len(factsForGeneration), nil, workerID)
	return nil
}

func (s Service) recordProjectionResult(ctx context.Context, work ScopeGenerationWork, start time.Time, status string, factCount int, err error, workerID int) {
	duration := time.Since(start).Seconds()

	if s.Instruments != nil {
		s.Instruments.ProjectorRunDuration.Record(ctx, duration, metric.WithAttributes(
			telemetry.AttrScopeID(work.Scope.ScopeID),
		))
		s.Instruments.ProjectionsCompleted.Add(ctx, 1, metric.WithAttributes(
			telemetry.AttrScopeID(work.Scope.ScopeID),
			attribute.String("queue", "projector"),
			attribute.String("status", status),
		))
	}

	if s.Logger != nil {
		scopeAttrs := telemetry.ScopeAttrs(work.Scope.ScopeID, work.Generation.GenerationID, work.Scope.SourceSystem)
		logAttrs := make([]any, 0, len(scopeAttrs)+5)
		for _, a := range scopeAttrs {
			logAttrs = append(logAttrs, a)
		}
		logAttrs = append(logAttrs, slog.String("queue", "projector"))
		logAttrs = append(logAttrs, slog.String("status", status))
		logAttrs = append(logAttrs, slog.Int("fact_count", factCount))
		logAttrs = append(logAttrs, slog.Float64("duration_seconds", duration))
		logAttrs = append(logAttrs, slog.Int("worker_id", workerID))
		logAttrs = append(logAttrs, telemetry.PhaseAttr(telemetry.PhaseProjection))
		if err != nil {
			logAttrs = append(logAttrs, slog.String("error", err.Error()))
			failureClass := "projection_failure"
			message := "projection failed"
			if status == "ack_failed" {
				failureClass = "ack_failure"
				message = "projection ack failed"
			}
			logAttrs = append(logAttrs, telemetry.FailureClassAttr(failureClass))
			s.Logger.ErrorContext(ctx, message, logAttrs...)
		} else {
			s.Logger.InfoContext(ctx, "projection succeeded", logAttrs...)
		}
	}
}

// InitLargeGenSemaphore sets up the large-generation semaphore. Call after
// setting FactCounter, LargeGenThreshold, and LargeGenMaxConcurrent.
func (s *Service) InitLargeGenSemaphore() {
	if s.FactCounter == nil {
		return
	}
	maxConcurrent := s.LargeGenMaxConcurrent
	if maxConcurrent <= 0 {
		maxConcurrent = 2
	}
	s.largeSem = make(chan struct{}, maxConcurrent)
}

func (s Service) largeGenThreshold() int {
	if s.LargeGenThreshold <= 0 {
		return 10000
	}
	return s.LargeGenThreshold
}

func (s Service) acquireLargeGenSem(ctx context.Context, work ScopeGenerationWork, workerID int) func() {
	if s.FactCounter == nil || s.largeSem == nil {
		return nil
	}

	count, err := s.FactCounter.CountFacts(ctx, work.Scope.ScopeID, work.Generation.GenerationID)
	if err != nil {
		// On error, skip semaphore (don't block).
		if s.Logger != nil {
			s.Logger.WarnContext(ctx, "fact count failed, skipping large-gen semaphore",
				slog.String("error", err.Error()),
				slog.Int("worker_id", workerID),
			)
		}
		return nil
	}

	if count <= s.largeGenThreshold() {
		return nil // small/medium repo, no semaphore needed
	}

	if s.Logger != nil {
		scopeAttrs := telemetry.ScopeAttrs(work.Scope.ScopeID, work.Generation.GenerationID, work.Scope.SourceSystem)
		logAttrs := make([]any, 0, len(scopeAttrs)+3)
		for _, a := range scopeAttrs {
			logAttrs = append(logAttrs, a)
		}
		logAttrs = append(logAttrs,
			slog.Int("fact_count", count),
			slog.Int("threshold", s.largeGenThreshold()),
			slog.Int("worker_id", workerID),
		)
		s.Logger.InfoContext(ctx, "large generation detected, acquiring semaphore", logAttrs...)
	}

	// Record semaphore wait time.
	waitStart := time.Now()
	select {
	case s.largeSem <- struct{}{}:
		if s.Instruments != nil {
			s.Instruments.LargeRepoSemaphoreWait.Record(ctx, time.Since(waitStart).Seconds())
		}
		if s.Logger != nil {
			s.Logger.InfoContext(ctx, "large generation semaphore acquired",
				slog.Int("fact_count", count),
				slog.Int("worker_id", workerID),
			)
		}
		return func() { <-s.largeSem }
	case <-ctx.Done():
		return nil
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
