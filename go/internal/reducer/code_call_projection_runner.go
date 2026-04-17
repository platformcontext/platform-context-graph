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
	defaultCodeCallLeaseOwner = "code-call-projection-runner"
	maxCodeCallPollInterval   = 5 * time.Second
	// Acceptance-unit processing must either see the full bounded slice or fail
	// safely instead of silently truncating the snapshot.
	maxCodeCallAcceptanceScanLimit = 10_000
)

// CodeCallProjectionIntentReader reads code-call intents by domain and bounded
// acceptance unit.
type CodeCallProjectionIntentReader interface {
	ListPendingDomainIntents(ctx context.Context, domain string, limit int) ([]SharedProjectionIntentRow, error)
	ListPendingAcceptanceUnitIntents(ctx context.Context, key SharedProjectionAcceptanceKey, domain string, limit int) ([]SharedProjectionIntentRow, error)
	MarkIntentsCompleted(ctx context.Context, intentIDs []string, completedAt time.Time) error
}

// CodeCallProjectionRunnerConfig configures the controlled code-calls lane.
type CodeCallProjectionRunnerConfig struct {
	LeaseOwner   string
	PollInterval time.Duration
	LeaseTTL     time.Duration
	BatchLimit   int
}

func (c CodeCallProjectionRunnerConfig) pollInterval() time.Duration {
	if c.PollInterval <= 0 {
		return defaultSharedPollInterval
	}
	return c.PollInterval
}

func (c CodeCallProjectionRunnerConfig) leaseTTL() time.Duration {
	if c.LeaseTTL <= 0 {
		return defaultLeaseTTL
	}
	return c.LeaseTTL
}

func (c CodeCallProjectionRunnerConfig) batchLimit() int {
	if c.BatchLimit <= 0 {
		return defaultBatchLimit
	}
	return c.BatchLimit
}

func (c CodeCallProjectionRunnerConfig) leaseOwner() string {
	if c.LeaseOwner == "" {
		return defaultCodeCallLeaseOwner
	}
	return c.LeaseOwner
}

// CodeCallProjectionRunner processes code-call shared intents one repo/run at a time.
type CodeCallProjectionRunner struct {
	IntentReader        CodeCallProjectionIntentReader
	LeaseManager        PartitionLeaseManager
	EdgeWriter          SharedProjectionEdgeWriter
	AcceptedGen         AcceptedGenerationLookup
	AcceptedGenPrefetch AcceptedGenerationPrefetch
	Config              CodeCallProjectionRunnerConfig
	Wait                func(context.Context, time.Duration) error

	Tracer      trace.Tracer
	Instruments *telemetry.Instruments
	Logger      *slog.Logger
}

// Run drains code-call work until the context is canceled.
func (r *CodeCallProjectionRunner) Run(ctx context.Context) error {
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
			r.recordCodeCallCycleFailure(ctx, err, time.Since(cycleStart).Seconds())
			if err := r.wait(ctx, codeCallPollBackoff(r.Config.pollInterval(), consecutiveEmpty)); err != nil {
				if errors.Is(err, context.Canceled) || errors.Is(err, context.DeadlineExceeded) || ctx.Err() != nil {
					return nil
				}
				return fmt.Errorf("wait for code call work: %w", err)
			}
			continue
		}
		if didWork {
			consecutiveEmpty = 0
			continue
		}

		consecutiveEmpty++
		if err := r.wait(ctx, codeCallPollBackoff(r.Config.pollInterval(), consecutiveEmpty)); err != nil {
			if errors.Is(err, context.Canceled) || errors.Is(err, context.DeadlineExceeded) || ctx.Err() != nil {
				return nil
			}
			return fmt.Errorf("wait for code call work: %w", err)
		}
	}
}

func (r *CodeCallProjectionRunner) runOneCycle(ctx context.Context) (bool, error) {
	result, err := r.processOnce(ctx, time.Now().UTC())
	if err != nil {
		return true, err
	}
	return result.ProcessedIntents > 0, nil
}

func (r *CodeCallProjectionRunner) processOnce(ctx context.Context, now time.Time) (PartitionProcessResult, error) {
	cycleStart := time.Now()
	acceptanceTelemetry := sharedAcceptanceTelemetry{
		Instruments: r.Instruments,
		Logger:      r.Logger,
	}
	claimStart := time.Now()
	claimed, err := r.LeaseManager.ClaimPartitionLease(
		ctx,
		DomainCodeCalls,
		0,
		1,
		r.Config.leaseOwner(),
		r.Config.leaseTTL(),
	)
	if r.Instruments != nil {
		r.Instruments.QueueClaimDuration.Record(ctx, time.Since(claimStart).Seconds(), metric.WithAttributes(
			attribute.String("queue", "code_calls"),
		))
	}
	if err != nil {
		return PartitionProcessResult{}, fmt.Errorf("claim code call lease: %w", err)
	}
	if !claimed {
		return PartitionProcessResult{LeaseAcquired: false}, nil
	}

	defer func() {
		_ = r.LeaseManager.ReleasePartitionLease(ctx, DomainCodeCalls, 0, 1, r.Config.leaseOwner())
	}()

	key, err := r.selectAcceptanceUnitWork(ctx)
	if err != nil {
		return PartitionProcessResult{LeaseAcquired: true}, err
	}
	if key == (SharedProjectionAcceptanceKey{}) {
		return PartitionProcessResult{LeaseAcquired: true}, nil
	}

	rows, err := r.loadAllAcceptanceUnitIntents(ctx, key)
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
	acceptanceTelemetry.RecordStaleIntents(ctx, "code_call_projection", DomainCodeCalls, len(staleIDs))
	if len(active) == 0 && len(staleIDs) == 0 {
		return PartitionProcessResult{LeaseAcquired: true}, nil
	}

	result := PartitionProcessResult{LeaseAcquired: true}
	if len(active) > 0 {
		if err := r.retractRepo(ctx, active); err != nil {
			return result, err
		}

		writtenRows, writtenGroups, err := r.writeActiveRows(ctx, active)
		if err != nil {
			return result, err
		}
		result.RetractedRows = len(active)
		result.UpsertedRows = writtenRows
		if err := r.recordCodeCallCycle(ctx, key, acceptedGenerationID(active), writtenRows, writtenGroups, cycleStart); err != nil {
			return result, err
		}
	}

	processedIDs := make([]string, 0, len(staleIDs)+len(active))
	processedIDs = append(processedIDs, staleIDs...)
	for _, row := range active {
		processedIDs = append(processedIDs, row.IntentID)
	}
	if len(processedIDs) > 0 {
		if err := r.IntentReader.MarkIntentsCompleted(ctx, processedIDs, now); err != nil {
			return result, fmt.Errorf("mark code call intents completed: %w", err)
		}
	}

	result.ProcessedIntents = len(processedIDs)
	return result, nil
}

func (r *CodeCallProjectionRunner) selectAcceptanceUnitWork(ctx context.Context) (SharedProjectionAcceptanceKey, error) {
	start := time.Now()
	acceptanceTelemetry := sharedAcceptanceTelemetry{
		Instruments: r.Instruments,
		Logger:      r.Logger,
	}
	scanLimit := r.Config.batchLimit()
	if scanLimit > maxCodeCallAcceptanceScanLimit {
		scanLimit = maxCodeCallAcceptanceScanLimit
	}

	for {
		pending, err := r.IntentReader.ListPendingDomainIntents(ctx, DomainCodeCalls, scanLimit)
		if err != nil {
			acceptanceTelemetry.RecordLookup(ctx, sharedAcceptanceLookupEvent{
				Runner:   "code_call_projection",
				Result:   "error",
				Duration: time.Since(start).Seconds(),
				Err:      err,
			})
			return SharedProjectionAcceptanceKey{}, fmt.Errorf("list pending code call intents: %w", err)
		}
		if len(pending) == 0 {
			acceptanceTelemetry.RecordLookup(ctx, sharedAcceptanceLookupEvent{
				Runner:   "code_call_projection",
				Result:   "miss",
				Duration: time.Since(start).Seconds(),
			})
			return SharedProjectionAcceptanceKey{}, nil
		}

		lookup := r.AcceptedGen
		if r.AcceptedGenPrefetch != nil {
			resolvedLookup, err := r.AcceptedGenPrefetch(ctx, pending)
			if err != nil {
				acceptanceTelemetry.RecordLookup(ctx, sharedAcceptanceLookupEvent{
					Runner:   "code_call_projection",
					Result:   "error",
					Duration: time.Since(start).Seconds(),
					Err:      err,
				})
				return SharedProjectionAcceptanceKey{}, fmt.Errorf("prefetch accepted generations: %w", err)
			}
			lookup = resolvedLookup
		}

		seen := make(map[SharedProjectionAcceptanceKey]struct{}, len(pending))
		for _, row := range pending {
			key, ok := row.AcceptanceKey()
			if !ok {
				return SharedProjectionAcceptanceKey{}, fmt.Errorf(
					"pending code call intent %q is missing scope, acceptance unit, or source run",
					row.IntentID,
				)
			}
			if _, ok := seen[key]; ok {
				continue
			}
			seen[key] = struct{}{}
			if _, ok := lookup(key); ok {
				acceptanceTelemetry.RecordLookup(ctx, sharedAcceptanceLookupEvent{
					Runner:   "code_call_projection",
					Result:   "hit",
					Duration: time.Since(start).Seconds(),
				})
				return key, nil
			}
		}

		if len(pending) < scanLimit {
			acceptanceTelemetry.RecordLookup(ctx, sharedAcceptanceLookupEvent{
				Runner:   "code_call_projection",
				Result:   "miss",
				Duration: time.Since(start).Seconds(),
			})
			return SharedProjectionAcceptanceKey{}, nil
		}
		if scanLimit >= maxCodeCallAcceptanceScanLimit {
			acceptanceTelemetry.RecordLookup(ctx, sharedAcceptanceLookupEvent{
				Runner:   "code_call_projection",
				Result:   "error",
				Duration: time.Since(start).Seconds(),
				Err: fmt.Errorf(
					"scan limit cap reached before finding accepted code call work (%d)",
					maxCodeCallAcceptanceScanLimit,
				),
			})
			return SharedProjectionAcceptanceKey{}, fmt.Errorf(
				"code call acceptance scan reached cap (%d) before locating accepted work",
				maxCodeCallAcceptanceScanLimit,
			)
		}

		nextLimit := scanLimit * 2
		if nextLimit > maxCodeCallAcceptanceScanLimit {
			nextLimit = maxCodeCallAcceptanceScanLimit
		}
		scanLimit = nextLimit
	}
}

func (r *CodeCallProjectionRunner) loadAllAcceptanceUnitIntents(ctx context.Context, key SharedProjectionAcceptanceKey) ([]SharedProjectionIntentRow, error) {
	limit := r.Config.batchLimit()
	if limit > maxCodeCallAcceptanceScanLimit {
		limit = maxCodeCallAcceptanceScanLimit
	}
	for {
		rows, err := r.IntentReader.ListPendingAcceptanceUnitIntents(ctx, key, DomainCodeCalls, limit)
		if err != nil {
			return nil, fmt.Errorf("list pending code call acceptance intents: %w", err)
		}
		if len(rows) < limit {
			return rows, nil
		}
		if limit >= maxCodeCallAcceptanceScanLimit {
			return nil, fmt.Errorf(
				"code call acceptance intent scan reached cap (%d) for scope %q unit %q run %q",
				maxCodeCallAcceptanceScanLimit,
				key.ScopeID,
				key.AcceptanceUnitID,
				key.SourceRunID,
			)
		}
		nextLimit := limit * 2
		if nextLimit > maxCodeCallAcceptanceScanLimit {
			nextLimit = maxCodeCallAcceptanceScanLimit
		}
		limit = nextLimit
	}
}

func (r *CodeCallProjectionRunner) retractRepo(ctx context.Context, rows []SharedProjectionIntentRow) error {
	retractRows := buildCodeCallRetractRows(uniqueRepositoryIDs(rows))
	for _, evidenceSource := range codeCallEvidenceSources() {
		if err := r.EdgeWriter.RetractEdges(ctx, DomainCodeCalls, retractRows, evidenceSource); err != nil {
			return fmt.Errorf("retract code call edges for %s: %w", evidenceSource, err)
		}
	}
	return nil
}

func (r *CodeCallProjectionRunner) writeActiveRows(ctx context.Context, rows []SharedProjectionIntentRow) (int, int, error) {
	groups := groupCodeCallUpsertRows(rows)
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
		if err := r.EdgeWriter.WriteEdges(ctx, DomainCodeCalls, group, source); err != nil {
			return 0, 0, fmt.Errorf("write code call edges for %s: %w", source, err)
		}
		writtenRows += len(group)
	}

	return writtenRows, len(sources), nil
}

func (r *CodeCallProjectionRunner) recordCodeCallCycle(ctx context.Context, key SharedProjectionAcceptanceKey, generationID string, writtenRows, writtenGroups int, startedAt time.Time) error {
	duration := time.Since(startedAt).Seconds()
	if r.Instruments != nil {
		attrs := metric.WithAttributes(telemetry.AttrDomain(DomainCodeCalls))
		r.Instruments.CanonicalWriteDuration.Record(ctx, duration, attrs)
		r.Instruments.CanonicalWrites.Add(ctx, int64(writtenRows), attrs)
	}

	if r.Logger != nil {
		logAttrs := make([]any, 0, 6+len(telemetry.AcceptanceAttrs(key.ScopeID, key.AcceptanceUnitID, key.SourceRunID, generationID)))
		for _, attr := range telemetry.AcceptanceAttrs(key.ScopeID, key.AcceptanceUnitID, key.SourceRunID, generationID) {
			logAttrs = append(logAttrs, attr)
		}
		logAttrs = append(logAttrs,
			slog.Int("written_rows", writtenRows),
			slog.Int("written_groups", writtenGroups),
			slog.Float64("duration_seconds", duration),
			telemetry.PhaseAttr(telemetry.PhaseReduction),
		)
		r.Logger.InfoContext(ctx, "code call projection cycle completed", logAttrs...)
	}

	return nil
}

func (r *CodeCallProjectionRunner) recordCodeCallCycleFailure(ctx context.Context, err error, duration float64) {
	if r.Logger == nil {
		return
	}

	failureClass := "code_call_projection_cycle_error"
	if IsRetryable(err) {
		failureClass = "code_call_projection_retryable"
	}

	logAttrs := make([]any, 0, 6)
	for _, attr := range telemetry.DomainAttrs(string(DomainCodeCalls), "") {
		logAttrs = append(logAttrs, attr)
	}
	logAttrs = append(logAttrs,
		slog.Float64("duration_seconds", duration),
		slog.Bool("retryable", IsRetryable(err)),
		slog.String("error", err.Error()),
		telemetry.FailureClassAttr(failureClass),
		telemetry.PhaseAttr(telemetry.PhaseReduction),
	)
	r.Logger.ErrorContext(ctx, "code call projection cycle failed", logAttrs...)
}

func (r *CodeCallProjectionRunner) validate() error {
	if r.IntentReader == nil {
		return errors.New("code call projection runner: intent reader is required")
	}
	if r.LeaseManager == nil {
		return errors.New("code call projection runner: lease manager is required")
	}
	if r.EdgeWriter == nil {
		return errors.New("code call projection runner: edge writer is required")
	}
	if r.AcceptedGen == nil {
		return errors.New("code call projection runner: accepted generation lookup is required")
	}
	return nil
}

func (r *CodeCallProjectionRunner) wait(ctx context.Context, interval time.Duration) error {
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

func codeCallPollBackoff(base time.Duration, consecutiveEmpty int) time.Duration {
	backoff := base
	for i := 1; i < consecutiveEmpty && i < 4; i++ {
		backoff *= 2
	}
	if backoff > maxCodeCallPollInterval {
		backoff = maxCodeCallPollInterval
	}
	return backoff
}

func codeCallEvidenceSources() []string {
	return []string{codeCallEvidenceSource, pythonMetaclassEvidenceSource}
}

func buildCodeCallRetractRows(repositoryIDs []string) []SharedProjectionIntentRow {
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

func groupCodeCallUpsertRows(rows []SharedProjectionIntentRow) map[string][]SharedProjectionIntentRow {
	groups := make(map[string][]SharedProjectionIntentRow)
	for _, row := range rows {
		if !isCodeCallEdgeRow(row) {
			continue
		}
		source := codeCallRowEvidenceSource(row)
		groups[source] = append(groups[source], row)
	}
	return groups
}

func uniqueRepositoryIDs(rows []SharedProjectionIntentRow) []string {
	seen := make(map[string]struct{}, len(rows))
	repositoryIDs := make([]string, 0, len(rows))
	for _, row := range rows {
		repositoryID := strings.TrimSpace(row.RepositoryID)
		if repositoryID == "" {
			continue
		}
		if _, ok := seen[repositoryID]; ok {
			continue
		}
		seen[repositoryID] = struct{}{}
		repositoryIDs = append(repositoryIDs, repositoryID)
	}
	sort.Strings(repositoryIDs)
	return repositoryIDs
}

func acceptedGenerationID(rows []SharedProjectionIntentRow) string {
	for _, row := range rows {
		if generationID := strings.TrimSpace(row.GenerationID); generationID != "" {
			return generationID
		}
	}
	return ""
}

func isCodeCallEdgeRow(row SharedProjectionIntentRow) bool {
	if row.Payload == nil {
		return false
	}
	if action := codeCallRowPayloadString(row, "action"); action == "delete" {
		return false
	}
	if codeCallRowPayloadString(row, "relationship_type") == "USES_METACLASS" {
		return codeCallRowPayloadString(row, "source_entity_id") != "" && codeCallRowPayloadString(row, "target_entity_id") != ""
	}
	return codeCallRowPayloadString(row, "caller_entity_id") != "" && codeCallRowPayloadString(row, "callee_entity_id") != ""
}

func codeCallRowEvidenceSource(row SharedProjectionIntentRow) string {
	if source := strings.TrimSpace(codeCallRowPayloadString(row, "evidence_source")); source != "" {
		return source
	}
	if codeCallRowPayloadString(row, "relationship_type") == "USES_METACLASS" {
		return pythonMetaclassEvidenceSource
	}
	return codeCallEvidenceSource
}

func codeCallRowPayloadString(row SharedProjectionIntentRow, key string) string {
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
