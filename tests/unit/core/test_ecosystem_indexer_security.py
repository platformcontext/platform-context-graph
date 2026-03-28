from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from platform_context_graph.core.ecosystem import EcosystemManifest, EcosystemRepo
from platform_context_graph.core.ecosystem_indexer import EcosystemIndexer


def _indexer() -> EcosystemIndexer:
    indexer = EcosystemIndexer(MagicMock(), MagicMock())
    indexer._create_ecosystem_nodes = lambda _manifest: None  # type: ignore[method-assign]
    return indexer


def test_index_ecosystem_rejects_non_github_clone_urls(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    manifest = EcosystemManifest(
        name="platform",
        org="platformcontext",
        repos={
            "payments-api": EcosystemRepo(
                name="payments-api",
                tier="core",
                github_url="https://evil.example.com/platformcontext/payments-api.git",
            )
        },
    )

    monkeypatch.setattr(
        "platform_context_graph.core.ecosystem_indexer.parse_manifest",
        lambda _path: manifest,
    )
    monkeypatch.setattr(
        "platform_context_graph.core.ecosystem_indexer.resolve_repo_paths",
        lambda _manifest, _base_path: {"payments-api": ""},
    )
    monkeypatch.setattr(
        "platform_context_graph.core.ecosystem_indexer.load_state",
        lambda: SimpleNamespace(repos={}, manifest_path="", last_updated=""),
    )
    monkeypatch.setattr(
        "platform_context_graph.core.ecosystem_indexer.save_state",
        lambda _state: None,
    )
    monkeypatch.setattr(
        "platform_context_graph.core.ecosystem_indexer.topological_sort_tiers",
        lambda _manifest: [],
    )

    with pytest.raises(ValueError, match="Unsupported GitHub clone target"):
        asyncio.run(
            _indexer().index_ecosystem(
                manifest_path="dependency-graph.yaml",
                base_path=str(tmp_path),
                clone_missing=True,
            )
        )


def test_index_ecosystem_clones_valid_github_urls_using_slug(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    manifest = EcosystemManifest(
        name="platform",
        org="platformcontext",
        repos={
            "payments-api": EcosystemRepo(
                name="payments-api",
                tier="core",
                github_url="https://github.com/PlatformContext/payments-api.git",
            )
        },
    )

    clone_path = tmp_path / "payments-api"
    clone_commands: list[list[str]] = []

    def _run(command, **_kwargs):
        clone_commands.append(command)
        clone_path.mkdir(parents=True, exist_ok=True)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(
        "platform_context_graph.core.ecosystem_indexer.parse_manifest",
        lambda _path: manifest,
    )
    monkeypatch.setattr(
        "platform_context_graph.core.ecosystem_indexer.resolve_repo_paths",
        lambda _manifest, _base_path: {"payments-api": ""},
    )
    monkeypatch.setattr(
        "platform_context_graph.core.ecosystem_indexer.load_state",
        lambda: SimpleNamespace(repos={}, manifest_path="", last_updated=""),
    )
    monkeypatch.setattr(
        "platform_context_graph.core.ecosystem_indexer.save_state",
        lambda _state: None,
    )
    monkeypatch.setattr(
        "platform_context_graph.core.ecosystem_indexer.topological_sort_tiers",
        lambda _manifest: [],
    )
    monkeypatch.setattr(
        "platform_context_graph.core.ecosystem_indexer.subprocess.run",
        _run,
    )

    results = asyncio.run(
        _indexer().index_ecosystem(
            manifest_path="dependency-graph.yaml",
            base_path=str(tmp_path),
            clone_missing=True,
        )
    )

    assert clone_commands == [
        ["gh", "repo", "clone", "PlatformContext/payments-api", str(clone_path)]
    ]
    assert results["missing_repos"] == []
