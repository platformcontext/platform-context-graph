package reducer

import (
	"context"
	"fmt"
	"sort"
	"time"
)

// SharedProjectionEdgeWriter writes and retracts canonical graph edges for one
// shared projection domain.
type SharedProjectionEdgeWriter interface {
	RetractEdges(ctx context.Context, domain string, rows []SharedProjectionIntentRow, evidenceSource string) error
	WriteEdges(ctx context.Context, domain string, rows []SharedProjectionIntentRow, evidenceSource string) error
}

// PartitionLeaseManager manages partition leases for shared projection workers.
type PartitionLeaseManager interface {
	ClaimPartitionLease(ctx context.Context, domain string, partitionID, partitionCount int, leaseOwner string, leaseTTL time.Duration) (bool, error)
	ReleasePartitionLease(ctx context.Context, domain string, partitionID, partitionCount int, leaseOwner string) error
}

// SharedIntentReader reads and marks shared projection intents.
type SharedIntentReader interface {
	ListPendingDomainIntents(ctx context.Context, domain string, limit int) ([]SharedProjectionIntentRow, error)
	MarkIntentsCompleted(ctx context.Context, intentIDs []string, completedAt time.Time) error
}

// AcceptedGenerationLookup returns the accepted generation for a
// (repositoryID, sourceRunID) pair. Returns empty string and false when no
// accepted generation is known.
type AcceptedGenerationLookup func(repositoryID, sourceRunID string) (string, bool)

// PartitionBatchResult holds the result of selecting one partition batch.
type PartitionBatchResult struct {
	LatestRows    []SharedProjectionIntentRow
	StaleIDs      []string
	SupersededIDs []string
}

// PartitionProcessorConfig holds configuration for one partition processor
// cycle.
type PartitionProcessorConfig struct {
	Domain         string
	PartitionID    int
	PartitionCount int
	LeaseOwner     string
	LeaseTTL       time.Duration
	BatchLimit     int
	EvidenceSource string
}

// PartitionProcessResult captures the outcome of one partition processing
// cycle.
type PartitionProcessResult struct {
	LeaseAcquired    bool
	ProcessedIntents int
	UpsertedRows     int
	RetractedRows    int
}

// LatestIntentsByRepoAndPartition deduplicates intents to the most recent per
// (repository_id, partition_key) pair, matching the Python
// _latest_intents_by_repo_and_partition function.
func LatestIntentsByRepoAndPartition(intents []SharedProjectionIntentRow) ([]SharedProjectionIntentRow, []string) {
	if len(intents) == 0 {
		return nil, nil
	}

	sorted := make([]SharedProjectionIntentRow, len(intents))
	copy(sorted, intents)
	sort.SliceStable(sorted, func(i, j int) bool {
		if !sorted[i].CreatedAt.Equal(sorted[j].CreatedAt) {
			return sorted[i].CreatedAt.Before(sorted[j].CreatedAt)
		}
		return sorted[i].IntentID < sorted[j].IntentID
	})

	type repoPartitionKey struct {
		repositoryID string
		partitionKey string
	}

	latestByKey := make(map[repoPartitionKey]SharedProjectionIntentRow)
	order := make([]repoPartitionKey, 0)
	var supersededIDs []string

	for _, intent := range sorted {
		k := repoPartitionKey{
			repositoryID: intent.RepositoryID,
			partitionKey: intent.PartitionKey,
		}
		if prev, ok := latestByKey[k]; ok {
			supersededIDs = append(supersededIDs, prev.IntentID)
		} else {
			order = append(order, k)
		}
		latestByKey[k] = intent
	}

	result := make([]SharedProjectionIntentRow, 0, len(order))
	for _, k := range order {
		result = append(result, latestByKey[k])
	}

	return result, supersededIDs
}

// FilterAuthoritativeIntents splits intents into active (matching accepted
// generation) and stale (mismatching generation) sets, matching the Python
// _filter_authoritative_intents function.
func FilterAuthoritativeIntents(
	intents []SharedProjectionIntentRow,
	acceptedGen AcceptedGenerationLookup,
) (active []SharedProjectionIntentRow, staleIDs []string) {
	for _, intent := range intents {
		accepted, ok := acceptedGen(intent.RepositoryID, intent.SourceRunID)
		if !ok {
			continue
		}
		if intent.GenerationID != accepted {
			staleIDs = append(staleIDs, intent.IntentID)
			continue
		}
		active = append(active, intent)
	}
	return active, staleIDs
}

// SelectPartitionBatch selects one accepted partition batch, matching the
// Python _select_partition_batch function. It scans pending intents, filters
// by partition, checks authoritative generation state, and deduplicates to
// latest per repo/partition pair.
func SelectPartitionBatch(
	ctx context.Context,
	reader SharedIntentReader,
	domain string,
	partitionID, partitionCount int,
	batchLimit int,
	acceptedGen AcceptedGenerationLookup,
) (PartitionBatchResult, error) {
	if batchLimit < 1 {
		batchLimit = 1
	}

	scanLimit := batchLimit * max(partitionCount, 1) * 2

	for {
		if err := ctx.Err(); err != nil {
			return PartitionBatchResult{}, err
		}

		pending, err := reader.ListPendingDomainIntents(ctx, domain, scanLimit)
		if err != nil {
			return PartitionBatchResult{}, fmt.Errorf("list pending intents: %w", err)
		}

		partitionRows := RowsForPartition(pending, partitionID, partitionCount)
		if len(partitionRows) == 0 {
			return PartitionBatchResult{}, nil
		}

		active, staleIDs := FilterAuthoritativeIntents(partitionRows, acceptedGen)
		latest, supersededIDs := LatestIntentsByRepoAndPartition(active)

		if len(latest) >= batchLimit || len(pending) < scanLimit {
			if len(latest) > batchLimit {
				latest = latest[:batchLimit]
			}
			return PartitionBatchResult{
				LatestRows:    latest,
				StaleIDs:      staleIDs,
				SupersededIDs: supersededIDs,
			}, nil
		}

		scanLimit *= 2
	}
}

// ProcessPartitionOnce processes one partition cycle: claim lease, select
// batch, retract/write edges, mark completed, release lease. Matches the
// Python process_platform_partition_once and process_dependency_partition_once
// functions.
func ProcessPartitionOnce(
	ctx context.Context,
	now time.Time,
	cfg PartitionProcessorConfig,
	leaseManager PartitionLeaseManager,
	reader SharedIntentReader,
	edgeWriter SharedProjectionEdgeWriter,
	acceptedGen AcceptedGenerationLookup,
) (PartitionProcessResult, error) {
	claimed, err := leaseManager.ClaimPartitionLease(
		ctx, cfg.Domain, cfg.PartitionID, cfg.PartitionCount,
		cfg.LeaseOwner, cfg.LeaseTTL,
	)
	if err != nil {
		return PartitionProcessResult{}, fmt.Errorf("claim lease: %w", err)
	}
	if !claimed {
		return PartitionProcessResult{LeaseAcquired: false}, nil
	}

	defer func() {
		_ = leaseManager.ReleasePartitionLease(
			ctx, cfg.Domain, cfg.PartitionID, cfg.PartitionCount, cfg.LeaseOwner,
		)
	}()

	batchLimit := cfg.BatchLimit
	if batchLimit < 1 {
		batchLimit = 100
	}

	batch, err := SelectPartitionBatch(
		ctx, reader, cfg.Domain,
		cfg.PartitionID, cfg.PartitionCount,
		batchLimit, acceptedGen,
	)
	if err != nil {
		return PartitionProcessResult{LeaseAcquired: true}, fmt.Errorf("select batch: %w", err)
	}

	if len(batch.LatestRows) == 0 && len(batch.StaleIDs) == 0 && len(batch.SupersededIDs) == 0 {
		return PartitionProcessResult{LeaseAcquired: true}, nil
	}

	evidenceSource := cfg.EvidenceSource
	if evidenceSource == "" {
		evidenceSource = "finalization/workloads"
	}

	if err := edgeWriter.RetractEdges(ctx, cfg.Domain, batch.LatestRows, evidenceSource); err != nil {
		return PartitionProcessResult{LeaseAcquired: true}, fmt.Errorf("retract edges: %w", err)
	}

	upsertRows := filterUpsertRows(batch.LatestRows)
	if err := edgeWriter.WriteEdges(ctx, cfg.Domain, upsertRows, evidenceSource); err != nil {
		return PartitionProcessResult{LeaseAcquired: true}, fmt.Errorf("write edges: %w", err)
	}

	var processedIDs []string
	processedIDs = append(processedIDs, batch.StaleIDs...)
	processedIDs = append(processedIDs, batch.SupersededIDs...)
	for _, row := range batch.LatestRows {
		processedIDs = append(processedIDs, row.IntentID)
	}

	if len(processedIDs) > 0 {
		if err := reader.MarkIntentsCompleted(ctx, processedIDs, now); err != nil {
			return PartitionProcessResult{LeaseAcquired: true}, fmt.Errorf("mark completed: %w", err)
		}
	}

	return PartitionProcessResult{
		LeaseAcquired:    true,
		ProcessedIntents: len(processedIDs),
		UpsertedRows:     len(upsertRows),
		RetractedRows:    len(batch.LatestRows),
	}, nil
}

// filterUpsertRows returns rows whose payload action is "upsert" or absent.
func filterUpsertRows(rows []SharedProjectionIntentRow) []SharedProjectionIntentRow {
	var result []SharedProjectionIntentRow
	for _, row := range rows {
		action, ok := row.Payload["action"]
		if ok {
			if s, isStr := action.(string); isStr && s != "upsert" {
				continue
			}
		}
		result = append(result, row)
	}
	return result
}
