"""Generate sanitized templated IaC fixture repos from local real sources."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.generate_templated_iac_fixtures_support import generate_fixture_corpus


def build_parser() -> argparse.ArgumentParser:
    """Return the CLI parser for fixture generation."""

    parser = argparse.ArgumentParser(
        description=(
            "Generate sanitized templated IaC fixtures from local repos under ~/repos."
        )
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "tests/fixtures/templated_iac_corpus",
        help="Directory where sanitized fixture repos will be written.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Generate the fixture corpus and print a short summary."""

    args = build_parser().parse_args(argv)
    records = generate_fixture_corpus(args.output)
    print(f"Generated {len(records)} sanitized fixture files in {args.output}")
    for record in records:
        print(f"- {record.target} <- {record.source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
