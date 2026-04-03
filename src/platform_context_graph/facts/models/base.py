"""Shared base types and id helpers for facts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> datetime:
    """Return the current UTC timestamp."""

    return datetime.now(tz=timezone.utc)


def _normalize_json_value(value: Any) -> Any:
    """Return a JSON-stable representation for deterministic fact ids."""

    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, dict):
        return {
            str(key): _normalize_json_value(nested_value)
            for key, nested_value in sorted(
                value.items(), key=lambda item: str(item[0])
            )
        }
    if isinstance(value, (list, tuple)):
        return [_normalize_json_value(item) for item in value]
    return value


def stable_fact_id(*, fact_type: str, identity: dict[str, Any]) -> str:
    """Return a deterministic identifier for one fact observation."""

    payload = json.dumps(
        {
            "fact_type": fact_type,
            "identity": _normalize_json_value(identity),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class FactProvenance:
    """Source provenance for one observed fact."""

    source_system: str
    source_run_id: str
    source_snapshot_id: str
    observed_at: datetime
    ingested_at: datetime = field(default_factory=utc_now)
    details: dict[str, Any] = field(default_factory=dict)
