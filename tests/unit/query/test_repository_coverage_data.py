"""Unit tests for durable repository coverage payload normalization."""

from __future__ import annotations

from datetime import datetime, timezone

from platform_context_graph.query.repositories import coverage_data


def test_get_repository_coverage_payload_normalizes_datetimes(
    monkeypatch,
) -> None:
    """Coverage payloads should serialize timestamps before MCP wraps them."""

    monkeypatch.setattr(
        coverage_data,
        "get_runtime_repository_coverage",
        lambda **_kwargs: {
            "run_id": "run-123",
            "repo_id": "repository:r_ab12cd34",
            "repo_name": "payments-api",
            "repo_path": "/data/repos/payments-api",
            "status": "completed",
            "phase": "completed",
            "finalization_status": "completed",
            "graph_available": True,
            "server_content_available": True,
            "discovered_file_count": 10,
            "graph_recursive_file_count": 9,
            "content_file_count": 8,
            "content_entity_count": 7,
            "root_file_count": 2,
            "root_directory_count": 3,
            "top_level_function_count": 4,
            "class_method_count": 5,
            "total_function_count": 9,
            "class_count": 1,
            "last_error": None,
            "created_at": datetime(2026, 3, 24, 12, 0, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 3, 24, 12, 1, tzinfo=timezone.utc),
            "commit_finished_at": datetime(2026, 3, 24, 12, 2, tzinfo=timezone.utc),
            "finalization_finished_at": datetime(
                2026, 3, 24, 12, 3, tzinfo=timezone.utc
            ),
        },
    )

    result = coverage_data.get_repository_coverage_payload(
        repo_id="repository:r_ab12cd34"
    )

    assert result["created_at"] == "2026-03-24T12:00:00+00:00"
    assert result["updated_at"] == "2026-03-24T12:01:00+00:00"
    assert result["commit_finished_at"] == "2026-03-24T12:02:00+00:00"
    assert result["finalization_finished_at"] == "2026-03-24T12:03:00+00:00"
    assert result["summary"]["updated_at"] == "2026-03-24T12:01:00+00:00"


def test_list_repository_coverage_payload_normalizes_datetimes(
    monkeypatch,
) -> None:
    """Coverage listing payloads should be JSON-serializable for MCP transport."""

    monkeypatch.setattr(
        coverage_data,
        "list_runtime_repository_coverage",
        lambda **_kwargs: [
            {
                "run_id": "run-123",
                "repo_id": "repository:r_ab12cd34",
                "repo_name": "payments-api",
                "repo_path": "/data/repos/payments-api",
                "status": "commit_incomplete",
                "phase": "committing",
                "finalization_status": "pending",
                "graph_available": True,
                "server_content_available": True,
                "discovered_file_count": 10,
                "graph_recursive_file_count": 5,
                "content_file_count": 4,
                "content_entity_count": 3,
                "root_file_count": 2,
                "root_directory_count": 3,
                "top_level_function_count": 4,
                "class_method_count": 1,
                "total_function_count": 5,
                "class_count": 1,
                "last_error": None,
                "created_at": datetime(2026, 3, 24, 12, 0, tzinfo=timezone.utc),
                "updated_at": datetime(2026, 3, 24, 12, 1, tzinfo=timezone.utc),
                "commit_finished_at": None,
                "finalization_finished_at": None,
            }
        ],
    )

    result = coverage_data.list_repository_coverage_payload(run_id="run-123")

    assert result["repositories"][0]["created_at"] == "2026-03-24T12:00:00+00:00"
    assert result["repositories"][0]["updated_at"] == "2026-03-24T12:01:00+00:00"
    assert result["repositories"][0]["summary"]["updated_at"] == (
        "2026-03-24T12:01:00+00:00"
    )


def test_coverage_summary_reports_graph_partial_gaps(monkeypatch) -> None:
    """Coverage summaries should expose graph and content gaps clearly."""

    monkeypatch.setattr(
        coverage_data,
        "get_runtime_repository_coverage",
        lambda **_kwargs: {
            "run_id": "run-graph-partial",
            "repo_id": "repository:r_api_node_boats",
            "repo_name": "api-node-boats",
            "repo_path": "/data/repos/api-node-boats",
            "status": "completed",
            "phase": "completed",
            "finalization_status": "completed",
            "graph_available": True,
            "server_content_available": False,
            "discovered_file_count": 196,
            "graph_recursive_file_count": 12,
            "content_file_count": 0,
            "content_entity_count": 0,
            "root_file_count": 12,
            "root_directory_count": 5,
            "top_level_function_count": 0,
            "class_method_count": 0,
            "total_function_count": 0,
            "class_count": 0,
            "last_error": None,
            "created_at": datetime(2026, 3, 26, 12, 0, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 3, 26, 12, 1, tzinfo=timezone.utc),
            "commit_finished_at": datetime(2026, 3, 26, 12, 2, tzinfo=timezone.utc),
            "finalization_finished_at": datetime(
                2026, 3, 26, 12, 3, tzinfo=timezone.utc
            ),
        },
    )

    result = coverage_data.get_repository_coverage_payload(
        repo_id="repository:r_api_node_boats"
    )

    assert result["summary"]["completeness_state"] == "graph_partial"
    assert result["summary"]["graph_gap_count"] == 184
    assert result["summary"]["content_gap_count"] == 12
    assert result["completeness_state"] == "graph_partial"
    assert result["graph_gap_count"] == 184
    assert result["content_gap_count"] == 12


def test_coverage_summary_reports_failed_state(monkeypatch) -> None:
    """Failed runs should report failed completeness regardless of counters."""

    monkeypatch.setattr(
        coverage_data,
        "get_runtime_repository_coverage",
        lambda **_kwargs: {
            "run_id": "run-failed",
            "repo_id": "repository:r_failed",
            "repo_name": "failed-repo",
            "repo_path": "/data/repos/failed-repo",
            "status": "failed",
            "phase": "parsing",
            "finalization_status": "failed",
            "graph_available": False,
            "server_content_available": False,
            "discovered_file_count": 40,
            "graph_recursive_file_count": 3,
            "content_file_count": 0,
            "content_entity_count": 0,
            "root_file_count": 1,
            "root_directory_count": 1,
            "top_level_function_count": 0,
            "class_method_count": 0,
            "total_function_count": 0,
            "class_count": 0,
            "last_error": "parse failure",
            "created_at": datetime(2026, 3, 26, 12, 0, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 3, 26, 12, 1, tzinfo=timezone.utc),
            "commit_finished_at": None,
            "finalization_finished_at": None,
        },
    )

    result = coverage_data.get_repository_coverage_payload(
        repo_id="repository:r_failed"
    )

    assert result["summary"]["completeness_state"] == "failed"
    assert result["completeness_state"] == "failed"


def test_coverage_summary_reports_limitations_for_partial_rows() -> None:
    """Partial coverage should keep the limitations list truthful."""

    summary = coverage_data.coverage_summary_from_row(
        {
            "run_id": "run-partial",
            "status": "completed",
            "phase": "completed",
            "finalization_status": "completed",
            "graph_available": True,
            "server_content_available": False,
            "discovered_file_count": 12,
            "graph_recursive_file_count": 4,
            "content_file_count": 2,
            "content_entity_count": 0,
            "root_file_count": 1,
            "root_directory_count": 1,
            "top_level_function_count": 0,
            "class_method_count": 0,
            "total_function_count": 0,
            "class_count": 0,
            "last_error": None,
            "updated_at": None,
        }
    )

    assert summary is not None
    assert summary["completeness_state"] == "graph_partial"
    assert summary["limitations"] == ["graph_partial", "content_partial"]


def test_coverage_summary_reports_finalization_incomplete_limitation() -> None:
    """Completed counts should still surface pending finalization truthfully."""

    summary = coverage_data.coverage_summary_from_row(
        {
            "run_id": "run-finalization-pending",
            "status": "completed",
            "phase": "completed",
            "finalization_status": "pending",
            "graph_available": True,
            "server_content_available": True,
            "discovered_file_count": 199,
            "graph_recursive_file_count": 199,
            "content_file_count": 199,
            "content_entity_count": 3106,
            "root_file_count": 12,
            "root_directory_count": 6,
            "top_level_function_count": 347,
            "class_method_count": 0,
            "total_function_count": 347,
            "class_count": 0,
            "last_error": None,
            "updated_at": None,
        }
    )

    assert summary is not None
    assert summary["completeness_state"] == "complete"
    assert summary["limitations"] == ["finalization_incomplete"]
