"""Schema bootstrap helpers for the fact work queue."""

FACT_WORK_QUEUE_SCHEMA = """
CREATE TABLE IF NOT EXISTS fact_work_items (
    work_item_id TEXT PRIMARY KEY,
    work_type TEXT NOT NULL,
    repository_id TEXT NOT NULL,
    source_run_id TEXT NOT NULL,
    lease_owner TEXT NULL,
    lease_expires_at TIMESTAMPTZ NULL,
    status TEXT NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NULL,
    failure_stage TEXT NULL,
    error_class TEXT NULL,
    failure_class TEXT NULL,
    failure_code TEXT NULL,
    retry_disposition TEXT NULL,
    dead_lettered_at TIMESTAMPTZ NULL,
    last_attempt_started_at TIMESTAMPTZ NULL,
    last_attempt_finished_at TIMESTAMPTZ NULL,
    next_retry_at TIMESTAMPTZ NULL,
    operator_note TEXT NULL,
    parent_work_item_id TEXT NULL,
    projection_domain TEXT NULL,
    accepted_generation_id TEXT NULL,
    authoritative_shared_domains TEXT[] NOT NULL DEFAULT '{}',
    completed_shared_domains TEXT[] NOT NULL DEFAULT '{}',
    shared_projection_pending BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
ALTER TABLE fact_work_items
    ADD COLUMN IF NOT EXISTS parent_work_item_id TEXT NULL;
ALTER TABLE fact_work_items
    ADD COLUMN IF NOT EXISTS projection_domain TEXT NULL;
ALTER TABLE fact_work_items
    ADD COLUMN IF NOT EXISTS accepted_generation_id TEXT NULL;
ALTER TABLE fact_work_items
    ADD COLUMN IF NOT EXISTS authoritative_shared_domains TEXT[] NOT NULL DEFAULT '{}';
ALTER TABLE fact_work_items
    ADD COLUMN IF NOT EXISTS completed_shared_domains TEXT[] NOT NULL DEFAULT '{}';
ALTER TABLE fact_work_items
    ADD COLUMN IF NOT EXISTS shared_projection_pending BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS fact_work_items_status_idx
    ON fact_work_items (status, work_type, updated_at);
CREATE INDEX IF NOT EXISTS fact_work_items_shared_projection_idx
    ON fact_work_items (shared_projection_pending, source_run_id, updated_at);

CREATE TABLE IF NOT EXISTS fact_replay_events (
    replay_event_id TEXT PRIMARY KEY,
    work_item_id TEXT NOT NULL,
    repository_id TEXT NOT NULL,
    source_run_id TEXT NOT NULL,
    work_type TEXT NOT NULL,
    failure_class TEXT NULL,
    operator_note TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS fact_replay_events_work_item_idx
    ON fact_replay_events (work_item_id, created_at);

CREATE TABLE IF NOT EXISTS fact_backfill_requests (
    backfill_request_id TEXT PRIMARY KEY,
    repository_id TEXT NULL,
    source_run_id TEXT NULL,
    operator_note TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS fact_backfill_requests_repo_idx
    ON fact_backfill_requests (repository_id, source_run_id, created_at);
"""
