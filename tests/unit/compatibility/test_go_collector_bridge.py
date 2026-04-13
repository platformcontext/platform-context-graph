"""Tests for the Go collector compatibility bridge."""

from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path

from platform_context_graph.collectors.git.types import RepositoryParseSnapshot
from platform_context_graph.content.identity import canonical_content_entity_id
from platform_context_graph.repository_identity import repository_metadata
from platform_context_graph.runtime.ingester.config import RepoSyncConfig, RepoSyncResult
from platform_context_graph.runtime.ingester.go_collector_bridge import collect_batch


def test_collect_batch_emits_repository_file_content_and_reducer_facts(
    tmp_path: Path,
) -> None:
    """The bridge should emit rich file and content-entity facts."""

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
        component="collector-git-bridge",
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

    batch = collect_batch(
        config,
        run_repo_sync_cycle_fn=fake_run_repo_sync_cycle,
        resolve_repository_file_sets_fn=fake_resolve_repository_file_sets,
        parse_repository_snapshot_async_fn=fake_parse_repository_snapshot_async,
        build_parser_registry_fn=lambda _ignored: {},
        git_remote_for_path_fn=lambda _path: "https://github.com/example/service",
        repository_metadata_fn=repository_metadata,
        utc_now_fn=lambda: observed_at,
        pathspec_module=object(),
    )

    assert list(batch) == ["collected"]
    assert len(batch["collected"]) == 1
    json.dumps(batch)

    collected = batch["collected"][0]
    repo_id = collected["scope"]["metadata"]["repo_id"]
    content_repo_id = repository_metadata(
        name="service",
        local_path=repo_path,
        remote_url="https://github.com/example/service",
    )["id"]
    assert collected["scope"]["scope_kind"] == "repository"
    assert collected["scope"]["collector_kind"] == "git"
    assert collected["scope"]["partition_key"] == repo_id
    assert collected["generation"]["scope_id"] == collected["scope"]["scope_id"]
    assert collected["generation"]["status"] == "pending"
    assert collected["generation"]["trigger_kind"] == "snapshot"
    assert collected["generation"]["observed_at"] == "2026-04-12T15:30:00+00:00"

    facts = collected["facts"]
    assert [fact["fact_kind"] for fact in facts] == [
        "repository",
        "file",
        "content",
        "content_entity",
        "content_entity",
        "shared_followup",
    ]

    repository_fact = facts[0]
    assert repository_fact["payload"]["graph_id"] == repo_id
    assert repository_fact["payload"]["graph_kind"] == "repository"
    assert repository_fact["payload"]["name"] == "service"
    assert repository_fact["payload"]["remote_url"] == "https://github.com/example/service"

    file_fact = facts[1]
    assert file_fact["payload"]["graph_kind"] == "file"
    assert file_fact["payload"]["relative_path"] == "app.py"
    assert file_fact["payload"]["repo_id"] == repo_id
    parsed_file_data = file_fact["payload"]["parsed_file_data"]
    assert parsed_file_data["functions"][0]["uid"] == canonical_content_entity_id(
        repo_id=content_repo_id,
        relative_path="app.py",
        entity_type="Function",
        entity_name="handler",
        line_number=1,
    )
    assert parsed_file_data["classes"][0]["uid"] == canonical_content_entity_id(
        repo_id=content_repo_id,
        relative_path="app.py",
        entity_type="Class",
        entity_name="Worker",
        line_number=4,
    )

    content_fact = facts[2]
    assert content_fact["payload"]["content_path"] == "app.py"
    assert (
        content_fact["payload"]["content_body"]
        == "def handler():\n    return 1\n\nclass Worker:\n    pass\n"
    )
    assert content_fact["payload"]["content_digest"] == hashlib.sha1(
        source_file.read_bytes()
    ).hexdigest()
    assert content_fact["payload"]["language"] == "python"
    assert content_fact["payload"]["repo_id"] == repo_id

    function_fact = facts[3]
    assert function_fact["payload"]["graph_kind"] == "content_entity"
    assert function_fact["payload"]["entity_id"] == canonical_content_entity_id(
        repo_id=content_repo_id,
        relative_path="app.py",
        entity_type="Function",
        entity_name="handler",
        line_number=1,
    )
    assert function_fact["payload"]["entity_name"] == "handler"
    assert function_fact["payload"]["source_cache"] == "def handler():\n    return 1\n"
    assert function_fact["payload"]["repo_id"] == content_repo_id

    class_fact = facts[4]
    assert class_fact["payload"]["entity_id"] == canonical_content_entity_id(
        repo_id=content_repo_id,
        relative_path="app.py",
        entity_type="Class",
        entity_name="Worker",
        line_number=4,
    )
    assert class_fact["payload"]["entity_type"] == "Class"
    assert class_fact["payload"]["source_cache"] == "class Worker:\n    pass\n"
    assert class_fact["payload"]["repo_id"] == content_repo_id

    reducer_fact = facts[5]
    assert reducer_fact["payload"]["reducer_domain"] == "workload_identity"
    assert reducer_fact["payload"]["entity_key"] == "workload:service"
    assert "shared workload identity" in reducer_fact["payload"]["reason"]


def test_collect_batch_returns_empty_when_sync_selects_no_repositories(
    tmp_path: Path,
) -> None:
    """The bridge should emit an empty batch when repo sync selects nothing."""

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
        component="collector-git-bridge",
    )

    batch = collect_batch(
        config,
        run_repo_sync_cycle_fn=lambda _config, *, index_workspace: RepoSyncResult(),
    )

    assert batch == {"collected": []}
