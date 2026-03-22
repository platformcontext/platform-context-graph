from __future__ import annotations

import importlib
import json
from datetime import datetime, timezone
from pathlib import Path

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
    assert lock_dir.exists()


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
