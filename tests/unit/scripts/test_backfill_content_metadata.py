"""Unit tests for the content metadata backfill script."""

from __future__ import annotations

import importlib.util
import sys
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "backfill_content_metadata.py"
SUPPORT_PATH = REPO_ROOT / "scripts" / "backfill_content_metadata_support.py"


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


class _FakeStore:
    """In-memory backfill store used to verify metadata propagation."""

    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.file_updates: dict[tuple[str, str], dict[str, object]] = {}
        self.entity_updates: dict[tuple[str, str], dict[str, object]] = {}

    def fetch_file_batch(
        self,
        *,
        last_seen: tuple[str, str] | None,
        batch_size: int,
        repo_ids: list[str] | None,
        remaining_limit: int | None,
    ) -> list[dict[str, object]]:
        rows = self.rows
        if repo_ids:
            rows = [row for row in rows if row["repo_id"] in repo_ids]
        rows = sorted(rows, key=lambda row: (row["repo_id"], row["relative_path"]))
        if last_seen is not None:
            rows = [
                row
                for row in rows
                if (row["repo_id"], row["relative_path"]) > last_seen
            ]
        limit = batch_size if remaining_limit is None else min(batch_size, remaining_limit)
        return rows[:limit]

    def update_file_metadata(self, updates: list[object]) -> int:
        changed = 0
        for update in updates:
            key = (update.repo_id, update.relative_path)
            payload = {
                "artifact_type": update.artifact_type,
                "template_dialect": update.template_dialect,
                "iac_relevant": update.iac_relevant,
            }
            if self.file_updates.get(key) != payload:
                self.file_updates[key] = payload
                changed += 1
        return changed

    def update_entity_metadata(self, updates: list[object]) -> int:
        changed = 0
        for update in updates:
            key = (update.repo_id, update.relative_path)
            payload = {
                "artifact_type": update.artifact_type,
                "template_dialect": update.template_dialect,
                "iac_relevant": update.iac_relevant,
            }
            if self.entity_updates.get(key) != payload:
                self.entity_updates[key] = payload
                changed += 1
        return changed


def test_run_backfill_updates_file_and_entity_metadata() -> None:
    """Backfill should classify rows once and cascade metadata to entities."""

    support = _load_module(
        SUPPORT_PATH,
        "backfill_content_metadata_support_test",
    )
    store = _FakeStore(
        [
            {
                "repo_id": "repository:r_chart",
                "relative_path": "chart/templates/_helpers.tpl",
                "content": '{{- define "pcg.fullname" -}}pcg{{- end -}}\n',
            },
            {
                "repo_id": "repository:r_tf",
                "relative_path": "templates/ecs/container.tpl",
                "content": '{"memoryReservation": ${memory}}\n',
            },
        ]
    )

    result = support.run_backfill(
        store=store,
        batch_size=1,
        repo_ids=None,
        limit=None,
        dry_run=False,
    )

    assert result.scanned_files == 2
    assert result.updated_files == 2
    assert result.updated_entities == 2
    assert store.file_updates[("repository:r_chart", "chart/templates/_helpers.tpl")] == {
        "artifact_type": "helm_helper_tpl",
        "template_dialect": "go_template",
        "iac_relevant": True,
    }
    assert store.entity_updates[("repository:r_tf", "templates/ecs/container.tpl")] == {
        "artifact_type": "terraform_template_text",
        "template_dialect": "terraform_template",
        "iac_relevant": True,
    }


def test_run_backfill_dry_run_scans_without_mutation() -> None:
    """Dry-run mode should report candidate rows without updating store state."""

    support = _load_module(
        SUPPORT_PATH,
        "backfill_content_metadata_support_dry_run_test",
    )
    store = _FakeStore(
        [
            {
                "repo_id": "repository:r_docker",
                "relative_path": "Dockerfile",
                "content": "FROM python:3.12-slim\n",
            }
        ]
    )

    result = support.run_backfill(
        store=store,
        batch_size=50,
        repo_ids=None,
        limit=None,
        dry_run=True,
    )

    assert result.scanned_files == 1
    assert result.updated_files == 0
    assert result.updated_entities == 0
    assert store.file_updates == {}
    assert store.entity_updates == {}


def test_run_backfill_is_idempotent_for_repeated_rows() -> None:
    """A second backfill pass should not report new updates for unchanged rows."""

    support = _load_module(
        SUPPORT_PATH,
        "backfill_content_metadata_support_idempotent_test",
    )
    store = _FakeStore(
        [
            {
                "repo_id": "repository:r_ansible",
                "relative_path": "roles/web/templates/site.conf.j2",
                "content": "ServerName {{ host_name }}\n",
            }
        ]
    )

    first = support.run_backfill(
        store=store,
        batch_size=10,
        repo_ids=None,
        limit=None,
        dry_run=False,
    )
    second = support.run_backfill(
        store=store,
        batch_size=10,
        repo_ids=None,
        limit=None,
        dry_run=False,
    )

    assert first.updated_files == 1
    assert first.updated_entities == 1
    assert second.updated_files == 0
    assert second.updated_entities == 0


def test_postgres_backfill_store_batches_updates_into_one_statement() -> None:
    """The Postgres store should update one batch with one SQL statement."""

    support = _load_module(
        SUPPORT_PATH,
        "backfill_content_metadata_support_batch_test",
    )
    provider = MagicMock()
    cursor = MagicMock()
    cursor.rowcount = 3

    @contextmanager
    def _cursor():
        yield cursor

    provider._cursor = _cursor
    store = support.PostgresBackfillStore(provider)

    changed = store.update_file_metadata(
        [
            support.MetadataUpdate(
                repo_id="repository:r_chart",
                relative_path="chart/templates/_helpers.tpl",
                artifact_type="helm_helper_tpl",
                template_dialect="go_template",
                iac_relevant=True,
            ),
            support.MetadataUpdate(
                repo_id="repository:r_tf",
                relative_path="templates/ecs/container.tpl",
                artifact_type="terraform_template_text",
                template_dialect="terraform_template",
                iac_relevant=True,
            ),
        ]
    )

    assert changed == 3
    assert cursor.execute.call_count == 1
    query, params = cursor.execute.call_args.args
    assert "UPDATE content_files AS target" in query
    assert "FROM (" in query
    assert "VALUES" in query
    assert params["repo_id_0"] == "repository:r_chart"
    assert params["relative_path_1"] == "templates/ecs/container.tpl"


def test_cli_reports_summary_and_accepts_repo_id_filter(
    monkeypatch,
    capsys,
) -> None:
    """The CLI should pass through repo filters and print the backfill summary."""

    module = _load_module(
        SCRIPT_PATH,
        "backfill_content_metadata_cli_test",
    )
    captured: dict[str, object] = {}

    class _FakeProvider:
        enabled = True

    def fake_run_backfill(**kwargs):
        captured.update(kwargs)
        return module.BackfillResult(
            scanned_files=3,
            updated_files=2,
            updated_entities=4,
        )

    monkeypatch.setattr(module, "get_postgres_content_provider", lambda: _FakeProvider())
    monkeypatch.setattr(module, "PostgresBackfillStore", lambda provider: ("store", provider))
    monkeypatch.setattr(module, "run_backfill", fake_run_backfill)

    exit_code = module.main(["--repo-id", "repository:r_test", "--limit", "3"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert captured["repo_ids"] == ["repository:r_test"]
    assert captured["limit"] == 3
    assert "scanned_files=3" in output
