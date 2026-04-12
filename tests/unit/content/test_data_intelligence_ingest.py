"""Focused ingest coverage for data-intelligence content entities."""

from __future__ import annotations

from pathlib import Path

from platform_context_graph.content.identity import is_content_entity_id
from platform_context_graph.content.ingest import prepare_content_entries
from platform_context_graph.repository_identity import repository_metadata


def test_prepare_content_entries_assigns_uids_to_governance_entities(
    tmp_path: Path,
) -> None:
    """Governance buckets should participate in content-entity dual write."""

    repo_path = tmp_path / "analytics-governance"
    repo_path.mkdir()
    file_path = repo_path / "governance_replay.json"
    file_path.write_text('{"metadata":{"workspace":"finance"}}\n', encoding="utf-8")

    repository = repository_metadata(
        name="analytics-governance",
        local_path=repo_path,
        remote_url="https://github.com/platformcontext/analytics-governance.git",
    )
    file_data = {
        "path": str(file_path),
        "repo_path": str(repo_path),
        "lang": "json",
        "data_owners": [
            {
                "name": "Finance Analytics",
                "line_number": 1,
                "team": "finance-analytics",
            }
        ],
        "data_contracts": [
            {
                "name": "daily_revenue_contract",
                "line_number": 1,
                "contract_level": "gold",
            }
        ],
    }

    _file_entry, entity_entries = prepare_content_entries(
        file_data=file_data,
        repository=repository,
    )

    assert {entry.entity_type for entry in entity_entries} == {
        "DataContract",
        "DataOwner",
    }
    assert all(is_content_entity_id(entry.entity_id) for entry in entity_entries)
    assert file_data["data_owners"][0]["uid"].startswith("content-entity:")
    assert file_data["data_contracts"][0]["uid"].startswith("content-entity:")

