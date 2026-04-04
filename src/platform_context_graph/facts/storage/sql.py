"""SQL statements and parameter builders for the PostgreSQL fact store.

Centralizes all raw SQL used by :class:`PostgresFactStore` so that the
store class itself focuses on connection management, observability, and
public API surface.
"""

from __future__ import annotations

from typing import Any

from .models import FactRecordRow
from .models import FactRunRow

try:
    from psycopg.types.json import Jsonb
except ImportError:  # pragma: no cover
    Jsonb = None  # type: ignore[assignment,misc]

# ---------------------------------------------------------------------------
# Upsert statements
# ---------------------------------------------------------------------------

FACT_RUN_UPSERT_SQL = """
INSERT INTO fact_runs (
    source_run_id,
    source_system,
    source_snapshot_id,
    repository_id,
    status,
    started_at,
    completed_at
) VALUES (
    %(source_run_id)s,
    %(source_system)s,
    %(source_snapshot_id)s,
    %(repository_id)s,
    %(status)s,
    %(started_at)s,
    %(completed_at)s
)
ON CONFLICT (source_run_id) DO UPDATE
SET source_system = EXCLUDED.source_system,
    source_snapshot_id = EXCLUDED.source_snapshot_id,
    repository_id = EXCLUDED.repository_id,
    status = EXCLUDED.status,
    started_at = EXCLUDED.started_at,
    completed_at = EXCLUDED.completed_at
"""

FACT_RECORD_UPSERT_SQL = """
INSERT INTO fact_records (
    fact_id,
    fact_type,
    repository_id,
    checkout_path,
    relative_path,
    source_system,
    source_run_id,
    source_snapshot_id,
    payload,
    observed_at,
    ingested_at,
    provenance
) VALUES (
    %(fact_id)s,
    %(fact_type)s,
    %(repository_id)s,
    %(checkout_path)s,
    %(relative_path)s,
    %(source_system)s,
    %(source_run_id)s,
    %(source_snapshot_id)s,
    %(payload)s,
    %(observed_at)s,
    %(ingested_at)s,
    %(provenance)s
)
ON CONFLICT (fact_id) DO UPDATE
SET fact_type = EXCLUDED.fact_type,
    repository_id = EXCLUDED.repository_id,
    checkout_path = EXCLUDED.checkout_path,
    relative_path = EXCLUDED.relative_path,
    source_system = EXCLUDED.source_system,
    source_run_id = EXCLUDED.source_run_id,
    source_snapshot_id = EXCLUDED.source_snapshot_id,
    payload = EXCLUDED.payload,
    observed_at = EXCLUDED.observed_at,
    ingested_at = EXCLUDED.ingested_at,
    provenance = EXCLUDED.provenance
"""


# ---------------------------------------------------------------------------
# Parameter builders
# ---------------------------------------------------------------------------


def fact_run_params(entry: FactRunRow) -> dict[str, Any]:
    """Build SQL parameters for one fact run row.

    Args:
        entry: The fact run row to parameterise.

    Returns:
        Dict suitable for passing to ``cursor.execute()`` with
        ``FACT_RUN_UPSERT_SQL``.
    """
    return {
        "source_run_id": entry.source_run_id,
        "source_system": entry.source_system,
        "source_snapshot_id": entry.source_snapshot_id,
        "repository_id": entry.repository_id,
        "status": entry.status,
        "started_at": entry.started_at,
        "completed_at": entry.completed_at,
    }


def fact_record_params(entry: FactRecordRow) -> dict[str, Any]:
    """Build SQL parameters for one fact record row.

    Wraps ``payload`` and ``provenance`` in ``psycopg.types.json.Jsonb``
    so Postgres receives native JSONB values rather than text.

    Args:
        entry: The fact record row to parameterise.

    Returns:
        Dict suitable for passing to ``cursor.execute()`` with
        ``FACT_RECORD_UPSERT_SQL``.
    """
    return {
        "fact_id": entry.fact_id,
        "fact_type": entry.fact_type,
        "repository_id": entry.repository_id,
        "checkout_path": entry.checkout_path,
        "relative_path": entry.relative_path,
        "source_system": entry.source_system,
        "source_run_id": entry.source_run_id,
        "source_snapshot_id": entry.source_snapshot_id,
        "payload": Jsonb(entry.payload),
        "observed_at": entry.observed_at,
        "ingested_at": entry.ingested_at,
        "provenance": Jsonb(entry.provenance),
    }
