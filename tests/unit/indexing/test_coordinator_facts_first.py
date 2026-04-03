"""Unit tests for execute_index_run facts-first cutover behavior."""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import sys
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = REPO_ROOT / "src" / "platform_context_graph"


def _load_module(module_name: str, module_path: Path) -> ModuleType:
    """Load one module from source without importing package side effects."""

    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.pop(module_name, None)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _load_coordinator_module() -> ModuleType:
    """Load the coordinator with a minimal dependency skeleton."""

    try:
        return importlib.import_module("platform_context_graph.indexing.coordinator")
    except ImportError:
        module_names = (
            "platform_context_graph",
            "platform_context_graph.collectors",
            "platform_context_graph.collectors.git",
            "platform_context_graph.collectors.git.indexing",
            "platform_context_graph.collectors.git.parse_worker",
            "platform_context_graph.graph",
            "platform_context_graph.graph.persistence",
            "platform_context_graph.graph.persistence.worker",
            "platform_context_graph.indexing",
            "platform_context_graph.indexing.commit_timing",
            "platform_context_graph.indexing.coordinator",
            "platform_context_graph.indexing.coordinator_async_commit",
            "platform_context_graph.indexing.coordinator_coverage",
            "platform_context_graph.indexing.coordinator_models",
            "platform_context_graph.indexing.coordinator_pipeline",
            "platform_context_graph.indexing.coordinator_runtime_status",
            "platform_context_graph.indexing.coordinator_storage",
            "platform_context_graph.indexing.run_summary",
            "platform_context_graph.observability",
            "platform_context_graph.repository_identity",
            "platform_context_graph.utils",
            "platform_context_graph.utils.debug_log",
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

            utils_pkg = ModuleType("platform_context_graph.utils")
            utils_pkg.__path__ = [str(PACKAGE_ROOT / "utils")]
            sys.modules["platform_context_graph.utils"] = utils_pkg

            collectors_indexing = ModuleType(
                "platform_context_graph.collectors.git.indexing"
            )
            collectors_indexing.finalize_index_batch = lambda *_args, **_kwargs: None
            collectors_indexing.parse_repository_snapshot_async = None
            collectors_indexing.resolve_repository_file_sets = None

            def _merge_import_maps(
                target: dict[str, list[str]],
                source: dict[str, list[str]],
            ) -> dict[str, list[str]]:
                for symbol, paths in source.items():
                    merged = target.setdefault(symbol, [])
                    for path in paths:
                        if path not in merged:
                            merged.append(path)
                return target

            collectors_indexing.merge_import_maps = _merge_import_maps
            sys.modules["platform_context_graph.collectors.git.indexing"] = (
                collectors_indexing
            )

            parse_worker = ModuleType("platform_context_graph.collectors.git.parse_worker")
            parse_worker.init_parse_worker = lambda: None
            sys.modules["platform_context_graph.collectors.git.parse_worker"] = (
                parse_worker
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
                return None

            async_commit.commit_repository_snapshot_async = (
                _commit_repository_snapshot_async
            )
            sys.modules["platform_context_graph.indexing.coordinator_async_commit"] = (
                async_commit
            )

            observability = ModuleType("platform_context_graph.observability")
            observability.get_observability = lambda: SimpleNamespace()
            sys.modules["platform_context_graph.observability"] = observability

            repository_identity = ModuleType(
                "platform_context_graph.repository_identity"
            )
            repository_identity.git_remote_for_path = lambda _path: None
            repository_identity.repository_metadata = (
                lambda **kwargs: {"id": kwargs["local_path"], "name": kwargs["name"]}
            )
            sys.modules["platform_context_graph.repository_identity"] = (
                repository_identity
            )

            debug_log = ModuleType("platform_context_graph.utils.debug_log")
            debug_log.emit_log_call = lambda logger_fn, message, **_kwargs: logger_fn(
                message
            )
            debug_log.warning_logger = lambda *_args, **_kwargs: None
            sys.modules["platform_context_graph.utils.debug_log"] = debug_log

            coordinator_coverage = ModuleType(
                "platform_context_graph.indexing.coordinator_coverage"
            )
            coordinator_coverage.publish_run_repository_coverage = (
                lambda **_kwargs: None
            )
            sys.modules["platform_context_graph.indexing.coordinator_coverage"] = (
                coordinator_coverage
            )

            coordinator_runtime_status = ModuleType(
                "platform_context_graph.indexing.coordinator_runtime_status"
            )
            coordinator_runtime_status.publish_runtime_progress = (
                lambda **_kwargs: None
            )
            sys.modules[
                "platform_context_graph.indexing.coordinator_runtime_status"
            ] = coordinator_runtime_status

            run_summary = ModuleType("platform_context_graph.indexing.run_summary")

            class RunSummaryConfig:
                @classmethod
                def from_env(cls) -> "RunSummaryConfig":
                    return cls()

            run_summary.RunSummaryConfig = RunSummaryConfig
            run_summary.build_run_summary = lambda **_kwargs: {}
            run_summary.write_run_summary = lambda **_kwargs: "/tmp/run-summary.json"
            sys.modules["platform_context_graph.indexing.run_summary"] = run_summary

            coordinator_storage = ModuleType(
                "platform_context_graph.indexing.coordinator_storage"
            )
            coordinator_storage._archive_run = lambda *_args, **_kwargs: None
            coordinator_storage._delete_snapshots = lambda *_args, **_kwargs: None
            coordinator_storage._graph_store_adapter = lambda *_args, **_kwargs: None
            coordinator_storage._iter_snapshot_file_data = (
                lambda *_args, **_kwargs: iter(())
            )
            coordinator_storage._iter_snapshot_file_data_batches = (
                lambda *_args, **_kwargs: iter(())
            )
            coordinator_storage._load_or_create_run = lambda *_args, **_kwargs: None
            coordinator_storage._load_run_state_by_id = lambda *_args, **_kwargs: None
            coordinator_storage._load_snapshot_metadata = (
                lambda *_args, **_kwargs: None
            )
            coordinator_storage._matching_run_states = lambda *_args, **_kwargs: []
            coordinator_storage._persist_run_state = lambda *_args, **_kwargs: None
            coordinator_storage._record_checkpoint_metric = (
                lambda *_args, **_kwargs: None
            )
            coordinator_storage._snapshot_file_data_exists = (
                lambda *_args, **_kwargs: False
            )
            coordinator_storage._save_snapshot_file_data = (
                lambda *_args, **_kwargs: None
            )
            coordinator_storage._save_snapshot_metadata = (
                lambda *_args, **_kwargs: None
            )
            coordinator_storage._update_pending_repository_gauge = (
                lambda *_args, **_kwargs: None
            )
            coordinator_storage._utc_now = lambda: "2026-01-01T00:00:00Z"
            sys.modules["platform_context_graph.indexing.coordinator_storage"] = (
                coordinator_storage
            )

            _load_module(
                "platform_context_graph.indexing.commit_timing",
                PACKAGE_ROOT / "indexing" / "commit_timing.py",
            )
            _load_module(
                "platform_context_graph.indexing.coordinator_models",
                PACKAGE_ROOT / "indexing" / "coordinator_models.py",
            )
            _load_module(
                "platform_context_graph.indexing.coordinator_pipeline",
                PACKAGE_ROOT / "indexing" / "coordinator_pipeline.py",
            )
            coordinator = _load_module(
                "platform_context_graph.indexing.coordinator",
                PACKAGE_ROOT / "indexing" / "coordinator.py",
            )
        finally:
            for module_name, original_module in original_modules.items():
                if original_module is None:
                    sys.modules.pop(module_name, None)
                else:
                    sys.modules[module_name] = original_module
        return coordinator


COORDINATOR = _load_coordinator_module()
MODELS = importlib.import_module("platform_context_graph.indexing.coordinator_models")
IndexRunState = MODELS.IndexRunState
RepositoryRunState = MODELS.RepositoryRunState
RepositoryParseSnapshot = importlib.import_module(
    "platform_context_graph.collectors.git.types"
).RepositoryParseSnapshot


def test_execute_index_run_uses_facts_first_handlers_and_skips_legacy_finalize(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """When fact runtime is enabled, indexing should bypass legacy finalization."""

    repo = tmp_path / "service"
    repo.mkdir()
    file_path = repo / "app.py"
    file_path.write_text("def handler():\n    return 1\n", encoding="utf-8")

    run_state = IndexRunState(
        run_id="run-123",
        root_path=str(tmp_path.resolve()),
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

    async def _parse_repository_snapshot_async(
        _builder,
        repo_path,
        repo_files,
        **_kwargs,
    ) -> RepositoryParseSnapshot:
        return RepositoryParseSnapshot(
            repo_path=str(repo_path.resolve()),
            file_count=len(repo_files),
            imports_map={"handler": [str(repo_files[0].resolve())]},
            file_data=[
                {
                    "path": str(repo_files[0].resolve()),
                    "repo_path": str(repo_path.resolve()),
                    "lang": "python",
                    "functions": [{"name": "handler", "line_number": 1}],
                }
            ],
        )

    monkeypatch.setattr(
        COORDINATOR,
        "resolve_repository_file_sets",
        lambda *_args, **_kwargs: {
            repo.resolve(): [file_path],
        },
    )
    monkeypatch.setattr(
        COORDINATOR,
        "_load_or_create_run",
        lambda **_kwargs: (run_state, False),
    )
    monkeypatch.setattr(
        COORDINATOR,
        "parse_repository_snapshot_async",
        _parse_repository_snapshot_async,
    )
    monkeypatch.setattr(COORDINATOR, "facts_first_projection_enabled", lambda: True)
    monkeypatch.setattr(
        COORDINATOR,
        "get_fact_store",
        lambda: SimpleNamespace(enabled=True),
    )
    monkeypatch.setattr(
        COORDINATOR,
        "get_fact_work_queue",
        lambda: SimpleNamespace(enabled=True),
    )

    emitted_runs: list[str] = []
    committed_snapshots: list[str] = []
    finalized_metrics: list[dict[str, object]] = []

    monkeypatch.setattr(
        COORDINATOR,
        "create_snapshot_fact_emitter",
        lambda **_kwargs: (
            lambda *, run_id, repo_path, snapshot, is_dependency: emitted_runs.append(
                f"{run_id}:{repo_path.name}:{snapshot.file_count}:{int(is_dependency)}"
            )
            or snapshot.file_count
        ),
    )
    monkeypatch.setattr(
        COORDINATOR,
        "create_facts_first_commit_callback",
        lambda **_kwargs: (
            lambda _builder, snapshot, **_commit_kwargs: committed_snapshots.append(
                snapshot.repo_path
            )
        ),
    )
    monkeypatch.setattr(
        COORDINATOR,
        "finalize_facts_first_run",
        lambda **kwargs: (
            setattr(kwargs["run_state"], "status", "completed"),
            setattr(kwargs["run_state"], "finalization_status", "completed"),
            finalized_metrics.append(kwargs["last_metrics"]),
        ),
    )
    monkeypatch.setattr(
        COORDINATOR,
        "finalize_repository_batch",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("legacy finalize path should not run")
        ),
    )
    monkeypatch.setattr(
        COORDINATOR,
        "_commit_repository_snapshot",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("legacy direct commit path should not run")
        ),
    )
    monkeypatch.setattr(
        COORDINATOR,
        "publish_run_repository_coverage",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(COORDINATOR, "_persist_run_state", lambda _state: None)
    monkeypatch.setattr(COORDINATOR, "_delete_snapshots", lambda *_args: None)
    monkeypatch.setattr(COORDINATOR, "_save_snapshot_metadata", lambda *_args: None)
    monkeypatch.setattr(COORDINATOR, "_save_snapshot_file_data", lambda *_args: None)
    monkeypatch.setattr(
        COORDINATOR,
        "_snapshot_file_data_exists",
        lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr(COORDINATOR, "_load_snapshot_metadata", lambda *_args: None)
    monkeypatch.setattr(
        COORDINATOR,
        "_iter_snapshot_file_data_batches",
        lambda *_args, **_kwargs: iter(()),
    )
    monkeypatch.setattr(COORDINATOR, "_iter_snapshot_file_data", lambda *_args: iter(()))
    monkeypatch.setattr(COORDINATOR, "_record_checkpoint_metric", lambda **_kwargs: None)
    monkeypatch.setattr(
        COORDINATOR,
        "_update_pending_repository_gauge",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(COORDINATOR, "_publish_runtime_progress", lambda **_kwargs: None)
    monkeypatch.setattr(COORDINATOR, "_utc_now", lambda: "2026-01-01T00:00:00Z")

    @contextmanager
    def _index_run_scope(**_kwargs):
        yield SimpleNamespace(status=None, finalization_status=None)

    @contextmanager
    def _span_scope(*_args, **_kwargs):
        yield SimpleNamespace(record_exception=lambda _exc: None)

    telemetry = SimpleNamespace(
        index_run=_index_run_scope,
        start_span=_span_scope,
        record_index_repositories=lambda **_kwargs: None,
        record_index_repository_duration=lambda **_kwargs: None,
    )
    monkeypatch.setattr(COORDINATOR, "get_observability", lambda: telemetry)

    builder = SimpleNamespace(
        job_manager=SimpleNamespace(update_job=lambda *_args, **_kwargs: None)
    )

    result = asyncio.run(
        COORDINATOR.execute_index_run(
            builder,
            tmp_path,
            is_dependency=False,
            job_id=None,
            selected_repositories=[repo],
            family="index",
            source="manual",
            force=False,
            component="cli",
            asyncio_module=asyncio,
            datetime_cls=SimpleNamespace(now=lambda: None),
            info_logger_fn=lambda *_args, **_kwargs: None,
            warning_logger_fn=lambda *_args, **_kwargs: None,
            error_logger_fn=lambda *_args, **_kwargs: None,
            job_status_enum=SimpleNamespace(COMPLETED="completed", FAILED="failed"),
            pathspec_module=SimpleNamespace(),
        )
    )

    assert emitted_runs == ["run-123:service:1:0"]
    assert committed_snapshots == [str(repo.resolve())]
    assert finalized_metrics == [{"projected_repositories": 1}]
    assert result.status == "completed"
