#!/usr/bin/env python3
"""Populate durable repository coverage rows for a checkpointed run."""

from __future__ import annotations

import argparse
from pathlib import Path

from platform_context_graph.content.state import get_postgres_content_provider
from platform_context_graph.core.database import DatabaseManager
from platform_context_graph.indexing.coordinator_storage import (
    _load_run_state_by_id,
    _matching_run_states,
)
from platform_context_graph.runtime.status_store import get_runtime_status_store

from scripts.backfill_repository_coverage_support import (
    CoverageBackfillResult,
    RuntimeCoverageBackfillStore,
    load_target_run_state,
    run_backfill,
)

__all__ = [
    "CoverageBackfillResult",
    "RuntimeCoverageBackfillStore",
    "load_target_run_state",
    "main",
    "run_backfill",
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the repository coverage backfill command."""

    parser = argparse.ArgumentParser(
        description="Backfill durable repository coverage rows from checkpoint state.",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Optional explicit run identifier. Defaults to the latest run for the configured root.",
    )
    parser.add_argument(
        "--root-path",
        default=None,
        help="Optional checkpoint root path used when selecting the latest run.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan and compute coverage without writing updates.",
    )
    parser.add_argument(
        "--repo-id",
        action="append",
        default=None,
        dest="repo_ids",
        help="Optional canonical repository id filter. Repeat to scope to multiple repos.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional maximum number of repositories to scan.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the repository coverage backfill CLI."""

    args = parse_args(argv)
    runtime_store = get_runtime_status_store()
    if runtime_store is None or not runtime_store.enabled:
        print("error: runtime status store is not configured or unavailable.")
        return 1

    run_state = load_target_run_state(
        run_id=args.run_id,
        root_path=Path(args.root_path).resolve() if args.root_path else None,
        load_run_state_by_id_fn=_load_run_state_by_id,
        matching_run_states_fn=_matching_run_states,
    )
    if run_state is None:
        print("error: checkpointed run state not found.")
        return 1

    result = run_backfill(
        store=RuntimeCoverageBackfillStore(
            db_manager=DatabaseManager(),
            content_provider=get_postgres_content_provider(),
        ),
        run_state=run_state,
        repo_ids=args.repo_ids,
        limit=args.limit,
        dry_run=args.dry_run,
    )
    print(
        "repository coverage backfill "
        f"run_id={result.run_id} "
        f"scanned_repositories={result.scanned_repositories} "
        f"updated_repositories={result.updated_repositories}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
