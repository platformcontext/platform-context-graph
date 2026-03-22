"""Unit tests for content-store ingest helpers."""

from __future__ import annotations

from pathlib import Path

from platform_context_graph.content.identity import is_content_entity_id
from platform_context_graph.content.ingest import (
    CONTENT_ENTITY_BUCKETS,
    prepare_content_entries,
    repository_metadata_from_row,
)
from platform_context_graph.repository_identity import repository_metadata


def test_prepare_content_entries_uses_portable_file_and_entity_identity(
    tmp_path: Path,
) -> None:
    """Build file and entity rows from repo-relative identity, not raw paths."""

    repo_path = tmp_path / "payments-api"
    repo_path.mkdir()
    file_path = repo_path / "src" / "payments.py"
    file_path.parent.mkdir()
    file_path.write_text(
        "def process_payment():\n    return True\n",
        encoding="utf-8",
    )

    repository = repository_metadata(
        name="payments-api",
        local_path=repo_path,
        remote_url="git@github.com:platformcontext/payments-api.git",
    )
    file_data = {
        "path": str(file_path),
        "repo_path": str(repo_path),
        "lang": "python",
        "functions": [
            {
                "name": "process_payment",
                "line_number": 1,
                "end_line": 2,
                "source": "def process_payment():\n    return True\n",
            }
        ],
    }

    file_entry, entity_entries = prepare_content_entries(
        file_data=file_data,
        repository=repository,
    )

    assert file_entry is not None
    assert file_entry.repo_id == repository["id"]
    assert file_entry.relative_path == "src/payments.py"
    assert len(entity_entries) == 1
    assert entity_entries[0].repo_id == repository["id"]
    assert entity_entries[0].relative_path == "src/payments.py"
    assert entity_entries[0].entity_type == "Function"
    assert entity_entries[0].source_cache.startswith("def process_payment")
    assert is_content_entity_id(entity_entries[0].entity_id)
    assert file_data["functions"][0]["uid"] == entity_entries[0].entity_id


def test_prepare_content_entries_derives_infra_source_cache_from_file_text(
    tmp_path: Path,
) -> None:
    """Use file slices for infra entities whose ``source`` field is metadata."""

    repo_path = tmp_path / "infra-live"
    repo_path.mkdir()
    file_path = repo_path / "main.tf"
    file_path.write_text(
        'module "vpc" {\n'
        '  source = "terraform-aws-modules/vpc/aws"\n'
        '  version = "5.0.0"\n'
        "}\n",
        encoding="utf-8",
    )

    repository = repository_metadata(
        name="infra-live",
        local_path=repo_path,
        remote_url="https://github.com/platformcontext/infra-live.git",
    )
    file_data = {
        "path": str(file_path),
        "repo_path": str(repo_path),
        "lang": "hcl",
        "terraform_modules": [
            {
                "name": "vpc",
                "line_number": 1,
                "source": "terraform-aws-modules/vpc/aws",
                "version": "5.0.0",
            }
        ],
    }

    file_entry, entity_entries = prepare_content_entries(
        file_data=file_data,
        repository=repository,
    )

    assert file_entry is not None
    assert len(entity_entries) == 1
    assert entity_entries[0].entity_type == "TerraformModule"
    assert entity_entries[0].source_cache.startswith('module "vpc"')
    assert "terraform-aws-modules/vpc/aws" in entity_entries[0].source_cache
    assert entity_entries[0].source_cache != "terraform-aws-modules/vpc/aws"


def test_repository_metadata_from_row_prefers_stored_remote_identity(
    tmp_path: Path,
) -> None:
    """Preserve stored repository metadata when the graph row already has it."""

    repo_path = tmp_path / "catalog"
    repo_path.mkdir()
    row = {
        "id": "repository:r_deadbeef",
        "name": "catalog",
        "path": str(repo_path),
        "local_path": str(repo_path),
        "remote_url": "https://github.com/platformcontext/catalog",
        "repo_slug": "platformcontext/catalog",
        "has_remote": True,
    }

    metadata = repository_metadata_from_row(row=row, repo_path=repo_path)

    assert metadata["id"] == "repository:r_deadbeef"
    assert metadata["remote_url"] == "https://github.com/platformcontext/catalog"
    assert metadata["repo_slug"] == "platformcontext/catalog"
    assert metadata["local_path"] == str(repo_path.resolve())


def test_content_entity_bucket_labels_include_expected_infra_and_code_types() -> None:
    """Expose one shared list of content-bearing labels for queries and writes."""

    bucket_labels = {label for _, label in CONTENT_ENTITY_BUCKETS}

    assert "Function" in bucket_labels
    assert "Class" in bucket_labels
    assert "K8sResource" in bucket_labels
    assert "TerraformModule" in bucket_labels
