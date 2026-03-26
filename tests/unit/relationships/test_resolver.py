"""Unit tests for repository relationship resolution."""

from __future__ import annotations

import importlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from platform_context_graph.relationships.models import (
    RelationshipAssertion,
    RelationshipEvidenceFact,
    RepositoryCheckout,
    ResolvedRelationship,
    ResolutionGeneration,
)
from platform_context_graph.utils.debug_log import info_logger
from platform_context_graph.relationships.resolver import (
    project_resolved_relationships,
    resolve_repository_relationships_for_committed_repositories,
    resolve_repository_relationships,
)


def test_resolve_repository_relationships_groups_evidence_into_one_edge() -> None:
    """Multiple evidence facts for one repo pair should aggregate deterministically."""

    evidence = [
        RelationshipEvidenceFact(
            evidence_kind="WORKLOAD_DEPENDS_ON",
            relationship_type="DEPENDS_ON",
            source_repo_id="repository:r_payments",
            target_repo_id="repository:r_auth",
            confidence=0.9,
            rationale="Runtime services list declares workload dependency",
            details={"source_workload": "workload:payments"},
        ),
        RelationshipEvidenceFact(
            evidence_kind="SOURCES_FROM",
            relationship_type="DEPENDS_ON",
            source_repo_id="repository:r_payments",
            target_repo_id="repository:r_auth",
            confidence=0.98,
            rationale="Argo source repository reference points at target repo",
            details={"source_node": "argocd:payments"},
        ),
    ]

    candidates, resolved = resolve_repository_relationships(evidence, assertions=[])

    assert len(candidates) == 1
    assert candidates[0].source_repo_id == "repository:r_payments"
    assert candidates[0].target_repo_id == "repository:r_auth"
    assert candidates[0].confidence == 0.98
    assert candidates[0].evidence_count == 2
    assert len(resolved) == 1
    assert resolved[0].resolution_source == "inferred"
    assert resolved[0].confidence == 0.98
    assert resolved[0].evidence_count == 2


def test_resolve_repository_relationships_rejection_blocks_inferred_edge() -> None:
    """Explicit rejections should prevent inference from becoming canonical."""

    evidence = [
        RelationshipEvidenceFact(
            evidence_kind="WORKLOAD_DEPENDS_ON",
            relationship_type="DEPENDS_ON",
            source_repo_id="repository:r_payments",
            target_repo_id="repository:r_auth",
            confidence=0.9,
            rationale="Runtime services list declares workload dependency",
        )
    ]
    assertions = [
        RelationshipAssertion(
            source_repo_id="repository:r_payments",
            target_repo_id="repository:r_auth",
            relationship_type="DEPENDS_ON",
            decision="reject",
            reason="False positive for fixture repo",
            actor="tester",
        )
    ]

    candidates, resolved = resolve_repository_relationships(evidence, assertions)

    assert len(candidates) == 1
    assert resolved == []


def test_resolve_repository_relationships_assertion_creates_edge_without_evidence() -> (
    None
):
    """Explicit assertions should create canonical edges even without raw evidence."""

    assertions = [
        RelationshipAssertion(
            source_repo_id="repository:r_deployments",
            target_repo_id="repository:r_payments",
            relationship_type="DEPENDS_ON",
            decision="assert",
            reason="Deployment repo intentionally tracks service repo",
            actor="tester",
        )
    ]

    candidates, resolved = resolve_repository_relationships([], assertions)

    assert candidates == []
    assert len(resolved) == 1
    assert resolved[0].source_repo_id == "repository:r_deployments"
    assert resolved[0].target_repo_id == "repository:r_payments"
    assert resolved[0].confidence == 1.0
    assert resolved[0].resolution_source == "assertion"
    assert resolved[0].evidence_count == 0


def test_resolve_repository_relationships_latest_decision_wins_for_conflicts() -> None:
    """Conflicting review actions should honor the most recent decision for an edge."""

    assertions = [
        RelationshipAssertion(
            source_repo_id="repository:r_deployments",
            target_repo_id="repository:r_payments",
            relationship_type="DEPENDS_ON",
            decision="reject",
            reason="Older false-positive review",
            actor="alice",
        ),
        RelationshipAssertion(
            source_repo_id="repository:r_deployments",
            target_repo_id="repository:r_payments",
            relationship_type="DEPENDS_ON",
            decision="assert",
            reason="Later validated dependency",
            actor="bob",
        ),
    ]

    candidates, resolved = resolve_repository_relationships([], assertions)

    assert candidates == []
    assert len(resolved) == 1
    assert resolved[0].source_repo_id == "repository:r_deployments"
    assert resolved[0].target_repo_id == "repository:r_payments"
    assert resolved[0].resolution_source == "assertion"
    assert resolved[0].rationale == "Later validated dependency"


def test_project_resolved_relationships_raises_when_repository_nodes_are_missing() -> (
    None
):
    """Projection must fail before activation when graph repository nodes are absent."""

    class FakeResult:
        def __init__(self, rows):
            self._rows = rows

        def data(self):
            return self._rows

    class FakeTx:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, object]]] = []

        def run(self, query: str, **params: object):
            self.calls.append((query, params))
            if "UNWIND $repo_ids AS repo_id" in query:
                return FakeResult(
                    [
                        {"repo_id": "repository:r_missing", "repo_count": 0},
                    ]
                )
            return FakeResult([])

    class FakeSession:
        def __init__(self) -> None:
            self.tx = FakeTx()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute_write(self, callback):
            return callback(self.tx)

    class FakeDriver:
        def session(self):
            return FakeSession()

    db_manager = SimpleNamespace(get_driver=lambda: FakeDriver())
    resolved = [
        ResolvedRelationship(
            source_repo_id="repository:r_missing",
            target_repo_id="repository:r_present",
            relationship_type="DEPENDS_ON",
            confidence=1.0,
            evidence_count=0,
            rationale="Manual assertion",
            resolution_source="assertion",
        )
    ]

    with pytest.raises(RuntimeError, match="missing Repository nodes"):
        project_resolved_relationships(
            db_manager=db_manager,
            generation_id="generation_123",
            resolved=resolved,
        )


def test_resolve_repository_relationships_for_committed_repositories_activates_after_projection(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A new generation should become active only after Neo4j projection succeeds."""

    repo_path = tmp_path / "payments-api"
    repo_path.mkdir()
    call_order: list[str] = []

    class FakeStore:
        enabled = True

        def list_relationship_assertions(self, *, relationship_type: str):
            call_order.append(f"assertions:{relationship_type}")
            return []

        def replace_generation(self, **_kwargs):
            call_order.append("replace_generation")
            return ResolutionGeneration(
                generation_id="generation_123",
                scope="repo_dependencies",
                run_id="run_123",
                status="pending",
            )

        def activate_generation(self, *, scope: str, generation_id: str) -> None:
            call_order.append(f"activate:{scope}:{generation_id}")

    monkeypatch.setattr(
        "platform_context_graph.relationships.resolver.get_relationship_store",
        lambda: FakeStore(),
    )
    monkeypatch.setattr(
        "platform_context_graph.relationships.resolver.build_repository_checkouts",
        lambda repo_paths: [
            RepositoryCheckout(
                checkout_id="checkout_123",
                logical_repo_id="repository:r_payments",
                repo_name=Path(next(iter(repo_paths))).name,
                checkout_path=str(repo_path),
            )
        ],
    )
    monkeypatch.setattr(
        "platform_context_graph.relationships.resolver.discover_repository_dependency_evidence",
        lambda _driver: [
            RelationshipEvidenceFact(
                evidence_kind="WORKLOAD_DEPENDS_ON",
                relationship_type="DEPENDS_ON",
                source_repo_id="repository:r_payments",
                target_repo_id="repository:r_orders",
                confidence=0.9,
                rationale="Workload dependency implies repository dependency",
            )
        ],
    )
    monkeypatch.setattr(
        "platform_context_graph.relationships.resolver.project_resolved_relationships",
        lambda **_kwargs: call_order.append("project"),
    )

    stats = resolve_repository_relationships_for_committed_repositories(
        builder=SimpleNamespace(driver=object(), db_manager=object()),
        committed_repo_paths=[repo_path],
        run_id="run_123",
        info_logger_fn=MagicMock(),
    )

    assert stats == {
        "checkouts": 1,
        "evidence_facts": 1,
        "candidates": 1,
        "resolved_relationships": 1,
    }
    assert call_order == [
        "assertions:DEPENDS_ON",
        "replace_generation",
        "project",
        "activate:repo_dependencies:generation_123",
    ]


def test_project_resolved_relationships_emits_generation_trace_attributes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Projection spans should carry scope and generation correlation fields."""

    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    observability = importlib.import_module("platform_context_graph.observability")
    observability.reset_observability_for_tests()
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    monkeypatch.setenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "http://otel-collector.monitoring.svc.cluster.local:4317",
    )
    observability.configure_test_exporters(
        span_exporter=InMemorySpanExporter(),
        metric_reader=InMemoryMetricReader(),
    )
    span_exporter = InMemorySpanExporter()
    observability.configure_test_exporters(
        span_exporter=span_exporter,
        metric_reader=InMemoryMetricReader(),
    )
    observability.initialize_observability(component="bootstrap-index")

    class FakeResult:
        def __init__(self, rows):
            self._rows = rows

        def data(self):
            return self._rows

    class FakeTx:
        def run(self, query: str, **params: object):
            if "UNWIND $repo_ids AS repo_id" in query:
                repo_ids = params["repo_ids"]
                return FakeResult(
                    [{"repo_id": repo_id, "repo_count": 1} for repo_id in repo_ids]
                )
            return FakeResult([])

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute_write(self, callback):
            return callback(FakeTx())

    class FakeDriver:
        def session(self):
            return FakeSession()

    project_resolved_relationships(
        db_manager=SimpleNamespace(get_driver=lambda: FakeDriver()),
        generation_id="generation_123",
        resolved=[
            ResolvedRelationship(
                source_repo_id="repository:r_payments",
                target_repo_id="repository:r_orders",
                relationship_type="DEPENDS_ON",
                confidence=0.9,
                evidence_count=1,
                rationale="Runtime dependency",
                resolution_source="inferred",
            )
        ],
    )

    spans = span_exporter.get_finished_spans()
    projection_span = next(
        span for span in spans if span.name == "pcg.relationships.project"
    )
    assert projection_span.attributes["pcg.relationships.scope"] == "repo_dependencies"
    assert projection_span.attributes["pcg.relationships.generation_id"] == (
        "generation_123"
    )
    assert projection_span.attributes["pcg.relationships.resolved_count"] == 1


def test_resolve_repository_relationships_emits_json_logs_and_trace_context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Relationship resolution should emit structured JSON logs linked to a trace."""

    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    observability = importlib.import_module("platform_context_graph.observability")
    observability.reset_observability_for_tests()
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    monkeypatch.setenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "http://otel-collector.monitoring.svc.cluster.local:4317",
    )
    monkeypatch.setenv("ENABLE_APP_LOGS", "INFO")
    monkeypatch.setenv("PCG_LOG_FORMAT", "json")

    span_exporter = InMemorySpanExporter()
    observability.configure_test_exporters(
        span_exporter=span_exporter,
        metric_reader=InMemoryMetricReader(),
    )
    runtime = observability.initialize_observability(component="bootstrap-index")
    buffer = io.StringIO()
    observability.configure_logging(
        component="bootstrap-index",
        runtime_role="bootstrap-index",
        stream=buffer,
    )

    repo_path = tmp_path / "payments-api"
    repo_path.mkdir()

    class FakeStore:
        enabled = True

        def list_relationship_assertions(self, *, relationship_type: str):
            assert relationship_type == "DEPENDS_ON"
            return []

        def replace_generation(self, **_kwargs):
            return ResolutionGeneration(
                generation_id="generation_123",
                scope="repo_dependencies",
                run_id="run_123",
                status="pending",
            )

        def activate_generation(self, *, scope: str, generation_id: str) -> None:
            assert scope == "repo_dependencies"
            assert generation_id == "generation_123"

    monkeypatch.setattr(
        "platform_context_graph.relationships.resolver.get_relationship_store",
        lambda: FakeStore(),
    )
    monkeypatch.setattr(
        "platform_context_graph.relationships.resolver.build_repository_checkouts",
        lambda repo_paths: [
            RepositoryCheckout(
                checkout_id="checkout_123",
                logical_repo_id="repository:r_payments",
                repo_name=Path(next(iter(repo_paths))).name,
                checkout_path=str(repo_path),
            )
        ],
    )
    monkeypatch.setattr(
        "platform_context_graph.relationships.resolver.discover_repository_dependency_evidence",
        lambda _driver: [
            RelationshipEvidenceFact(
                evidence_kind="WORKLOAD_DEPENDS_ON",
                relationship_type="DEPENDS_ON",
                source_repo_id="repository:r_payments",
                target_repo_id="repository:r_orders",
                confidence=0.9,
                rationale="Workload dependency implies repository dependency",
            )
        ],
    )
    monkeypatch.setattr(
        "platform_context_graph.relationships.resolver.project_resolved_relationships",
        lambda **_kwargs: None,
    )

    with runtime.request_context(component="bootstrap-index"):
        resolve_repository_relationships_for_committed_repositories(
            builder=SimpleNamespace(driver=object(), db_manager=object()),
            committed_repo_paths=[repo_path],
            run_id="run_123",
            info_logger_fn=info_logger,
        )

    records = [
        json.loads(line) for line in buffer.getvalue().splitlines() if line.strip()
    ]
    started_record = next(
        record
        for record in records
        if record.get("event_name") == "relationships.resolve.started"
    )
    completed_record = next(
        record
        for record in records
        if record.get("event_name") == "relationships.resolve.completed"
    )
    assert started_record["component"] == "bootstrap-index"
    assert isinstance(started_record["trace_id"], str) and started_record["trace_id"]
    assert isinstance(started_record["span_id"], str) and started_record["span_id"]
    assert started_record["extra_keys"]["scope"] == "repo_dependencies"
    assert started_record["extra_keys"]["run_id"] == "run_123"
    assert completed_record["extra_keys"]["generation_id"] == "generation_123"
    assert completed_record["extra_keys"]["resolved_count"] == 1
    assert completed_record["trace_id"] == started_record["trace_id"]

    spans = span_exporter.get_finished_spans()
    resolve_span = next(
        span
        for span in spans
        if span.name == "pcg.relationships.resolve_repository_dependencies"
    )
    assert resolve_span.attributes["pcg.relationships.run_id"] == "run_123"
    assert resolve_span.attributes["pcg.relationships.scope"] == "repo_dependencies"
    assert resolve_span.attributes["pcg.relationships.repo_count"] == 1
