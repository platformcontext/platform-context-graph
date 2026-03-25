"""Unit tests for the repository coverage backfill script."""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "backfill_repository_coverage.py"
SUPPORT_PATH = REPO_ROOT / "scripts" / "backfill_repository_coverage_support.py"


def _load_module(path: Path, module_name: str) -> ModuleType:
    """Load a standalone script/support module under a unique test name."""

    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.pop(module_name, None)
    sys.path.insert(0, str(REPO_ROOT))
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@dataclass
class _RepoState:
    repo_path: str
    status: str = "completed"
    phase: str | None = "completed"
    file_count: int = 0
    error: str | None = None
    updated_at: str | None = "2026-03-24T12:05:00Z"
    commit_finished_at: str | None = "2026-03-24T12:04:00Z"


@dataclass
class _RunState:
    run_id: str
    finalization_status: str
    created_at: str
    updated_at: str
    finalization_finished_at: str | None
    last_error: str | None
    repositories: dict[str, _RepoState]


class _FakeStore:
    """In-memory repository coverage store used to verify backfill behavior."""

    def __init__(self) -> None:
        self.updates: dict[tuple[str, str], dict[str, object]] = {}

    def graph_counts(self, *, repo_metadata: dict[str, object]) -> dict[str, int]:
        if repo_metadata["name"] == "boatgest-php-youboat":
            return {
                "root_file_count": 2,
                "root_directory_count": 15,
                "file_count": 6356,
                "top_level_function_count": 40271,
                "class_method_count": 22363,
                "total_function_count": 62634,
                "class_count": 3373,
            }
        return {
            "root_file_count": 1,
            "root_directory_count": 2,
            "file_count": 12,
            "top_level_function_count": 4,
            "class_method_count": 2,
            "total_function_count": 6,
            "class_count": 1,
        }

    def content_counts(self, *, repo_id: str) -> dict[str, int]:
        if repo_id == "repository:r_221a72af":
            return {"content_file_count": 6350, "content_entity_count": 227015}
        return {"content_file_count": 5, "content_entity_count": 11}

    def existing_coverage(
        self, *, run_id: str, repo_id: str
    ) -> dict[str, object] | None:
        return self.updates.get((run_id, repo_id))

    def upsert_repository_coverage(self, update: object) -> None:
        self.updates[(update.run_id, update.repo_id)] = asdict(update)


def test_run_backfill_persists_graph_and_content_truth(monkeypatch) -> None:
    """Backfill should compute durable coverage from repo state and live counts."""

    support = _load_module(
        SUPPORT_PATH,
        "backfill_repository_coverage_support_test",
    )
    store = _FakeStore()
    run_state = _RunState(
        run_id="run-123",
        finalization_status="running",
        created_at="2026-03-24T12:00:00Z",
        updated_at="2026-03-24T12:05:00Z",
        finalization_finished_at=None,
        last_error=None,
        repositories={
            "/tmp/boatgest-php-youboat": _RepoState(
                repo_path="/tmp/boatgest-php-youboat",
                file_count=5698,
            )
        },
    )
    monkeypatch.setattr(
        support,
        "repository_metadata",
        lambda **kwargs: {
            "id": "repository:r_221a72af",
            "name": kwargs["name"],
            "local_path": kwargs["local_path"],
        },
    )
    monkeypatch.setattr(support, "git_remote_for_path", lambda _path: None)

    result = support.run_backfill(
        store=store,
        run_state=run_state,
        repo_ids=None,
        limit=None,
        dry_run=False,
    )

    assert result.run_id == "run-123"
    assert result.scanned_repositories == 1
    assert result.updated_repositories == 1
    row = store.updates[("run-123", "repository:r_221a72af")]
    assert row["graph_recursive_file_count"] == 6356
    assert row["content_file_count"] == 6350
    assert row["root_file_count"] == 2
    assert row["root_directory_count"] == 15
    assert row["total_function_count"] == 62634
    assert row["server_content_available"] is True


def test_run_backfill_is_idempotent_for_unchanged_rows(monkeypatch) -> None:
    """A second pass should not report updates when the stored row already matches."""

    support = _load_module(
        SUPPORT_PATH,
        "backfill_repository_coverage_support_idempotent_test",
    )
    store = _FakeStore()
    run_state = _RunState(
        run_id="run-123",
        finalization_status="completed",
        created_at="2026-03-24T12:00:00Z",
        updated_at="2026-03-24T12:06:00Z",
        finalization_finished_at="2026-03-24T12:06:00Z",
        last_error=None,
        repositories={
            "/tmp/simple-repo": _RepoState(
                repo_path="/tmp/simple-repo",
                file_count=12,
                commit_finished_at="2026-03-24T12:04:00Z",
            )
        },
    )
    monkeypatch.setattr(
        support,
        "repository_metadata",
        lambda **kwargs: {
            "id": "repository:r_simple",
            "name": kwargs["name"],
            "local_path": kwargs["local_path"],
        },
    )
    monkeypatch.setattr(support, "git_remote_for_path", lambda _path: None)

    first = support.run_backfill(
        store=store,
        run_state=run_state,
        repo_ids=None,
        limit=None,
        dry_run=False,
    )
    second = support.run_backfill(
        store=store,
        run_state=run_state,
        repo_ids=None,
        limit=None,
        dry_run=False,
    )

    assert first.updated_repositories == 1
    assert second.updated_repositories == 0


def test_load_target_run_state_prefers_explicit_run_id() -> None:
    """Run selection should honor an explicit run id before falling back to root."""

    support = _load_module(
        SUPPORT_PATH,
        "backfill_repository_coverage_support_select_test",
    )

    result = support.load_target_run_state(
        run_id="run-123",
        root_path=None,
        load_run_state_by_id_fn=lambda run_id: {"run_id": run_id},
        matching_run_states_fn=lambda _root: [{"run_id": "run-other"}],
    )

    assert result == {"run_id": "run-123"}


def test_default_run_root_prefers_working_checkout_root(monkeypatch) -> None:
    """Backfill should target the working checkout root before the source root."""

    support = _load_module(
        SUPPORT_PATH,
        "backfill_repository_coverage_support_default_root_test",
    )
    monkeypatch.setenv("PCG_REPOS_DIR", "/tmp/repos")
    monkeypatch.setenv("PCG_FILESYSTEM_ROOT", "/tmp/source-root")

    result = support.default_run_root()

    assert result is not None
    assert result == Path("/tmp/repos").resolve()


def test_cli_reports_summary_and_filters_repo_ids(monkeypatch, capsys) -> None:
    """The CLI should pass repo filters through and print the coverage summary."""

    module = _load_module(
        SCRIPT_PATH,
        "backfill_repository_coverage_cli_test",
    )
    captured: dict[str, object] = {}

    class _FakeStore:
        enabled = True

    class _FakeDatabaseManager:
        def __init__(self) -> None:
            captured["db_manager_created"] = True

    monkeypatch.setattr(module, "get_runtime_status_store", lambda: _FakeStore())
    monkeypatch.setattr(module, "get_postgres_content_provider", lambda: "provider")
    monkeypatch.setattr(module, "DatabaseManager", _FakeDatabaseManager)
    monkeypatch.setattr(
        module,
        "load_target_run_state",
        lambda **kwargs: {"run_id": "run-123", "repositories": {}},
    )
    monkeypatch.setattr(
        module,
        "RuntimeCoverageBackfillStore",
        lambda **kwargs: ("store", kwargs),
    )

    def fake_run_backfill(**kwargs):
        captured.update(kwargs)
        return module.CoverageBackfillResult(
            run_id="run-123",
            scanned_repositories=2,
            updated_repositories=1,
        )

    monkeypatch.setattr(module, "run_backfill", fake_run_backfill)

    exit_code = module.main(["--repo-id", "repository:r_test", "--limit", "2"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert captured["repo_ids"] == ["repository:r_test"]
    assert captured["limit"] == 2
    assert captured["run_state"] == {"run_id": "run-123", "repositories": {}}
    assert "run_id=run-123" in output
    assert "scanned_repositories=2" in output
