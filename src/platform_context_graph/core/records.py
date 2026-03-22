"""Shared helpers for normalizing database record wrappers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

__all__ = ["record_to_dict"]


def record_to_dict(record: Any) -> dict[str, Any]:
    """Return a plain dictionary for Neo4j/Falkor/Kuzu record wrappers.

    Args:
        record: Database row wrapper or mapping-like object.

    Returns:
        Plain dictionary view of the record.
    """

    if record is None:
        return {}
    if isinstance(record, Mapping):
        return dict(record)

    raw_data = getattr(record, "_data", None)
    if isinstance(raw_data, Mapping):
        return dict(raw_data)

    data_method = getattr(record, "data", None)
    if callable(data_method):
        data = data_method()
        if isinstance(data, Mapping):
            return dict(data)

    keys_method = getattr(record, "keys", None)
    if callable(keys_method):
        try:
            return {key: record[key] for key in keys_method()}
        except Exception:
            pass

    items_method = getattr(record, "items", None)
    if callable(items_method):
        try:
            return dict(items_method())
        except Exception:
            pass

    return dict(record)
