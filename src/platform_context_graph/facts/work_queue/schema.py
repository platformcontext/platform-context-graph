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
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS fact_work_items_status_idx
    ON fact_work_items (status, work_type, updated_at);
"""
