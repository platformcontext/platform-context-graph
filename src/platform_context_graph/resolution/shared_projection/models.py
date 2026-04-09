"""Typed models for durable shared projection intents."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True, slots=True)
class SharedProjectionIntentRow:
    """One durable shared-domain projection intent emitted in shadow mode."""

    intent_id: str
    projection_domain: str
    partition_key: str
    repository_id: str
    source_run_id: str
    generation_id: str
    payload: dict[str, Any]
    created_at: datetime


def _normalize_json_value(value: Any) -> Any:
    """Return a JSON-stable representation for deterministic intent ids."""

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


def _stable_intent_id(*, identity: dict[str, Any]) -> str:
    """Return a deterministic identifier for one shared projection intent."""

    payload = json.dumps(
        {"identity": _normalize_json_value(identity)},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_shared_projection_intent(
    *,
    projection_domain: str,
    partition_key: str,
    repository_id: str,
    source_run_id: str,
    generation_id: str,
    payload: dict[str, Any],
    created_at: datetime,
) -> SharedProjectionIntentRow:
    """Build one deterministic shared projection intent row."""

    return SharedProjectionIntentRow(
        intent_id=_stable_intent_id(
            identity={
                "generation_id": generation_id,
                "partition_key": partition_key,
                "projection_domain": projection_domain,
                "repository_id": repository_id,
                "source_run_id": source_run_id,
            },
        ),
        projection_domain=projection_domain,
        partition_key=partition_key,
        repository_id=repository_id,
        source_run_id=source_run_id,
        generation_id=generation_id,
        payload=payload,
        created_at=created_at,
    )


__all__ = ["SharedProjectionIntentRow", "build_shared_projection_intent"]
