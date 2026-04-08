"""Tests for declarative framework semantic pack loading and execution."""

from __future__ import annotations

from pathlib import Path

import yaml

from platform_context_graph.parsers.framework_packs import load_framework_pack_specs
from platform_context_graph.parsers.framework_semantics import (
    build_framework_semantics,
)


def test_load_framework_pack_specs_exposes_react_and_nextjs() -> None:
    """Load the canonical declarative framework packs from disk."""

    specs = load_framework_pack_specs()

    names = {spec["framework"] for spec in specs}

    assert "react" in names
    assert "nextjs" in names


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
