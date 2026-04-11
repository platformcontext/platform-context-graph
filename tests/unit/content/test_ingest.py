"""Unit tests for content-store ingest helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

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


def test_prepare_content_entries_for_raw_text_file_only_writes_file_content(
    tmp_path: Path,
) -> None:
    """Raw-text indexed files should dual-write searchable file content only."""

    repo_path = tmp_path / "service"
    repo_path.mkdir()
    file_path = repo_path / "Dockerfile"
    file_path.write_text(
        "FROM python:3.12-slim\nRUN pip install -r requirements.txt\n",
        encoding="utf-8",
    )

    repository = repository_metadata(
        name="service",
        local_path=repo_path,
        remote_url="https://github.com/platformcontext/service.git",
    )
    file_data = {
        "path": str(file_path),
        "repo_path": str(repo_path),
        "lang": "dockerfile",
        "functions": [],
        "classes": [],
        "imports": [],
        "variables": [],
        "function_calls": [],
    }

    file_entry, entity_entries = prepare_content_entries(
        file_data=file_data,
        repository=repository,
    )

    assert file_entry is not None
    assert file_entry.relative_path == "Dockerfile"
    assert file_entry.language == "dockerfile"
    assert entity_entries == []


def test_prepare_content_entries_reads_cp1252_source_text(
    tmp_path: Path,
) -> None:
    """Legacy Windows-1252 files should still populate file and entity content."""

    repo_path = tmp_path / "legacy-service"
    repo_path.mkdir()
    file_path = repo_path / "security.php"
    file_path.write_bytes("<?php\n$price = '£9';\n".encode("cp1252"))

    repository = repository_metadata(
        name="legacy-service",
        local_path=repo_path,
        remote_url="https://github.com/platformcontext/legacy-service.git",
    )
    file_data = {
        "path": str(file_path),
        "repo_path": str(repo_path),
        "lang": "php",
        "variables": [{"name": "$price", "line_number": 2}],
    }

    file_entry, entity_entries = prepare_content_entries(
        file_data=file_data,
        repository=repository,
    )

    assert file_entry is not None
    assert file_entry.content == "<?php\n$price = '£9';\n"
    assert len(entity_entries) == 1
    assert entity_entries[0].source_cache == "$price = '£9';\n"


def test_prepare_content_entries_assigns_uids_to_sql_entities(
    tmp_path: Path,
) -> None:
    """SQL buckets should participate in the content-entity dual-write path."""

    repo_path = tmp_path / "warehouse"
    repo_path.mkdir()
    file_path = repo_path / "schema.sql"
    file_path.write_text(
        "CREATE TABLE public.users (\n  id BIGSERIAL PRIMARY KEY\n);\n",
        encoding="utf-8",
    )

    repository = repository_metadata(
        name="warehouse",
        local_path=repo_path,
        remote_url="https://github.com/platformcontext/warehouse.git",
    )
    file_data = {
        "path": str(file_path),
        "repo_path": str(repo_path),
        "lang": "sql",
        "sql_tables": [{"name": "public.users", "line_number": 1}],
        "sql_columns": [{"name": "public.users.id", "line_number": 2}],
    }

    _file_entry, entity_entries = prepare_content_entries(
        file_data=file_data,
        repository=repository,
    )

    assert {entry.entity_type for entry in entity_entries} == {"SqlTable", "SqlColumn"}
    assert all(is_content_entity_id(entry.entity_id) for entry in entity_entries)
    assert file_data["sql_tables"][0]["uid"].startswith("content-entity:")
    assert file_data["sql_columns"][0]["uid"].startswith("content-entity:")


def test_prepare_content_entries_strips_nul_bytes_for_content_store(
    tmp_path: Path,
) -> None:
    """Embedded NUL bytes should be stripped before building content-store rows."""

    repo_path = tmp_path / "legacy-php"
    repo_path.mkdir()
    file_path = repo_path / "timthumb.php"
    file_path.write_bytes(b'<?php\nfunction thumbnail() {\n    return "A\x00B";\n}\n')

    repository = repository_metadata(
        name="legacy-php",
        local_path=repo_path,
        remote_url="https://github.com/platformcontext/legacy-php.git",
    )
    file_data = {
        "path": str(file_path),
        "repo_path": str(repo_path),
        "lang": "php",
        "functions": [
            {
                "name": "thumbnail",
                "line_number": 2,
                "end_line": 4,
                "source": 'function thumbnail() {\n    return "A\x00B";\n}\n',
            }
        ],
    }

    file_entry, entity_entries = prepare_content_entries(
        file_data=file_data,
        repository=repository,
    )

    assert file_entry is not None
    assert "\x00" not in file_entry.content
    assert 'return "AB";' in file_entry.content
    assert len(entity_entries) == 1
    assert "\x00" not in entity_entries[0].source_cache
    assert 'return "AB";' in entity_entries[0].source_cache


def test_prepare_content_entries_skips_symlink_targets_outside_repository(
    tmp_path: Path,
) -> None:
    """Content ingest should not follow repository symlinks outside the repo root."""

    repo_path = tmp_path / "service"
    repo_path.mkdir()
    external_path = tmp_path / "external" / "secrets.py"
    external_path.parent.mkdir()
    external_path.write_text(
        "def leak_secret():\n    return 'nope'\n", encoding="utf-8"
    )

    symlink_path = repo_path / "src" / "secrets.py"
    symlink_path.parent.mkdir()
    try:
        symlink_path.symlink_to(external_path)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable in test environment: {exc}")

    repository = repository_metadata(
        name="service",
        local_path=repo_path,
        remote_url="https://github.com/platformcontext/service.git",
    )
    file_data = {
        "path": str(symlink_path),
        "repo_path": str(repo_path),
        "lang": "python",
        "functions": [{"name": "leak_secret", "line_number": 1}],
    }

    file_entry, entity_entries = prepare_content_entries(
        file_data=file_data,
        repository=repository,
    )

    assert file_entry is None
    assert entity_entries == []


def test_prepare_content_entries_stamps_file_metadata_onto_entities(
    tmp_path: Path,
) -> None:
    """File classification metadata should flow to the file row and all entities."""

    repo_path = tmp_path / "infra-live"
    repo_path.mkdir()
    file_path = repo_path / "main.tf"
    file_path.write_text(
        'module "service" {\n'
        '  source = "./modules/service"\n'
        '  name   = "${var.environment}-api"\n'
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
                "name": "service",
                "line_number": 1,
                "source": "./modules/service",
            }
        ],
    }

    file_entry, entity_entries = prepare_content_entries(
        file_data=file_data,
        repository=repository,
    )

    assert file_entry is not None
    assert file_entry.artifact_type == "terraform_hcl"
    assert file_entry.template_dialect == "terraform_template"
    assert file_entry.iac_relevant is True
    assert len(entity_entries) == 1
    assert entity_entries[0].artifact_type == "terraform_hcl"
    assert entity_entries[0].template_dialect == "terraform_template"
    assert entity_entries[0].iac_relevant is True


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
    assert "KustomizeOverlay" in bucket_labels
    assert "HelmValues" in bucket_labels
    assert "TerraformProvider" in bucket_labels
    assert "TerraformLocal" in bucket_labels
    assert "TerragruntConfig" in bucket_labels
    assert "CloudFormationResource" in bucket_labels
    assert "CloudFormationParameter" in bucket_labels
    assert "CloudFormationOutput" in bucket_labels
