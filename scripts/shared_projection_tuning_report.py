"""Print a deterministic local tuning report for shared-write settings."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence
from typing import TextIO

from scripts.shared_projection_tuning_report_support import build_tuning_report
from scripts.shared_projection_tuning_report_support import format_tuning_report_table


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the local tuning report script."""

    parser = argparse.ArgumentParser(
        prog="shared_projection_tuning_report",
        description="Report deterministic shared-write tuning recommendations.",
    )
    parser.add_argument(
        "--format",
        choices=("json", "table"),
        default="table",
        help="Output format for the generated report.",
    )
    parser.add_argument(
        "--include-platform",
        action="store_true",
        help="Include platform shared-followup work in the seeded scenario.",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    """Run the local shared-write tuning report CLI."""

    del stderr
    args = parse_args(argv)
    report = build_tuning_report(include_platform=bool(args.include_platform))
    if args.format == "json":
        stdout.write(json.dumps(report, sort_keys=True, indent=2))
        stdout.write("\n")
        return 0
    stdout.write(format_tuning_report_table(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
