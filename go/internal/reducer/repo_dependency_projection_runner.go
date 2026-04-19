package reducer

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"sort"
	"strings"
	"time"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/metric"
	"go.opentelemetry.io/otel/trace"

	"github.com/platformcontext/platform-context-graph/go/internal/telemetry"
)

const (
	defaultRepoDependencyLeaseOwner      = "repo-dependency-projection-runner"
	maxRepoDependencyPollInterval        = 5 * time.Second
	maxRepoDependencyAcceptanceScanLimit = 10_000
)

// RepoDependencyProjectionIntentReader reads repo-dependency intents by domain
// and by source-repo-owned acceptance unit.
type RepoDependencyProjectionIntentReader interface {
	ListPendingDomainIntents(ctx context.Context, domain string, limit int) ([]SharedProjectionIntentRow, error)
	ListAcceptanceUnitDomainIntents(ctx context.Context, acceptanceUnitID, domain string, limit int) ([]SharedProjectionIntentRow, error)
	MarkIntentsCompleted(ctx context.Context, intentIDs []string, completedAt time.Time) error
}

// RepoDependencyProjectionRunnerConfig configures the controlled repo-dependency lane.
type RepoDependencyProjectionRunnerConfig struct {
	LeaseOwner   string
	PollInterval time.Duration
	LeaseTTL     time.Duration
	BatchLimit   int
}

func (c RepoDependencyProjectionRunnerConfig) pollInterval() time.Duration {
	if c.PollInterval <= 0 {
		return defaultSharedPollInterval
	}
	return c.PollInterval
}

func (c RepoDependencyProjectionRunnerConfig) leaseTTL() time.Duration {
	if c.LeaseTTL <= 0 {
		return defaultLeaseTTL
	}
	return c.LeaseTTL
}

func (c RepoDependencyProjectionRunnerConfig) batchLimit() int {
	if c.BatchLimit <= 0 {
		return defaultBatchLimit
	}
	return c.BatchLimit
}

func (c RepoDependencyProjectionRunnerConfig) leaseOwner() string {
	if c.LeaseOwner == "" {
		return defaultRepoDependencyLeaseOwner
	}
	return c.LeaseOwner
}

// RepoDependencyProjectionRunner processes repo-dependency shared intents one
// source repository at a time so repo-wide retractions cannot race with
// partition-sliced snapshots.
type RepoDependencyProjectionRunner struct {
	IntentReader        RepoDependencyProjectionIntentReader
	LeaseManager        PartitionLeaseManager
	EdgeWriter          SharedProjectionEdgeWriter
	AcceptedGen         AcceptedGenerationLookup
	AcceptedGenPrefetch AcceptedGenerationPrefetch
	Config              RepoDependencyProjectionRunnerConfig
	Wait                func(context.Context, time.Duration) error

	Tracer      trace.Tracer
	Instruments *telemetry.Instruments
	Logger      *slog.Logger
}

// Run drains repo-dependency work until the context is canceled.
func (r *RepoDependencyProjectionRunner) Run(ctx context.Context) error {
	if err := r.validate(); err != nil {
		return err
	}

	consecutiveEmpty := 0
	for {
		if ctx.Err() != nil {
			return nil
		}

		cycleStart := time.Now()
		didWork, err := r.runOneCycle(ctx)
		if err != nil {
			consecutiveEmpty++
			r.recordRepoDependencyCycleFailure(ctx, err, time.Since(cycleStart).Seconds())
			if err := r.wait(ctx, repoDependencyPollBackoff(r.Config.pollInterval(), consecutiveEmpty)); err != nil {
				if errors.Is(err, context.Canceled) || errors.Is(err, context.DeadlineExceeded) || ctx.Err() != nil {
					return nil
				}
				return fmt.Errorf("wait for repo dependency work: %w", err)
			}
			continue
		}
		if didWork {
			consecutiveEmpty = 0
			continue
		}

		consecutiveEmpty++
		if err := r.wait(ctx, repoDependencyPollBackoff(r.Config.pollInterval(), consecutiveEmpty)); err != nil {
			if errors.Is(err, context.Canceled) || errors.Is(err, context.DeadlineExceeded) || ctx.Err() != nil {
				return nil
			}
			return fmt.Errorf("wait for repo dependency work: %w", err)
		}
	}
}

func (r *RepoDependencyProjectionRunner) runOneCycle(ctx context.Context) (bool, error) {
	result, err := r.processOnce(ctx, time.Now().UTC())
	if err != nil {
		return true, err
	}
	return result.ProcessedIntents > 0, nil
}

func (r *RepoDependencyProjectionRunner) processOnce(ctx context.Context, now time.Time) (PartitionProcessResult, error) {
	cycleStart := time.Now()
	claimStart := time.Now()
	claimed, err := r.LeaseManager.ClaimPartitionLease(
		ctx,
		DomainRepoDependency,
		0,
		1,
		r.Config.leaseOwner(),
		r.Config.leaseTTL(),
	)
	if r.Instruments != nil {
		r.Instruments.QueueClaimDuration.Record(ctx, time.Since(claimStart).Seconds(), metric.WithAttributes(
			attribute.String("queue", "repo_dependency"),
		))
	}
	if err != nil {
		return PartitionProcessResult{}, fmt.Errorf("claim repo dependency lease: %w", err)
	}
	if !claimed {
		return PartitionProcessResult{LeaseAcquired: false}, nil
	}
	defer func() {
		_ = r.LeaseManager.ReleasePartitionLease(ctx, DomainRepoDependency, 0, 1, r.Config.leaseOwner())
	}()

	acceptanceUnitID, err := r.selectAcceptanceUnitWork(ctx)
	if err != nil {
		return PartitionProcessResult{LeaseAcquired: true}, err
	}
	if acceptanceUnitID == "" {
		return PartitionProcessResult{LeaseAcquired: true}, nil
	}

	rows, err := r.loadAllAcceptanceUnitIntents(ctx, acceptanceUnitID)
	if err != nil {
		return PartitionProcessResult{LeaseAcquired: true}, err
	}

	lookup := r.AcceptedGen
	if r.AcceptedGenPrefetch != nil {
		resolvedLookup, err := r.AcceptedGenPrefetch(ctx, rows)
		if err != nil {
			return PartitionProcessResult{LeaseAcquired: true}, fmt.Errorf("prefetch accepted generations: %w", err)
		}
		lookup = resolvedLookup
	}

	active, staleIDs := FilterAuthoritativeIntents(rows, lookup)
	if len(active) == 0 && len(staleIDs) == 0 {
		return PartitionProcessResult{LeaseAcquired: true}, nil
	}

	result := PartitionProcessResult{LeaseAcquired: true}
	if len(active) > 0 {
		retractedRows, err := r.retractRepo(ctx, active)
		if err != nil {
			return result, err
		}
		writtenRows, writtenGroups, err := r.writeActiveRows(ctx, active)
		if err != nil {
			return result, err
		}
		result.RetractedRows = retractedRows
		result.UpsertedRows = writtenRows
		r.recordRepoDependencyCycle(ctx, acceptanceUnitID, active, writtenRows, writtenGroups, cycleStart)
	}

	processedIDs := make([]string, 0, len(staleIDs)+len(active))
	processedIDs = append(processedIDs, staleIDs...)
	for _, row := range active {
		processedIDs = append(processedIDs, row.IntentID)
	}
	if len(processedIDs) > 0 {
		if err := r.IntentReader.MarkIntentsCompleted(ctx, processedIDs, now); err != nil {
			return result, fmt.Errorf("mark repo dependency intents completed: %w", err)
		}
	}
	result.ProcessedIntents = len(processedIDs)
	return result, nil
}

func (r *RepoDependencyProjectionRunner) selectAcceptanceUnitWork(ctx context.Context) (string, error) {
	scanLimit := r.Config.batchLimit()
	if scanLimit > maxRepoDependencyAcceptanceScanLimit {
		scanLimit = maxRepoDependencyAcceptanceScanLimit
	}

	for {
		pending, err := r.IntentReader.ListPendingDomainIntents(ctx, DomainRepoDependency, scanLimit)
		if err != nil {
			return "", fmt.Errorf("list pending repo dependency intents: %w", err)
		}
		if len(pending) == 0 {
			return "", nil
		}

		lookup := r.AcceptedGen
		if r.AcceptedGenPrefetch != nil {
			resolvedLookup, err := r.AcceptedGenPrefetch(ctx, pending)
			if err != nil {
				return "", fmt.Errorf("prefetch accepted generations: %w", err)
			}
			lookup = resolvedLookup
		}

		acceptedByUnit := make(map[string]bool, len(pending))
		order := make([]string, 0, len(pending))
		for _, row := range pending {
			unitID, ok := repoDependencyAcceptanceUnitID(row)
			if !ok {
				return "", fmt.Errorf("pending repo dependency intent %q is missing acceptance unit", row.IntentID)
			}
			if _, seen := acceptedByUnit[unitID]; !seen {
				order = append(order, unitID)
				acceptedByUnit[unitID] = false
			}
			key, ok := row.AcceptanceKey()
			if !ok {
				return "", fmt.Errorf(
					"pending repo dependency intent %q is missing scope, acceptance unit, or source run",
					row.IntentID,
				)
			}
			acceptedGeneration, ok := lookup(key)
			if !ok {
				continue
			}
			if strings.TrimSpace(row.GenerationID) == strings.TrimSpace(acceptedGeneration) {
				acceptedByUnit[unitID] = true
			}
		}

		for _, unitID := range order {
			if acceptedByUnit[unitID] {
				return unitID, nil
			}
		}

		if len(pending) < scanLimit {
			return "", nil
		}
		if scanLimit >= maxRepoDependencyAcceptanceScanLimit {
			return "", fmt.Errorf(
				"repo dependency acceptance scan reached cap (%d) before locating accepted work",
				maxRepoDependencyAcceptanceScanLimit,
			)
		}

		nextLimit := scanLimit * 2
		if nextLimit > maxRepoDependencyAcceptanceScanLimit {
			nextLimit = maxRepoDependencyAcceptanceScanLimit
		}
		scanLimit = nextLimit
	}
}

func (r *RepoDependencyProjectionRunner) loadAllAcceptanceUnitIntents(ctx context.Context, acceptanceUnitID string) ([]SharedProjectionIntentRow, error) {
	limit := r.Config.batchLimit()
	if limit > maxRepoDependencyAcceptanceScanLimit {
		limit = maxRepoDependencyAcceptanceScanLimit
	}
	for {
		rows, err := r.IntentReader.ListAcceptanceUnitDomainIntents(ctx, acceptanceUnitID, DomainRepoDependency, limit)
		if err != nil {
			return nil, fmt.Errorf("list repo dependency acceptance intents: %w", err)
		}
		if len(rows) < limit {
			return rows, nil
		}
		if limit >= maxRepoDependencyAcceptanceScanLimit {
			return nil, fmt.Errorf(
				"repo dependency acceptance intent scan reached cap (%d) for unit %q",
				maxRepoDependencyAcceptanceScanLimit,
				acceptanceUnitID,
			)
		}
		nextLimit := limit * 2
		if nextLimit > maxRepoDependencyAcceptanceScanLimit {
			nextLimit = maxRepoDependencyAcceptanceScanLimit
		}
		limit = nextLimit
	}
}

func (r *RepoDependencyProjectionRunner) retractRepo(ctx context.Context, rows []SharedProjectionIntentRow) (int, error) {
	retractRows := buildRepoDependencyRetractRows(uniqueRepositoryIDs(rows))
	if len(retractRows) == 0 {
		return 0, nil
	}
	sources := repoDependencyEvidenceSources(rows)
	for _, source := range sources {
		if err := r.EdgeWriter.RetractEdges(ctx, DomainRepoDependency, retractRows, source); err != nil {
			return 0, fmt.Errorf("retract repo dependency edges for %s: %w", source, err)
		}
	}
	return len(retractRows) * len(sources), nil
}

func (r *RepoDependencyProjectionRunner) writeActiveRows(ctx context.Context, rows []SharedProjectionIntentRow) (int, int, error) {
	groups := groupRepoDependencyUpsertRows(rows)
	if len(groups) == 0 {
		return 0, 0, nil
	}

	sources := make([]string, 0, len(groups))
	for source := range groups {
		sources = append(sources, source)
	}
	sort.Strings(sources)

	writtenRows := 0
	for _, source := range sources {
		group := groups[source]
		if len(group) == 0 {
			continue
		}
		if err := r.EdgeWriter.WriteEdges(ctx, DomainRepoDependency, group, source); err != nil {
			return 0, 0, fmt.Errorf("write repo dependency edges for %s: %w", source, err)
		}
		writtenRows += len(group)
	}
	return writtenRows, len(sources), nil
}

func (r *RepoDependencyProjectionRunner) recordRepoDependencyCycle(
	ctx context.Context,
	acceptanceUnitID string,
	rows []SharedProjectionIntentRow,
	writtenRows int,
	writtenGroups int,
	startedAt time.Time,
) {
	duration := time.Since(startedAt).Seconds()
	if r.Instruments != nil {
		attrs := metric.WithAttributes(telemetry.AttrDomain(DomainRepoDependency))
		r.Instruments.CanonicalWriteDuration.Record(ctx, duration, attrs)
		r.Instruments.CanonicalWrites.Add(ctx, int64(writtenRows), attrs)
	}
	if r.Logger != nil {
		r.Logger.InfoContext(
			ctx,
			"repo dependency projection cycle completed",
			slog.String(telemetry.LogKeyAcceptanceUnitID, acceptanceUnitID),
			slog.Int("written_rows", writtenRows),
			slog.Int("written_groups", writtenGroups),
			slog.Int("active_generations", len(uniqueGenerationIDs(rows))),
			slog.Float64("duration_seconds", duration),
			telemetry.PhaseAttr(telemetry.PhaseReduction),
		)
	}
}

func (r *RepoDependencyProjectionRunner) recordRepoDependencyCycleFailure(ctx context.Context, err error, duration float64) {
	if r.Logger == nil {
		return
	}
	failureClass := "repo_dependency_projection_cycle_error"
	if IsRetryable(err) {
		failureClass = "repo_dependency_projection_retryable"
	}
	logAttrs := make([]any, 0, 6)
	for _, attr := range telemetry.DomainAttrs(string(DomainRepoDependency), "") {
		logAttrs = append(logAttrs, attr)
	}
	logAttrs = append(logAttrs,
		slog.Float64("duration_seconds", duration),
		slog.Bool("retryable", IsRetryable(err)),
		slog.String("error", err.Error()),
		telemetry.FailureClassAttr(failureClass),
		telemetry.PhaseAttr(telemetry.PhaseReduction),
	)
	r.Logger.ErrorContext(ctx, "repo dependency projection cycle failed", logAttrs...)
}

func (r *RepoDependencyProjectionRunner) validate() error {
	if r.IntentReader == nil {
		return errors.New("repo dependency projection runner: intent reader is required")
	}
	if r.LeaseManager == nil {
		return errors.New("repo dependency projection runner: lease manager is required")
	}
	if r.EdgeWriter == nil {
		return errors.New("repo dependency projection runner: edge writer is required")
	}
	if r.AcceptedGen == nil {
		return errors.New("repo dependency projection runner: accepted generation lookup is required")
	}
	return nil
}

func (r *RepoDependencyProjectionRunner) wait(ctx context.Context, interval time.Duration) error {
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

func repoDependencyPollBackoff(base time.Duration, consecutiveEmpty int) time.Duration {
	backoff := base
	for i := 1; i < consecutiveEmpty && i < 4; i++ {
		backoff *= 2
	}
	if backoff > maxRepoDependencyPollInterval {
		backoff = maxRepoDependencyPollInterval
	}
	return backoff
}

func repoDependencyAcceptanceUnitID(row SharedProjectionIntentRow) (string, bool) {
	if value := strings.TrimSpace(row.AcceptanceUnitID); value != "" {
		return value, true
	}
	if key, ok := row.AcceptanceKey(); ok && strings.TrimSpace(key.AcceptanceUnitID) != "" {
		return strings.TrimSpace(key.AcceptanceUnitID), true
	}
	if value := strings.TrimSpace(row.RepositoryID); value != "" {
		return value, true
	}
	return "", false
}

func buildRepoDependencyRetractRows(repositoryIDs []string) []SharedProjectionIntentRow {
	rows := make([]SharedProjectionIntentRow, 0, len(repositoryIDs))
	for _, repositoryID := range repositoryIDs {
		repositoryID = strings.TrimSpace(repositoryID)
		if repositoryID == "" {
			continue
		}
		rows = append(rows, SharedProjectionIntentRow{
			RepositoryID: repositoryID,
			Payload:      map[string]any{"repo_id": repositoryID},
		})
	}
	return rows
}

func groupRepoDependencyUpsertRows(rows []SharedProjectionIntentRow) map[string][]SharedProjectionIntentRow {
	groups := make(map[string][]SharedProjectionIntentRow)
	for _, row := range rows {
		if !isRepoDependencyUpsertRow(row) {
			continue
		}
		source := repoDependencyRowEvidenceSource(row)
		groups[source] = append(groups[source], row)
	}
	return groups
}

func isRepoDependencyUpsertRow(row SharedProjectionIntentRow) bool {
	if row.Payload == nil {
		return false
	}
	action := strings.TrimSpace(repoDependencyPayloadString(row, "action"))
	if action == "delete" || action == "retract" {
		return false
	}

	repoID := strings.TrimSpace(repoDependencyPayloadString(row, "repo_id"))
	if repoID == "" {
		repoID = strings.TrimSpace(row.RepositoryID)
	}
	if repoID == "" {
		return false
	}
	if relationshipType := strings.TrimSpace(repoDependencyPayloadString(row, "relationship_type")); relationshipType == "RUNS_ON" {
		return strings.TrimSpace(repoDependencyPayloadString(row, "platform_id")) != ""
	}
	return strings.TrimSpace(repoDependencyPayloadString(row, "target_repo_id")) != ""
}

func repoDependencyEvidenceSources(rows []SharedProjectionIntentRow) []string {
	seen := make(map[string]struct{}, len(rows))
	sources := make([]string, 0, len(rows))
	for _, row := range rows {
		source := repoDependencyRowEvidenceSource(row)
		if _, ok := seen[source]; ok {
			continue
		}
		seen[source] = struct{}{}
		sources = append(sources, source)
	}
	sort.Strings(sources)
	return sources
}

func repoDependencyRowEvidenceSource(row SharedProjectionIntentRow) string {
	if source := strings.TrimSpace(repoDependencyPayloadString(row, "evidence_source")); source != "" {
		return source
	}
	return defaultEvidenceSource
}

func repoDependencyPayloadString(row SharedProjectionIntentRow, key string) string {
	if row.Payload == nil {
		return ""
	}
	value, ok := row.Payload[key]
	if !ok {
		return ""
	}
	str, ok := value.(string)
	if !ok {
		return ""
	}
	return strings.TrimSpace(str)
}

func uniqueGenerationIDs(rows []SharedProjectionIntentRow) []string {
	seen := make(map[string]struct{}, len(rows))
	ids := make([]string, 0, len(rows))
	for _, row := range rows {
		generationID := strings.TrimSpace(row.GenerationID)
		if generationID == "" {
			continue
		}
		if _, ok := seen[generationID]; ok {
			continue
		}
		seen[generationID] = struct{}{}
		ids = append(ids, generationID)
	}
	sort.Strings(ids)
	return ids
}
