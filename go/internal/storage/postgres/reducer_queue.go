package postgres

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/projector"
	"github.com/platformcontext/platform-context-graph/go/internal/reducer"
)

const enqueueReducerWorkQuery = `
INSERT INTO fact_work_items (
    work_item_id,
    scope_id,
    generation_id,
    stage,
    domain,
    status,
    attempt_count,
    lease_owner,
    claim_until,
    visible_at,
    last_attempt_at,
    next_attempt_at,
    failure_class,
    failure_message,
    failure_details,
    payload,
    created_at,
    updated_at
) VALUES (
    $1, $2, $3, 'reducer', $4, 'pending', 0, NULL, NULL, $5, NULL, NULL, NULL, NULL, NULL, $6::jsonb, $5, $5
)
ON CONFLICT (work_item_id) DO NOTHING
`

const claimReducerWorkQuery = `
WITH candidate AS (
    SELECT work_item_id
    FROM fact_work_items
    WHERE stage = 'reducer'
      AND status IN ('pending', 'retrying')
      AND (visible_at IS NULL OR visible_at <= $1)
      AND (claim_until IS NULL OR claim_until <= $1)
      AND ($2 = '' OR domain = $2)
    ORDER BY updated_at ASC, work_item_id ASC
    LIMIT 1
    FOR UPDATE SKIP LOCKED
),
claimed AS (
    UPDATE fact_work_items AS work
    SET status = 'claimed',
        attempt_count = work.attempt_count + 1,
        lease_owner = $3,
        claim_until = $4,
        last_attempt_at = $1,
        updated_at = $1
    FROM candidate
    WHERE work.work_item_id = candidate.work_item_id
    RETURNING
        work.work_item_id,
        work.scope_id,
        work.generation_id,
        work.domain,
        work.attempt_count,
        work.created_at,
        COALESCE(work.visible_at, work.created_at) AS available_at,
        work.payload
)
SELECT
    work_item_id,
    scope_id,
    generation_id,
    domain,
    attempt_count,
    created_at,
    available_at,
    payload
FROM claimed
`

const ackReducerWorkQuery = `
UPDATE fact_work_items
SET status = 'succeeded',
    lease_owner = NULL,
    claim_until = NULL,
    visible_at = NULL,
    updated_at = $1,
    failure_class = NULL,
    failure_message = NULL,
    failure_details = NULL
WHERE work_item_id = $2
  AND stage = 'reducer'
  AND lease_owner = $3
  AND status IN ('claimed', 'running')
`

const failReducerWorkQuery = `
UPDATE fact_work_items
SET status = 'failed',
    lease_owner = NULL,
    claim_until = NULL,
    visible_at = NULL,
    updated_at = $1,
    failure_class = $2,
    failure_message = $3,
    failure_details = $4
WHERE work_item_id = $5
  AND stage = 'reducer'
  AND lease_owner = $6
  AND status IN ('claimed', 'running')
`

const retryReducerWorkQuery = `
UPDATE fact_work_items
SET status = 'retrying',
    lease_owner = NULL,
    claim_until = NULL,
    visible_at = $5,
    next_attempt_at = $5,
    updated_at = $1,
    failure_class = $2,
    failure_message = $3,
    failure_details = $4
WHERE work_item_id = $6
  AND stage = 'reducer'
  AND lease_owner = $7
  AND status IN ('claimed', 'running')
`

// ReducerQueue provides reducer-stage queue behavior over fact_work_items.
type ReducerQueue struct {
	db            ExecQueryer
	LeaseOwner    string
	LeaseDuration time.Duration
	RetryDelay    time.Duration
	MaxAttempts   int
	Now           func() time.Time
}

// NewReducerQueue constructs a Postgres-backed reducer work queue.
func NewReducerQueue(
	db ExecQueryer,
	leaseOwner string,
	leaseDuration time.Duration,
) ReducerQueue {
	return ReducerQueue{
		db:            db,
		LeaseOwner:    leaseOwner,
		LeaseDuration: leaseDuration,
	}
}

// Enqueue implements projector.ReducerIntentWriter over fact_work_items.
func (q ReducerQueue) Enqueue(
	ctx context.Context,
	intents []projector.ReducerIntent,
) (projector.IntentResult, error) {
	if err := q.validate(); err != nil {
		return projector.IntentResult{}, err
	}

	now := q.now()
	count := 0
	for _, intent := range intents {
		if err := intent.Domain.Validate(); err != nil {
			return projector.IntentResult{}, fmt.Errorf("enqueue reducer intent: %w", err)
		}
		payloadJSON, err := marshalPayload(map[string]any{
			"entity_key":    intent.EntityKey,
			"reason":        intent.Reason,
			"fact_id":       intent.FactID,
			"source_system": intent.SourceSystem,
		})
		if err != nil {
			return projector.IntentResult{}, fmt.Errorf("marshal reducer payload: %w", err)
		}

		if _, err := q.db.ExecContext(
			ctx,
			enqueueReducerWorkQuery,
			reducerWorkItemID(intent),
			intent.ScopeID,
			intent.GenerationID,
			string(intent.Domain),
			now,
			payloadJSON,
		); err != nil {
			return projector.IntentResult{}, fmt.Errorf("enqueue reducer intent: %w", err)
		}
		count++
	}

	return projector.IntentResult{Count: count}, nil
}

// Claim implements reducer.WorkSource over fact_work_items.
func (q ReducerQueue) Claim(ctx context.Context) (reducer.Intent, bool, error) {
	if err := q.validate(); err != nil {
		return reducer.Intent{}, false, err
	}

	now := q.now()
	rows, err := q.db.QueryContext(
		ctx,
		claimReducerWorkQuery,
		now,
		"",
		q.LeaseOwner,
		now.Add(q.LeaseDuration),
	)
	if err != nil {
		return reducer.Intent{}, false, fmt.Errorf("claim reducer work: %w", err)
	}
	defer func() { _ = rows.Close() }()

	if !rows.Next() {
		if err := rows.Err(); err != nil {
			return reducer.Intent{}, false, fmt.Errorf("claim reducer work: %w", err)
		}
		return reducer.Intent{}, false, nil
	}

	intent, err := scanReducerIntent(rows)
	if err != nil {
		return reducer.Intent{}, false, fmt.Errorf("claim reducer work: %w", err)
	}
	if err := rows.Err(); err != nil {
		return reducer.Intent{}, false, fmt.Errorf("claim reducer work: %w", err)
	}

	return intent, true, nil
}

// Ack marks one claimed reducer work item as succeeded.
func (q ReducerQueue) Ack(ctx context.Context, intent reducer.Intent, _ reducer.Result) error {
	if err := q.validate(); err != nil {
		return err
	}

	_, err := q.db.ExecContext(ctx, ackReducerWorkQuery, q.now(), intent.IntentID, q.LeaseOwner)
	if err != nil {
		return fmt.Errorf("ack reducer work: %w", err)
	}

	return nil
}

// Fail marks one claimed reducer work item as failed.
func (q ReducerQueue) Fail(ctx context.Context, intent reducer.Intent, cause error) error {
	if err := q.validate(); err != nil {
		return err
	}
	if cause == nil {
		return errors.New("reducer failure cause is required")
	}

	if err := q.failIntent(ctx, intent, cause); err != nil {
		return err
	}

	return nil
}

func (q ReducerQueue) validate() error {
	if q.db == nil {
		return errors.New("reducer queue database is required")
	}
	if q.LeaseOwner == "" {
		return errors.New("reducer queue lease owner is required")
	}
	if q.LeaseDuration <= 0 {
		return errors.New("reducer queue lease duration must be positive")
	}

	return nil
}

func (q ReducerQueue) now() time.Time {
	if q.Now != nil {
		return q.Now().UTC()
	}

	return time.Now().UTC()
}

func (q ReducerQueue) retryDelay() time.Duration {
	if q.RetryDelay > 0 {
		return q.RetryDelay
	}

	return 30 * time.Second
}

func (q ReducerQueue) maxAttempts() int {
	if q.MaxAttempts > 0 {
		return q.MaxAttempts
	}

	return 3
}

func scanReducerIntent(rows Rows) (reducer.Intent, error) {
	var intentID string
	var scopeID string
	var generationID string
	var domain string
	var attemptCount int
	var enqueuedAt time.Time
	var availableAt time.Time
	var rawPayload []byte

	if err := rows.Scan(
		&intentID,
		&scopeID,
		&generationID,
		&domain,
		&attemptCount,
		&enqueuedAt,
		&availableAt,
		&rawPayload,
	); err != nil {
		return reducer.Intent{}, err
	}

	payload, err := unmarshalPayload(rawPayload)
	if err != nil {
		return reducer.Intent{}, err
	}

	entityKey, _ := payload["entity_key"].(string)
	reason, _ := payload["reason"].(string)
	factID, _ := payload["fact_id"].(string)
	sourceSystem, _ := payload["source_system"].(string)

	domainValue, err := reducer.ParseDomain(domain)
	if err != nil {
		return reducer.Intent{}, err
	}

	intent := reducer.Intent{
		IntentID:        intentID,
		ScopeID:         scopeID,
		GenerationID:    generationID,
		SourceSystem:    sourceSystem,
		Domain:          domainValue,
		Cause:           reason,
		AttemptCount:    attemptCount,
		EntityKeys:      nil,
		RelatedScopeIDs: []string{scopeID},
		Status:          reducer.IntentStatusClaimed,
		EnqueuedAt:      enqueuedAt.UTC(),
		AvailableAt:     availableAt.UTC(),
	}
	if entityKey != "" {
		intent.EntityKeys = []string{entityKey}
	}
	if reason == "" {
		intent.Cause = "projector emitted shared work"
	}
	if sourceSystem == "" {
		intent.SourceSystem = "unknown"
	}
	if factID != "" && len(intent.EntityKeys) == 0 {
		intent.EntityKeys = []string{factID}
	}
	if err := intent.Validate(); err != nil {
		return reducer.Intent{}, err
	}

	return intent, nil
}

func (q ReducerQueue) retryable(cause error, attemptCount int) bool {
	return reducer.IsRetryable(cause) && attemptCount < q.maxAttempts()
}

func (q ReducerQueue) failIntent(
	ctx context.Context,
	intent reducer.Intent,
	cause error,
) error {
	now := q.now()
	failureClass := "reducer_failed"
	query := failReducerWorkQuery
	args := []any{
		now,
		failureClass,
		cause.Error(),
		cause.Error(),
		intent.IntentID,
		q.LeaseOwner,
	}

	if q.retryable(cause, intent.AttemptCount) {
		failureClass = "reducer_retryable"
		query = retryReducerWorkQuery
		args = []any{
			now,
			failureClass,
			cause.Error(),
			cause.Error(),
			now.Add(q.retryDelay()),
			intent.IntentID,
			q.LeaseOwner,
		}
	}

	_, err := q.db.ExecContext(ctx, query, args...)
	if err != nil {
		return fmt.Errorf("fail reducer work: %w", err)
	}

	return nil
}

func reducerWorkItemID(intent projector.ReducerIntent) string {
	parts := []string{
		intent.ScopeID,
		intent.GenerationID,
		string(intent.Domain),
		intent.EntityKey,
	}
	sanitized := make([]string, 0, len(parts))
	for _, part := range parts {
		part = strings.TrimSpace(part)
		if part == "" {
			continue
		}
		part = strings.ReplaceAll(part, ":", "_")
		part = strings.ReplaceAll(part, "/", "_")
		sanitized = append(sanitized, part)
	}
	return "reducer_" + strings.Join(sanitized, "_")
}
