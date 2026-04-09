"""Tests for declarative framework semantic pack loading and execution."""

from __future__ import annotations

from pathlib import Path

import yaml

from platform_context_graph.parsers.framework_packs import (
    load_framework_pack_specs,
    validate_framework_pack_specs,
)
from platform_context_graph.parsers.framework_semantics import (
    build_framework_semantics,
)


def test_load_framework_pack_specs_exposes_supported_framework_packs() -> None:
    """Load the canonical declarative framework packs from disk."""

    specs = load_framework_pack_specs()

    names = {spec["framework"] for spec in specs}

    assert "aws" in names
    assert "express" in names
    assert "fastapi" in names
    assert "flask" in names
    assert "gcp" in names
    assert "hapi" in names
    assert "react" in names
    assert "nextjs" in names


def test_validate_framework_pack_specs_has_no_errors() -> None:
    """Validate the built-in framework pack set."""

    assert validate_framework_pack_specs() == []


def test_load_framework_pack_specs_supports_repo_root_override(tmp_path: Path) -> None:
    """Load declarative packs from an explicit repository-style root override."""

    spec_root = (
        tmp_path
        / "src"
        / "platform_context_graph"
        / "parsers"
        / "framework_packs"
        / "specs"
    )
    spec_root.mkdir(parents=True)
    spec_root.joinpath("demo.yaml").write_text(
        yaml.safe_dump(
            {
                "framework": "demo",
                "title": "Demo Framework Pack",
                "strategy": "react_module",
                "compute_order": 10,
                "surface_order": 10,
                "config": {
                    "boundary_directives": ["client", "server"],
                    "hook_name_pattern": r"^use[A-Z][A-Za-z0-9]*$",
                    "component_name_pattern": r"^[A-Z][A-Za-z0-9]*$",
                    "component_export_patterns": [],
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    specs = load_framework_pack_specs(tmp_path)

    assert specs[0]["framework"] == "demo"
    assert specs[0]["spec_path"] == (
        "src/platform_context_graph/parsers/framework_packs/specs/demo.yaml"
    )


def test_validate_framework_pack_specs_rejects_unknown_strategy(
    tmp_path: Path,
) -> None:
    """Reject framework-pack specs that declare unsupported strategies."""

    spec_root = (
        tmp_path
        / "src"
        / "platform_context_graph"
        / "parsers"
        / "framework_packs"
        / "specs"
    )
    spec_root.mkdir(parents=True)
    spec_root.joinpath("broken.yaml").write_text(
        yaml.safe_dump(
            {
                "framework": "demo",
                "title": "Broken Framework Pack",
                "strategy": "unknown_strategy",
                "compute_order": 10,
                "surface_order": 20,
                "config": {},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    errors = validate_framework_pack_specs(tmp_path)

    assert (
        "src/platform_context_graph/parsers/framework_packs/specs/broken.yaml: "
        "unknown strategy 'unknown_strategy'"
    ) in errors


def test_validate_framework_pack_specs_rejects_missing_required_fields(
    tmp_path: Path,
) -> None:
    """Reject framework-pack specs missing required top-level fields."""

    spec_root = (
        tmp_path
        / "src"
        / "platform_context_graph"
        / "parsers"
        / "framework_packs"
        / "specs"
    )
    spec_root.mkdir(parents=True)
    spec_root.joinpath("broken.yaml").write_text(
        yaml.safe_dump(
            {
                "framework": "demo",
                "strategy": "react_module",
                "compute_order": "ten",
                "surface_order": 20,
                "config": [],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    errors = validate_framework_pack_specs(tmp_path)

    assert (
        "src/platform_context_graph/parsers/framework_packs/specs/broken.yaml: "
        "missing required field 'title'"
    ) in errors
    assert (
        "src/platform_context_graph/parsers/framework_packs/specs/broken.yaml: "
        "field 'compute_order' must be an integer"
    ) in errors
    assert (
        "src/platform_context_graph/parsers/framework_packs/specs/broken.yaml: "
        "field 'config' must be a mapping"
    ) in errors


def test_validate_framework_pack_specs_rejects_duplicate_framework_keys(
    tmp_path: Path,
) -> None:
    """Reject duplicate framework keys that would collide at runtime."""

    spec_root = (
        tmp_path
        / "src"
        / "platform_context_graph"
        / "parsers"
        / "framework_packs"
        / "specs"
    )
    spec_root.mkdir(parents=True)
    for filename in ("one.yaml", "two.yaml"):
        spec_root.joinpath(filename).write_text(
            yaml.safe_dump(
                {
                    "framework": "demo",
                    "title": f"{filename} Framework Pack",
                    "strategy": "react_module",
                    "compute_order": 10,
                    "surface_order": 20,
                    "config": {},
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )

    errors = validate_framework_pack_specs(tmp_path)

    assert (
        "src/platform_context_graph/parsers/framework_packs/specs/two.yaml: "
        "duplicate framework 'demo' also declared in "
        "src/platform_context_graph/parsers/framework_packs/specs/one.yaml"
    ) in errors


def test_build_framework_semantics_accepts_custom_react_pack_specs() -> None:
    """Use declarative pack specs instead of hard-coded React constants."""

    semantics = build_framework_semantics(
        Path("widgets/Widget.view"),
        """\
'use client';

export function Widget() {
  return null;
}
""",
        imports=[],
        functions=[{"name": "Widget"}],
        function_calls=[],
        classes=[],
        components=[],
        pack_specs=[
            {
                "framework": "react",
                "strategy": "react_module",
                "compute_order": 10,
                "surface_order": 20,
                "config": {
                    "boundary_directives": ["client", "server"],
                    "hook_name_pattern": r"^use[A-Z][A-Za-z0-9]*$",
                    "component_name_pattern": r"^[A-Z][A-Za-z0-9]*$",
                    "react_candidate_path_suffixes": [".view"],
                    "react_candidate_path_segments": ["widgets"],
                    "react_candidate_import_sources": ["react"],
                    "component_export_patterns": [
                        r"^\s*export\s+(?:async\s+)?function\s+([A-Z][A-Za-z0-9]*)\b"
                    ],
                },
            }
        ],
    )

    assert semantics["frameworks"] == ["react"]
    assert semantics["react"]["boundary"] == "client"
    assert semantics["react"]["component_exports"] == ["Widget"]
    assert semantics["react"]["hooks_used"] == []


def test_build_framework_semantics_accepts_custom_nextjs_pack_specs() -> None:
    """Use declarative pack specs instead of hard-coded Next.js constants."""

    semantics = build_framework_semantics(
        Path("src/screens/boats/view.ts"),
        """\
import { RequestLike, ResponseLike } from 'custom/server';

export async function FETCH(_request: RequestLike) {
  return ResponseLike.json({ ok: true });
}
""",
        imports=[
            {"source": "custom/server", "name": "RequestLike", "alias": "RequestLike"},
            {
                "source": "custom/server",
                "name": "ResponseLike",
                "alias": "ResponseLike",
            },
        ],
        functions=[{"name": "FETCH"}],
        function_calls=[],
        classes=[],
        components=[],
        pack_specs=[
            {
                "framework": "nextjs",
                "strategy": "nextjs_app_router",
                "compute_order": 20,
                "surface_order": 10,
                "config": {
                    "module_root_segments": ["screens"],
                    "module_kinds": ["view", "route"],
                    "route_verbs": ["FETCH"],
                    "static_metadata_patterns": [
                        r"^\s*export\s+const\s+metadata\b",
                    ],
                    "dynamic_metadata_patterns": [
                        r"^\s*export\s+(?:async\s+)?function\s+generateMetadata\b",
                    ],
                    "request_response_import_sources": ["custom/server"],
                    "request_response_api_names": ["RequestLike", "ResponseLike"],
                },
            }
        ],
    )

    assert semantics["frameworks"] == ["nextjs"]
    assert semantics["nextjs"]["module_kind"] == "view"
    assert semantics["nextjs"]["route_verbs"] == ["FETCH"]
    assert semantics["nextjs"]["route_segments"] == ["boats"]
    assert semantics["nextjs"]["request_response_apis"] == [
        "RequestLike",
        "ResponseLike",
    ]


def test_build_framework_semantics_skips_packs_for_other_languages() -> None:
    """Ignore pack specs whose declared parser lanes do not match the file."""

    semantics = build_framework_semantics(
        Path("service.py"),
        "def handler():\n    return None\n",
        parser_language="python",
        imports=[],
        functions=[{"name": "handler", "decorators": []}],
        function_calls=[],
        variables=[],
        classes=[],
        components=[],
        pack_specs=[
            {
                "framework": "react",
                "strategy": "react_module",
                "compute_order": 10,
                "surface_order": 20,
                "languages": ["javascript", "typescriptjsx"],
                "config": {
                    "boundary_directives": ["client", "server"],
                    "hook_name_pattern": r"^use[A-Z][A-Za-z0-9]*$",
                    "component_name_pattern": r"^[A-Z][A-Za-z0-9]*$",
                    "component_export_patterns": [],
                },
            }
        ],
    )

    assert semantics["frameworks"] == []


def test_build_framework_semantics_accepts_custom_provider_pack_specs() -> None:
    """Use declarative provider packs instead of hard-coded SDK constants."""

    semantics = build_framework_semantics(
        Path("src/aws/client.ts"),
        """\
import { S3Client, GetObjectCommand } from '@aws-sdk/client-s3';

const client = new S3Client({ region: 'us-east-1' });
""",
        parser_language="typescript",
        imports=[
            {
                "source": "@aws-sdk/client-s3",
                "name": "@aws-sdk/client-s3",
                "alias": "{ S3Client, GetObjectCommand }",
            }
        ],
        functions=[],
        function_calls=[
            {
                "name": "S3Client",
                "full_name": "new S3Client({ region: 'us-east-1' })",
            }
        ],
        variables=[],
        classes=[],
        components=[],
        pack_specs=[
            {
                "framework": "aws",
                "strategy": "provider_sdk_usage",
                "compute_order": 10,
                "surface_order": 10,
                "languages": ["javascript", "typescript"],
                "config": {
                    "import_source_prefixes": ["@aws-sdk/client-"],
                    "client_name_suffixes": ["Client"],
                },
            }
        ],
    )

    assert semantics["frameworks"] == ["aws"]
    assert semantics["aws"]["services"] == ["s3"]
    assert semantics["aws"]["client_symbols"] == ["S3Client"]


def test_build_framework_semantics_limits_provider_clients_to_imported_sdk_symbols() -> (
    None
):
    """Ignore unrelated `*Client` constructors in SDK-adjacent files."""

    semantics = build_framework_semantics(
        Path("src/aws/client.ts"),
        """\
import { S3Client } from '@aws-sdk/client-s3';

const sdkClient = new S3Client({ region: 'us-east-1' });
const apiClient = new ApiClient();
""",
        parser_language="typescript",
        imports=[
            {
                "source": "@aws-sdk/client-s3",
                "name": "S3Client",
                "alias": None,
            }
        ],
        functions=[],
        function_calls=[
            {
                "name": "S3Client",
                "full_name": "new S3Client({ region: 'us-east-1' })",
            },
            {
                "name": "ApiClient",
                "full_name": "new ApiClient()",
            },
        ],
        variables=[],
        classes=[],
        components=[],
        pack_specs=[
            {
                "framework": "aws",
                "strategy": "provider_sdk_usage",
                "compute_order": 10,
                "surface_order": 10,
                "languages": ["javascript", "typescript"],
                "config": {
                    "import_source_prefixes": ["@aws-sdk/client-"],
                    "client_name_suffixes": ["Client"],
                },
            }
        ],
    )

    assert semantics["frameworks"] == ["aws"]
    assert semantics["aws"]["services"] == ["s3"]
    assert semantics["aws"]["client_symbols"] == ["S3Client"]


def test_build_framework_semantics_ignores_non_constructor_client_helpers() -> None:
    """Do not classify helper calls ending in Client as SDK client symbols."""

    semantics = build_framework_semantics(
        Path("src/aws/client.ts"),
        """\
import { S3Client } from '@aws-sdk/client-s3';

const getS3Client = () => new S3Client({ region: 'us-east-1' });
const client = getS3Client();
""",
        parser_language="typescript",
        imports=[
            {
                "source": "@aws-sdk/client-s3",
                "name": "@aws-sdk/client-s3",
                "alias": "{ S3Client }",
            }
        ],
        functions=[],
        function_calls=[
            {
                "name": "S3Client",
                "full_name": "new S3Client({ region: 'us-east-1' })",
            },
            {
                "name": "getS3Client",
                "full_name": "getS3Client()",
            },
        ],
        variables=[],
        classes=[],
        components=[],
        pack_specs=[
            {
                "framework": "aws",
                "strategy": "provider_sdk_usage",
                "compute_order": 10,
                "surface_order": 10,
                "languages": ["javascript", "typescript"],
                "config": {
                    "import_source_prefixes": ["@aws-sdk/client-"],
                    "client_name_suffixes": ["Client"],
                },
            }
        ],
    )

    assert semantics["aws"]["client_symbols"] == ["S3Client"]
