"""Unit tests for batched workload dependency content reads."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from platform_context_graph.resolution.workloads.dependency_support import (
    _load_runtime_dependency_targets,
)


class _FakeResult:
    def __init__(self, *, records=None):
        self._records = records or []

    def data(self):
        return self._records


def test_load_runtime_dependency_targets_batches_content_store_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Runtime dependency extraction should batch content-store reads."""

    class _FakeProvider:
        enabled = True

        def __init__(self) -> None:
            self.calls: list[list[dict[str, str]]] = []

        def get_file_contents_batch(
            self, *, repo_files: list[dict[str, str]]
        ) -> dict[tuple[str, str], str]:
            self.calls.append(list(repo_files))
            return {
                ("repository:r_search", "api-node-search.ts"): (
                    "await api.start({ services: ['api-node-forex'] });"
                ),
                ("repository:r_catalog", "api-node-catalog.ts"): (
                    "await api.start({ services: ['api-node-search'] });"
                ),
            }

    provider = _FakeProvider()
    monkeypatch.setattr(
        "platform_context_graph.content.state.get_postgres_content_provider",
        lambda: provider,
    )

    session = MagicMock()

    def resolve(query: str, kwargs: dict[str, object]) -> _FakeResult:
        if "RETURN f.path as path" in query:
            return _FakeResult(
                records=[
                    {
                        "repo_id": "repository:r_search",
                        "repo_name": "api-node-search",
                        "path": "/does/not/exist/api-node-search.ts",
                        "relative_path": "api-node-search.ts",
                    },
                    {
                        "repo_id": "repository:r_catalog",
                        "repo_name": "api-node-catalog",
                        "path": "/does/not/exist/api-node-catalog.ts",
                        "relative_path": "api-node-catalog.ts",
                    },
                ]
            )
        if "MATCH (target_repo:Repository)" in query:
            return _FakeResult(
                records=[
                    {
                        "repo_id": "repository:r_forex",
                        "repo_name": "api-node-forex",
                    },
                    {
                        "repo_id": "repository:r_search",
                        "repo_name": "api-node-search",
                    },
                ]
            )
        raise AssertionError(f"unexpected query: {query}")

    session.run.side_effect = lambda query, **kwargs: resolve(query, kwargs)

    repo_dependency_rows, workload_dependency_rows = _load_runtime_dependency_targets(
        session,
        repo_descriptors=[
            {
                "repo_id": "repository:r_search",
                "repo_name": "api-node-search",
                "workload_id": "workload:api-node-search",
            },
            {
                "repo_id": "repository:r_catalog",
                "repo_name": "api-node-catalog",
                "workload_id": "workload:api-node-catalog",
            },
        ],
    )

    assert provider.calls == [
        [
            {
                "relative_path": "api-node-search.ts",
                "repo_id": "repository:r_search",
            },
            {
                "relative_path": "api-node-catalog.ts",
                "repo_id": "repository:r_catalog",
            },
        ]
    ]
    assert repo_dependency_rows == [
        {
            "dependency_name": "api-node-forex",
            "repo_id": "repository:r_search",
            "target_repo_id": "repository:r_forex",
        },
        {
            "dependency_name": "api-node-search",
            "repo_id": "repository:r_catalog",
            "target_repo_id": "repository:r_search",
        },
    ]
    assert workload_dependency_rows == [
        {
            "dependency_name": "api-node-forex",
            "repo_id": "repository:r_search",
            "target_repo_id": "repository:r_forex",
            "target_workload_id": "workload:api-node-forex",
            "workload_id": "workload:api-node-search",
        },
        {
            "dependency_name": "api-node-search",
            "repo_id": "repository:r_catalog",
            "target_repo_id": "repository:r_search",
            "target_workload_id": "workload:api-node-search",
            "workload_id": "workload:api-node-catalog",
        },
    ]
