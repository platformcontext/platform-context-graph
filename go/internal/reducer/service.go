package reducer

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"time"
)

const defaultPollInterval = time.Second

// WorkSource claims one reducer intent at a time.
type WorkSource interface {
	Claim(context.Context) (Intent, bool, error)
}

// Executor executes one claimed reducer intent.
type Executor interface {
	Execute(context.Context, Intent) (Result, error)
}

// WorkSink acknowledges or fails one claimed reducer intent.
type WorkSink interface {
	Ack(context.Context, Intent, Result) error
	Fail(context.Context, Intent, error) error
}

// Service coordinates reducer polling and one-intent-at-a-time execution.
type Service struct {
	PollInterval time.Duration
	WorkSource   WorkSource
	Executor     Executor
	WorkSink     WorkSink
	Wait         func(context.Context, time.Duration) error

	// SharedProjectionEdgeWriter is the Neo4j edge writer used by the shared
	// projection worker loop (ProcessPartitionOnce). Nil until Neo4j is wired.
	SharedProjectionEdgeWriter SharedProjectionEdgeWriter

	// SharedProjectionRunner runs the shared projection intent processing loop
	// concurrently with the main claim/execute/ack loop. Nil disables the runner.
	SharedProjectionRunner *SharedProjectionRunner
}

// Run polls for reducer work until the context is canceled. If a
// SharedProjectionRunner is configured, it runs concurrently as a goroutine.
func (s Service) Run(ctx context.Context) error {
	if err := s.validate(); err != nil {
		return err
	}

	ctx, cancel := context.WithCancel(ctx)
	defer cancel()

	var wg sync.WaitGroup
	var runnerErr error

	if s.SharedProjectionRunner != nil {
		wg.Add(1)
		go func() {
			defer wg.Done()
			if err := s.SharedProjectionRunner.Run(ctx); err != nil {
				runnerErr = err
				cancel()
			}
		}()
	}

	err := s.runMainLoop(ctx)

	cancel()
	wg.Wait()

	if err != nil {
		return err
	}
	return runnerErr
}

// runMainLoop is the main claim/execute/ack loop extracted for concurrent use.
func (s Service) runMainLoop(ctx context.Context) error {
	for {
		intent, ok, err := s.WorkSource.Claim(ctx)
		if err != nil {
			return fmt.Errorf("claim reducer work: %w", err)
		}
		if !ok {
			if err := s.wait(ctx, s.pollInterval()); err != nil {
				if errors.Is(err, context.Canceled) || errors.Is(err, context.DeadlineExceeded) || ctx.Err() != nil {
					return nil
				}
				return fmt.Errorf("wait for reducer work: %w", err)
			}
			continue
		}

		result, err := s.Executor.Execute(ctx, intent)
		if err != nil {
			if failErr := s.WorkSink.Fail(ctx, intent, err); failErr != nil {
				return errors.Join(err, fmt.Errorf("fail reducer work: %w", failErr))
			}
			continue
		}

		if err := s.WorkSink.Ack(ctx, intent, result); err != nil {
			return fmt.Errorf("ack reducer work: %w", err)
		}
	}
}

func (s Service) validate() error {
	if s.WorkSource == nil {
		return errors.New("work source is required")
	}
	if s.Executor == nil {
		return errors.New("executor is required")
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
