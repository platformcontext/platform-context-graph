"""Integration coverage for remote workspace status rendering."""

from __future__ import annotations

from unittest.mock import MagicMock
from unittest.mock import patch

from typer.testing import CliRunner

from platform_context_graph.cli.main import app

runner = CliRunner()


class _Response:
    """Minimal requests response stub for remote CLI tests."""

    def __init__(self, payload: object, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self) -> object:
        """Return the configured JSON payload."""

        return self._payload

    def raise_for_status(self) -> None:
        """Raise for non-success responses."""

        if self.status_code >= 400:
            raise RuntimeError(self.text)


@patch("platform_context_graph.cli.remote.requests.request")
def test_workspace_status_renders_shared_projection_tuning(
    mock_request: MagicMock,
) -> None:
    """Remote workspace status should surface the shared-write recommendation."""

    mock_request.return_value = _Response(
        {
            "ingester": "repository",
            "status": "indexing",
            "active_run_id": "run-ops",
            "repository_count": 42,
            "completed_repositories": 10,
            "failed_repositories": 0,
            "pending_repositories": 32,
            "shared_projection_pending_repositories": 2,
            "shared_projection_tuning": {
                "recommended": {"setting": "4x2"},
                "current_pending_intents": 5,
                "current_oldest_pending_age_seconds": 33.0,
            },
            "truth_summary": {
                "state": "degraded",
                "reducer_queue_available": True,
                "projection_decision_store_available": True,
                "pending_reducer_work_items": 5,
                "shared_projection_backlog_count": 1,
                "shared_projection_domains": ["repo_dependency"],
                "shared_projection_oldest_pending_age_seconds": 33.0,
                "reason": "5 reducer work item(s) still awaiting follow-up; 1 shared projection domain(s) still pending",
            },
        }
    )

    result = runner.invoke(
        app,
        ["workspace", "status", "--service-url", "https://pcg.example.com"],
    )

    assert result.exit_code == 0
    output = f"{result.stdout}{result.stderr}"
    assert "Shared follow-up: repos=2 intents=5 oldest=33.0s" in output
    assert "Recommended tuning: 4x2" in output
    assert "Truth summary: degraded" in output
