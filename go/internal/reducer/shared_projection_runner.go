package reducer

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"runtime"
	"strconv"
	"strings"
	"sync"
	"time"

	"go.opentelemetry.io/otel/metric"
	"go.opentelemetry.io/otel/trace"

	"github.com/platformcontext/platform-context-graph/go/internal/telemetry"
)

const (
	defaultPartitionCount     = 8
	defaultSharedPollInterval = 500 * time.Millisecond
	defaultLeaseTTL           = 60 * time.Second
	defaultBatchLimit         = 100
	defaultEvidenceSource     = "finalization/workloads"
	maxSharedPollInterval     = 5 * time.Second
)

// sharedProjectionDomains lists the shared projection domains processed
// by the partition worker.
var sharedProjectionDomains = []string{
	DomainPlatformInfra,
	DomainRepoDependency,
	DomainWorkloadDependency,
	DomainInheritanceEdges,
	DomainSQLRelationships,
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
	Workers        int // concurrent partition workers; 0 or 1 means sequential
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
	IntentReader        SharedIntentReader
	LeaseManager        PartitionLeaseManager
	EdgeWriter          SharedProjectionEdgeWriter
	AcceptedGen         AcceptedGenerationLookup
	AcceptedGenPrefetch AcceptedGenerationPrefetch
	ReadinessLookup     GraphProjectionReadinessLookup
	ReadinessPrefetch   GraphProjectionReadinessPrefetch
	Config              SharedProjectionRunnerConfig
	Wait                func(context.Context, time.Duration) error

	// Telemetry fields (optional)
	Tracer      trace.Tracer
	Instruments *telemetry.Instruments
	Logger      *slog.Logger
}

// Run processes shared projection intents until the context is cancelled.
// Each cycle iterates over all domains and partitions, calling
// ProcessPartitionOnce for each combination. When no work is found, the
// poll interval doubles on each consecutive empty cycle (up to 5s) to
// avoid sustained high-frequency polling during idle periods.
func (r *SharedProjectionRunner) Run(ctx context.Context) error {
	if err := r.validate(); err != nil {
		return err
	}

	consecutiveEmpty := 0

	for {
		if ctx.Err() != nil {
			return nil
		}

		didWork := r.runOneCycle(ctx)

		if didWork {
			consecutiveEmpty = 0
			continue // immediately re-poll
		}

		consecutiveEmpty++
		backoff := r.Config.pollInterval()
		for i := 1; i < consecutiveEmpty && i < 4; i++ {
			backoff *= 2
		}
		if backoff > maxSharedPollInterval {
			backoff = maxSharedPollInterval
		}

		if err := r.wait(ctx, backoff); err != nil {
			if errors.Is(err, context.Canceled) || errors.Is(err, context.DeadlineExceeded) || ctx.Err() != nil {
				return nil
			}
			return fmt.Errorf("wait for shared projection work: %w", err)
		}
	}
}

// runOneCycle iterates all domains and partitions, returning true if any
// partition processed work.
func (r *SharedProjectionRunner) runOneCycle(ctx context.Context) bool {
	if r.Config.Workers <= 1 {
		return r.runOneCycleSequential(ctx)
	}
	return r.runOneCycleConcurrent(ctx)
}

// runOneCycleSequential processes partitions one at a time.
func (r *SharedProjectionRunner) runOneCycleSequential(ctx context.Context) bool {
	now := time.Now().UTC()
	partitionCount := r.Config.partitionCount()
	didWork := false

	for _, domain := range sharedProjectionDomains {
		for partitionID := 0; partitionID < partitionCount; partitionID++ {
			if ctx.Err() != nil {
				return didWork
			}

			result, err := r.processPartitionWithTelemetry(
				ctx,
				now,
				domain,
				partitionID,
				partitionCount,
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

// partitionWork represents a single domain/partition combination to process.
type partitionWork struct {
	domain      string
	partitionID int
}

// runOneCycleConcurrent processes partitions across N concurrent workers.
func (r *SharedProjectionRunner) runOneCycleConcurrent(ctx context.Context) bool {
	now := time.Now().UTC()
	partitionCount := r.Config.partitionCount()

	// Build work queue
	var work []partitionWork
	for _, domain := range sharedProjectionDomains {
		for partitionID := 0; partitionID < partitionCount; partitionID++ {
			work = append(work, partitionWork{domain: domain, partitionID: partitionID})
		}
	}

	workChan := make(chan partitionWork, len(work))
	for _, w := range work {
		workChan <- w
	}
	close(workChan)

	var (
		wg      sync.WaitGroup
		didWork bool
		mu      sync.Mutex
	)

	for i := 0; i < r.Config.Workers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for w := range workChan {
				if ctx.Err() != nil {
					return
				}

				result, err := r.processPartitionWithTelemetry(
					ctx,
					now,
					w.domain,
					w.partitionID,
					partitionCount,
				)
				if err != nil {
					continue
				}
				if result.ProcessedIntents > 0 {
					mu.Lock()
					didWork = true
					mu.Unlock()
				}
			}
		}()
	}

	wg.Wait()
	return didWork
}

func (r *SharedProjectionRunner) processPartitionWithTelemetry(
	ctx context.Context,
	now time.Time,
	domain string,
	partitionID int,
	partitionCount int,
) (PartitionProcessResult, error) {
	start := time.Now()

	if r.Tracer != nil {
		var span trace.Span
		ctx, span = r.Tracer.Start(ctx, telemetry.SpanCanonicalWrite)
		defer span.End()
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
		r.AcceptedGenPrefetch,
		r.ReadinessLookup,
		r.ReadinessPrefetch,
	)

	duration := time.Since(start).Seconds()
	acceptanceTelemetry := sharedAcceptanceTelemetry{
		Instruments: r.Instruments,
		Logger:      r.Logger,
	}
	acceptanceTelemetry.RecordStaleIntents(ctx, "shared_projection", domain, result.StaleIntents)
	if result.BlockedReadiness > 0 && r.Logger != nil {
		r.Logger.InfoContext(
			ctx,
			"shared projection skipped intents until semantic readiness is committed",
			slog.String("domain", domain),
			slog.Int("partition_id", partitionID),
			slog.Int("partition_count", partitionCount),
			slog.Int("blocked_count", result.BlockedReadiness),
			telemetry.PhaseAttr(telemetry.PhaseShared),
		)
	}

	if err == nil && result.ProcessedIntents > 0 {
		r.recordSharedProjectionCycle(ctx, domain, duration)
	}

	return result, err
}

func (r *SharedProjectionRunner) recordSharedProjectionCycle(ctx context.Context, domain string, duration float64) {
	if r.Instruments != nil {
		attrs := metric.WithAttributes(
			telemetry.AttrDomain(domain),
		)
		r.Instruments.SharedProjectionCycles.Add(ctx, 1, attrs)
		r.Instruments.CanonicalWriteDuration.Record(ctx, duration, attrs)
	}

	if r.Logger != nil {
		domainAttrs := telemetry.DomainAttrs(domain, "")
		logAttrs := make([]any, 0, len(domainAttrs)+1)
		for _, a := range domainAttrs {
			logAttrs = append(logAttrs, a)
		}
		logAttrs = append(logAttrs, slog.Float64("duration_seconds", duration))
		logAttrs = append(logAttrs, telemetry.PhaseAttr(telemetry.PhaseShared))
		r.Logger.InfoContext(ctx, "shared projection cycle completed", logAttrs...)
	}
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

// LoadSharedProjectionConfig parses shared projection env vars.
func LoadSharedProjectionConfig(getenv func(string) string) SharedProjectionRunnerConfig {
	return SharedProjectionRunnerConfig{
		PartitionCount: intFromEnvDefault(getenv, "PCG_SHARED_PROJECTION_PARTITION_COUNT", defaultPartitionCount),
		PollInterval:   durationFromEnv(getenv, "PCG_SHARED_PROJECTION_POLL_INTERVAL", defaultSharedPollInterval),
		LeaseTTL:       durationFromEnv(getenv, "PCG_SHARED_PROJECTION_LEASE_TTL", defaultLeaseTTL),
		BatchLimit:     intFromEnvDefault(getenv, "PCG_SHARED_PROJECTION_BATCH_LIMIT", defaultBatchLimit),
		Workers:        intFromEnvDefault(getenv, "PCG_SHARED_PROJECTION_WORKERS", defaultSharedProjectionWorkers()),
	}
}

func defaultSharedProjectionWorkers() int {
	n := runtime.NumCPU()
	if n > 4 {
		n = 4
	}
	if n < 1 {
		n = 1
	}
	return n
}

func intFromEnvDefault(getenv func(string) string, key string, defaultValue int) int {
	raw := strings.TrimSpace(getenv(key))
	if raw == "" {
		return defaultValue
	}
	value, err := strconv.Atoi(raw)
	if err != nil || value <= 0 {
		return defaultValue
	}
	return value
}

func durationFromEnv(getenv func(string) string, key string, defaultValue time.Duration) time.Duration {
	raw := strings.TrimSpace(getenv(key))
	if raw == "" {
		return defaultValue
	}
	value, err := time.ParseDuration(raw)
	if err != nil || value <= 0 {
		return defaultValue
	}
	return value
}
