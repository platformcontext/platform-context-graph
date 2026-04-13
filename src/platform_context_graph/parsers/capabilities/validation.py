"""Validation helpers for parser capability contracts."""

from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path
import re

from .models import CapabilitySpec, LanguageCapabilitySpec, SUPPORTED_STATUSES

NamedTestNode = ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
GO_TEST_FUNC_RE = re.compile(r"(?m)^func\s+(Test[0-9A-Za-z_]+)\s*\(")


def validate_spec(root: Path, spec: LanguageCapabilitySpec) -> list[str]:
    """Validate one parser capability spec payload."""

    errors: list[str] = []
    required_keys = {
        "language",
        "title",
        "family",
        "parser",
        "parser_entrypoint",
        "doc_path",
        "fixture_repo",
        "unit_test_file",
        "integration_test_suite",
        "capabilities",
        "known_limitations",
        "spec_path",
    }
    missing = sorted(required_keys - spec.keys())
    if missing:
        return [f"{spec.get('spec_path', '<unknown>')}: missing keys {missing}"]

    for key in ("fixture_repo", "unit_test_file"):
        if not (root / spec[key]).exists():
            errors.append(f"{spec['spec_path']}: missing path {spec[key]}")

    doc_path = root / spec["doc_path"]
    if doc_path.suffix != ".md":
        errors.append(f"{spec['spec_path']}: doc_path must point to a Markdown file")
    if not doc_path.parent.exists():
        errors.append(
            f"{spec['spec_path']}: doc_path parent does not exist {doc_path.parent.relative_to(root)}"
        )

    if spec["family"] not in {"language", "iac"}:
        errors.append(
            f"{spec['spec_path']}: family must be 'language' or 'iac', got {spec['family']}"
        )

    seen_ids: set[str] = set()
    for capability in spec["capabilities"]:
        errors.extend(validate_capability(root, spec["spec_path"], capability))
        capability_id = capability.get("id")
        if capability_id in seen_ids:
            errors.append(
                f"{spec['spec_path']}: duplicate capability id {capability_id}"
            )
        if capability_id is not None:
            seen_ids.add(capability_id)

    return errors


def validate_capability(
    root: Path, spec_path: str, capability: CapabilitySpec
) -> list[str]:
    """Validate one capability entry."""

    errors: list[str] = []
    required_keys = {
        "id",
        "name",
        "status",
        "extracted_bucket",
        "required_fields",
        "graph_surface",
        "unit_test",
        "integration_test",
    }
    missing = sorted(required_keys - capability.keys())
    if missing:
        return [f"{spec_path}: capability missing keys {missing}"]

    if capability["status"] not in SUPPORTED_STATUSES:
        errors.append(
            f"{spec_path}:{capability['id']}: invalid status {capability['status']}"
        )
    if (
        not isinstance(capability["required_fields"], list)
        or not capability["required_fields"]
    ):
        errors.append(
            f"{spec_path}:{capability['id']}: required_fields must be a non-empty list"
        )
    if not isinstance(capability["graph_surface"], dict):
        errors.append(
            f"{spec_path}:{capability['id']}: graph_surface must be a mapping"
        )
        return errors
    if capability["status"] == "supported":
        graph_surface = capability["graph_surface"]
        if graph_surface.get("kind") in (None, "", "none") or not graph_surface.get(
            "target"
        ):
            errors.append(
                f"{spec_path}:{capability['id']}: supported capability must declare graph surface"
            )
    if capability["status"] in {"partial", "unsupported"}:
        rationale = capability.get("rationale", "").strip()
        if not rationale:
            errors.append(
                f"{spec_path}:{capability['id']}: partial/unsupported capability requires rationale"
            )
    for ref_key in ("unit_test", "integration_test"):
        ref = capability[ref_key]
        if not test_ref_exists(root, ref):
            errors.append(
                f"{spec_path}:{capability['id']}: {ref_key} must reference a concrete test function {ref}"
            )
    return errors


@lru_cache(maxsize=None)
def _parsed_test_file(path: str) -> ast.Module:
    """Return the parsed AST for a test file path."""

    return ast.parse(Path(path).read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def _go_test_names(path: str) -> frozenset[str]:
    """Return top-level Go `Test*` function names defined in one file."""

    content = Path(path).read_text(encoding="utf-8")
    return frozenset(GO_TEST_FUNC_RE.findall(content))


def test_ref_exists(root: Path, ref: str) -> bool:
    """Return whether a Python or Go test ref resolves to a concrete test."""

    parts = ref.split("::")
    if not parts:
        return False
    path = root / parts[0]
    if not path.exists():
        return False
    if len(parts) == 1:
        return False
    if path.suffix == ".go":
        return _go_test_ref_exists(path, parts[1:])
    if path.suffix != ".py":
        return False

    try:
        current_nodes: list[ast.stmt] = list(_parsed_test_file(str(path)).body)
    except SyntaxError:
        return False
    for index, name in enumerate(parts[1:], start=1):
        match = _find_named_node(current_nodes, name)
        if match is None:
            return False
        if index == len(parts) - 1:
            return isinstance(
                match, (ast.FunctionDef, ast.AsyncFunctionDef)
            ) and match.name.startswith("test_")
        if not isinstance(match, ast.ClassDef):
            return False
        current_nodes = list(match.body)
    return True


def _go_test_ref_exists(path: Path, parts: list[str]) -> bool:
    """Return whether a Go test ref resolves to a concrete `Test*` function."""

    if len(parts) != 1:
        return False
    test_name = parts[0]
    if not test_name.startswith("Test"):
        return False
    return test_name in _go_test_names(str(path))


def _find_named_node(nodes: list[ast.stmt], name: str) -> NamedTestNode | None:
    """Return the class or function node matching ``name``."""

    for node in nodes:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == name:
                return node
    return None
