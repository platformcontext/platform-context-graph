"""Generate or check parser capability docs from canonical YAML specs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from platform_context_graph.tools.parser_capabilities import (  # noqa: E402
    validate_language_capability_specs,
    write_generated_language_docs,
)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for doc generation."""

    parser = argparse.ArgumentParser(
        description="Generate parser capability docs from canonical YAML specs."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if specs are invalid or generated docs are out of sync.",
    )
    return parser.parse_args()


def main() -> int:
    """Generate docs or check for drift."""

    args = parse_args()
    errors = validate_language_capability_specs(REPO_ROOT)
    if errors:
        print("Parser capability spec validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    changed = write_generated_language_docs(REPO_ROOT, check=args.check)
    if args.check and changed:
        print(
            "Generated language docs are out of sync with the YAML specs:",
            file=sys.stderr,
        )
        for relative_path in changed:
            print(f"- {relative_path}", file=sys.stderr)
        return 1

    if args.check:
        print("Parser capability specs and generated docs are in sync.")
        return 0

    if changed:
        print("Updated generated language docs:")
        for relative_path in changed:
            print(f"- {relative_path}")
        return 0

    print("Generated language docs already match the YAML specs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
