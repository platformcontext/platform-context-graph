"""Print a deterministic local tuning report for shared-write settings."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence
from typing import TextIO

from scripts.shared_projection_tuning_report_support import build_tuning_report


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


def _format_table(report: dict[str, object]) -> str:
    """Render one readable table-oriented report payload."""

    scenarios = list(report.get("scenarios") or [])
    lines = [
        "Shared Projection Tuning Report",
        f"Projection domains: {', '.join(report.get('projection_domains') or [])}",
        "",
        f"{'Setting':<10} {'Rounds':<8} {'Mean/round':<12} {'Peak backlog':<13}",
        f"{'-' * 10} {'-' * 8} {'-' * 12} {'-' * 13}",
    ]
    for scenario in scenarios:
        lines.append(
            f"{scenario['setting']:<10} {scenario['round_count']:<8} "
            f"{scenario['mean_processed_per_round']:<12} "
            f"{scenario.get('peak_pending_total', ''):<13}"
        )
    recommended = dict(report.get("recommended") or {})
    lines.extend(
        [
            "",
            "Recommended setting: "
            f"{recommended.get('setting', 'n/a')} "
            f"(rounds={recommended.get('round_count', 'n/a')}, "
            f"mean_per_round={recommended.get('mean_processed_per_round', 'n/a')})",
        ]
    )
    return "\n".join(lines) + "\n"


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
    stdout.write(_format_table(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
