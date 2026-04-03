"""Tests for shared Phase 2 fact runtime state helpers."""

from __future__ import annotations

from platform_context_graph import facts
from platform_context_graph.facts import state as fact_state


def test_git_facts_first_enabled_defaults_to_runtime_readiness(
    monkeypatch,
) -> None:
    """Facts-first indexing should follow fact runtime readiness by default."""

    monkeypatch.delenv("PCG_GIT_FACTS_FIRST_ENABLED", raising=False)
    monkeypatch.delenv("PCG_POSTGRES_DSN", raising=False)
    fact_state.reset_facts_runtime_for_tests()

    assert fact_state.git_facts_first_enabled() is False

    monkeypatch.setenv("PCG_POSTGRES_DSN", "postgresql://facts")
    monkeypatch.setattr(fact_state, "PostgresFactStore", lambda _dsn: object())
    monkeypatch.setattr(fact_state, "PostgresFactWorkQueue", lambda _dsn: object())
    fact_state.reset_facts_runtime_for_tests()

    assert fact_state.git_facts_first_enabled() is True

    fact_state.reset_facts_runtime_for_tests()


def test_get_fact_runtime_uses_shared_postgres_instances(monkeypatch) -> None:
    """Fact helpers should cache one store and one queue per process."""

    created: list[tuple[str, str]] = []

    class _FakeStore:
        def __init__(self, dsn: str) -> None:
            created.append(("store", dsn))

        def close(self) -> None:
            return None

    class _FakeQueue:
        def __init__(self, dsn: str) -> None:
            created.append(("queue", dsn))

        def close(self) -> None:
            return None

    class _FakeDecisionStore:
        def __init__(self, dsn: str) -> None:
            created.append(("decision_store", dsn))

        def close(self) -> None:
            return None

    monkeypatch.setenv("PCG_POSTGRES_DSN", "postgresql://facts")
    monkeypatch.setattr(fact_state, "PostgresFactStore", _FakeStore)
    monkeypatch.setattr(fact_state, "PostgresFactWorkQueue", _FakeQueue)
    monkeypatch.setattr(
        fact_state,
        "PostgresProjectionDecisionStore",
        _FakeDecisionStore,
    )
    fact_state.reset_facts_runtime_for_tests()

    first_store = fact_state.get_fact_store()
    second_store = fact_state.get_fact_store()
    first_queue = fact_state.get_fact_work_queue()
    second_queue = fact_state.get_fact_work_queue()
    first_decision_store = fact_state.get_projection_decision_store()
    second_decision_store = fact_state.get_projection_decision_store()

    assert first_store is second_store
    assert first_queue is second_queue
    assert first_decision_store is second_decision_store
    assert created == [
        ("store", "postgresql://facts"),
        ("queue", "postgresql://facts"),
        ("decision_store", "postgresql://facts"),
    ]

    fact_state.reset_facts_runtime_for_tests()


def test_facts_package_exports_state_helpers() -> None:
    """The facts package should expose the shared runtime helpers."""

    assert callable(facts.get_fact_store)
    assert callable(facts.get_fact_work_queue)
    assert callable(fact_state.get_projection_decision_store)
    assert callable(facts.git_facts_first_enabled)
