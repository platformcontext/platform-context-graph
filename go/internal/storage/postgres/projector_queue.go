package postgres

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/projector"
	"github.com/platformcontext/platform-context-graph/go/internal/scope"
)

const claimProjectorWorkQuery = `
WITH candidate AS (
    SELECT work_item_id
    FROM fact_work_items
    WHERE stage = 'projector'
      AND status IN ('pending', 'retrying')
      AND (visible_at IS NULL OR visible_at <= $1)
      AND (claim_until IS NULL OR claim_until <= $1)
    ORDER BY updated_at ASC, work_item_id ASC
    LIMIT 1
    FOR UPDATE SKIP LOCKED
),
claimed AS (
    UPDATE fact_work_items AS work
    SET status = 'claimed',
        attempt_count = work.attempt_count + 1,
        lease_owner = $2,
        claim_until = $3,
        last_attempt_at = $1,
        updated_at = $1
    FROM candidate
    WHERE work.work_item_id = candidate.work_item_id
    RETURNING work.scope_id, work.generation_id
)
SELECT
    scope.scope_id,
    scope.source_system,
    scope.scope_kind,
    COALESCE(scope.parent_scope_id, ''),
    scope.collector_kind,
    scope.partition_key,
    generation.generation_id,
    generation.observed_at,
    generation.ingested_at,
    generation.status,
    generation.trigger_kind,
    COALESCE(generation.freshness_hint, '')
FROM claimed
JOIN ingestion_scopes AS scope
  ON scope.scope_id = claimed.scope_id
JOIN scope_generations AS generation
  ON generation.generation_id = claimed.generation_id
`

const ackProjectorWorkQuery = `
UPDATE fact_work_items
SET status = 'succeeded',
    lease_owner = NULL,
    claim_until = NULL,
    visible_at = NULL,
    updated_at = $1,
    failure_class = NULL,
    failure_message = NULL,
    failure_details = NULL
WHERE stage = 'projector'
  AND scope_id = $2
  AND generation_id = $3
  AND lease_owner = $4
  AND status IN ('claimed', 'running')
`

const failProjectorWorkQuery = `
UPDATE fact_work_items
SET status = 'failed',
    lease_owner = NULL,
    claim_until = NULL,
    visible_at = NULL,
    updated_at = $1,
    failure_class = $2,
    failure_message = $3,
    failure_details = $4
WHERE stage = 'projector'
  AND scope_id = $5
  AND generation_id = $6
  AND lease_owner = $7
  AND status IN ('claimed', 'running')
`

// ProjectorQueue provides projector-stage queue claim and ack behavior.
type ProjectorQueue struct {
	db            ExecQueryer
	LeaseOwner    string
	LeaseDuration time.Duration
	Now           func() time.Time
}

// NewProjectorQueue constructs a Postgres-backed projector work queue.
func NewProjectorQueue(
	db ExecQueryer,
	leaseOwner string,
	leaseDuration time.Duration,
) ProjectorQueue {
	return ProjectorQueue{
		db:            db,
		LeaseOwner:    leaseOwner,
		LeaseDuration: leaseDuration,
	}
}

// Claim implements projector.ProjectorWorkSource over fact_work_items.
func (q ProjectorQueue) Claim(ctx context.Context) (projector.ScopeGenerationWork, bool, error) {
	if err := q.validate(); err != nil {
		return projector.ScopeGenerationWork{}, false, err
	}

	now := q.now()
	rows, err := q.db.QueryContext(ctx, claimProjectorWorkQuery, now, q.LeaseOwner, now.Add(q.LeaseDuration))
	if err != nil {
		return projector.ScopeGenerationWork{}, false, fmt.Errorf("claim projector work: %w", err)
	}
	defer rows.Close()

	if !rows.Next() {
		if err := rows.Err(); err != nil {
			return projector.ScopeGenerationWork{}, false, fmt.Errorf("claim projector work: %w", err)
		}
		return projector.ScopeGenerationWork{}, false, nil
	}

	work, err := scanProjectorWork(rows)
	if err != nil {
		return projector.ScopeGenerationWork{}, false, fmt.Errorf("claim projector work: %w", err)
	}
	if err := rows.Err(); err != nil {
		return projector.ScopeGenerationWork{}, false, fmt.Errorf("claim projector work: %w", err)
	}

	return work, true, nil
}

// Ack marks one claimed projector work item as succeeded.
func (q ProjectorQueue) Ack(
	ctx context.Context,
	work projector.ScopeGenerationWork,
	_ projector.Result,
) error {
	if err := q.validate(); err != nil {
		return err
	}

	_, err := q.db.ExecContext(
		ctx,
		ackProjectorWorkQuery,
		q.now(),
		work.Scope.ScopeID,
		work.Generation.GenerationID,
		q.LeaseOwner,
	)
	if err != nil {
		return fmt.Errorf("ack projector work: %w", err)
	}

	return nil
}

// Fail marks one claimed projector work item as failed.
func (q ProjectorQueue) Fail(
	ctx context.Context,
	work projector.ScopeGenerationWork,
	cause error,
) error {
	if err := q.validate(); err != nil {
		return err
	}

	_, err := q.db.ExecContext(
		ctx,
		failProjectorWorkQuery,
		q.now(),
		"projection_failed",
		cause.Error(),
		cause.Error(),
		work.Scope.ScopeID,
		work.Generation.GenerationID,
		q.LeaseOwner,
	)
	if err != nil {
		return fmt.Errorf("fail projector work: %w", err)
	}

	return nil
}

func (q ProjectorQueue) validate() error {
	if q.db == nil {
		return errors.New("projector queue database is required")
	}
	if q.LeaseOwner == "" {
		return errors.New("projector queue lease owner is required")
	}
	if q.LeaseDuration <= 0 {
		return errors.New("projector queue lease duration must be positive")
	}

	return nil
}

func (q ProjectorQueue) now() time.Time {
	if q.Now != nil {
		return q.Now().UTC()
	}

	return time.Now().UTC()
}

func scanProjectorWork(rows Rows) (projector.ScopeGenerationWork, error) {
	var work projector.ScopeGenerationWork
	var scopeKind string
	var collectorKind string
	var generationStatus string
	var triggerKind string

	if err := rows.Scan(
		&work.Scope.ScopeID,
		&work.Scope.SourceSystem,
		&scopeKind,
		&work.Scope.ParentScopeID,
		&collectorKind,
		&work.Scope.PartitionKey,
		&work.Generation.GenerationID,
		&work.Generation.ObservedAt,
		&work.Generation.IngestedAt,
		&generationStatus,
		&triggerKind,
		&work.Generation.FreshnessHint,
	); err != nil {
		return projector.ScopeGenerationWork{}, err
	}

	work.Scope.ScopeKind = scope.ScopeKind(scopeKind)
	work.Scope.CollectorKind = scope.CollectorKind(collectorKind)
	work.Generation.ScopeID = work.Scope.ScopeID
	work.Generation.Status = scope.GenerationStatus(generationStatus)
	work.Generation.TriggerKind = scope.TriggerKind(triggerKind)
	work.Generation.ObservedAt = work.Generation.ObservedAt.UTC()
	work.Generation.IngestedAt = work.Generation.IngestedAt.UTC()

	return work, nil
}
