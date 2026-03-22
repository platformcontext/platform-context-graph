from __future__ import annotations

import importlib
import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
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
    repo_sync = importlib.import_module("platform_context_graph.runtime.ingester")
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
    repo_sync = importlib.import_module("platform_context_graph.runtime.ingester")

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

    result = repo_sync.run_bootstrap_index(
        config, index_workspace=lambda _workspace: None
    )

    assert result.discovered == 1
    assert result.indexed == 1
    assert (config.repos_dir / "service-a" / "main.py").exists()
    assert not (config.repos_dir / "service-a" / "missing.tpl").exists()


def test_repo_sync_cycle_records_lock_contention_skip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observability = importlib.import_module("platform_context_graph.observability")
    repo_sync = importlib.import_module("platform_context_graph.runtime.ingester")
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


def test_repo_sync_cycle_indexes_only_changed_and_resumable_repositories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sync should index only changed repos plus resumable incomplete repos."""

    repo_sync = importlib.import_module("platform_context_graph.runtime.ingester")
    sync = importlib.import_module("platform_context_graph.runtime.ingester.sync")

    repos_dir = tmp_path / "workspace" / "repos"
    repo_a = repos_dir / "platformcontext--payments-api"
    repo_c = repos_dir / "platformcontext--inventory-api"
    repo_d = repos_dir / "platformcontext--docs"
    (repo_a / ".git").mkdir(parents=True)
    (repo_c / ".git").mkdir(parents=True)
    (repo_d / ".git").mkdir(parents=True)

    config = repo_sync.RepoSyncConfig(
        repos_dir=repos_dir,
        source_mode="githubOrg",
        git_auth_method="token",
        github_org="platformcontext",
        repositories=[],
        filesystem_root=None,
        clone_depth=1,
        repo_limit=20,
        sync_lock_dir=repos_dir / ".pcg-sync.lock",
        component="repo-sync",
    )

    repo_b = repos_dir / "platformcontext--orders-api"
    captured: dict[str, object] = {}

    @contextmanager
    def _workspace_lock(_config):
        yield True

    @contextmanager
    def _index_cycle(**_kwargs):
        yield

    monkeypatch.setattr(sync, "initialize_observability", lambda **_kwargs: None)
    monkeypatch.setattr(sync, "workspace_lock", _workspace_lock)
    monkeypatch.setattr(sync, "begin_index_cycle", _index_cycle)
    monkeypatch.setattr(sync, "record_phase", lambda **_kwargs: None)
    monkeypatch.setattr(sync, "git_token", lambda _config: "token")
    monkeypatch.setattr(
        sync,
        "clone_missing_repositories_detailed",
        lambda _config, _token: (
            [
                "platformcontext/payments-api",
                "platformcontext/orders-api",
                "platformcontext/inventory-api",
                "platformcontext/docs",
            ],
            [repo_b],
            3,
            0,
        ),
        raising=False,
    )
    monkeypatch.setattr(
        sync,
        "clone_missing_repositories",
        lambda _config, _token: (
            [
                "platformcontext/payments-api",
                "platformcontext/orders-api",
                "platformcontext/inventory-api",
                "platformcontext/docs",
            ],
            1,
            3,
            0,
        ),
    )
    monkeypatch.setattr(
        sync,
        "update_existing_repositories_detailed",
        lambda _config, _token: ([repo_a], 0),
        raising=False,
    )
    monkeypatch.setattr(
        sync,
        "update_existing_repositories",
        lambda _config, _token: (1, 0),
    )
    monkeypatch.setattr(
        sync,
        "resumable_repository_paths",
        lambda _workspace: [repo_c.resolve()],
        raising=False,
    )

    def _index_workspace(
        workspace: Path,
        *,
        selected_repositories: list[Path] | None = None,
        family: str | None = None,
        source: str | None = None,
        component: str | None = None,
    ) -> None:
        captured["workspace"] = workspace
        captured["selected_repositories"] = selected_repositories
        captured["family"] = family
        captured["source"] = source
        captured["component"] = component

    result = sync.run_repo_sync_cycle(config, index_workspace=_index_workspace)

    assert captured["workspace"] == repos_dir
    assert captured["family"] == "sync"
    assert captured["source"] == "githubOrg"
    assert captured["component"] == "repo-sync"
    assert set(captured["selected_repositories"]) == {
        repo_a.resolve(),
        repo_b.resolve(),
        repo_c.resolve(),
    }
    assert result.indexed == 3


def test_bootstrap_index_reaps_stale_empty_lock_and_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bootstrap should recover from a stale lock directory left on disk."""

    repo_sync = importlib.import_module("platform_context_graph.runtime.ingester")

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

    repo_sync = importlib.import_module("platform_context_graph.runtime.ingester")

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

    repo_sync = importlib.import_module("platform_context_graph.runtime.ingester")

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

    bootstrap = importlib.import_module(
        "platform_context_graph.runtime.ingester.bootstrap"
    )
    repo_sync = importlib.import_module("platform_context_graph.runtime.ingester")

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

    result = repo_sync.run_bootstrap_index(
        config, index_workspace=lambda _workspace: None
    )

    assert attempts["count"] == 2
    assert sleeps == [1.0]
    assert result.lock_skipped is False


def test_github_app_token_retries_transient_request_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GitHub App token minting should retry transient request failures."""

    github_auth = importlib.import_module(
        "platform_context_graph.runtime.ingester.github_auth"
    )

    github_auth.clear_cached_github_app_token()
    monkeypatch.setenv("GITHUB_APP_ID", "123")
    monkeypatch.setenv("GITHUB_APP_INSTALLATION_ID", "456")
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", "test-private-key")
    monkeypatch.setenv("PCG_GITHUB_API_RETRY_ATTEMPTS", "3")
    monkeypatch.setenv("PCG_GITHUB_API_RETRY_DELAY_SECONDS", "1")
    monkeypatch.setattr(
        github_auth.jwt, "encode", lambda *_args, **_kwargs: "encoded-jwt"
    )

    attempts = {"count": 0}

    def _request(method, url, **_kwargs):
        assert method == "post"
        assert url == "https://api.github.com/app/installations/456/access_tokens"
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
    monkeypatch.setattr(
        github_auth.time, "sleep", lambda seconds: sleeps.append(seconds)
    )

    token = github_auth.github_app_token()

    assert token == "ghs_test"
    assert attempts["count"] == 3
    assert sleeps == [1.0, 1.0]


def test_github_app_token_normalizes_flattened_pem_private_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GitHub App token minting should repair PEM keys flattened into one line."""

    github_auth = importlib.import_module(
        "platform_context_graph.runtime.ingester.github_auth"
    )

    github_auth.clear_cached_github_app_token()
    monkeypatch.setenv("GITHUB_APP_ID", "123")
    monkeypatch.setenv("GITHUB_APP_INSTALLATION_ID", "456")
    monkeypatch.setenv(
        "GITHUB_APP_PRIVATE_KEY",
        (
            "-----BEGIN RSA PRIVATE KEY----- "
            "LINEONE "
            "LINETWO "
            "-----END RSA PRIVATE KEY-----"
        ),
    )

    captured: dict[str, object] = {}

    def _encode(payload, key, algorithm):
        captured["payload"] = payload
        captured["key"] = key
        captured["algorithm"] = algorithm
        return "encoded-jwt"

    response = MagicMock()
    response.json.return_value = {"token": "ghs_test"}
    response.raise_for_status.return_value = None

    monkeypatch.setattr(github_auth.jwt, "encode", _encode)
    monkeypatch.setattr(
        github_auth.requests, "request", lambda *_args, **_kwargs: response
    )

    token = github_auth.github_app_token()

    assert token == "ghs_test"
    assert captured["algorithm"] == "RS256"
    assert captured["key"] == (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "LINEONE\n"
        "LINETWO\n"
        "-----END RSA PRIVATE KEY-----\n"
    )


def test_github_app_token_is_cached_until_near_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GitHub App tokens should be reused while they remain safely valid."""

    github_auth = importlib.import_module(
        "platform_context_graph.runtime.ingester.github_auth"
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
        "platform_context_graph.runtime.ingester.github_auth"
    )

    github_auth.clear_cached_github_app_token()
    monkeypatch.setenv("GITHUB_APP_ID", "123")
    monkeypatch.setenv("GITHUB_APP_INSTALLATION_ID", "456")
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", "test-private-key")
    monkeypatch.setenv("PCG_GITHUB_APP_TOKEN_REFRESH_SECONDS", "60")
    monkeypatch.setattr(github_auth.jwt, "encode", lambda *_args, **_kwargs: "jwt")

    attempts = {"count": 0}
    responses = [
        {
            "token": "ghs_old",
            "expires_at": (
                datetime.now(timezone.utc) + timedelta(seconds=20)
            ).isoformat(),
        },
        {
            "token": "ghs_new",
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        },
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
        "platform_context_graph.runtime.ingester.github_auth"
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
        response.json.return_value = {
            "token": "ghs_after_limit",
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        }
        response.raise_for_status.return_value = None
        return response

    sleeps: list[float] = []
    monkeypatch.setattr(github_auth.requests, "request", _request)
    monkeypatch.setattr(
        github_auth.time, "sleep", lambda seconds: sleeps.append(seconds)
    )
    monkeypatch.setattr(
        github_auth, "warning_logger", lambda message: warnings.append(message)
    )

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
        "platform_context_graph.runtime.ingester.github_auth"
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
    monkeypatch.setattr(
        github_auth.time, "sleep", lambda seconds: sleeps.append(seconds)
    )
    monkeypatch.setattr(
        github_auth, "warning_logger", lambda message: warnings.append(message)
    )

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
    repo_sync = importlib.import_module("platform_context_graph.runtime.ingester")
    sync_module = importlib.import_module(
        "platform_context_graph.runtime.ingester.sync"
    )
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

    monkeypatch.setattr(
        sync_module,
        "clone_missing_repositories_detailed",
        lambda *_args: ([], [], 0, 0),
        raising=False,
    )
    monkeypatch.setattr(
        sync_module,
        "update_existing_repositories_detailed",
        lambda *_args: ([], 0),
        raising=False,
    )
    monkeypatch.setattr(
        sync_module, "clone_missing_repositories", lambda *_args: ([], 0, 0, 0)
    )
    monkeypatch.setattr(
        sync_module, "update_existing_repositories", lambda *_args: (0, 0)
    )
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


def test_repo_sync_loop_records_degraded_status_and_retries_transient_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Transient sync failures should degrade the ingester instead of crashing it."""

    requests = pytest.importorskip("requests")
    sync = importlib.import_module("platform_context_graph.runtime.ingester.sync")
    monkeypatch.setenv("PCG_REPO_SYNC_INITIAL_DELAY_SECONDS", "0")

    recorded_statuses: list[dict[str, object]] = []
    monkeypatch.setattr(
        sync,
        "update_runtime_ingester_status",
        lambda **kwargs: recorded_statuses.append(kwargs),
        raising=False,
    )

    def _sleep(_seconds: float) -> None:
        raise StopIteration

    monkeypatch.setattr(sync.time, "sleep", _sleep)
    monkeypatch.setattr(
        sync,
        "run_repo_sync_cycle",
        MagicMock(
            side_effect=requests.exceptions.ConnectionError("temporary dns failure")
        ),
    )

    with pytest.raises(StopIteration):
        sync.run_repo_sync_loop(interval_seconds=900)

    assert recorded_statuses
    assert recorded_statuses[-1]["status"] == "degraded"
    assert recorded_statuses[-1]["last_error_kind"] == "network"


def test_persist_ingester_status_defaults_repository_counts_to_zero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Persisted ingester status should never publish null repository counts."""

    repo_sync = importlib.import_module("platform_context_graph.runtime.ingester")
    sync = importlib.import_module("platform_context_graph.runtime.ingester.sync")

    recorded_statuses: list[dict[str, object]] = []
    monkeypatch.setattr(
        sync, "_current_ingester_status", lambda _component: {}, raising=False
    )
    monkeypatch.setattr(
        sync,
        "update_runtime_ingester_status",
        lambda **kwargs: recorded_statuses.append(kwargs),
        raising=False,
    )

    config = repo_sync.RepoSyncConfig(
        repos_dir=tmp_path / "workspace" / "repos",
        source_mode="githubOrg",
        git_auth_method="githubApp",
        github_org="platformcontext",
        repositories=[],
        filesystem_root=None,
        clone_depth=1,
        repo_limit=100,
        sync_lock_dir=tmp_path / "workspace" / "repos" / ".pcg-sync.lock",
        component="repository",
    )

    sync._persist_ingester_status(config, status="degraded", last_error_kind="network")

    assert recorded_statuses == [
        {
            "ingester": "repository",
            "source_mode": "githubOrg",
            "status": "degraded",
            "active_run_id": None,
            "repository_count": 0,
            "pulled_repositories": 0,
            "in_sync_repositories": 0,
            "pending_repositories": 0,
            "completed_repositories": 0,
            "failed_repositories": 0,
            "last_error_kind": "network",
        }
    ]


def test_retry_delay_clamps_attempt_exponent_before_growth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retry delay should cap exponential growth before computing huge powers."""

    retry = importlib.import_module("platform_context_graph.runtime.ingester.retry")

    monkeypatch.setattr(retry.random, "randint", lambda _low, _high: 0)

    delay = retry.retry_after_seconds(RuntimeError("boom"), attempt=10_000)

    assert delay == retry.MAX_REPO_SYNC_RETRY_SECONDS


def test_repo_sync_loop_claims_and_completes_manual_scan_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Manual ingester scan requests should run through the normal sync cycle."""

    sync = importlib.import_module("platform_context_graph.runtime.ingester.sync")
    monkeypatch.setenv("PCG_REPO_SYNC_INITIAL_DELAY_SECONDS", "0")

    recorded_statuses: list[dict[str, object]] = []
    completed_requests: list[dict[str, object]] = []
    monkeypatch.setattr(
        sync,
        "update_runtime_ingester_status",
        lambda **kwargs: recorded_statuses.append(kwargs),
        raising=False,
    )
    monkeypatch.setattr(
        sync,
        "claim_ingester_scan_request",
        MagicMock(
            side_effect=[
                {
                    "ingester": "repository",
                    "scan_request_token": "scan-123",
                    "scan_request_state": "running",
                },
                None,
            ]
        ),
        raising=False,
    )
    monkeypatch.setattr(
        sync,
        "complete_ingester_scan_request",
        lambda **kwargs: completed_requests.append(kwargs),
        raising=False,
    )
    monkeypatch.setattr(
        sync,
        "_current_ingester_status",
        lambda _component: {
            "repository_count": 5,
            "pulled_repositories": 5,
            "in_sync_repositories": 4,
            "pending_repositories": 1,
            "completed_repositories": 4,
            "failed_repositories": 0,
        },
        raising=False,
    )
    monkeypatch.setattr(
        sync,
        "run_repo_sync_cycle",
        MagicMock(return_value=SimpleNamespace(discovered=5)),
    )

    def _stop_after_first_cycle(_component: str, _delay_seconds: int):
        raise KeyboardInterrupt

    monkeypatch.setattr(sync, "_wait_for_next_cycle", _stop_after_first_cycle)

    with pytest.raises(KeyboardInterrupt):
        sync.run_repo_sync_loop(interval_seconds=900)

    assert recorded_statuses
    assert recorded_statuses[0]["ingester"] == "repository"
    assert completed_requests == [
        {
            "ingester": "repository",
            "request_token": "scan-123",
        }
    ]


def test_update_existing_repositories_refreshes_https_origin_with_fresh_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Existing HTTPS remotes should be rewritten with a fresh token before fetch."""

    git_module = importlib.import_module("platform_context_graph.runtime.ingester.git")
    repo_sync = importlib.import_module("platform_context_graph.runtime.ingester")

    repos_dir = tmp_path / "workspace" / "repos"
    repo_dir = repos_dir / "api-node-boattrader"
    (repo_dir / ".git").mkdir(parents=True)

    config = repo_sync.RepoSyncConfig(
        repos_dir=repos_dir,
        source_mode="githubOrg",
        git_auth_method="githubApp",
        github_org="boatsgroup",
        repositories=[],
        filesystem_root=None,
        clone_depth=1,
        repo_limit=100,
        sync_lock_dir=repos_dir / ".pcg-sync.lock",
        component="repository",
    )

    calls: list[list[str]] = []

    def _run(command, **_kwargs):
        calls.append(command)
        if command[3:5] == ["remote", "get-url"]:
            return SimpleNamespace(
                returncode=0,
                stdout=(
                    "https://x-access-token:expired-token@github.com/"
                    "boatsgroup/api-node-boattrader.git\n"
                ),
                stderr="",
            )
        if command[3:5] == ["remote", "set-url"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if command[3:4] == ["symbolic-ref"]:
            return SimpleNamespace(
                returncode=0,
                stdout="refs/remotes/origin/main\n",
                stderr="",
            )
        if command[3:4] == ["fetch"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if command[3:] == ["rev-parse", "HEAD"]:
            return SimpleNamespace(returncode=0, stdout="local-head\n", stderr="")
        if command[3:] == ["rev-parse", "FETCH_HEAD"]:
            return SimpleNamespace(returncode=0, stdout="remote-head\n", stderr="")
        if command[3:5] == ["reset", "--hard"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(git_module.subprocess, "run", _run)

    updated, failed = git_module.update_existing_repositories(config, "fresh-token")

    assert (updated, failed) == (1, 0)
    get_url_call = [
        "git",
        "-C",
        str(repo_dir),
        "remote",
        "get-url",
        "origin",
    ]
    set_url_call = [
        "git",
        "-C",
        str(repo_dir),
        "remote",
        "set-url",
        "origin",
        "https://x-access-token:fresh-token@github.com/boatsgroup/api-node-boattrader.git",
    ]
    fetch_call = [
        "git",
        "-C",
        str(repo_dir),
        "fetch",
        "origin",
        "main",
        "--depth=1",
    ]
    assert get_url_call in calls
    assert set_url_call in calls
    assert fetch_call in calls
    assert (
        calls.index(get_url_call) < calls.index(set_url_call) < calls.index(fetch_call)
    )


def test_update_existing_repositories_skips_origin_refresh_without_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-token modes should not inspect or rewrite repository origins."""

    git_module = importlib.import_module("platform_context_graph.runtime.ingester.git")
    repo_sync = importlib.import_module("platform_context_graph.runtime.ingester")

    repos_dir = tmp_path / "workspace" / "repos"
    repo_dir = repos_dir / "api-node-boattrader"
    (repo_dir / ".git").mkdir(parents=True)

    config = repo_sync.RepoSyncConfig(
        repos_dir=repos_dir,
        source_mode="githubOrg",
        git_auth_method="none",
        github_org="boatsgroup",
        repositories=[],
        filesystem_root=None,
        clone_depth=1,
        repo_limit=100,
        sync_lock_dir=repos_dir / ".pcg-sync.lock",
        component="repository",
    )

    calls: list[list[str]] = []

    def _run(command, **_kwargs):
        calls.append(command)
        if command[3:4] == ["symbolic-ref"]:
            return SimpleNamespace(
                returncode=0,
                stdout="refs/remotes/origin/main\n",
                stderr="",
            )
        if command[3:4] == ["fetch"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if command[3:] == ["rev-parse", "HEAD"]:
            return SimpleNamespace(returncode=0, stdout="local-head\n", stderr="")
        if command[3:] == ["rev-parse", "FETCH_HEAD"]:
            return SimpleNamespace(returncode=0, stdout="local-head\n", stderr="")
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(git_module.subprocess, "run", _run)

    updated, failed = git_module.update_existing_repositories(config, None)

    assert (updated, failed) == (0, 0)
    assert all(command[3:5] != ["remote", "get-url"] for command in calls)
    assert all(command[3:5] != ["remote", "set-url"] for command in calls)
