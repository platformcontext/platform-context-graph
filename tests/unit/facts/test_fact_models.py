"""Tests for Phase 2 fact models and deterministic identifiers."""

from __future__ import annotations

from datetime import datetime, timezone

from platform_context_graph.facts.models.base import FactProvenance
from platform_context_graph.facts.models.git import FileObservedFact
from platform_context_graph.facts.models.git import ParsedEntityObservedFact
from platform_context_graph.facts.models.git import RepositoryObservedFact


def _observed_at() -> datetime:
    """Return a stable UTC timestamp for deterministic fact tests."""

    return datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc)


def test_repository_observed_fact_has_stable_type_and_provenance() -> None:
    """Repository facts should expose a stable type and carry provenance."""

    provenance = FactProvenance(
        source_system="git",
        source_run_id="run-123",
        source_snapshot_id="snapshot-abc",
        observed_at=_observed_at(),
    )

    fact = RepositoryObservedFact(
        repository_id="github.com/acme/service",
        checkout_path="/tmp/service",
        is_dependency=False,
        provenance=provenance,
    )

    assert fact.fact_type == "RepositoryObserved"
    assert fact.provenance.source_system == "git"
    assert fact.provenance.source_run_id == "run-123"
    assert fact.provenance.source_snapshot_id == "snapshot-abc"
    assert fact.provenance.observed_at == _observed_at()


def test_file_observed_fact_id_is_deterministic_for_same_source_input() -> None:
    """File facts should generate the same id for the same source observation."""

    provenance = FactProvenance(
        source_system="git",
        source_run_id="run-123",
        source_snapshot_id="snapshot-abc",
        observed_at=_observed_at(),
    )

    first = FileObservedFact(
        repository_id="github.com/acme/service",
        checkout_path="/tmp/service",
        relative_path="src/app.py",
        language="python",
        is_dependency=False,
        provenance=provenance,
    )
    second = FileObservedFact(
        repository_id="github.com/acme/service",
        checkout_path="/tmp/service",
        relative_path="src/app.py",
        language="python",
        is_dependency=False,
        provenance=provenance,
    )

    assert first.fact_type == "FileObserved"
    assert first.fact_id == second.fact_id


def test_parsed_entity_observed_fact_distinguishes_payload_changes() -> None:
    """Parsed entity fact ids should change when the observed payload changes."""

    provenance = FactProvenance(
        source_system="git",
        source_run_id="run-123",
        source_snapshot_id="snapshot-abc",
        observed_at=_observed_at(),
    )

    first = ParsedEntityObservedFact(
        repository_id="github.com/acme/service",
        checkout_path="/tmp/service",
        relative_path="src/app.py",
        entity_kind="Function",
        entity_name="handler",
        start_line=10,
        end_line=20,
        language="python",
        provenance=provenance,
    )
    second = ParsedEntityObservedFact(
        repository_id="github.com/acme/service",
        checkout_path="/tmp/service",
        relative_path="src/app.py",
        entity_kind="Function",
        entity_name="handler_v2",
        start_line=10,
        end_line=20,
        language="python",
        provenance=provenance,
    )

    assert first.fact_type == "ParsedEntityObserved"
    assert first.fact_id != second.fact_id
