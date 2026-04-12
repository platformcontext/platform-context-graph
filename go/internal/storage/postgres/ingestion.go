package postgres

import (
	"context"
	"fmt"
	"strings"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/facts"
	"github.com/platformcontext/platform-context-graph/go/internal/scope"
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
    status = EXCLUDED.status,
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

// CommitScopeGeneration persists one scope generation worth of facts and
// enqueues one projector work item for the same durable boundary.
func (s IngestionStore) CommitScopeGeneration(
	ctx context.Context,
	scopeValue scope.IngestionScope,
	generation scope.ScopeGeneration,
	envelopes []facts.Envelope,
) error {
	if err := validateProjectionInput(scopeValue, generation, envelopes); err != nil {
		return err
	}
	if s.beginner == nil {
		return fmt.Errorf("transaction beginner is required")
	}

	tx, err := s.beginner.Begin(ctx)
	if err != nil {
		return fmt.Errorf("begin ingestion transaction: %w", err)
	}

	committed := false
	defer func() {
		if !committed {
			_ = tx.Rollback()
		}
	}()

	if err := upsertIngestionScope(ctx, tx, scopeValue, generation); err != nil {
		return fmt.Errorf("upsert ingestion scope: %w", err)
	}
	if err := upsertScopeGeneration(ctx, tx, generation); err != nil {
		return fmt.Errorf("upsert scope generation: %w", err)
	}
	if err := upsertFacts(ctx, tx, envelopes); err != nil {
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

func validateProjectionInput(
	scopeValue scope.IngestionScope,
	generation scope.ScopeGeneration,
	envelopes []facts.Envelope,
) error {
	if err := generation.ValidateForScope(scopeValue); err != nil {
		return err
	}
	if generation.IsTerminal() {
		return fmt.Errorf("generation %q must not be terminal before projection", generation.GenerationID)
	}

	for _, envelope := range envelopes {
		if envelope.ScopeID != scopeValue.ScopeID {
			return fmt.Errorf("fact %q scope_id %q does not match scope %q", envelope.FactID, envelope.ScopeID, scopeValue.ScopeID)
		}
		if envelope.GenerationID != generation.GenerationID {
			return fmt.Errorf("fact %q generation_id %q does not match generation %q", envelope.FactID, envelope.GenerationID, generation.GenerationID)
		}
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
