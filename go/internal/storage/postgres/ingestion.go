package postgres

import (
	"context"
	"fmt"
	"log"
	"strings"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/facts"
	"github.com/platformcontext/platform-context-graph/go/internal/scope"
	"github.com/platformcontext/platform-context-graph/go/internal/telemetry"
)

const upsertIngestionScopeQuery = `
INSERT INTO ingestion_scopes (
    scope_id,
    scope_kind,
    source_system,
    source_key,
    parent_scope_id,
    collector_kind,
    partition_key,
    observed_at,
    ingested_at,
    status,
    active_generation_id,
    payload
) VALUES (
    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12::jsonb
)
ON CONFLICT (scope_id) DO UPDATE SET
    scope_kind = EXCLUDED.scope_kind,
    source_system = EXCLUDED.source_system,
    source_key = EXCLUDED.source_key,
    parent_scope_id = EXCLUDED.parent_scope_id,
    collector_kind = EXCLUDED.collector_kind,
    partition_key = EXCLUDED.partition_key,
    observed_at = EXCLUDED.observed_at,
    ingested_at = EXCLUDED.ingested_at,
    status = CASE
        WHEN ingestion_scopes.active_generation_id IS NOT NULL
            AND EXCLUDED.active_generation_id IS NULL
            AND EXCLUDED.status = 'pending'
        THEN ingestion_scopes.status
        ELSE EXCLUDED.status
    END,
    active_generation_id = CASE
        WHEN EXCLUDED.active_generation_id IS NOT NULL THEN EXCLUDED.active_generation_id
        ELSE ingestion_scopes.active_generation_id
    END,
    payload = EXCLUDED.payload
`

const upsertScopeGenerationQuery = `
INSERT INTO scope_generations (
    generation_id,
    scope_id,
    trigger_kind,
    freshness_hint,
    observed_at,
    ingested_at,
    status,
    activated_at,
    superseded_at,
    payload
) VALUES (
    $1, $2, $3, $4, $5, $6, $7, $8, NULL, '{}'::jsonb
)
ON CONFLICT (generation_id) DO UPDATE SET
    scope_id = EXCLUDED.scope_id,
    trigger_kind = EXCLUDED.trigger_kind,
    freshness_hint = EXCLUDED.freshness_hint,
    observed_at = EXCLUDED.observed_at,
    ingested_at = EXCLUDED.ingested_at,
    status = EXCLUDED.status,
    activated_at = EXCLUDED.activated_at,
    payload = EXCLUDED.payload
`

const activeGenerationFreshnessQuery = `
SELECT generation.generation_id, COALESCE(generation.freshness_hint, '')
FROM ingestion_scopes AS scope
JOIN scope_generations AS generation
  ON generation.generation_id = scope.active_generation_id
WHERE scope.scope_id = $1
LIMIT 1
`

// IngestionStore owns the durable commit boundary for scope generations, facts,
// and projector follow-up work.
type IngestionStore struct {
	db       ExecQueryer
	beginner Beginner
	Now      func() time.Time
}

// NewIngestionStore constructs a transactional storage boundary for projection
// input.
func NewIngestionStore(db ExecQueryer) IngestionStore {
	store := IngestionStore{db: db}
	if beginner, ok := db.(Beginner); ok {
		store.beginner = beginner
	}

	return store
}

// drainFacts reads and discards all remaining facts from the channel.
// This prevents the producer goroutine from leaking when the consumer
// must abort early (skip, validation error, rollback).
func drainFacts(factStream <-chan facts.Envelope) {
	if factStream == nil {
		return
	}
	for range factStream {
	}
}

// CommitScopeGeneration persists one scope generation worth of facts and
// enqueues one projector work item for the same durable boundary. Facts
// arrive through a channel and are committed in batched multi-row INSERTs
// so memory stays proportional to the batch size, not the total fact count.
func (s IngestionStore) CommitScopeGeneration(
	ctx context.Context,
	scopeValue scope.IngestionScope,
	generation scope.ScopeGeneration,
	factStream <-chan facts.Envelope,
) error {
	if err := validateGenerationInput(scopeValue, generation); err != nil {
		drainFacts(factStream)
		return err
	}
	skip, err := s.shouldSkipUnchangedGeneration(ctx, scopeValue.ScopeID, generation.FreshnessHint)
	if err != nil {
		drainFacts(factStream)
		return fmt.Errorf("check active generation freshness: %w", err)
	}
	if skip {
		drainFacts(factStream)
		telemetry.RecordSkippedRefresh()
		log.Printf(
			"%s=true %s=%q %s=%q %s=%q %s=%q %s=%q",
			telemetry.LogKeyRefreshSkipped,
			telemetry.LogKeyScopeID,
			scopeValue.ScopeID,
			telemetry.LogKeyScopeKind,
			string(scopeValue.ScopeKind),
			telemetry.LogKeySourceSystem,
			scopeValue.SourceSystem,
			telemetry.LogKeyCollectorKind,
			string(scopeValue.CollectorKind),
			telemetry.LogKeyGenerationID,
			generation.GenerationID,
		)
		return nil
	}
	if s.beginner == nil {
		drainFacts(factStream)
		return fmt.Errorf("transaction beginner is required")
	}

	tx, err := s.beginner.Begin(ctx)
	if err != nil {
		drainFacts(factStream)
		return fmt.Errorf("begin ingestion transaction: %w", err)
	}

	committed := false
	defer func() {
		if !committed {
			drainFacts(factStream)
			_ = tx.Rollback()
		}
	}()

	if err := upsertIngestionScope(ctx, tx, scopeValue, generation); err != nil {
		return fmt.Errorf("upsert ingestion scope: %w", err)
	}
	if err := upsertScopeGeneration(ctx, tx, generation); err != nil {
		return fmt.Errorf("upsert scope generation: %w", err)
	}
	if err := upsertStreamingFacts(ctx, tx, factStream, scopeValue.ScopeID, generation.GenerationID); err != nil {
		return err
	}

	queue := ProjectorQueue{db: tx, Now: s.now}
	if err := queue.Enqueue(ctx, scopeValue.ScopeID, generation.GenerationID); err != nil {
		return err
	}

	if err := tx.Commit(); err != nil {
		return fmt.Errorf("commit ingestion transaction: %w", err)
	}
	committed = true

	return nil
}

func (s IngestionStore) now() time.Time {
	if s.Now != nil {
		return s.Now().UTC()
	}

	return time.Now().UTC()
}

func (s IngestionStore) shouldSkipUnchangedGeneration(
	ctx context.Context,
	scopeID string,
	freshnessHint string,
) (bool, error) {
	if s.db == nil {
		return false, nil
	}
	if strings.TrimSpace(scopeID) == "" || strings.TrimSpace(freshnessHint) == "" {
		return false, nil
	}

	rows, err := s.db.QueryContext(ctx, activeGenerationFreshnessQuery, scopeID)
	if err != nil {
		return false, err
	}
	defer func() { _ = rows.Close() }()

	if !rows.Next() {
		if err := rows.Err(); err != nil {
			return false, err
		}
		return false, nil
	}

	var generationID string
	var activeFreshnessHint string
	if err := rows.Scan(&generationID, &activeFreshnessHint); err != nil {
		return false, err
	}
	if err := rows.Err(); err != nil {
		return false, err
	}

	return strings.TrimSpace(activeFreshnessHint) == strings.TrimSpace(freshnessHint), nil
}

// validateGenerationInput checks scope/generation preconditions before
// opening a transaction. Per-fact validation (scope_id, generation_id match)
// happens inside upsertStreamingFacts as facts arrive from the channel.
func validateGenerationInput(
	scopeValue scope.IngestionScope,
	generation scope.ScopeGeneration,
) error {
	if err := generation.ValidateForScope(scopeValue); err != nil {
		return err
	}
	if generation.IsTerminal() {
		return fmt.Errorf("generation %q must not be terminal before projection", generation.GenerationID)
	}

	return nil
}

func upsertIngestionScope(
	ctx context.Context,
	db ExecQueryer,
	scopeValue scope.IngestionScope,
	generation scope.ScopeGeneration,
) error {
	payloadJSON, err := marshalPayload(stringMapToAny(scopeValue.MetadataCopy()))
	if err != nil {
		return fmt.Errorf("marshal scope payload: %w", err)
	}

	_, err = db.ExecContext(
		ctx,
		upsertIngestionScopeQuery,
		scopeValue.ScopeID,
		string(scopeValue.ScopeKind),
		scopeValue.SourceSystem,
		scopeSourceKey(scopeValue),
		emptyToNil(scopeValue.ParentScopeID),
		string(scopeValue.CollectorKind),
		scopeValue.PartitionKey,
		generation.ObservedAt.UTC(),
		generation.IngestedAt.UTC(),
		string(generation.Status),
		activeGenerationID(generation),
		payloadJSON,
	)
	if err != nil {
		return err
	}

	return nil
}

func upsertScopeGeneration(
	ctx context.Context,
	db ExecQueryer,
	generation scope.ScopeGeneration,
) error {
	_, err := db.ExecContext(
		ctx,
		upsertScopeGenerationQuery,
		generation.GenerationID,
		generation.ScopeID,
		string(generation.TriggerKind),
		emptyToNil(generation.FreshnessHint),
		generation.ObservedAt.UTC(),
		generation.IngestedAt.UTC(),
		string(generation.Status),
		activeTimestamp(generation),
	)
	if err != nil {
		return err
	}

	return nil
}

func scopeSourceKey(scopeValue scope.IngestionScope) string {
	if scopeValue.Metadata != nil {
		if sourceKey := strings.TrimSpace(scopeValue.Metadata["source_key"]); sourceKey != "" {
			return sourceKey
		}
	}

	return scopeValue.ScopeID
}

func activeGenerationID(generation scope.ScopeGeneration) any {
	if generation.Status == scope.GenerationStatusActive {
		return generation.GenerationID
	}

	return nil
}

func activeTimestamp(generation scope.ScopeGeneration) any {
	if generation.Status == scope.GenerationStatusActive {
		return generation.IngestedAt.UTC()
	}

	return nil
}

func stringMapToAny(input map[string]string) map[string]any {
	if len(input) == 0 {
		return nil
	}

	output := make(map[string]any, len(input))
	for key, value := range input {
		output[key] = value
	}

	return output
}
