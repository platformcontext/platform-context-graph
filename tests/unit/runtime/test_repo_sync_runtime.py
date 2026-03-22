from __future__ import annotations

import importlib
import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytest.importorskip("opentelemetry.sdk")
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


def _metric_points(
    reader: InMemoryMetricReader,
) -> list[tuple[str, dict[str, object], object]]:
    points: list[tuple[str, dict[str, object], object]] = []
    metrics_data = reader.get_metrics_data()
    for resource_metric in metrics_data.resource_metrics:
        for scope_metric in resource_metric.scope_metrics:
            for metric in scope_metric.metrics:
                for point in metric.data.data_points:
                    points.append(
                        (
                            metric.name,
                            dict(point.attributes),
                            getattr(point, "value", None),
                        )
                    )
    return points


def _write_active_lock(lock_dir: Path) -> None:
    """Create a live-looking workspace lock metadata file for contention tests."""

    lock_dir.mkdir(parents=True, exist_ok=True)
    (lock_dir / "lock.json").write_text(
        json.dumps(
            {
                "component": "repo-sync",
                "pid": 1234,
                "hostname": "test-host",
                "heartbeat_at": datetime.now(timezone.utc).isoformat(),
            }
        ),
        encoding="utf-8",
    )


def _write_stale_lock(lock_dir: Path) -> None:
    """Create a stale workspace lock metadata file."""

    lock_dir.mkdir(parents=True, exist_ok=True)
    (lock_dir / "lock.json").write_text(
        json.dumps(
            {
                "component": "bootstrap-index",
                "pid": 1234,
                "hostname": "test-host",
                "heartbeat_at": "2000-01-01T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )


def test_bootstrap_index_copies_filesystem_repos_and_emits_metrics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observability = importlib.import_module("platform_context_graph.observability")
    repo_sync = importlib.import_module("platform_context_graph.runtime.repo_sync")
    observability.reset_observability_for_tests()

    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    monkeypatch.setenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "http://otel-collector.monitoring.svc.cluster.local:4317",
    )

    reader = InMemoryMetricReader()
    observability.initialize_observability(
        component="bootstrap-index",
        metric_reader=reader,
        span_exporter=InMemorySpanExporter(),
    )

    source_root = tmp_path / "fixtures"
    (source_root / "service-a").mkdir(parents=True)
    (source_root / "service-a" / "main.py").write_text("print('a')\n")
    (source_root / "service-b").mkdir(parents=True)
    (source_root / "service-b" / "main.py").write_text("print('b')\n")

    config = repo_sync.RepoSyncConfig(
        repos_dir=tmp_path / "workspace" / "repos",
        source_mode="filesystem",
        git_auth_method="none",
        github_org=None,
        repositories=[],
        filesystem_root=source_root,
        clone_depth=1,
        repo_limit=100,
        sync_lock_dir=tmp_path / "workspace" / "repos" / ".pcg-sync.lock",
        component="bootstrap-index",
    )

    captured: dict[str, object] = {}

    def fake_index_workspace(workspace: Path) -> None:
        captured["workspace"] = workspace
        captured["points"] = _metric_points(reader)

    result = repo_sync.run_bootstrap_index(config, index_workspace=fake_index_workspace)

    assert result.discovered == 2
    assert result.indexed == 2
    assert captured["workspace"] == config.repos_dir
    assert (config.repos_dir / "service-a" / "main.py").exists()
    assert (config.repos_dir / "service-b" / "main.py").exists()
    assert any(
        metric_name == "pcg_index_repositories_total"
        and attrs.get("phase") == "indexed"
        and value == 2
        for metric_name, attrs, value in captured["points"]
    )


def test_bootstrap_index_ignores_dangling_symlinks_in_filesystem_mode(
    tmp_path: Path,
) -> None:
    repo_sync = importlib.import_module("platform_context_graph.runtime.repo_sync")

    source_root = tmp_path / "fixtures"
    repo_dir = source_root / "service-a"
    repo_dir.mkdir(parents=True)
    (repo_dir / "main.py").write_text("print('a')\n")

    broken_link = repo_dir / "missing.tpl"
    try:
        broken_link.symlink_to("does-not-exist.tpl")
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"symlinks unavailable in test environment: {exc}")

    config = repo_sync.RepoSyncConfig(
        repos_dir=tmp_path / "workspace" / "repos",
        source_mode="filesystem",
        git_auth_method="none",
        github_org=None,
        repositories=[],
        filesystem_root=source_root,
        clone_depth=1,
        repo_limit=100,
        sync_lock_dir=tmp_path / "workspace" / "repos" / ".pcg-sync.lock",
        component="bootstrap-index",
    )

    result = repo_sync.run_bootstrap_index(config, index_workspace=lambda _workspace: None)

    assert result.discovered == 1
    assert result.indexed == 1
    assert (config.repos_dir / "service-a" / "main.py").exists()
    assert not (config.repos_dir / "service-a" / "missing.tpl").exists()


def test_repo_sync_cycle_records_lock_contention_skip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observability = importlib.import_module("platform_context_graph.observability")
    repo_sync = importlib.import_module("platform_context_graph.runtime.repo_sync")
    observability.reset_observability_for_tests()

    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    monkeypatch.setenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "http://otel-collector.monitoring.svc.cluster.local:4317",
    )

    reader = InMemoryMetricReader()
    observability.initialize_observability(
        component="repo-sync",
        metric_reader=reader,
        span_exporter=InMemorySpanExporter(),
    )

    repos_dir = tmp_path / "workspace" / "repos"
    repos_dir.mkdir(parents=True)
    lock_dir = repos_dir / ".pcg-sync.lock"
    _write_active_lock(lock_dir)

    config = repo_sync.RepoSyncConfig(
        repos_dir=repos_dir,
        source_mode="filesystem",
        git_auth_method="none",
        github_org=None,
        repositories=[],
        filesystem_root=tmp_path / "fixtures",
        clone_depth=1,
        repo_limit=100,
        sync_lock_dir=lock_dir,
        component="repo-sync",
    )

    result = repo_sync.run_repo_sync_cycle(
        config, index_workspace=lambda _workspace: pytest.fail("index should not run")
    )

    assert result.lock_skipped is True
    assert any(
        metric_name == "pcg_index_lock_contention_skips_total"
        and attrs.get("component") == "repo-sync"
        and value == 1
        for metric_name, attrs, value in _metric_points(reader)
    )


def test_bootstrap_index_reaps_stale_empty_lock_and_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bootstrap should recover from a stale lock directory left on disk."""

    repo_sync = importlib.import_module("platform_context_graph.runtime.repo_sync")

    source_root = tmp_path / "fixtures"
    (source_root / "service-a").mkdir(parents=True)
    (source_root / "service-a" / "main.py").write_text("print('a')\n")

    repos_dir = tmp_path / "workspace" / "repos"
    lock_dir = repos_dir / ".pcg-sync.lock"
    lock_dir.mkdir(parents=True)

    config = repo_sync.RepoSyncConfig(
        repos_dir=repos_dir,
        source_mode="filesystem",
        git_auth_method="none",
        github_org=None,
        repositories=[],
        filesystem_root=source_root,
        clone_depth=1,
        repo_limit=100,
        sync_lock_dir=lock_dir,
        component="bootstrap-index",
    )

    called: list[Path] = []
    monkeypatch.setenv("PCG_SYNC_LOCK_STALE_SECONDS", "1")

    result = repo_sync.run_bootstrap_index(
        config,
        index_workspace=lambda workspace: called.append(workspace),
    )

    assert result.discovered == 1
    assert called == [repos_dir]
    assert not lock_dir.exists()


def test_repo_sync_cycle_skips_with_fresh_metadata_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fresh lock metadata should still prevent concurrent sync cycles."""

    repo_sync = importlib.import_module("platform_context_graph.runtime.repo_sync")

    repos_dir = tmp_path / "workspace" / "repos"
    repos_dir.mkdir(parents=True)
    lock_dir = repos_dir / ".pcg-sync.lock"
    _write_active_lock(lock_dir)
    monkeypatch.setenv("PCG_SYNC_LOCK_STALE_SECONDS", "600")

    config = repo_sync.RepoSyncConfig(
        repos_dir=repos_dir,
        source_mode="filesystem",
        git_auth_method="none",
        github_org=None,
        repositories=[],
        filesystem_root=tmp_path / "fixtures",
        clone_depth=1,
        repo_limit=100,
        sync_lock_dir=lock_dir,
        component="repo-sync",
    )

    result = repo_sync.run_repo_sync_cycle(
        config, index_workspace=lambda _workspace: pytest.fail("index should not run")
    )

    assert result.lock_skipped is True


def test_bootstrap_index_reaps_stale_metadata_lock_and_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bootstrap should recover from stale lock metadata left on disk."""

    repo_sync = importlib.import_module("platform_context_graph.runtime.repo_sync")

    source_root = tmp_path / "fixtures"
    (source_root / "service-a").mkdir(parents=True)
    (source_root / "service-a" / "main.py").write_text("print('a')\n")

    repos_dir = tmp_path / "workspace" / "repos"
    lock_dir = repos_dir / ".pcg-sync.lock"
    _write_stale_lock(lock_dir)

    config = repo_sync.RepoSyncConfig(
        repos_dir=repos_dir,
        source_mode="filesystem",
        git_auth_method="none",
        github_org=None,
        repositories=[],
        filesystem_root=source_root,
        clone_depth=1,
        repo_limit=100,
        sync_lock_dir=lock_dir,
        component="bootstrap-index",
    )

    called: list[Path] = []
    monkeypatch.setenv("PCG_SYNC_LOCK_STALE_SECONDS", "1")

    result = repo_sync.run_bootstrap_index(
        config,
        index_workspace=lambda workspace: called.append(workspace),
    )

    assert result.discovered == 1
    assert called == [repos_dir]
    assert not lock_dir.exists()


def test_bootstrap_index_waits_for_workspace_lock_before_indexing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bootstrap should retry lock acquisition instead of exiting cleanly."""

    bootstrap = importlib.import_module("platform_context_graph.runtime.repo_sync.bootstrap")
    repo_sync = importlib.import_module("platform_context_graph.runtime.repo_sync")

    source_root = tmp_path / "fixtures"
    (source_root / "service-a").mkdir(parents=True)
    (source_root / "service-a" / "main.py").write_text("print('a')\n")

    config = repo_sync.RepoSyncConfig(
        repos_dir=tmp_path / "workspace" / "repos",
        source_mode="filesystem",
        git_auth_method="none",
        github_org=None,
        repositories=[],
        filesystem_root=source_root,
        clone_depth=1,
        repo_limit=100,
        sync_lock_dir=tmp_path / "workspace" / "repos" / ".pcg-sync.lock",
        component="bootstrap-index",
    )

    attempts = {"count": 0}

    @contextmanager
    def _workspace_lock(_config):
        attempts["count"] += 1
        yield attempts["count"] > 1

    sleeps: list[float] = []
    monkeypatch.setattr(bootstrap, "workspace_lock", _workspace_lock)
    monkeypatch.setattr(bootstrap.time, "sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setenv("PCG_BOOTSTRAP_LOCK_RETRY_SECONDS", "1")
    monkeypatch.setenv("PCG_BOOTSTRAP_LOCK_MAX_WAIT_SECONDS", "10")

    result = repo_sync.run_bootstrap_index(config, index_workspace=lambda _workspace: None)

    assert attempts["count"] == 2
    assert sleeps == [1.0]
    assert result.lock_skipped is False


def test_github_app_token_retries_transient_request_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GitHub App token minting should retry transient request failures."""

    github_auth = importlib.import_module(
        "platform_context_graph.runtime.repo_sync.github_auth"
    )

    github_auth.clear_cached_github_app_token()
    monkeypatch.setenv("GITHUB_APP_ID", "123")
    monkeypatch.setenv("GITHUB_APP_INSTALLATION_ID", "456")
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", "test-private-key")
    monkeypatch.setenv("PCG_GITHUB_API_RETRY_ATTEMPTS", "3")
    monkeypatch.setenv("PCG_GITHUB_API_RETRY_DELAY_SECONDS", "1")
    monkeypatch.setattr(github_auth.jwt, "encode", lambda *_args, **_kwargs: "encoded-jwt")

    attempts = {"count": 0}

    def _request(method, url, **_kwargs):
        assert method == "post"
        assert (
            url
            == "https://api.github.com/app/installations/456/access_tokens"
        )
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise github_auth.requests.exceptions.ConnectionError(
                "temporary dns failure"
            )
        response = MagicMock()
        response.json.return_value = {"token": "ghs_test"}
        response.raise_for_status.return_value = None
        return response

    sleeps: list[float] = []
    monkeypatch.setattr(github_auth.requests, "request", _request)
    monkeypatch.setattr(github_auth.time, "sleep", lambda seconds: sleeps.append(seconds))

    token = github_auth.github_app_token()

    assert token == "ghs_test"
    assert attempts["count"] == 3
    assert sleeps == [1.0, 1.0]


def test_github_app_token_is_cached_until_near_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GitHub App tokens should be reused while they remain safely valid."""

    github_auth = importlib.import_module(
        "platform_context_graph.runtime.repo_sync.github_auth"
    )

    github_auth.clear_cached_github_app_token()
    monkeypatch.setenv("GITHUB_APP_ID", "123")
    monkeypatch.setenv("GITHUB_APP_INSTALLATION_ID", "456")
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", "test-private-key")
    monkeypatch.setenv("PCG_GITHUB_APP_TOKEN_REFRESH_SECONDS", "60")
    monkeypatch.setattr(github_auth.jwt, "encode", lambda *_args, **_kwargs: "jwt")

    attempts = {"count": 0}
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

    def _request(method, url, **_kwargs):
        assert method == "post"
        assert "access_tokens" in url
        attempts["count"] += 1
        response = MagicMock()
        response.json.return_value = {"token": "ghs_cached", "expires_at": expires_at}
        response.raise_for_status.return_value = None
        return response

    monkeypatch.setattr(github_auth.requests, "request", _request)

    first = github_auth.github_app_token()
    second = github_auth.github_app_token()

    assert first == "ghs_cached"
    assert second == "ghs_cached"
    assert attempts["count"] == 1


def test_github_app_token_refreshes_when_near_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GitHub App tokens should refresh when they are close to expiring."""

    github_auth = importlib.import_module(
        "platform_context_graph.runtime.repo_sync.github_auth"
    )

    github_auth.clear_cached_github_app_token()
    monkeypatch.setenv("GITHUB_APP_ID", "123")
    monkeypatch.setenv("GITHUB_APP_INSTALLATION_ID", "456")
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", "test-private-key")
    monkeypatch.setenv("PCG_GITHUB_APP_TOKEN_REFRESH_SECONDS", "60")
    monkeypatch.setattr(github_auth.jwt, "encode", lambda *_args, **_kwargs: "jwt")

    attempts = {"count": 0}
    responses = [
        {"token": "ghs_old", "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=20)).isoformat()},
        {"token": "ghs_new", "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()},
    ]

    def _request(method, url, **_kwargs):
        assert method == "post"
        assert "access_tokens" in url
        response = MagicMock()
        response.json.return_value = responses[attempts["count"]]
        response.raise_for_status.return_value = None
        attempts["count"] += 1
        return response

    monkeypatch.setattr(github_auth.requests, "request", _request)

    first = github_auth.github_app_token()
    second = github_auth.github_app_token()

    assert first == "ghs_old"
    assert second == "ghs_new"
    assert attempts["count"] == 2


def test_github_app_token_retries_rate_limit_responses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GitHub App token minting should back off and retry on rate limits."""

    github_auth = importlib.import_module(
        "platform_context_graph.runtime.repo_sync.github_auth"
    )

    github_auth.clear_cached_github_app_token()
    monkeypatch.setenv("GITHUB_APP_ID", "123")
    monkeypatch.setenv("GITHUB_APP_INSTALLATION_ID", "456")
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", "test-private-key")
    monkeypatch.setenv("PCG_GITHUB_API_RETRY_ATTEMPTS", "2")
    monkeypatch.setenv("PCG_GITHUB_API_RETRY_DELAY_SECONDS", "1")
    monkeypatch.setattr(github_auth.jwt, "encode", lambda *_args, **_kwargs: "jwt")

    attempts = {"count": 0}
    warnings: list[str] = []

    def _request(method, url, **_kwargs):
        attempts["count"] += 1
        if attempts["count"] == 1:
            response = MagicMock()
            response.status_code = 429
            response.headers = {"Retry-After": "4", "X-RateLimit-Remaining": "0"}
            response.raise_for_status.side_effect = github_auth.requests.HTTPError(
                response=response
            )
            return response

        response = MagicMock()
        response.json.return_value = {"token": "ghs_after_limit", "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()}
        response.raise_for_status.return_value = None
        return response

    sleeps: list[float] = []
    monkeypatch.setattr(github_auth.requests, "request", _request)
    monkeypatch.setattr(github_auth.time, "sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr(github_auth, "warning_logger", lambda message: warnings.append(message))

    token = github_auth.github_app_token()

    assert token == "ghs_after_limit"
    assert attempts["count"] == 2
    assert sleeps == [4.0]
    assert any("rate limit" in message.lower() for message in warnings)


def test_github_api_request_retries_rate_limit_403_responses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GitHub API requests should back off on 403 rate-limit responses too."""

    github_auth = importlib.import_module(
        "platform_context_graph.runtime.repo_sync.github_auth"
    )

    monkeypatch.setenv("PCG_GITHUB_API_RETRY_ATTEMPTS", "2")
    monkeypatch.setenv("PCG_GITHUB_API_RETRY_DELAY_SECONDS", "1")

    attempts = {"count": 0}
    warnings: list[str] = []

    def _request(method, url, **_kwargs):
        attempts["count"] += 1
        if attempts["count"] == 1:
            response = MagicMock()
            response.status_code = 403
            response.headers = {
                "X-RateLimit-Remaining": "0",
                "Retry-After": "3",
            }
            response.text = "API rate limit exceeded"
            response.raise_for_status.side_effect = github_auth.requests.HTTPError(
                response=response
            )
            return response

        response = MagicMock()
        response.json.return_value = {"ok": True}
        response.raise_for_status.return_value = None
        return response

    sleeps: list[float] = []
    monkeypatch.setattr(github_auth.requests, "request", _request)
    monkeypatch.setattr(github_auth.time, "sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr(github_auth, "warning_logger", lambda message: warnings.append(message))

    response = github_auth.github_api_request(
        "get",
        "https://api.github.com/orgs/platformcontext/repos",
    )

    assert response.json() == {"ok": True}
    assert attempts["count"] == 2
    assert sleeps == [3.0]
    assert any("rate limit" in message.lower() for message in warnings)


def test_repo_sync_cycle_reports_stale_unmanaged_checkouts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Count stale git checkouts when discovery no longer includes them."""

    observability = importlib.import_module("platform_context_graph.observability")
    repo_sync = importlib.import_module("platform_context_graph.runtime.repo_sync")
    sync_module = importlib.import_module("platform_context_graph.runtime.repo_sync.sync")
    observability.reset_observability_for_tests()

    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    monkeypatch.setenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "http://otel-collector.monitoring.svc.cluster.local:4317",
    )

    reader = InMemoryMetricReader()
    observability.initialize_observability(
        component="repo-sync",
        metric_reader=reader,
        span_exporter=InMemorySpanExporter(),
    )

    repos_dir = tmp_path / "workspace" / "repos"
    stale_repo = repos_dir / "legacy-repo"
    (stale_repo / ".git").mkdir(parents=True)

    config = repo_sync.RepoSyncConfig(
        repos_dir=repos_dir,
        source_mode="githubOrg",
        git_auth_method="githubApp",
        github_org="platformcontext",
        repositories=[],
        filesystem_root=None,
        clone_depth=1,
        repo_limit=100,
        sync_lock_dir=repos_dir / ".pcg-sync.lock",
        component="repo-sync",
    )

    monkeypatch.setattr(sync_module, "clone_missing_repositories", lambda *_args: ([], 0, 0, 0))
    monkeypatch.setattr(sync_module, "update_existing_repositories", lambda *_args: (0, 0))
    monkeypatch.setattr(sync_module, "git_token", lambda _config: None)

    result = repo_sync.run_repo_sync_cycle(
        config, index_workspace=lambda _workspace: pytest.fail("index should not run")
    )

    assert result.stale == 1
    assert any(
        metric_name == "pcg_index_repositories_total"
        and attrs.get("phase") == "stale"
        and value == 1
        for metric_name, attrs, value in _metric_points(reader)
    )
