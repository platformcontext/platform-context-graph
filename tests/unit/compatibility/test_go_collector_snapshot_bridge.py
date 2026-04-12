"""Tests for the narrowed Go collector snapshot bridge."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from platform_context_graph.collectors.git.types import RepositoryParseSnapshot
from platform_context_graph.runtime.ingester.config import RepoSyncConfig, RepoSyncResult
from platform_context_graph.runtime.ingester.go_collector_bridge import _BridgeBuilder
from platform_context_graph.runtime.ingester.go_collector_snapshot_bridge import (
    collect_snapshot_batch,
    main,
)


def test_collect_snapshot_batch_emits_repo_snapshots_and_content_entries(
    tmp_path: Path,
) -> None:
    """The snapshot bridge should emit parse snapshots plus content transport."""

    repo_path = tmp_path / "service"
    repo_path.mkdir()
    source_file = repo_path / "app.py"
    source_file.write_text(
        "def handler():\n"
        "    return 1\n"
        "\n"
        "class Worker:\n"
        "    pass\n",
        encoding="utf-8",
    )

    observed_at = datetime(2026, 4, 12, 15, 30, tzinfo=timezone.utc)
    config = RepoSyncConfig(
        repos_dir=tmp_path / "workspace",
        source_mode="filesystem",
        git_auth_method="none",
        github_org=None,
        repositories=[],
        filesystem_root=tmp_path,
        clone_depth=1,
        repo_limit=50,
        sync_lock_dir=tmp_path / ".pcg-sync.lock",
        component="collector-git-snapshot-bridge",
    )

    def fake_run_repo_sync_cycle(
        _config: RepoSyncConfig,
        *,
        index_workspace,
    ) -> RepoSyncResult:
        index_workspace(
            config.repos_dir,
            selected_repositories=[repo_path],
            family="sync",
            source="filesystem",
            component=config.component,
        )
        return RepoSyncResult(discovered=1, indexed=1)

    def fake_resolve_repository_file_sets(
        _builder: object,
        _workspace: Path,
        *,
        selected_repositories,
        pathspec_module: object,
    ) -> dict[Path, list[Path]]:
        del pathspec_module
        assert [path.resolve() for path in selected_repositories] == [repo_path.resolve()]
        return {repo_path.resolve(): [source_file]}

    async def fake_parse_repository_snapshot_async(
        _builder: object,
        repo_root: Path,
        repo_files: list[Path],
        *,
        is_dependency: bool,
        job_id: str | None,
        asyncio_module: object,
        info_logger_fn,
        progress_callback=None,
        parse_executor=None,
        component: str | None = None,
        mode: str | None = None,
        source: str | None = None,
        parse_workers: int = 1,
        emit_log_call_fn=None,
        get_observability_fn=None,
        parse_file_in_worker_fn=None,
        repository_display_name_fn=None,
        repo_parse_progress_min_files: int = 0,
        repo_parse_progress_target_steps: int = 0,
        slow_parse_file_threshold_seconds: float = 0.0,
        time_monotonic_fn=None,
    ) -> RepositoryParseSnapshot:
        del (
            asyncio_module,
            component,
            emit_log_call_fn,
            get_observability_fn,
            info_logger_fn,
            is_dependency,
            job_id,
            mode,
            parse_executor,
            parse_file_in_worker_fn,
            parse_workers,
            progress_callback,
            repo_parse_progress_min_files,
            repo_parse_progress_target_steps,
            repository_display_name_fn,
            slow_parse_file_threshold_seconds,
            source,
            time_monotonic_fn,
        )
        assert repo_root == repo_path.resolve()
        assert repo_files == [source_file]
        return RepositoryParseSnapshot(
            repo_path=str(repo_root),
            file_count=1,
            imports_map={},
            file_data=[
                {
                    "path": str(source_file.resolve()),
                    "lang": "python",
                    "functions": [
                        {
                            "name": "handler",
                            "line_number": 1,
                            "end_line": 2,
                        }
                    ],
                    "classes": [
                        {
                            "name": "Worker",
                            "line_number": 4,
                            "end_line": 5,
                        }
                    ],
                }
            ],
        )

    batch = collect_snapshot_batch(
        config,
        run_repo_sync_cycle_fn=fake_run_repo_sync_cycle,
        resolve_repository_file_sets_fn=fake_resolve_repository_file_sets,
        parse_repository_snapshot_async_fn=fake_parse_repository_snapshot_async,
        build_parser_registry_fn=lambda _ignored: {},
        git_remote_for_path_fn=lambda _path: "https://github.com/example/service",
        utc_now_fn=lambda: observed_at,
        pathspec_module=object(),
    )

    json.dumps(batch)

    assert batch["observed_at"] == "2026-04-12T15:30:00+00:00"
    assert len(batch["collected"]) == 1

    collected = batch["collected"][0]
    assert collected["repo_path"] == str(repo_path.resolve())
    assert collected["remote_url"] == "https://github.com/example/service"
    assert collected["file_count"] == 1
    assert collected["file_data"][0]["functions"][0]["uid"].startswith("content-entity:e_")

    content_file = collected["content_files"][0]
    assert content_file["relative_path"] == "app.py"
    assert content_file["language"] == "python"
    assert content_file["content_body"] == source_file.read_text(encoding="utf-8")
    assert content_file["content_digest"]

    entity_names = [entity["entity_name"] for entity in collected["content_entities"]]
    assert entity_names == ["handler", "Worker"]
    assert collected["content_entities"][0]["entity_type"] == "Function"
    assert collected["content_entities"][1]["entity_type"] == "Class"


def test_bridge_builder_parse_file_delegates_to_registry_entrypoint(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """The bridge builder should provide the parse surface async parse expects."""

    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    file_path = repo_path / "app.py"
    file_path.write_text("print('ok')\n", encoding="utf-8")

    captured: dict[str, object] = {}

    def fake_parse_file(
        builder: object,
        repo_root: Path,
        path: Path,
        is_dependency: bool,
        *,
        get_config_value_fn,
        debug_log_fn,
        error_logger_fn,
        warning_logger_fn,
    ) -> dict[str, object]:
        del get_config_value_fn, debug_log_fn, error_logger_fn, warning_logger_fn
        captured["builder"] = builder
        captured["repo_path"] = repo_root
        captured["path"] = path
        captured["is_dependency"] = is_dependency
        return {"path": str(path), "lang": "python"}

    monkeypatch.setattr(
        "platform_context_graph.parsers.registry.parse_file",
        fake_parse_file,
    )

    builder = _BridgeBuilder(parsers={".py": object()})
    result = builder.parse_file(repo_path, file_path, is_dependency=True)

    assert result == {"path": str(file_path), "lang": "python"}
    assert captured == {
        "builder": builder,
        "repo_path": repo_path,
        "path": file_path,
        "is_dependency": True,
    }


def test_main_reserves_stdout_for_json_payload(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """The snapshot bridge should keep incidental bridge logs off stdout."""

    config = RepoSyncConfig(
        repos_dir=tmp_path / "workspace",
        source_mode="filesystem",
        git_auth_method="none",
        github_org=None,
        repositories=[],
        filesystem_root=tmp_path,
        clone_depth=1,
        repo_limit=50,
        sync_lock_dir=tmp_path / ".pcg-sync.lock",
        component="collector-git-snapshot-bridge",
    )

    def fake_collect_snapshot_batch(
        _config: RepoSyncConfig,
        *,
        utc_now_fn,
    ) -> dict[str, object]:
        print("bridge-noise")
        return {
            "observed_at": utc_now_fn().isoformat(),
            "collected": [],
        }

    monkeypatch.setattr(RepoSyncConfig, "from_env", lambda *, component: config)
    monkeypatch.setattr(
        "platform_context_graph.runtime.ingester.go_collector_snapshot_bridge.collect_snapshot_batch",
        fake_collect_snapshot_batch,
    )

    assert main() == 0

    captured = capsys.readouterr()
    assert "bridge-noise" not in captured.out
    assert "bridge-noise" in captured.err
    payload = json.loads(captured.out)
    assert payload["collected"] == []
