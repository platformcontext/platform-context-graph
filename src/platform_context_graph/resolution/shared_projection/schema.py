"""Schema bootstrap helpers for shared projection intent storage."""

SHARED_PROJECTION_INTENT_SCHEMA = """
CREATE TABLE IF NOT EXISTS shared_projection_intents (
    intent_id TEXT PRIMARY KEY,
    projection_domain TEXT NOT NULL,
    partition_key TEXT NOT NULL,
    repository_id TEXT NOT NULL,
    source_run_id TEXT NOT NULL,
    generation_id TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS shared_projection_intents_repo_run_idx
    ON shared_projection_intents (
        repository_id,
        source_run_id,
        projection_domain,
        created_at
    );
"""
