#!/usr/bin/env python3
"""Enforce the repository Python source file length policy.

This script validates that handwritten Python modules under ``src/`` remain at or
below a configurable maximum line count. Generated artifacts can be exempted with
explicit paths.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_MAX_LINES = 500
DEFAULT_SCAN_ROOT = Path("src")
DEFAULT_EXEMPT_PATHS = (
    Path("src/platform_context_graph/tools/scip_pb2.py"),
    Path("src/platform_context_graph.egg-info"),
)


@dataclass(frozen=True, slots=True)
class FileLengthViolation:
    """Describe a Python file that exceeds the configured line limit.

    Attributes:
        path: Repository-relative path to the offending file.
        line_count: Number of lines in the file.
        max_lines: Maximum permitted line count.
    """

    path: Path
    line_count: int
    max_lines: int


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for the file length check.

    Args:
        argv: Optional explicit argument vector for tests.

    Returns:
        Parsed namespace for the current invocation.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Fail if handwritten Python source files under src/ exceed the "
            f"maximum line count of {DEFAULT_MAX_LINES}."
        )
    )
    parser.add_argument(
        "--root",
        default=str(DEFAULT_SCAN_ROOT),
        help="Root directory to scan for Python files.",
    )
    parser.add_argument(
        "--max-lines",
        type=int,
        default=DEFAULT_MAX_LINES,
        help="Maximum allowed line count for a handwritten Python module.",
    )
    parser.add_argument(
        "--exempt",
        action="append",
        default=[],
        help="Repository-relative path or directory to exempt. May be repeated.",
    )
    return parser.parse_args(argv)


def is_exempt(path: Path, exemptions: Iterable[Path]) -> bool:
    """Return whether a file path is covered by any exemption path.

    Args:
        path: Repository-relative file path being evaluated.
        exemptions: Relative file or directory paths that should be ignored.

    Returns:
        ``True`` when the path is explicitly exempt.
    """

    for exempt_path in exemptions:
        if path == exempt_path or exempt_path in path.parents:
            return True
    return False


def count_lines(path: Path) -> int:
    """Count lines in a UTF-8 text file.

    Args:
        path: Absolute path to the file to count.

    Returns:
        Number of newline-delimited lines in the file.
    """

    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for _ in handle)


def find_violations(
    *,
    repo_root: Path,
    scan_root: Path,
    max_lines: int,
    exemptions: Iterable[Path],
) -> list[FileLengthViolation]:
    """Collect Python modules that exceed the configured maximum line count.

    Args:
        repo_root: Absolute repository root used to derive relative file paths.
        scan_root: Absolute directory to recursively scan.
        max_lines: Maximum allowed line count.
        exemptions: Relative file or directory paths to ignore.

    Returns:
        Violations sorted by descending line count and then path.
    """

    violations: list[FileLengthViolation] = []
    for path in sorted(scan_root.rglob("*.py")):
        relative_path = path.relative_to(repo_root)
        if is_exempt(relative_path, exemptions):
            continue
        line_count = count_lines(path)
        if line_count > max_lines:
            violations.append(
                FileLengthViolation(
                    path=relative_path,
                    line_count=line_count,
                    max_lines=max_lines,
                )
            )
    violations.sort(key=lambda item: (-item.line_count, str(item.path)))
    return violations


def build_exemptions(extra_exemptions: Iterable[str]) -> tuple[Path, ...]:
    """Build the full exemption allowlist for the current invocation.

    Args:
        extra_exemptions: Additional relative exemptions provided by the caller.

    Returns:
        Tuple of repository-relative exemption paths.
    """

    configured = tuple(Path(value) for value in extra_exemptions)
    return DEFAULT_EXEMPT_PATHS + configured


def main(argv: list[str] | None = None) -> int:
    """Run the file length check and return a shell-compatible status code.

    Args:
        argv: Optional explicit argument vector for tests.

    Returns:
        ``0`` if all scanned files comply, otherwise ``1``.
    """

    args = parse_args(argv)
    repo_root = Path.cwd()
    scan_root = repo_root / args.root
    exemptions = build_exemptions(args.exempt)
    violations = find_violations(
        repo_root=repo_root,
        scan_root=scan_root,
        max_lines=args.max_lines,
        exemptions=exemptions,
    )
    if not violations:
        print(
            f"All handwritten Python files under {args.root} are <= {args.max_lines} lines."
        )
        return 0

    print(
        f"Found {len(violations)} Python file(s) over the {args.max_lines}-line limit:"
    )
    for violation in violations:
        print(f" - {violation.path}: {violation.line_count} lines")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
