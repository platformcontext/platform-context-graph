"""Shared PostgreSQL schema for evidence-backed relationship resolution."""

from __future__ import annotations

RELATIONSHIP_SCHEMA = """
CREATE TABLE IF NOT EXISTS relationship_checkouts (
    checkout_id TEXT PRIMARY KEY,
    logical_repo_id TEXT NOT NULL,
    repo_name TEXT NOT NULL,
    repo_slug TEXT,
    remote_url TEXT,
    checkout_path TEXT,
    last_seen_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS relationship_checkouts_repo_idx
    ON relationship_checkouts (logical_repo_id);

CREATE TABLE IF NOT EXISTS relationship_entities (
    entity_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    repository_id TEXT,
    subject_type TEXT,
    kind TEXT,
    provider TEXT,
    name TEXT NOT NULL,
    environment TEXT,
    path TEXT,
    region TEXT,
    locator TEXT,
    details JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS relationship_assertions (
    assertion_id TEXT PRIMARY KEY,
    source_repo_id TEXT NOT NULL,
    target_repo_id TEXT NOT NULL,
    relationship_type TEXT NOT NULL,
    decision TEXT NOT NULL,
    reason TEXT NOT NULL,
    actor TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS relationship_assertions_lookup_idx
    ON relationship_assertions (relationship_type, source_repo_id, target_repo_id);

ALTER TABLE relationship_assertions
    ADD COLUMN IF NOT EXISTS source_entity_id TEXT,
    ADD COLUMN IF NOT EXISTS target_entity_id TEXT;

CREATE TABLE IF NOT EXISTS metadata_assertions (
    assertion_id TEXT PRIMARY KEY,
    subject_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    actor TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS metadata_assertions_subject_idx
    ON metadata_assertions (subject_type, subject_id, key);

CREATE TABLE IF NOT EXISTS relationship_generations (
    generation_id TEXT PRIMARY KEY,
    scope TEXT NOT NULL,
    run_id TEXT,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    activated_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS relationship_generations_scope_idx
    ON relationship_generations (scope, status, created_at DESC);

CREATE TABLE IF NOT EXISTS relationship_evidence_facts (
    evidence_id TEXT PRIMARY KEY,
    generation_id TEXT NOT NULL,
    evidence_kind TEXT NOT NULL,
    relationship_type TEXT NOT NULL,
    source_repo_id TEXT NOT NULL,
    target_repo_id TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    rationale TEXT NOT NULL,
    details JSONB NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS relationship_evidence_generation_idx
    ON relationship_evidence_facts (generation_id, relationship_type);

ALTER TABLE relationship_evidence_facts
    ADD COLUMN IF NOT EXISTS source_entity_id TEXT,
    ADD COLUMN IF NOT EXISTS target_entity_id TEXT;

CREATE TABLE IF NOT EXISTS relationship_candidates (
    candidate_id TEXT PRIMARY KEY,
    generation_id TEXT NOT NULL,
    source_repo_id TEXT NOT NULL,
    target_repo_id TEXT NOT NULL,
    relationship_type TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    evidence_count INTEGER NOT NULL,
    rationale TEXT NOT NULL,
    details JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS relationship_candidates_generation_idx
    ON relationship_candidates (generation_id, relationship_type);

ALTER TABLE relationship_candidates
    ADD COLUMN IF NOT EXISTS source_entity_id TEXT,
    ADD COLUMN IF NOT EXISTS target_entity_id TEXT;

CREATE TABLE IF NOT EXISTS resolved_relationships (
    generation_id TEXT NOT NULL,
    source_repo_id TEXT NOT NULL,
    target_repo_id TEXT NOT NULL,
    relationship_type TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    evidence_count INTEGER NOT NULL,
    rationale TEXT NOT NULL,
    resolution_source TEXT NOT NULL,
    details JSONB NOT NULL,
    PRIMARY KEY (generation_id, source_repo_id, target_repo_id, relationship_type)
);

CREATE INDEX IF NOT EXISTS resolved_relationships_generation_idx
    ON resolved_relationships (generation_id, relationship_type);

ALTER TABLE resolved_relationships
    ADD COLUMN IF NOT EXISTS source_entity_id TEXT,
    ADD COLUMN IF NOT EXISTS target_entity_id TEXT;
"""

__all__ = ["RELATIONSHIP_SCHEMA"]
