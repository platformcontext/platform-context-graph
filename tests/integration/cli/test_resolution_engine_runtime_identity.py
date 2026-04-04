"""CLI regression coverage for resolution-engine runtime identity."""

from __future__ import annotations

import os
from unittest.mock import patch

from typer.testing import CliRunner

from platform_context_graph.cli.main import app

runner = CliRunner()


@patch("platform_context_graph.resolution.orchestration.start_resolution_engine")
@patch("platform_context_graph.facts.state.get_projection_decision_store")
@patch("platform_context_graph.facts.state.get_fact_work_queue")
@patch("platform_context_graph.facts.state.get_fact_store")
@patch("platform_context_graph.core.get_database_manager")
@patch("platform_context_graph.tools.graph_builder.GraphBuilder")
@patch("platform_context_graph.core.jobs.JobManager")
@patch("platform_context_graph.cli.commands.runtime.initialize_observability")
def test_internal_resolution_engine_initializes_identity_before_services(
    mock_initialize_observability,
    mock_job_manager,
    mock_graph_builder,
    mock_get_database_manager,
    mock_get_fact_store,
    mock_get_fact_work_queue,
    mock_get_projection_decision_store,
    mock_start_resolution_engine,
) -> None:
    """Initialize resolution-engine observability before service construction."""

    call_order: list[str] = []

    mock_get_fact_work_queue.return_value = object()
    mock_get_fact_store.return_value = object()
    mock_get_projection_decision_store.return_value = object()
    mock_get_database_manager.return_value = object()
    mock_job_manager.return_value = object()
    mock_graph_builder.return_value = object()

    mock_initialize_observability.side_effect = (
        lambda **_kwargs: call_order.append("initialize_observability")
    )
    mock_get_database_manager.side_effect = (
        lambda: call_order.append("get_database_manager")
        or object()
    )

    result = runner.invoke(app, ["internal", "resolution-engine"])

    assert result.exit_code == 0
    assert call_order == [
        "initialize_observability",
        "get_database_manager",
    ]
    mock_initialize_observability.assert_called_once_with(component="resolution-engine")
    mock_start_resolution_engine.assert_called_once()


@patch("platform_context_graph.resolution.orchestration.start_resolution_engine")
@patch("platform_context_graph.facts.state.get_projection_decision_store")
@patch("platform_context_graph.facts.state.get_fact_work_queue")
@patch("platform_context_graph.facts.state.get_fact_store")
@patch("platform_context_graph.core.get_database_manager")
@patch("platform_context_graph.tools.graph_builder.GraphBuilder")
@patch("platform_context_graph.core.jobs.JobManager")
@patch("platform_context_graph.cli.commands.runtime.initialize_observability")
def test_internal_resolution_engine_sets_resolution_engine_runtime_role(
    mock_initialize_observability,
    mock_job_manager,
    mock_graph_builder,
    mock_get_database_manager,
    mock_get_fact_store,
    mock_get_fact_work_queue,
    mock_get_projection_decision_store,
    mock_start_resolution_engine,
    monkeypatch,
) -> None:
    """Set the standalone runtime role before bootstrapping the engine."""

    mock_get_fact_work_queue.return_value = object()
    mock_get_fact_store.return_value = object()
    mock_get_projection_decision_store.return_value = object()
    mock_get_database_manager.return_value = object()
    mock_job_manager.return_value = object()
    mock_graph_builder.return_value = object()
    monkeypatch.delenv("PCG_RUNTIME_ROLE", raising=False)

    result = runner.invoke(app, ["internal", "resolution-engine"])

    assert result.exit_code == 0
    assert mock_initialize_observability.called
    assert os.environ["PCG_RUNTIME_ROLE"] == "resolution-engine"
