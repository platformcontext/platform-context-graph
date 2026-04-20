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
