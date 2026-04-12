package postgres

import (
	"context"
	"database/sql"
	"fmt"
	"strings"
)

// Definition describes one ordered bootstrap SQL payload.
type Definition struct {
	Name string
	Path string
	SQL  string
}

// Executor is the narrow adapter surface required to apply schema bootstrap
// statements against a SQL connection or transaction.
type Executor interface {
	ExecContext(context.Context, string, ...any) (sql.Result, error)
}

var bootstrapDefinitions = []Definition{
	{
		Name: "ingestion_scopes",
		Path: "schema/data-plane/postgres/001_ingestion_scopes.sql",
		SQL:  scopeSchemaSQL,
	},
	{
		Name: "scope_generations",
		Path: "schema/data-plane/postgres/002_scope_generations.sql",
		SQL:  scopeGenerationSchemaSQL,
	},
	{
		Name: "fact_records",
		Path: "schema/data-plane/postgres/003_fact_records.sql",
		SQL:  factRecordSchemaSQL,
	},
	{
		Name: "fact_work_items",
		Path: "schema/data-plane/postgres/004_fact_work_items.sql",
		SQL:  workItemSchemaSQL,
	},
	{
		Name: "fact_work_item_audit",
		Path: "schema/data-plane/postgres/005_fact_work_item_audit.sql",
		SQL:  workItemAuditSchemaSQL,
	},
}

const scopeSchemaSQL = `
CREATE TABLE IF NOT EXISTS ingestion_scopes (
    scope_id TEXT PRIMARY KEY,
    scope_kind TEXT NOT NULL,
    source_system TEXT NOT NULL,
    source_key TEXT NOT NULL,
    parent_scope_id TEXT NULL,
    collector_kind TEXT NOT NULL,
    partition_key TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL,
    active_generation_id TEXT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS ingestion_scopes_source_idx
    ON ingestion_scopes (
        source_system,
        scope_kind,
        partition_key,
        observed_at DESC
    );

CREATE INDEX IF NOT EXISTS ingestion_scopes_parent_idx
    ON ingestion_scopes (parent_scope_id, observed_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS ingestion_scopes_active_generation_idx
    ON ingestion_scopes (active_generation_id)
    WHERE active_generation_id IS NOT NULL;
`

const scopeGenerationSchemaSQL = `
CREATE TABLE IF NOT EXISTS scope_generations (
    generation_id TEXT PRIMARY KEY,
    scope_id TEXT NOT NULL REFERENCES ingestion_scopes(scope_id) ON DELETE CASCADE,
    trigger_kind TEXT NOT NULL,
    freshness_hint TEXT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL,
    activated_at TIMESTAMPTZ NULL,
    superseded_at TIMESTAMPTZ NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS scope_generations_scope_idx
    ON scope_generations (scope_id, status, ingested_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS scope_generations_active_scope_idx
    ON scope_generations (scope_id)
    WHERE status = 'active';
`

const factRecordSchemaSQL = `
CREATE TABLE IF NOT EXISTS fact_records (
    fact_id TEXT PRIMARY KEY,
    scope_id TEXT NOT NULL REFERENCES ingestion_scopes(scope_id) ON DELETE CASCADE,
    generation_id TEXT NOT NULL REFERENCES scope_generations(generation_id) ON DELETE CASCADE,
    fact_kind TEXT NOT NULL,
    stable_fact_key TEXT NOT NULL,
    source_system TEXT NOT NULL,
    source_fact_key TEXT NOT NULL,
    source_uri TEXT NULL,
    source_record_id TEXT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL,
    is_tombstone BOOLEAN NOT NULL DEFAULT FALSE,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS fact_records_scope_generation_idx
    ON fact_records (scope_id, generation_id, fact_kind, observed_at DESC);

CREATE INDEX IF NOT EXISTS fact_records_stable_key_idx
    ON fact_records (stable_fact_key, generation_id);
`

const workItemSchemaSQL = `
CREATE TABLE IF NOT EXISTS fact_work_items (
    work_item_id TEXT PRIMARY KEY,
    scope_id TEXT NOT NULL REFERENCES ingestion_scopes(scope_id) ON DELETE CASCADE,
    generation_id TEXT NOT NULL REFERENCES scope_generations(generation_id) ON DELETE CASCADE,
    stage TEXT NOT NULL,
    domain TEXT NOT NULL,
    status TEXT NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    claim_until TIMESTAMPTZ NULL,
    visible_at TIMESTAMPTZ NULL,
    last_attempt_at TIMESTAMPTZ NULL,
    next_attempt_at TIMESTAMPTZ NULL,
    failure_class TEXT NULL,
    failure_message TEXT NULL,
    failure_details TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS fact_work_items_scope_generation_idx
    ON fact_work_items (scope_id, generation_id, status, updated_at DESC);

CREATE INDEX IF NOT EXISTS fact_work_items_status_idx
    ON fact_work_items (status, visible_at, updated_at DESC);

CREATE INDEX IF NOT EXISTS fact_work_items_claim_until_idx
    ON fact_work_items (claim_until)
    WHERE claim_until IS NOT NULL;
`

const workItemAuditSchemaSQL = `
CREATE TABLE IF NOT EXISTS fact_replay_events (
    replay_event_id TEXT PRIMARY KEY,
    work_item_id TEXT NOT NULL REFERENCES fact_work_items(work_item_id) ON DELETE CASCADE,
    scope_id TEXT NOT NULL REFERENCES ingestion_scopes(scope_id) ON DELETE CASCADE,
    generation_id TEXT NOT NULL REFERENCES scope_generations(generation_id) ON DELETE CASCADE,
    failure_class TEXT NULL,
    operator_note TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS fact_replay_events_work_item_idx
    ON fact_replay_events (work_item_id, created_at DESC);

CREATE TABLE IF NOT EXISTS fact_backfill_requests (
    backfill_request_id TEXT PRIMARY KEY,
    scope_id TEXT NULL REFERENCES ingestion_scopes(scope_id) ON DELETE SET NULL,
    generation_id TEXT NULL REFERENCES scope_generations(generation_id) ON DELETE SET NULL,
    operator_note TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS fact_backfill_requests_scope_idx
    ON fact_backfill_requests (scope_id, generation_id, created_at DESC);
`

// BootstrapDefinitions returns a copy of the ordered Wave 2 bootstrap layout.
func BootstrapDefinitions() []Definition {
	return append([]Definition(nil), bootstrapDefinitions...)
}

// BootstrapStatements returns the ordered SQL payloads that make up the
// bootstrap layout.
func BootstrapStatements() []string {
	statements := make([]string, 0, len(bootstrapDefinitions))
	for _, def := range bootstrapDefinitions {
		statements = append(statements, def.SQL)
	}

	return statements
}

// ValidateDefinitions checks that a schema layout is complete enough to apply.
func ValidateDefinitions(defs []Definition) error {
	seen := make(map[string]struct{}, len(defs))
	for i, def := range defs {
		if strings.TrimSpace(def.Name) == "" {
			return fmt.Errorf("definition %d has an empty name", i)
		}
		if strings.TrimSpace(def.Path) == "" {
			return fmt.Errorf("definition %q has an empty path", def.Name)
		}
		if strings.TrimSpace(def.SQL) == "" {
			return fmt.Errorf("definition %q has empty SQL", def.Name)
		}
		if _, ok := seen[def.Name]; ok {
			return fmt.Errorf("duplicate definition name %q", def.Name)
		}
		seen[def.Name] = struct{}{}
	}

	return nil
}

// ApplyDefinitions executes one ordered schema layout against the executor.
func ApplyDefinitions(ctx context.Context, exec Executor, defs []Definition) error {
	if err := ValidateDefinitions(defs); err != nil {
		return err
	}
	if exec == nil {
		return fmt.Errorf("executor is required")
	}

	for _, def := range defs {
		if _, err := exec.ExecContext(ctx, def.SQL); err != nil {
			return fmt.Errorf("apply %s: %w", def.Name, err)
		}
	}

	return nil
}

// ApplyBootstrap applies the Wave 2 schema bootstrap layout.
func ApplyBootstrap(ctx context.Context, exec Executor) error {
	return ApplyDefinitions(ctx, exec, bootstrapDefinitions)
}
