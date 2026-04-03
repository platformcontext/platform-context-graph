"""Lightweight projection helpers without runtime-side import chains."""

from __future__ import annotations

import re
from typing import Any

CYPHER_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def run_write_query(tx_or_session: Any, query: str, /, **parameters: Any) -> None:
    """Execute one write query and eagerly consume the result when supported."""

    result = tx_or_session.run(query, parameters=parameters)
    consume = getattr(result, "consume", None)
    if callable(consume):
        consume()


def run_managed_write(session: Any, write_fn: Any) -> None:
    """Execute one write callback with the best supported transaction primitive."""

    execute_write = getattr(session, "execute_write", None)
    if callable(execute_write):
        execute_write(write_fn)
        return

    write_transaction = getattr(session, "write_transaction", None)
    if callable(write_transaction):
        write_transaction(write_fn)
        return

    begin = getattr(session, "begin_transaction", None)
    if begin is None:
        write_fn(session)
        return

    try:
        tx = begin()
    except (AttributeError, NotImplementedError, RuntimeError, TypeError):
        write_fn(session)
        return

    try:
        write_fn(tx)
        tx.commit()
    except Exception:
        tx.rollback()
        raise


def validate_cypher_identifier(identifier: str) -> str:
    """Return a Cypher identifier only when it is safe to interpolate."""

    if CYPHER_IDENTIFIER_PATTERN.fullmatch(identifier) is None:
        raise ValueError(f"Invalid Cypher identifier: {identifier}")
    return identifier


__all__ = [
    "run_managed_write",
    "run_write_query",
    "validate_cypher_identifier",
]
