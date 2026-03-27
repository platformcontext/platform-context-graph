#!/usr/bin/env python3
"""Enforce the repository Python docstring policy.

This script validates that handwritten Python modules under ``src/`` include
module, class, function, and method docstrings. Generated artifacts can be
exempted with explicit paths.
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

DEFAULT_SCAN_ROOT = Path("src")
DEFAULT_EXEMPTIONS_FILE = Path("scripts/python_docstring_exemptions.txt")
DEFAULT_EXEMPT_PATHS = (
    Path("src/platform_context_graph/tools/scip_pb2.py"),
    Path("src/platform_context_graph.egg-info"),
)


@dataclass(frozen=True, slots=True)
class DocstringViolation:
    """Describe a Python object missing a docstring.

    Attributes:
        path: Repository-relative path containing the violation.
        object_type: Object kind such as ``module``, ``class``, or ``function``.
        qualified_name: Qualified object name within the module.
        line_number: Source line number where the object is defined.
    """

    path: Path
    object_type: str
    qualified_name: str
    line_number: int


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for the docstring check."""

    parser = argparse.ArgumentParser(
        description=(
            "Fail if handwritten Python source files under src/ are missing "
            "module, class, function, or method docstrings."
        )
    )
    parser.add_argument(
        "--root",
        default=str(DEFAULT_SCAN_ROOT),
        help="Root directory to scan for Python files.",
    )
    parser.add_argument(
        "--exempt",
        action="append",
        default=[],
        help="Repository-relative path or directory to exempt. May be repeated.",
    )
    return parser.parse_args(argv)


def is_exempt(path: Path, exemptions: Iterable[Path]) -> bool:
    """Return whether a path is covered by any configured exemption."""

    for exempt_path in exemptions:
        if path == exempt_path or exempt_path in path.parents:
            return True
    return False


def build_exemptions(extra_exemptions: Iterable[str]) -> tuple[Path, ...]:
    """Build the full exemption allowlist for the current invocation."""

    configured_file_exemptions = _load_file_exemptions(DEFAULT_EXEMPTIONS_FILE)
    configured = tuple(Path(value) for value in extra_exemptions)
    return DEFAULT_EXEMPT_PATHS + configured_file_exemptions + configured


def _load_file_exemptions(path: Path) -> tuple[Path, ...]:
    """Load repository-relative exemptions from a newline-delimited file."""

    if not path.exists():
        return ()
    return tuple(
        Path(line.strip())
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )


def find_violations(
    *,
    repo_root: Path,
    scan_root: Path,
    exemptions: Iterable[Path],
) -> list[DocstringViolation]:
    """Collect handwritten Python objects missing docstrings."""

    violations: list[DocstringViolation] = []
    for path in sorted(scan_root.rglob("*.py")):
        relative_path = path.relative_to(repo_root)
        if is_exempt(relative_path, exemptions):
            continue
        violations.extend(_collect_docstring_violations(relative_path, path))
    object_order = {"module": 0, "class": 1, "function": 2}
    violations.sort(
        key=lambda item: (
            str(item.path),
            item.line_number,
            object_order.get(item.object_type, 99),
            item.qualified_name,
        )
    )
    return violations


def _collect_docstring_violations(
    relative_path: Path, absolute_path: Path
) -> list[DocstringViolation]:
    """Collect missing docstrings for one Python module."""

    source = absolute_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    violations: list[DocstringViolation] = []
    module_name = absolute_path.stem

    if not ast.get_docstring(tree):
        violations.append(
            DocstringViolation(
                path=relative_path,
                object_type="module",
                qualified_name=module_name,
                line_number=1,
            )
        )

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.stack: list[str] = []

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            """Visit a class definition and recurse into its members."""

            self._record(node, "class")
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            """Visit a function or method definition and recurse into nested defs."""

            self._record(node, "function")
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            """Visit an async function or method definition."""

            self._record(node, "function")
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def _record(
            self,
            node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef,
            object_type: str,
        ) -> None:
            """Record a violation when a node lacks a docstring."""

            if ast.get_docstring(node):
                return
            qualified_name = (
                ".".join([*self.stack, node.name]) if self.stack else node.name
            )
            violations.append(
                DocstringViolation(
                    path=relative_path,
                    object_type=object_type,
                    qualified_name=qualified_name,
                    line_number=node.lineno,
                )
            )

    Visitor().visit(tree)
    return violations


def main(argv: list[str] | None = None) -> int:
    """Run the docstring check and return a shell-compatible status code."""

    args = parse_args(argv)
    repo_root = Path.cwd()
    scan_root = repo_root / args.root
    exemptions = build_exemptions(args.exempt)
    violations = find_violations(
        repo_root=repo_root,
        scan_root=scan_root,
        exemptions=exemptions,
    )
    if not violations:
        print(f"All handwritten Python files under {args.root} have docstrings.")
        return 0

    print(f"Found {len(violations)} missing Python docstring(s):")
    for violation in violations:
        print(
            f" - {violation.path}:{violation.line_number} "
            f"{violation.object_type} {violation.qualified_name}"
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
