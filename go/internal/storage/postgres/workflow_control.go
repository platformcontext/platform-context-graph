package postgres

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/scope"
	"github.com/platformcontext/platform-context-graph/go/internal/workflow"
)

const (
	workflowEnqueueBatchSize                = 250
	workflowColumnsPerWorkItem              = 20
	DefaultWorkflowClaimLeaseTTL            = 60 * time.Second
	DefaultWorkflowClaimHeartbeatInterval   = 20 * time.Second
	DefaultWorkflowExpiredClaimRequeueDelay = 5 * time.Second
)

// ErrWorkflowClaimRejected reports that a fenced claim mutation was rejected.
var ErrWorkflowClaimRejected = errors.New("workflow claim rejected")

const workflowControlSchemaSQL = `
CREATE TABLE IF NOT EXISTS workflow_runs (
    run_id TEXT PRIMARY KEY,
    trigger_kind TEXT NOT NULL,
    status TEXT NOT NULL,
    requested_scope_set JSONB NOT NULL DEFAULT '[]'::jsonb,
    requested_collector TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ NULL
);
CREATE INDEX IF NOT EXISTS workflow_runs_status_updated_idx
    ON workflow_runs (status, updated_at DESC);

CREATE TABLE IF NOT EXISTS workflow_work_items (
    work_item_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES workflow_runs(run_id) ON DELETE CASCADE,
    collector_kind TEXT NOT NULL,
    collector_instance_id TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    generation_id TEXT NULL,
    fairness_key TEXT NULL,
    status TEXT NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    current_claim_id TEXT NULL,
    current_fencing_token BIGINT NOT NULL DEFAULT 0,
    current_owner_id TEXT NULL,
    lease_expires_at TIMESTAMPTZ NULL,
    visible_at TIMESTAMPTZ NULL,
    last_claimed_at TIMESTAMPTZ NULL,
    last_completed_at TIMESTAMPTZ NULL,
    last_failure_class TEXT NULL,
    last_failure_message TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS workflow_work_items_claimable_idx
    ON workflow_work_items (
        collector_kind,
        collector_instance_id,
        status,
        visible_at,
        updated_at DESC
    );
CREATE INDEX IF NOT EXISTS workflow_work_items_lease_idx
    ON workflow_work_items (lease_expires_at)
    WHERE lease_expires_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS workflow_work_items_run_idx
    ON workflow_work_items (run_id, status, updated_at DESC);

CREATE TABLE IF NOT EXISTS workflow_claims (
    claim_id TEXT PRIMARY KEY,
    work_item_id TEXT NOT NULL REFERENCES workflow_work_items(work_item_id) ON DELETE CASCADE,
    fencing_token BIGINT NOT NULL,
    owner_id TEXT NOT NULL,
    status TEXT NOT NULL,
    claimed_at TIMESTAMPTZ NOT NULL,
    heartbeat_at TIMESTAMPTZ NOT NULL,
    lease_expires_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ NULL,
    failure_class TEXT NULL,
    failure_message TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    UNIQUE (work_item_id, fencing_token)
);
CREATE INDEX IF NOT EXISTS workflow_claims_active_expiry_idx
    ON workflow_claims (status, lease_expires_at ASC);
CREATE INDEX IF NOT EXISTS workflow_claims_work_item_idx
    ON workflow_claims (work_item_id, updated_at DESC);
`

const createWorkflowRunQuery = `
INSERT INTO workflow_runs (
    run_id,
    trigger_kind,
    status,
    requested_scope_set,
    requested_collector,
    created_at,
    updated_at,
    finished_at
) VALUES ($1, $2, $3, $4::jsonb, NULLIF($5, ''), $6, $7, NULLIF($8, '')::timestamptz)
ON CONFLICT (run_id) DO UPDATE
SET trigger_kind = EXCLUDED.trigger_kind,
    status = EXCLUDED.status,
    requested_scope_set = EXCLUDED.requested_scope_set,
    requested_collector = EXCLUDED.requested_collector,
    updated_at = EXCLUDED.updated_at,
    finished_at = EXCLUDED.finished_at
`

const enqueueWorkflowWorkItemsPrefix = `
INSERT INTO workflow_work_items (
    work_item_id,
    run_id,
    collector_kind,
    collector_instance_id,
    scope_id,
    generation_id,
    fairness_key,
    status,
    attempt_count,
    current_claim_id,
    current_fencing_token,
    current_owner_id,
    lease_expires_at,
    visible_at,
    last_claimed_at,
    last_completed_at,
    last_failure_class,
    last_failure_message,
    created_at,
    updated_at
) VALUES `

const enqueueWorkflowWorkItemsSuffix = `
ON CONFLICT (work_item_id) DO NOTHING
`

// TODO(phase-2-fairness): This selector is intentionally FIFO within one
// collector family. Multi-family fairness must move into an explicit scheduler
// before this ORDER BY changes, otherwise family starvation can regress
// silently under the wrong claim model.
const claimNextWorkflowWorkItemQuery = `
WITH candidate AS (
    SELECT work_item_id
    FROM workflow_work_items
    WHERE collector_kind = $1
      AND collector_instance_id = $2
      AND status = 'pending'
      AND (visible_at IS NULL OR visible_at <= $3)
    ORDER BY COALESCE(visible_at, created_at), created_at, work_item_id
    LIMIT 1
    FOR UPDATE SKIP LOCKED
),
claimed_item AS (
    UPDATE workflow_work_items AS item
    SET status = 'claimed',
        attempt_count = item.attempt_count + 1,
        current_claim_id = $5,
        current_fencing_token = item.current_fencing_token + 1,
        current_owner_id = $4,
        lease_expires_at = $6,
        last_claimed_at = $3,
        updated_at = $3
    FROM candidate
    WHERE item.work_item_id = candidate.work_item_id
    RETURNING
        item.work_item_id,
        item.run_id,
        item.collector_kind,
        item.collector_instance_id,
        item.scope_id,
        COALESCE(item.generation_id, '') AS generation_id,
        COALESCE(item.fairness_key, '') AS fairness_key,
        item.status,
        item.attempt_count,
        COALESCE(item.current_claim_id, '') AS current_claim_id,
        item.current_fencing_token,
        COALESCE(item.current_owner_id, '') AS current_owner_id,
        item.lease_expires_at,
        item.created_at,
        item.updated_at
),
inserted_claim AS (
    INSERT INTO workflow_claims (
        claim_id,
        work_item_id,
        fencing_token,
        owner_id,
        status,
        claimed_at,
        heartbeat_at,
        lease_expires_at,
        created_at,
        updated_at
    )
    SELECT
        $5,
        work_item_id,
        current_fencing_token,
        $4,
        'active',
        $3,
        $3,
        $6,
        $3,
        $3
    FROM claimed_item
    RETURNING
        work_item_id,
        claim_id,
        fencing_token,
        owner_id,
        status,
        claimed_at,
        heartbeat_at,
        lease_expires_at,
        created_at,
        updated_at
)
SELECT
    claimed_item.work_item_id,
    claimed_item.run_id,
    claimed_item.collector_kind,
    claimed_item.collector_instance_id,
    claimed_item.scope_id,
    claimed_item.generation_id,
    claimed_item.fairness_key,
    claimed_item.status,
    claimed_item.attempt_count,
    claimed_item.current_claim_id,
    claimed_item.current_fencing_token,
    claimed_item.current_owner_id,
    claimed_item.lease_expires_at,
    claimed_item.created_at,
    claimed_item.updated_at,
    inserted_claim.claim_id,
    inserted_claim.fencing_token,
    inserted_claim.owner_id,
    inserted_claim.status,
    inserted_claim.claimed_at,
    inserted_claim.heartbeat_at,
    inserted_claim.lease_expires_at,
    inserted_claim.created_at,
    inserted_claim.updated_at
FROM claimed_item
JOIN inserted_claim ON inserted_claim.work_item_id = claimed_item.work_item_id
`

const heartbeatWorkflowClaimQuery = `
WITH candidate AS (
    SELECT item.work_item_id
    FROM workflow_work_items AS item
    JOIN workflow_claims AS claim
      ON claim.claim_id = $5
     AND claim.work_item_id = item.work_item_id
    WHERE item.work_item_id = $6
      AND item.current_claim_id = $5
      AND item.current_fencing_token = $3
      AND item.current_owner_id = $4
      AND item.status = 'claimed'
      AND claim.fencing_token = $3
      AND claim.owner_id = $4
      AND claim.status = 'active'
    FOR UPDATE OF item, claim
),
updated_claim AS (
    UPDATE workflow_claims AS claim
    SET heartbeat_at = $1,
        lease_expires_at = $2,
        updated_at = $1
    FROM candidate
    WHERE claim.claim_id = $5
      AND claim.work_item_id = candidate.work_item_id
    RETURNING claim.claim_id
)
UPDATE workflow_work_items AS item
SET lease_expires_at = $2,
    updated_at = $1
FROM candidate
WHERE item.work_item_id = candidate.work_item_id
  AND EXISTS (SELECT 1 FROM updated_claim)
`

const completeWorkflowClaimQuery = `
WITH candidate AS (
    SELECT item.work_item_id
    FROM workflow_work_items AS item
    JOIN workflow_claims AS claim
      ON claim.claim_id = $5
     AND claim.work_item_id = item.work_item_id
    WHERE item.work_item_id = $6
      AND item.current_claim_id = $5
      AND item.current_fencing_token = $3
      AND item.current_owner_id = $4
      AND item.status = 'claimed'
      AND claim.fencing_token = $3
      AND claim.owner_id = $4
      AND claim.status = 'active'
    FOR UPDATE OF item, claim
),
updated_claim AS (
    UPDATE workflow_claims AS claim
    SET status = 'completed',
        finished_at = $1,
        updated_at = $1
    FROM candidate
    WHERE claim.claim_id = $5
      AND claim.work_item_id = candidate.work_item_id
    RETURNING claim.claim_id
)
UPDATE workflow_work_items AS item
SET status = 'completed',
    current_claim_id = NULL,
    current_owner_id = NULL,
    lease_expires_at = $2,
    last_completed_at = $1,
    updated_at = $1,
    last_failure_class = NULL,
    last_failure_message = NULL
FROM candidate
WHERE item.work_item_id = candidate.work_item_id
  AND EXISTS (SELECT 1 FROM updated_claim)
`

const failWorkflowClaimRetryableQuery = `
WITH candidate AS (
    SELECT item.work_item_id
    FROM workflow_work_items AS item
    JOIN workflow_claims AS claim
      ON claim.claim_id = $5
     AND claim.work_item_id = item.work_item_id
    WHERE item.work_item_id = $6
      AND item.current_claim_id = $5
      AND item.current_fencing_token = $3
      AND item.current_owner_id = $4
      AND item.status = 'claimed'
      AND claim.fencing_token = $3
      AND claim.owner_id = $4
      AND claim.status = 'active'
    FOR UPDATE OF item, claim
),
updated_claim AS (
    UPDATE workflow_claims AS claim
    SET status = 'failed_retryable',
        finished_at = $1,
        failure_class = NULLIF($7, ''),
        failure_message = NULLIF($8, ''),
        updated_at = $1
    FROM candidate
    WHERE claim.claim_id = $5
      AND claim.work_item_id = candidate.work_item_id
    RETURNING claim.claim_id
)
UPDATE workflow_work_items AS item
SET status = 'pending',
    current_claim_id = NULL,
    current_owner_id = NULL,
    lease_expires_at = NULL,
    visible_at = $2,
    updated_at = $1,
    last_failure_class = NULLIF($7, ''),
    last_failure_message = NULLIF($8, '')
FROM candidate
WHERE item.work_item_id = candidate.work_item_id
  AND EXISTS (SELECT 1 FROM updated_claim)
`

const failWorkflowClaimTerminalQuery = `
WITH candidate AS (
    SELECT item.work_item_id
    FROM workflow_work_items AS item
    JOIN workflow_claims AS claim
      ON claim.claim_id = $5
     AND claim.work_item_id = item.work_item_id
    WHERE item.work_item_id = $6
      AND item.current_claim_id = $5
      AND item.current_fencing_token = $3
      AND item.current_owner_id = $4
      AND item.status = 'claimed'
      AND claim.fencing_token = $3
      AND claim.owner_id = $4
      AND claim.status = 'active'
    FOR UPDATE OF item, claim
),
updated_claim AS (
    UPDATE workflow_claims AS claim
    SET status = 'failed_terminal',
        finished_at = $1,
        failure_class = NULLIF($7, ''),
        failure_message = NULLIF($8, ''),
        updated_at = $1
    FROM candidate
    WHERE claim.claim_id = $5
      AND claim.work_item_id = candidate.work_item_id
    RETURNING claim.claim_id
)
UPDATE workflow_work_items AS item
SET status = 'failed_terminal',
    current_claim_id = NULL,
    current_owner_id = NULL,
    lease_expires_at = NULL,
    updated_at = $1,
    last_failure_class = NULLIF($7, ''),
    last_failure_message = NULLIF($8, '')
FROM candidate
WHERE item.work_item_id = candidate.work_item_id
  AND EXISTS (SELECT 1 FROM updated_claim)
`

const reapExpiredWorkflowClaimsQuery = `
WITH candidate AS (
    SELECT
        claim.claim_id,
        claim.work_item_id,
        claim.fencing_token,
        claim.owner_id,
        claim.claimed_at,
        claim.heartbeat_at,
        claim.lease_expires_at,
        claim.created_at
    FROM workflow_claims AS claim
    JOIN workflow_work_items AS item
      ON item.work_item_id = claim.work_item_id
    WHERE claim.status = 'active'
      AND claim.lease_expires_at < $1
      AND item.current_claim_id = claim.claim_id
      AND item.current_fencing_token = claim.fencing_token
      AND item.current_owner_id = claim.owner_id
      AND item.status = 'claimed'
    ORDER BY claim.lease_expires_at ASC, claim.claim_id ASC
    LIMIT $2
    FOR UPDATE OF claim, item SKIP LOCKED
),
updated_claim AS (
    UPDATE workflow_claims AS claim
    SET status = 'expired',
        finished_at = $1,
        updated_at = $1
    FROM candidate
    WHERE claim.claim_id = candidate.claim_id
    RETURNING
        candidate.claim_id,
        candidate.work_item_id,
        candidate.fencing_token,
        candidate.owner_id,
        'expired' AS status,
        candidate.claimed_at,
        candidate.heartbeat_at,
        candidate.lease_expires_at,
        candidate.created_at,
        $1 AS updated_at
)
,
updated_item AS (
UPDATE workflow_work_items AS item
SET status = 'pending',
    current_claim_id = NULL,
    current_owner_id = NULL,
    lease_expires_at = NULL,
    visible_at = $3,
    updated_at = $1
FROM candidate
WHERE item.work_item_id = candidate.work_item_id
  AND item.current_claim_id = candidate.claim_id
  AND item.current_fencing_token = candidate.fencing_token
  AND item.current_owner_id = candidate.owner_id
  AND item.status = 'claimed'
RETURNING item.work_item_id
)
SELECT
    updated_claim.claim_id,
    updated_claim.work_item_id,
    updated_claim.fencing_token,
    updated_claim.owner_id,
    updated_claim.status,
    updated_claim.claimed_at,
    updated_claim.heartbeat_at,
    updated_claim.lease_expires_at,
    updated_claim.created_at,
    updated_claim.updated_at
FROM updated_claim
JOIN updated_item ON updated_item.work_item_id = updated_claim.work_item_id
`

// ClaimSelector aliases the workflow package selector at the storage boundary.
type ClaimSelector = workflow.ClaimSelector

// ClaimMutation aliases the workflow package mutation shape at the storage boundary.
type ClaimMutation = workflow.ClaimMutation

// WorkflowControlStore persists workflow coordinator control-plane state.
type WorkflowControlStore struct {
	db                         ExecQueryer
	beginner                   Beginner
	DefaultClaimLeaseTTL       time.Duration
	DefaultHeartbeatInterval   time.Duration
	DefaultExpiredRequeueDelay time.Duration
}

// NewWorkflowControlStore constructs a Postgres-backed workflow control store.
func NewWorkflowControlStore(db ExecQueryer) *WorkflowControlStore {
	beginner, _ := db.(Beginner)
	return &WorkflowControlStore{
		db:                         db,
		beginner:                   beginner,
		DefaultClaimLeaseTTL:       DefaultWorkflowClaimLeaseTTL,
		DefaultHeartbeatInterval:   DefaultWorkflowClaimHeartbeatInterval,
		DefaultExpiredRequeueDelay: DefaultWorkflowExpiredClaimRequeueDelay,
	}
}

// WorkflowControlSchemaSQL returns the DDL for the workflow control plane.
func WorkflowControlSchemaSQL() string {
	return workflowControlSchemaSQL
}

// EnsureSchema applies the workflow control-plane schema DDL.
func (s *WorkflowControlStore) EnsureSchema(ctx context.Context) error {
	if s.db == nil {
		return fmt.Errorf("workflow control store database is required")
	}
	_, err := s.db.ExecContext(ctx, workflowControlSchemaSQL)
	if err != nil {
		return fmt.Errorf("ensure workflow control schema: %w", err)
	}
	_, err = s.db.ExecContext(ctx, workflowCoordinatorStateSchemaSQL)
	if err != nil {
		return fmt.Errorf("ensure workflow coordinator state schema: %w", err)
	}
	return nil
}

// CreateRun upserts one durable workflow run.
func (s *WorkflowControlStore) CreateRun(ctx context.Context, run workflow.Run) error {
	if s.db == nil {
		return fmt.Errorf("workflow control store database is required")
	}
	if err := run.Validate(); err != nil {
		return fmt.Errorf("create workflow run: %w", err)
	}
	finishedAt := nullableRFC3339(run.FinishedAt)
	_, err := s.db.ExecContext(
		ctx,
		createWorkflowRunQuery,
		run.RunID,
		string(run.TriggerKind),
		string(run.Status),
		normalizeRequestedScopeSet(run.RequestedScopeSet),
		run.RequestedCollector,
		run.CreatedAt.UTC(),
		run.UpdatedAt.UTC(),
		finishedAt,
	)
	if err != nil {
		return fmt.Errorf("create workflow run: %w", err)
	}
	return nil
}

// EnqueueWorkItems inserts workflow work items in batches.
func (s *WorkflowControlStore) EnqueueWorkItems(ctx context.Context, items []workflow.WorkItem) error {
	if s.db == nil {
		return fmt.Errorf("workflow control store database is required")
	}
	if len(items) == 0 {
		return nil
	}

	for _, item := range items {
		if err := item.Validate(); err != nil {
			return fmt.Errorf("enqueue workflow work items: %w", err)
		}
	}

	for i := 0; i < len(items); i += workflowEnqueueBatchSize {
		end := i + workflowEnqueueBatchSize
		if end > len(items) {
			end = len(items)
		}
		if err := s.enqueueWorkItemBatch(ctx, items[i:end]); err != nil {
			return err
		}
	}

	return nil
}

// ClaimNextEligible claims the next bounded work item for one collector actor.
func (s *WorkflowControlStore) ClaimNextEligible(
	ctx context.Context,
	selector workflow.ClaimSelector,
	now time.Time,
	leaseDuration time.Duration,
) (workflow.WorkItem, workflow.Claim, bool, error) {
	if s.db == nil {
		return workflow.WorkItem{}, workflow.Claim{}, false, fmt.Errorf("workflow control store database is required")
	}
	if err := validateClaimSelector(selector); err != nil {
		return workflow.WorkItem{}, workflow.Claim{}, false, err
	}
	effectiveLeaseTTL, err := s.effectiveClaimLeaseTTL(leaseDuration)
	if err != nil {
		return workflow.WorkItem{}, workflow.Claim{}, false, err
	}

	rows, err := s.db.QueryContext(
		ctx,
		claimNextWorkflowWorkItemQuery,
		string(selector.CollectorKind),
		selector.CollectorInstanceID,
		now.UTC(),
		selector.OwnerID,
		selector.ClaimID,
		now.UTC().Add(effectiveLeaseTTL),
	)
	if err != nil {
		return workflow.WorkItem{}, workflow.Claim{}, false, fmt.Errorf("claim workflow work item: %w", err)
	}
	defer func() { _ = rows.Close() }()

	if !rows.Next() {
		if err := rows.Err(); err != nil {
			return workflow.WorkItem{}, workflow.Claim{}, false, fmt.Errorf("claim workflow work item: %w", err)
		}
		return workflow.WorkItem{}, workflow.Claim{}, false, nil
	}

	item, claim, err := scanClaimedWorkflowWorkItem(rows)
	if err != nil {
		return workflow.WorkItem{}, workflow.Claim{}, false, fmt.Errorf("claim workflow work item: %w", err)
	}
	if err := rows.Err(); err != nil {
		return workflow.WorkItem{}, workflow.Claim{}, false, fmt.Errorf("claim workflow work item: %w", err)
	}

	return item, claim, true, nil
}

// HeartbeatClaim extends the active ownership epoch.
func (s *WorkflowControlStore) HeartbeatClaim(ctx context.Context, mutation workflow.ClaimMutation) error {
	effectiveLeaseTTL, err := s.effectiveClaimLeaseTTL(mutation.LeaseDuration)
	if err != nil {
		return err
	}
	return s.execClaimMutation(ctx, mutation, heartbeatWorkflowClaimQuery, mutation.ObservedAt.UTC().Add(effectiveLeaseTTL))
}

// CompleteClaim marks the active ownership epoch and work item complete.
func (s *WorkflowControlStore) CompleteClaim(ctx context.Context, mutation workflow.ClaimMutation) error {
	return s.execClaimMutation(ctx, mutation, completeWorkflowClaimQuery, time.Time{})
}

// FailClaimRetryable marks the current epoch retryable and requeues the work item.
func (s *WorkflowControlStore) FailClaimRetryable(ctx context.Context, mutation workflow.ClaimMutation) error {
	if mutation.VisibleAt.IsZero() {
		mutation.VisibleAt = mutation.ObservedAt
	}
	return s.execTerminalClaimMutation(ctx, mutation, failWorkflowClaimRetryableQuery)
}

// FailClaimTerminal marks the current epoch terminal without requeueing.
func (s *WorkflowControlStore) FailClaimTerminal(ctx context.Context, mutation workflow.ClaimMutation) error {
	return s.execTerminalClaimMutation(ctx, mutation, failWorkflowClaimTerminalQuery)
}

// ReapExpiredClaims expires stale active claims atomically and requeues their work.
func (s *WorkflowControlStore) ReapExpiredClaims(
	ctx context.Context,
	asOf time.Time,
	limit int,
	requeueDelay time.Duration,
) ([]workflow.Claim, error) {
	if s.db == nil {
		return nil, fmt.Errorf("workflow control store database is required")
	}
	if limit <= 0 {
		return nil, fmt.Errorf("expired claim limit must be positive")
	}
	effectiveRequeueDelay := s.effectiveExpiredRequeueDelay(requeueDelay)
	rows, err := s.db.QueryContext(ctx, reapExpiredWorkflowClaimsQuery, asOf.UTC(), limit, asOf.UTC().Add(effectiveRequeueDelay))
	if err != nil {
		return nil, fmt.Errorf("reap expired workflow claims: %w", err)
	}
	defer func() { _ = rows.Close() }()

	claims := make([]workflow.Claim, 0)
	for rows.Next() {
		claim, err := scanWorkflowClaim(rows)
		if err != nil {
			return nil, fmt.Errorf("reap expired workflow claims: %w", err)
		}
		claims = append(claims, claim)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("reap expired workflow claims: %w", err)
	}
	return claims, nil
}

func (s *WorkflowControlStore) enqueueWorkItemBatch(ctx context.Context, items []workflow.WorkItem) error {
	args := make([]any, 0, len(items)*workflowColumnsPerWorkItem)
	var values strings.Builder

	for i, item := range items {
		if i > 0 {
			values.WriteString(", ")
		}
		offset := i * workflowColumnsPerWorkItem
		fmt.Fprintf(
			&values,
			"($%d, $%d, $%d, $%d, $%d, NULLIF($%d, ''), NULLIF($%d, ''), $%d, $%d, NULLIF($%d, ''), $%d, NULLIF($%d, ''), NULLIF($%d, '')::timestamptz, NULLIF($%d, '')::timestamptz, NULLIF($%d, '')::timestamptz, NULLIF($%d, '')::timestamptz, NULLIF($%d, ''), NULLIF($%d, ''), $%d, $%d)",
			offset+1, offset+2, offset+3, offset+4, offset+5, offset+6, offset+7, offset+8,
			offset+9, offset+10, offset+11, offset+12, offset+13, offset+14, offset+15,
			offset+16, offset+17, offset+18, offset+19, offset+20,
		)
		args = append(args,
			item.WorkItemID,
			item.RunID,
			string(item.CollectorKind),
			item.CollectorInstanceID,
			item.ScopeID,
			item.GenerationID,
			item.FairnessKey,
			string(item.Status),
			item.AttemptCount,
			item.CurrentClaimID,
			item.CurrentFencingToken,
			item.CurrentOwnerID,
			nullableRFC3339(item.LeaseExpiresAt),
			nullableRFC3339(item.VisibleAt),
			nullableRFC3339(item.LastClaimedAt),
			nullableRFC3339(item.LastCompletedAt),
			item.LastFailureClass,
			item.LastFailureMessage,
			item.CreatedAt.UTC(),
			item.UpdatedAt.UTC(),
		)
	}

	query := enqueueWorkflowWorkItemsPrefix + values.String() + enqueueWorkflowWorkItemsSuffix
	if _, err := s.db.ExecContext(ctx, query, args...); err != nil {
		return fmt.Errorf("enqueue workflow work item batch (%d items): %w", len(items), err)
	}
	return nil
}

func (s *WorkflowControlStore) execClaimMutation(
	ctx context.Context,
	mutation workflow.ClaimMutation,
	query string,
	leaseExpiresAt time.Time,
) error {
	if s.db == nil {
		return fmt.Errorf("workflow control store database is required")
	}
	if err := validateClaimMutation(mutation); err != nil {
		return err
	}

	args := []any{
		mutation.ObservedAt.UTC(),
		nullableTime(leaseExpiresAt),
		mutation.FencingToken,
		mutation.OwnerID,
		mutation.ClaimID,
		mutation.WorkItemID,
	}
	if strings.Contains(query, "$7") {
		args = append(args, mutation.FailureClass, mutation.FailureMessage)
	}

	result, err := s.db.ExecContext(ctx, query, args...)
	if err != nil {
		return fmt.Errorf("mutate workflow claim: %w", err)
	}
	return validateMutationResult(result)
}

func (s *WorkflowControlStore) execTerminalClaimMutation(
	ctx context.Context,
	mutation workflow.ClaimMutation,
	query string,
) error {
	if mutation.VisibleAt.IsZero() {
		mutation.VisibleAt = mutation.ObservedAt
	}
	if s.db == nil {
		return fmt.Errorf("workflow control store database is required")
	}
	if err := validateClaimMutation(mutation); err != nil {
		return err
	}
	args := []any{
		mutation.ObservedAt.UTC(),
		mutation.VisibleAt.UTC(),
		mutation.FencingToken,
		mutation.OwnerID,
		mutation.ClaimID,
		mutation.WorkItemID,
		mutation.FailureClass,
		mutation.FailureMessage,
	}
	result, err := s.db.ExecContext(ctx, query, args...)
	if err != nil {
		return fmt.Errorf("mutate terminal workflow claim: %w", err)
	}
	return validateMutationResult(result)
}

func scanClaimedWorkflowWorkItem(rows Rows) (workflow.WorkItem, workflow.Claim, error) {
	var item workflow.WorkItem
	var claim workflow.Claim
	var collectorKind string
	var generationID string
	var fairnessKey string
	var itemStatus string
	var claimID string
	var currentFencing sql.NullInt64
	var currentOwner string
	var claimFence sql.NullInt64
	var claimStatus string

	if err := rows.Scan(
		&item.WorkItemID,
		&item.RunID,
		&collectorKind,
		&item.CollectorInstanceID,
		&item.ScopeID,
		&generationID,
		&fairnessKey,
		&itemStatus,
		&item.AttemptCount,
		&claimID,
		&currentFencing,
		&currentOwner,
		&item.LeaseExpiresAt,
		&item.CreatedAt,
		&item.UpdatedAt,
		&claim.ClaimID,
		&claimFence,
		&claim.OwnerID,
		&claimStatus,
		&claim.ClaimedAt,
		&claim.HeartbeatAt,
		&claim.LeaseExpiresAt,
		&claim.CreatedAt,
		&claim.UpdatedAt,
	); err != nil {
		return workflow.WorkItem{}, workflow.Claim{}, err
	}

	item.GenerationID = strings.TrimSpace(generationID)
	item.FairnessKey = strings.TrimSpace(fairnessKey)
	item.CollectorKind = scope.CollectorKind(strings.TrimSpace(collectorKind))
	item.Status = workflow.WorkItemStatus(strings.TrimSpace(itemStatus))
	item.CurrentClaimID = strings.TrimSpace(claimID)
	item.CurrentFencingToken = currentFencing.Int64
	item.CurrentOwnerID = strings.TrimSpace(currentOwner)
	item.LastClaimedAt = claim.ClaimedAt

	claim.WorkItemID = item.WorkItemID
	claim.FencingToken = claimFence.Int64
	claim.Status = workflow.ClaimStatus(strings.TrimSpace(claimStatus))

	return item, claim, nil
}

func scanWorkflowClaim(rows Rows) (workflow.Claim, error) {
	var claim workflow.Claim
	var status string
	var fence sql.NullInt64
	if err := rows.Scan(
		&claim.ClaimID,
		&claim.WorkItemID,
		&fence,
		&claim.OwnerID,
		&status,
		&claim.ClaimedAt,
		&claim.HeartbeatAt,
		&claim.LeaseExpiresAt,
		&claim.CreatedAt,
		&claim.UpdatedAt,
	); err != nil {
		return workflow.Claim{}, err
	}
	claim.FencingToken = fence.Int64
	claim.Status = workflow.ClaimStatus(status)
	return claim, nil
}

func validateClaimSelector(selector workflow.ClaimSelector) error {
	if strings.TrimSpace(string(selector.CollectorKind)) == "" {
		return fmt.Errorf("collector kind is required")
	}
	if strings.TrimSpace(selector.CollectorInstanceID) == "" {
		return fmt.Errorf("collector instance id is required")
	}
	if strings.TrimSpace(selector.OwnerID) == "" {
		return fmt.Errorf("owner id is required")
	}
	if strings.TrimSpace(selector.ClaimID) == "" {
		return fmt.Errorf("claim id is required")
	}
	return nil
}

func validateClaimMutation(mutation workflow.ClaimMutation) error {
	if strings.TrimSpace(mutation.WorkItemID) == "" {
		return fmt.Errorf("work item id is required")
	}
	if strings.TrimSpace(mutation.ClaimID) == "" {
		return fmt.Errorf("claim id is required")
	}
	if mutation.FencingToken <= 0 {
		return fmt.Errorf("fencing token must be positive")
	}
	if strings.TrimSpace(mutation.OwnerID) == "" {
		return fmt.Errorf("owner id is required")
	}
	if mutation.ObservedAt.IsZero() {
		return fmt.Errorf("observed at is required")
	}
	return nil
}

func normalizeRequestedScopeSet(raw string) string {
	if strings.TrimSpace(raw) == "" {
		return "[]"
	}
	return raw
}

func (s *WorkflowControlStore) effectiveClaimLeaseTTL(provided time.Duration) (time.Duration, error) {
	ttl := provided
	if ttl <= 0 {
		ttl = s.DefaultClaimLeaseTTL
	}
	if ttl <= 0 {
		return 0, fmt.Errorf("claim lease duration must be positive")
	}
	if s.DefaultHeartbeatInterval <= 0 {
		return 0, fmt.Errorf("heartbeat interval must be positive")
	}
	if s.DefaultHeartbeatInterval >= ttl {
		return 0, fmt.Errorf("heartbeat interval must be less than claim lease duration")
	}
	return ttl, nil
}

func (s *WorkflowControlStore) effectiveExpiredRequeueDelay(provided time.Duration) time.Duration {
	if provided > 0 {
		return provided
	}
	if s.DefaultExpiredRequeueDelay > 0 {
		return s.DefaultExpiredRequeueDelay
	}
	return DefaultWorkflowExpiredClaimRequeueDelay
}

func validateMutationResult(result sql.Result) error {
	if result == nil {
		return fmt.Errorf("workflow claim mutation result is required")
	}
	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return fmt.Errorf("read workflow claim mutation rows affected: %w", err)
	}
	if rowsAffected == 0 {
		return ErrWorkflowClaimRejected
	}
	return nil
}

func nullableRFC3339(value time.Time) string {
	if value.IsZero() {
		return ""
	}
	return value.UTC().Format(time.RFC3339)
}

func nullableTime(value time.Time) any {
	if value.IsZero() {
		return nil
	}
	return value.UTC()
}

func workflowControlBootstrapDefinition() Definition {
	return Definition{
		Name: "workflow_control_plane",
		Path: "schema/data-plane/postgres/014_workflow_control_plane.sql",
		SQL:  workflowControlSchemaSQL,
	}
}

func init() {
	bootstrapDefinitions = append(bootstrapDefinitions, workflowControlBootstrapDefinition())
}

var _ workflow.ControlStore = (*WorkflowControlStore)(nil)
