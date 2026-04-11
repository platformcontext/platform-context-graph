from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from platform_context_graph.cli.main import app

runner = CliRunner()


def _combined_output(result) -> str:
    """Return combined stdout/stderr CLI output for assertions."""

    return f"{result.stdout}{result.stderr}"


class _Response:
    def __init__(self, payload: object, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self) -> object:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(self.text)


@patch("platform_context_graph.cli.remote.requests.request")
@patch("platform_context_graph.cli.main._load_credentials")
def test_index_status_uses_remote_api_when_service_url_is_set(
    mock_load_credentials: MagicMock,
    mock_request: MagicMock,
) -> None:
    """`pcg index-status --service-url` should query the remote HTTP API."""

    mock_request.return_value = _Response(
        {
            "run_id": "run-123",
            "root_path": "/srv/repos",
            "status": "running",
            "finalization_status": "pending",
            "repository_count": 10,
            "completed_repositories": 4,
            "failed_repositories": 0,
            "pending_repositories": 6,
        }
    )

    result = runner.invoke(
        app,
        ["index-status", "--service-url", "https://pcg.example.com"],
    )

    assert result.exit_code == 0
    assert "run-123" in _combined_output(result)
    mock_load_credentials.assert_not_called()
    mock_request.assert_called_once()
    _args, kwargs = mock_request.call_args
    assert kwargs["method"] == "GET"
    assert kwargs["url"] == "https://pcg.example.com/api/v0/index-status"


@patch("platform_context_graph.cli.remote.requests.request")
def test_workspace_status_uses_profile_backed_remote_target(
    mock_request: MagicMock,
    monkeypatch,
) -> None:
    """Remote CLI should resolve service URL and token from the selected profile."""

    monkeypatch.setenv("PCG_SERVICE_URL_OPS_QA", "https://pcg.example.com")
    monkeypatch.setenv("PCG_API_KEY_OPS_QA", "secret-token")
    mock_request.return_value = _Response(
        {
            "ingester": "repository",
            "status": "indexing",
            "active_run_id": "run-ops",
            "repository_count": 42,
            "completed_repositories": 10,
            "failed_repositories": 0,
            "pending_repositories": 32,
        }
    )

    result = runner.invoke(app, ["workspace", "status", "--profile", "ops-qa"])

    assert result.exit_code == 0
    assert "run-ops" in _combined_output(result)
    _args, kwargs = mock_request.call_args
    assert kwargs["headers"]["Authorization"] == "Bearer secret-token"
    assert kwargs["url"] == "https://pcg.example.com/api/v0/ingesters/repository"


@patch("platform_context_graph.cli.remote.requests.request")
def test_admin_reindex_posts_remote_request(
    mock_request: MagicMock,
) -> None:
    """`pcg admin reindex` should enqueue a remote reindex request."""

    mock_request.return_value = _Response(
        {
            "status": "accepted",
            "ingester": "repository",
            "request_token": "reindex-123",
            "request_state": "pending",
            "scope": "workspace",
            "force": True,
            "run_id": None,
        }
    )

    result = runner.invoke(
        app,
        ["admin", "reindex", "--service-url", "https://pcg.example.com"],
    )

    assert result.exit_code == 0
    assert "reindex-123" in _combined_output(result)
    _args, kwargs = mock_request.call_args
    assert kwargs["method"] == "POST"
    assert kwargs["url"] == "https://pcg.example.com/api/v0/admin/reindex"
    assert kwargs["json"] == {
        "ingester": "repository",
        "scope": "workspace",
        "force": True,
    }


@patch("platform_context_graph.cli.remote.requests.request")
def test_admin_tuning_report_fetches_remote_report(
    mock_request: MagicMock,
) -> None:
    """`pcg admin tuning-report` should fetch the deterministic admin report."""

    mock_request.return_value = _Response(
        {
            "projection_domains": ["repo_dependency", "workload_dependency"],
            "scenarios": [{"setting": "4x2", "round_count": 2}],
            "recommended": {"setting": "4x2", "round_count": 2},
        }
    )

    result = runner.invoke(
        app,
        [
            "admin",
            "tuning-report",
            "--service-url",
            "https://pcg.example.com",
            "--include-platform",
        ],
    )

    assert result.exit_code == 0
    assert "Recommended setting: 4x2" in _combined_output(result)
    _args, kwargs = mock_request.call_args
    assert kwargs["method"] == "GET"
    assert (
        kwargs["url"]
        == "https://pcg.example.com/api/v0/admin/shared-projection/tuning-report"
    )
    assert kwargs["params"] == {"include_platform": "true"}


@patch("platform_context_graph.cli.remote.requests.request")
def test_admin_facts_replay_posts_remote_request(
    mock_request: MagicMock,
) -> None:
    """`pcg admin facts replay` should post the replay selector payload."""

    mock_request.return_value = _Response(
        {
            "status": "replayed",
            "replayed_count": 1,
            "work_item_ids": ["work-1"],
        }
    )

    result = runner.invoke(
        app,
        [
            "admin",
            "facts",
            "replay",
            "--service-url",
            "https://pcg.example.com",
            "--work-item-id",
            "work-1",
            "--failure-class",
            "timeout",
            "--note",
            "operator replay",
        ],
    )

    assert result.exit_code == 0
    assert "work-1" in _combined_output(result)
    _args, kwargs = mock_request.call_args
    assert kwargs["method"] == "POST"
    assert kwargs["url"] == "https://pcg.example.com/api/v0/admin/facts/replay"
    assert kwargs["json"] == {
        "work_item_ids": ["work-1"],
        "repository_id": None,
        "source_run_id": None,
        "work_type": None,
        "failure_class": "timeout",
        "operator_note": "operator replay",
        "limit": 100,
    }


def test_admin_facts_replay_requires_one_selector() -> None:
    """The CLI should fail fast when replay is invoked without any selector."""

    result = runner.invoke(
        app,
        [
            "admin",
            "facts",
            "replay",
            "--service-url",
            "https://pcg.example.com",
        ],
    )

    assert result.exit_code == 2
    assert "At least one selector" in _combined_output(result)


@patch("platform_context_graph.cli.remote.requests.request")
def test_admin_facts_list_posts_remote_request(
    mock_request: MagicMock,
) -> None:
    """`pcg admin facts list` should post the work-item query payload."""

    mock_request.return_value = _Response({"count": 1, "items": []})

    result = runner.invoke(
        app,
        [
            "admin",
            "facts",
            "list",
            "--service-url",
            "https://pcg.example.com",
            "--status",
            "failed",
            "--failure-class",
            "timeout",
        ],
    )

    assert result.exit_code == 0
    _args, kwargs = mock_request.call_args
    assert kwargs["method"] == "POST"
    assert (
        kwargs["url"] == "https://pcg.example.com/api/v0/admin/facts/work-items/query"
    )
    assert kwargs["json"] == {
        "statuses": ["failed"],
        "repository_id": None,
        "source_run_id": None,
        "work_type": None,
        "failure_class": "timeout",
        "limit": 100,
    }


@patch("platform_context_graph.cli.remote.requests.request")
def test_admin_facts_decisions_posts_remote_request(
    mock_request: MagicMock,
) -> None:
    """`pcg admin facts decisions` should post the decision query payload."""

    mock_request.return_value = _Response({"count": 1, "decisions": []})

    result = runner.invoke(
        app,
        [
            "admin",
            "facts",
            "decisions",
            "--service-url",
            "https://pcg.example.com",
            "--repository-id",
            "repository:r_payments",
            "--source-run-id",
            "run-123",
            "--decision-type",
            "project_workloads",
            "--include-evidence",
        ],
    )

    assert result.exit_code == 0
    _args, kwargs = mock_request.call_args
    assert kwargs["method"] == "POST"
    assert kwargs["url"] == "https://pcg.example.com/api/v0/admin/facts/decisions/query"
    assert kwargs["json"] == {
        "repository_id": "repository:r_payments",
        "source_run_id": "run-123",
        "decision_type": "project_workloads",
        "include_evidence": True,
        "limit": 100,
    }


@patch("platform_context_graph.cli.remote.requests.request")
def test_admin_facts_dead_letter_posts_remote_request(
    mock_request: MagicMock,
) -> None:
    """`pcg admin facts dead-letter` should post the dead-letter selector payload."""

    mock_request.return_value = _Response({"count": 1, "items": []})

    result = runner.invoke(
        app,
        [
            "admin",
            "facts",
            "dead-letter",
            "--service-url",
            "https://pcg.example.com",
            "--repository-id",
            "repository:r_payments",
            "--failure-class",
            "manual_override",
            "--note",
            "manual stop",
        ],
    )

    assert result.exit_code == 0
    _args, kwargs = mock_request.call_args
    assert kwargs["method"] == "POST"
    assert kwargs["url"] == "https://pcg.example.com/api/v0/admin/facts/dead-letter"
    assert kwargs["json"] == {
        "work_item_ids": None,
        "repository_id": "repository:r_payments",
        "source_run_id": None,
        "work_type": None,
        "failure_class": "manual_override",
        "operator_note": "manual stop",
        "limit": 100,
    }


@patch("platform_context_graph.cli.remote.requests.request")
def test_admin_facts_skip_posts_remote_request(
    mock_request: MagicMock,
) -> None:
    """`pcg admin facts skip` should post the repository skip payload."""

    mock_request.return_value = _Response({"count": 2, "items": []})

    result = runner.invoke(
        app,
        [
            "admin",
            "facts",
            "skip",
            "--service-url",
            "https://pcg.example.com",
            "--repository-id",
            "repository:r_archived",
            "--note",
            "historical residue",
        ],
    )

    assert result.exit_code == 0
    _args, kwargs = mock_request.call_args
    assert kwargs["method"] == "POST"
    assert kwargs["url"] == "https://pcg.example.com/api/v0/admin/facts/skip"
    assert kwargs["json"] == {
        "repository_id": "repository:r_archived",
        "operator_note": "historical residue",
    }


def test_admin_facts_skip_requires_repository_id() -> None:
    """The CLI should reject repository skip without an explicit repo id."""

    result = runner.invoke(
        app,
        [
            "admin",
            "facts",
            "skip",
            "--service-url",
            "https://pcg.example.com",
        ],
    )

    assert result.exit_code == 2
    assert "repository-id" in _combined_output(result)


@patch("platform_context_graph.cli.remote.requests.request")
def test_admin_facts_backfill_posts_remote_request(
    mock_request: MagicMock,
) -> None:
    """`pcg admin facts backfill` should create a remote backfill request."""

    mock_request.return_value = _Response(
        {
            "status": "accepted",
            "backfill_request": {
                "backfill_request_id": "fact-backfill:1",
            },
        }
    )

    result = runner.invoke(
        app,
        [
            "admin",
            "facts",
            "backfill",
            "--service-url",
            "https://pcg.example.com",
            "--repository-id",
            "repository:r_payments",
            "--source-run-id",
            "run-123",
            "--note",
            "refresh after replay",
        ],
    )

    assert result.exit_code == 0
    assert "fact-backfill:1" in _combined_output(result)
    _args, kwargs = mock_request.call_args
    assert kwargs["method"] == "POST"
    assert kwargs["url"] == "https://pcg.example.com/api/v0/admin/facts/backfill"
    assert kwargs["json"] == {
        "repository_id": "repository:r_payments",
        "source_run_id": "run-123",
        "operator_note": "refresh after replay",
    }


def test_admin_facts_backfill_requires_scope_selector() -> None:
    """The CLI should reject unbounded backfill requests."""

    result = runner.invoke(
        app,
        [
            "admin",
            "facts",
            "backfill",
            "--service-url",
            "https://pcg.example.com",
        ],
    )

    assert result.exit_code == 2
    assert "At least one selector" in _combined_output(result)


@patch("platform_context_graph.cli.remote.requests.request")
def test_admin_facts_replay_events_posts_remote_request(
    mock_request: MagicMock,
) -> None:
    """`pcg admin facts replay-events` should query replay audit rows remotely."""

    mock_request.return_value = _Response({"count": 1, "events": []})

    result = runner.invoke(
        app,
        [
            "admin",
            "facts",
            "replay-events",
            "--service-url",
            "https://pcg.example.com",
            "--repository-id",
            "repository:r_payments",
            "--work-item-id",
            "work-1",
            "--failure-class",
            "timeout",
        ],
    )

    assert result.exit_code == 0
    _args, kwargs = mock_request.call_args
    assert kwargs["method"] == "POST"
    assert (
        kwargs["url"]
        == "https://pcg.example.com/api/v0/admin/facts/replay-events/query"
    )
    assert kwargs["json"] == {
        "repository_id": "repository:r_payments",
        "source_run_id": None,
        "work_item_id": "work-1",
        "failure_class": "timeout",
        "limit": 100,
    }


@patch("platform_context_graph.cli.remote.requests.request")
def test_analyze_callers_posts_code_relationship_request(
    mock_request: MagicMock,
) -> None:
    """Remote analyze commands should route through the HTTP code relationship API."""

    mock_request.return_value = _Response(
        {
            "query_type": "find_callers",
            "target": "handle_payment",
            "results": [{"caller_function": "main"}],
            "summary": "Found 1 functions that call 'handle_payment'",
        }
    )

    result = runner.invoke(
        app,
        [
            "analyze",
            "callers",
            "handle_payment",
            "--service-url",
            "https://pcg.example.com",
        ],
    )

    assert result.exit_code == 0
    assert "handle_payment" in _combined_output(result)
    _args, kwargs = mock_request.call_args
    assert kwargs["url"] == "https://pcg.example.com/api/v0/code/relationships"
    assert kwargs["json"]["query_type"] == "find_callers"
    assert kwargs["json"]["target"] == "handle_payment"


@patch("platform_context_graph.cli.remote.requests.request")
def test_find_name_posts_remote_search_request(
    mock_request: MagicMock,
) -> None:
    """Remote find-by-name should query the HTTP search API."""

    mock_request.return_value = _Response(
        {"ranked_results": [{"name": "handle_payment", "entity_type": "Function"}]}
    )

    result = runner.invoke(
        app,
        [
            "find",
            "name",
            "handle_payment",
            "--service-url",
            "https://pcg.example.com",
        ],
    )

    assert result.exit_code == 0
    assert "handle_payment" in _combined_output(result)
    _args, kwargs = mock_request.call_args
    assert kwargs["url"] == "https://pcg.example.com/api/v0/code/search"
    assert kwargs["json"]["query"] == "handle_payment"
    assert kwargs["json"]["exact"] is True
