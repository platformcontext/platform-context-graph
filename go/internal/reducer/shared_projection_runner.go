package reducer

import (
	"context"
	"errors"
	"fmt"
	"time"
)

const (
	defaultPartitionCount     = 8
	defaultSharedPollInterval = 5 * time.Second
	defaultLeaseTTL           = 60 * time.Second
	defaultBatchLimit         = 100
	defaultEvidenceSource     = "finalization/workloads"
)

// sharedProjectionDomains lists the three shared projection domains processed
// by the partition worker.
var sharedProjectionDomains = []string{
	DomainPlatformInfra,
	DomainRepoDependency,
	DomainWorkloadDependency,
}

// SharedProjectionRunnerConfig holds configuration for the shared projection
// partition worker.
type SharedProjectionRunnerConfig struct {
	PartitionCount int
	PollInterval   time.Duration
	LeaseTTL       time.Duration
	LeaseOwner     string
	BatchLimit     int
	EvidenceSource string
}

func (c SharedProjectionRunnerConfig) partitionCount() int {
	if c.PartitionCount <= 0 {
		return defaultPartitionCount
	}
	return c.PartitionCount
}

func (c SharedProjectionRunnerConfig) pollInterval() time.Duration {
	if c.PollInterval <= 0 {
		return defaultSharedPollInterval
	}
	return c.PollInterval
}

func (c SharedProjectionRunnerConfig) leaseTTL() time.Duration {
	if c.LeaseTTL <= 0 {
		return defaultLeaseTTL
	}
	return c.LeaseTTL
}

func (c SharedProjectionRunnerConfig) batchLimit() int {
	if c.BatchLimit <= 0 {
		return defaultBatchLimit
	}
	return c.BatchLimit
}

func (c SharedProjectionRunnerConfig) evidenceSource() string {
	if c.EvidenceSource == "" {
		return defaultEvidenceSource
	}
	return c.EvidenceSource
}

func (c SharedProjectionRunnerConfig) leaseOwner() string {
	if c.LeaseOwner == "" {
		return "shared-projection-runner"
	}
	return c.LeaseOwner
}

// SharedProjectionRunner processes shared projection intents across all
// domains and partitions. It runs as a long-lived goroutine alongside the
// main reducer claim/execute/ack loop.
type SharedProjectionRunner struct {
	IntentReader SharedIntentReader
	LeaseManager PartitionLeaseManager
	EdgeWriter   SharedProjectionEdgeWriter
	AcceptedGen  AcceptedGenerationLookup
	Config       SharedProjectionRunnerConfig
	Wait         func(context.Context, time.Duration) error
}

// Run processes shared projection intents until the context is cancelled.
// Each cycle iterates over all domains and partitions, calling
// ProcessPartitionOnce for each combination.
func (r *SharedProjectionRunner) Run(ctx context.Context) error {
	if err := r.validate(); err != nil {
		return err
	}

	for {
		if ctx.Err() != nil {
			return nil
		}

		didWork := r.runOneCycle(ctx)

		if !didWork {
			if err := r.wait(ctx, r.Config.pollInterval()); err != nil {
				if errors.Is(err, context.Canceled) || errors.Is(err, context.DeadlineExceeded) || ctx.Err() != nil {
					return nil
				}
				return fmt.Errorf("wait for shared projection work: %w", err)
			}
		}
	}
}

// runOneCycle iterates all domains and partitions, returning true if any
// partition processed work.
func (r *SharedProjectionRunner) runOneCycle(ctx context.Context) bool {
	now := time.Now().UTC()
	partitionCount := r.Config.partitionCount()
	didWork := false

	for _, domain := range sharedProjectionDomains {
		for partitionID := 0; partitionID < partitionCount; partitionID++ {
			if ctx.Err() != nil {
				return didWork
			}

			result, err := ProcessPartitionOnce(
				ctx,
				now,
				PartitionProcessorConfig{
					Domain:         domain,
					PartitionID:    partitionID,
					PartitionCount: partitionCount,
					LeaseOwner:     r.Config.leaseOwner(),
					LeaseTTL:       r.Config.leaseTTL(),
					BatchLimit:     r.Config.batchLimit(),
					EvidenceSource: r.Config.evidenceSource(),
				},
				r.LeaseManager,
				r.IntentReader,
				r.EdgeWriter,
				r.AcceptedGen,
			)
			if err != nil {
				continue
			}
			if result.ProcessedIntents > 0 {
				didWork = true
			}
		}
	}

	return didWork
}

func (r *SharedProjectionRunner) validate() error {
	if r.IntentReader == nil {
		return errors.New("shared projection runner: intent reader is required")
	}
	if r.LeaseManager == nil {
		return errors.New("shared projection runner: lease manager is required")
	}
	if r.EdgeWriter == nil {
		return errors.New("shared projection runner: edge writer is required")
	}
	return nil
}

func (r *SharedProjectionRunner) wait(ctx context.Context, interval time.Duration) error {
	if r.Wait != nil {
		return r.Wait(ctx, interval)
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
