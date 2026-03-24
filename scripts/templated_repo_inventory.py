#!/usr/bin/env python3
"""Inventory templated files across real repo families without rendering them."""

import argparse
from pathlib import Path
import sys
from typing import TextIO

if __package__ in {None, ""}:
    REPO_ROOT = Path(__file__).resolve().parents[1]
    SRC_ROOT = REPO_ROOT / "src"
    for candidate in (str(REPO_ROOT), str(SRC_ROOT)):
        if candidate not in sys.path:
            sys.path.insert(0, candidate)

from platform_context_graph.tools.languages.templated_detection import exclusion_reason
from scripts.templated_repo_inventory_support import (
    build_scan_roots,
    classify_file,
    emit_console_report,
    scan_root,
    ScanRoot,
    write_json_report,
)

__all__ = [
    "ScanRoot",
    "classify_file",
    "exclusion_reason",
    "main",
    "parse_args",
    "scan_root",
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Inventory authored templated files across repo families without "
            "rendering them."
        )
    )
    parser.add_argument(
        "--root",
        action="append",
        default=[],
        help="Repo root to scan. May be repeated. Defaults to the built-in repo families.",
    )
    parser.add_argument(
        "--family",
        default=None,
        help="Override family for custom --root values.",
    )
    parser.add_argument(
        "--json-out",
        default=None,
        help="Optional path to write a compact JSON report.",
    )
    parser.add_argument(
        "--max-examples",
        type=int,
        default=10,
        help="Maximum representative examples to keep per root.",
    )
    parser.add_argument(
        "--include-generated",
        action="store_true",
        help="Include generated and vendored directories normally excluded from the scan.",
    )
    return parser.parse_args(argv)


def main(
    argv: list[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Run the templated repo inventory spike."""

    args = parse_args(argv)
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    scan_roots = build_scan_roots(args.root, family_override=args.family)
    missing_roots = [root for root in scan_roots if not root.path.is_dir()]
    if missing_roots:
        for root in missing_roots:
            stderr.write(f"Missing root: {root.path}\n")
        return 1

    inventories = [
        scan_root(
            root,
            max_examples=args.max_examples,
            include_generated=args.include_generated,
        )
        for root in scan_roots
    ]
    emit_console_report(inventories, stdout=stdout)

    if args.json_out:
        write_json_report(inventories, output_path=Path(args.json_out))

    return 1 if any(root.ambiguous_files for root in inventories) else 0


if __name__ == "__main__":
    raise SystemExit(main())
