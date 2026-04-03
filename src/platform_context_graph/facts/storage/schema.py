"""Schema bootstrap helpers for fact storage."""

FACT_STORE_SCHEMA = """
CREATE TABLE IF NOT EXISTS fact_runs (
    source_run_id TEXT PRIMARY KEY,
    source_system TEXT NOT NULL,
    source_snapshot_id TEXT NOT NULL,
    repository_id TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ NULL
);

CREATE TABLE IF NOT EXISTS fact_records (
    fact_id TEXT PRIMARY KEY,
    fact_type TEXT NOT NULL,
    repository_id TEXT NOT NULL,
    checkout_path TEXT NOT NULL,
    relative_path TEXT NULL,
    source_system TEXT NOT NULL,
    source_run_id TEXT NOT NULL REFERENCES fact_runs(source_run_id) ON DELETE CASCADE,
    source_snapshot_id TEXT NOT NULL,
    payload JSONB NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL,
    provenance JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS fact_records_repository_run_idx
    ON fact_records (repository_id, source_run_id);
"""
