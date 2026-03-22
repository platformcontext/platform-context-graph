"""CLI for validating and generating parser capability documentation."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

REPO_ROOT = Path(__file__).resolve().parents[1]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for doc generation.

    Args:
        argv: Optional argument vector to parse instead of ``sys.argv``.

    Returns:
        Parsed command-line arguments.
    """

    parser = argparse.ArgumentParser(
        description="Generate parser capability docs from canonical YAML specs."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if specs are invalid or generated docs are out of sync.",
    )
    return parser.parse_args(argv)


def _ensure_repo_src_on_path() -> None:
    """Add the repository's ``src`` directory to ``sys.path`` when needed."""

    src_path = str(REPO_ROOT / "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)


def _validate_language_capability_specs(root: Path) -> list[str]:
    """Return parser capability validation errors for one repository root.

    Args:
        root: Repository root containing the parser capability specs.

    Returns:
        Validation errors emitted by the in-repo parser capability validator.
    """

    _ensure_repo_src_on_path()
    from platform_context_graph.tools.parser_capabilities import (
        validate_language_capability_specs,
    )

    return validate_language_capability_specs(root)


def _write_generated_language_docs(root: Path, *, check: bool) -> list[str]:
    """Write generated parser capability docs for one repository root.

    Args:
        root: Repository root containing the parser capability specs.
        check: Whether to report drift without writing files.

    Returns:
        Repo-relative doc paths whose content differs from the generated output.
    """

    _ensure_repo_src_on_path()
    from platform_context_graph.tools.parser_capabilities import (
        write_generated_language_docs,
    )

    return write_generated_language_docs(root, check=check)


def _write_lines(stream: TextIO, header: str, lines: Sequence[str]) -> None:
    """Write a header and bullet list to one text stream.

    Args:
        stream: Output stream to write.
        header: Leading line printed before the bullet list.
        lines: Bullet values to render.
    """

    print(header, file=stream)
    for line in lines:
        print(f"- {line}", file=stream)


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Generate docs or check whether generated files drifted.

    Args:
        argv: Optional argument vector to parse instead of ``sys.argv``.
        stdout: Optional stream for success output.
        stderr: Optional stream for validation and drift failures.

    Returns:
        Process exit code compatible with ``SystemExit``.
    """

    args = parse_args(argv)
    success_stream = stdout or sys.stdout
    error_stream = stderr or sys.stderr

    errors = _validate_language_capability_specs(REPO_ROOT)
    if errors:
        _write_lines(
            error_stream,
            "Parser capability spec validation failed:",
            errors,
        )
        return 1

    changed = _write_generated_language_docs(REPO_ROOT, check=args.check)
    if args.check and changed:
        _write_lines(
            error_stream,
            "Generated language docs are out of sync with the YAML specs:",
            changed,
        )
        return 1

    if args.check:
        print(
            "Parser capability specs and generated docs are in sync.",
            file=success_stream,
        )
        return 0

    if changed:
        _write_lines(success_stream, "Updated generated language docs:", changed)
        return 0

    print(
        "Generated language docs already match the YAML specs.",
        file=success_stream,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
