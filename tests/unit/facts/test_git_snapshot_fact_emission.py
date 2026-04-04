"""Tests for emitting facts from repository parse snapshots."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import importlib
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

from platform_context_graph.collectors.git.types import RepositoryParseSnapshot
from platform_context_graph.facts.emission.git_snapshot import emit_git_snapshot_facts

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = REPO_ROOT / "src" / "platform_context_graph"


def _load_module(module_name: str, module_path: Path) -> ModuleType:
    """Load one module from source without package side effects."""

    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules.pop(module_name, None)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _load_pipeline_modules() -> tuple[ModuleType, ModuleType]:
    """Load coordinator modules with a minimal package skeleton."""

    try:
        return (
            importlib.import_module(
                "platform_context_graph.indexing.coordinator_models"
            ),
            importlib.import_module(
                "platform_context_graph.indexing.coordinator_pipeline"
            ),
        )
    except ImportError:
        module_names = (
            "platform_context_graph",
            "platform_context_graph.collectors",
            "platform_context_graph.collectors.git",
            "platform_context_graph.collectors.git.indexing",
            "platform_context_graph.graph",
            "platform_context_graph.graph.persistence",
            "platform_context_graph.graph.persistence.worker",
            "platform_context_graph.indexing",
            "platform_context_graph.indexing.coordinator_async_commit",
            "platform_context_graph.indexing.coordinator_models",
            "platform_context_graph.indexing.coordinator_pipeline",
        )
        original_modules = {
            module_name: sys.modules.get(module_name) for module_name in module_names
        }
        try:
            platform_pkg = ModuleType("platform_context_graph")
            platform_pkg.__path__ = [str(PACKAGE_ROOT)]
            sys.modules["platform_context_graph"] = platform_pkg

            collectors_pkg = ModuleType("platform_context_graph.collectors")
            collectors_pkg.__path__ = [str(PACKAGE_ROOT / "collectors")]
            sys.modules["platform_context_graph.collectors"] = collectors_pkg

            git_pkg = ModuleType("platform_context_graph.collectors.git")
            git_pkg.__path__ = [str(PACKAGE_ROOT / "collectors" / "git")]
            sys.modules["platform_context_graph.collectors.git"] = git_pkg

            graph_pkg = ModuleType("platform_context_graph.graph")
            graph_pkg.__path__ = [str(PACKAGE_ROOT / "graph")]
            sys.modules["platform_context_graph.graph"] = graph_pkg

            graph_persistence_pkg = ModuleType(
                "platform_context_graph.graph.persistence"
            )
            graph_persistence_pkg.__path__ = [
                str(PACKAGE_ROOT / "graph" / "persistence")
            ]
            sys.modules["platform_context_graph.graph.persistence"] = (
                graph_persistence_pkg
            )

            indexing_pkg = ModuleType("platform_context_graph.indexing")
            indexing_pkg.__path__ = [str(PACKAGE_ROOT / "indexing")]
            sys.modules["platform_context_graph.indexing"] = indexing_pkg

            collectors_indexing = ModuleType(
                "platform_context_graph.collectors.git.indexing"
            )

            def _merge_import_maps(
                target: dict[str, list[str]],
                source: dict[str, list[str]],
            ) -> dict[str, list[str]]:
                """Merge import maps without loading collector runtime modules."""

                for symbol, paths in source.items():
                    merged_paths = target.setdefault(symbol, [])
                    for path in paths:
                        if path not in merged_paths:
                            merged_paths.append(path)
                return target

            collectors_indexing.merge_import_maps = _merge_import_maps
            sys.modules["platform_context_graph.collectors.git.indexing"] = (
                collectors_indexing
            )

            graph_worker = ModuleType("platform_context_graph.graph.persistence.worker")
            graph_worker.get_commit_worker_connection_params = lambda: {}
            sys.modules["platform_context_graph.graph.persistence.worker"] = (
                graph_worker
            )

            async_commit = ModuleType(
                "platform_context_graph.indexing.coordinator_async_commit"
            )
            async_commit._ASYNC_COMMIT_ENABLED = False

            async def _commit_repository_snapshot_async(*_args, **_kwargs) -> None:
                """Avoid loading the real async commit stack in unit tests."""

                return None

            async_commit.commit_repository_snapshot_async = (
                _commit_repository_snapshot_async
            )
            sys.modules["platform_context_graph.indexing.coordinator_async_commit"] = (
                async_commit
            )

            models = _load_module(
                "platform_context_graph.indexing.coordinator_models",
                PACKAGE_ROOT / "indexing" / "coordinator_models.py",
            )
            pipeline = _load_module(
                "platform_context_graph.indexing.coordinator_pipeline",
                PACKAGE_ROOT / "indexing" / "coordinator_pipeline.py",
            )
        finally:
            for module_name, original_module in original_modules.items():
                if original_module is None:
                    sys.modules.pop(module_name, None)
                else:
                    sys.modules[module_name] = original_module
        return models, pipeline


MODELS, PIPELINE = _load_pipeline_modules()
IndexRunState = MODELS.IndexRunState
RepositoryRunState = MODELS.RepositoryRunState
process_repository_snapshots = PIPELINE.process_repository_snapshots


def _utc_now() -> datetime:
    """Return a stable UTC timestamp for fact emission tests."""

    return datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc)


def test_emit_git_snapshot_facts_persists_run_facts_and_work_item() -> None:
    """Snapshot emission should write facts and enqueue one work item."""

    fact_store = MagicMock()
    work_queue = MagicMock()
    snapshot = RepositoryParseSnapshot(
        repo_path="/tmp/service",
        file_count=1,
        imports_map={"handler": ["src/app.py"]},
        file_data=[
            {
                "path": "/tmp/service/src/app.py",
                "repo_path": "/tmp/service",
                "lang": "python",
                "functions": [
                    {
                        "name": "handler",
                        "line_number": 10,
                        "end_line": 20,
                    }
                ],
            }
        ],
    )

    emitted = emit_git_snapshot_facts(
        snapshot=snapshot,
        repository_id="github.com/acme/service",
        source_run_id="run-123",
        source_snapshot_id="snapshot-abc",
        is_dependency=False,
        fact_store=fact_store,
        work_queue=work_queue,
        observed_at=_utc_now(),
    )

    assert emitted.fact_count > 0
    fact_store.upsert_fact_run.assert_called_once()
    fact_store.upsert_facts.assert_called_once()
    work_queue.enqueue_work_item.assert_called_once()
    assert emitted.work_item_id
    fact_rows = fact_store.upsert_facts.call_args.args[0]
    file_fact_row = next(row for row in fact_rows if row.fact_type == "FileObserved")
    assert (
        file_fact_row.payload["parsed_file_data"]["functions"][0]["name"] == "handler"
    )
    assert file_fact_row.payload["parsed_file_data"]["lang"] == "python"


def test_emit_git_snapshot_facts_preleases_inline_projection_work_item() -> None:
    """Inline-owned emission should enqueue a leased work item for bootstrap."""

    fact_store = MagicMock()
    work_queue = MagicMock()
    snapshot = RepositoryParseSnapshot(
        repo_path="/tmp/service",
        file_count=0,
        imports_map={},
        file_data=[],
    )

    emitted = emit_git_snapshot_facts(
        snapshot=snapshot,
        repository_id="github.com/acme/service",
        source_run_id="run-123",
        source_snapshot_id="snapshot-abc",
        is_dependency=False,
        fact_store=fact_store,
        work_queue=work_queue,
        observed_at=_utc_now(),
        inline_projection_owner="indexing",
        inline_projection_lease_ttl_seconds=300,
    )

    queued_row = work_queue.enqueue_work_item.call_args.args[0]
    assert queued_row.status == "leased"
    assert queued_row.lease_owner == "indexing"
    assert queued_row.attempt_count == 1
    assert queued_row.last_attempt_started_at == _utc_now()
    assert emitted.work_item is not None
    assert emitted.work_item.status == "leased"


def test_emit_git_snapshot_facts_keeps_import_map_only_on_repository_fact() -> None:
    """Only the repository fact should carry the imports map in provenance."""

    fact_store = MagicMock()
    work_queue = MagicMock()
    snapshot = RepositoryParseSnapshot(
        repo_path="/tmp/service",
        file_count=1,
        imports_map={"handler": ["src/app.py"]},
        file_data=[
            {
                "path": "/tmp/service/src/app.py",
                "repo_path": "/tmp/service",
                "lang": "python",
                "functions": [
                    {
                        "name": "handler",
                        "line_number": 10,
                        "end_line": 20,
                    }
                ],
            }
        ],
    )

    emit_git_snapshot_facts(
        snapshot=snapshot,
        repository_id="github.com/acme/service",
        source_run_id="run-123",
        source_snapshot_id="snapshot-abc",
        is_dependency=False,
        fact_store=fact_store,
        work_queue=work_queue,
        observed_at=_utc_now(),
    )

    fact_rows = fact_store.upsert_facts.call_args.args[0]
    repository_row = next(
        row for row in fact_rows if row.fact_type == "RepositoryObserved"
    )
    file_row = next(row for row in fact_rows if row.fact_type == "FileObserved")
    entity_row = next(
        row for row in fact_rows if row.fact_type == "ParsedEntityObserved"
    )

    assert repository_row.provenance["imports_map"] == {"handler": ["src/app.py"]}
    assert "imports_map" not in file_row.provenance
    assert "imports_map" not in entity_row.provenance


def test_process_repository_snapshots_emits_facts_before_queueing_commits(
    tmp_path: Path,
) -> None:
    """The coordinator pipeline should emit facts at the snapshot seam."""

    repo = tmp_path / "repo"
    repo.mkdir()
    file_path = repo / "app.py"
    file_path.write_text("def handler():\n    return 1\n", encoding="utf-8")
    run_state = IndexRunState(
        run_id="run-123",
        root_path=str(tmp_path),
        family="index",
        source="manual",
        discovery_signature="sig",
        is_dependency=False,
        status="running",
        finalization_status="pending",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
        repositories={
            str(repo.resolve()): RepositoryRunState(repo_path=str(repo.resolve()))
        },
    )
    emitted: list[tuple[str, int]] = []

    async def _parse_snapshot(*_args, **_kwargs) -> RepositoryParseSnapshot:
        return RepositoryParseSnapshot(
            repo_path=str(repo.resolve()),
            file_count=1,
            imports_map={"handler": ["app.py"]},
            file_data=[
                {
                    "path": str(file_path.resolve()),
                    "repo_path": str(repo.resolve()),
                    "lang": "python",
                    "functions": [{"name": "handler", "line_number": 1}],
                }
            ],
        )

    def _emit_snapshot_facts(
        *,
        run_id: str,
        repo_path: Path,
        snapshot: RepositoryParseSnapshot,
        is_dependency: bool,
    ) -> None:
        emitted.append((run_id, snapshot.file_count))

    telemetry = SimpleNamespace(
        start_span=lambda *_args, **_kwargs: _null_context(),
        record_index_repositories=lambda **_kwargs: None,
        record_index_repository_duration=lambda **_kwargs: None,
    )

    committed_repo_paths, _merged, _telemetry = asyncio.run(
        process_repository_snapshots(
            builder=SimpleNamespace(),
            run_state=run_state,
            repo_paths=[repo],
            repo_file_sets={repo: [file_path]},
            resumed=False,
            is_dependency=False,
            job_id=None,
            component="test",
            family="index",
            source="manual",
            asyncio_module=asyncio,
            info_logger_fn=lambda *_args, **_kwargs: None,
            warning_logger_fn=lambda *_args, **_kwargs: None,
            parse_worker_count_fn=lambda: 1,
            index_queue_depth_fn=lambda _workers: 2,
            parse_repository_snapshot_async_fn=_parse_snapshot,
            commit_repository_snapshot_fn=lambda *_args, **_kwargs: None,
            iter_snapshot_file_data_batches_fn=lambda *_args, **_kwargs: iter(()),
            load_snapshot_metadata_fn=lambda *_args, **_kwargs: None,
            snapshot_file_data_exists_fn=lambda *_args, **_kwargs: False,
            save_snapshot_metadata_fn=lambda *_args, **_kwargs: None,
            save_snapshot_file_data_fn=lambda *_args, **_kwargs: None,
            emit_snapshot_facts_fn=_emit_snapshot_facts,
            persist_run_state_fn=lambda _state: None,
            record_checkpoint_metric_fn=lambda **_kwargs: None,
            update_pending_repository_gauge_fn=lambda **_kwargs: None,
            publish_runtime_progress_fn=lambda **_kwargs: None,
            publish_run_repository_coverage_fn=lambda **_kwargs: None,
            utc_now_fn=lambda: "2026-01-01T00:00:00Z",
            telemetry=telemetry,
        )
    )

    assert committed_repo_paths == [repo.resolve()]
    assert emitted == [("run-123", 1)]


class _null_context:
    """Tiny context manager for telemetry spans in pipeline tests."""

    def __enter__(self) -> "_null_context":
        return self

    def __exit__(self, *_args: object) -> None:
        return None
