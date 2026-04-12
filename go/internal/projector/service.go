package projector

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/facts"
	"github.com/platformcontext/platform-context-graph/go/internal/scope"
)

const defaultPollInterval = time.Second

// ScopeGenerationWork captures one claimed scope generation for projection.
type ScopeGenerationWork struct {
	Scope      scope.IngestionScope
	Generation scope.ScopeGeneration
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
}

// Run polls for projector work until the context is canceled.
func (s Service) Run(ctx context.Context) error {
	if err := s.validate(); err != nil {
		return err
	}

	for {
		work, ok, err := s.WorkSource.Claim(ctx)
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

		factsForGeneration, err := s.FactStore.LoadFacts(ctx, work)
		if err != nil {
			if failErr := s.WorkSink.Fail(ctx, work, err); failErr != nil {
				return errors.Join(err, fmt.Errorf("fail projector work: %w", failErr))
			}
			continue
		}

		result, err := s.Runner.Project(ctx, work.Scope, work.Generation, factsForGeneration)
		if err != nil {
			if failErr := s.WorkSink.Fail(ctx, work, err); failErr != nil {
				return errors.Join(err, fmt.Errorf("fail projector work: %w", failErr))
			}
			continue
		}

		if err := s.WorkSink.Ack(ctx, work, result); err != nil {
			return fmt.Errorf("ack projector work: %w", err)
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
