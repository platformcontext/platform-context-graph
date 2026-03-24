#!/usr/bin/env python3
"""Populate content metadata columns for existing content-store rows."""

from __future__ import annotations

import argparse

from platform_context_graph.content.state import get_postgres_content_provider

from scripts.backfill_content_metadata_support import (
    BackfillResult,
    PostgresBackfillStore,
    run_backfill,
)

__all__ = [
    "BackfillResult",
    "PostgresBackfillStore",
    "main",
    "run_backfill",
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the metadata backfill command."""

    parser = argparse.ArgumentParser(
        description="Backfill artifact metadata on indexed content rows.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan and classify rows without writing updates.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=250,
        help="Maximum number of files to classify per batch.",
    )
    parser.add_argument(
        "--repo-id",
        action="append",
        default=None,
        dest="repo_ids",
        help="Optional repository id filter. Repeat to scope to multiple repos.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional maximum number of files to scan.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the content metadata backfill CLI."""

    args = parse_args(argv)
    provider = get_postgres_content_provider()
    if provider is None or not provider.enabled:
        print("error: PostgreSQL content store is not configured or unavailable.")
        return 1

    result = run_backfill(
        store=PostgresBackfillStore(provider),
        batch_size=args.batch_size,
        repo_ids=args.repo_ids,
        limit=args.limit,
        dry_run=args.dry_run,
    )
    print(
        "content metadata backfill "
        f"scanned_files={result.scanned_files} "
        f"updated_files={result.updated_files} "
        f"updated_entities={result.updated_entities}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
