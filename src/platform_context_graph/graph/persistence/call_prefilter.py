"""Pre-filter and adaptive guardrail helpers for CALLS resolution."""

from __future__ import annotations

import os
import time
from typing import Any
from typing import Iterable

from ...observability import get_observability

_LANGUAGE_FAMILIES: dict[str, str] = {
    "javascript": "js_family",
    "typescript": "js_family",
}

_MAX_CALLS_PER_FILE = int(os.environ.get("PCG_MAX_CALLS_PER_FILE", "50"))


def compatible_languages(lang: str | None) -> list[str]:
    """Return the list of languages compatible with *lang* for call resolution.

    Languages within the same family (e.g. JS/TS) are cross-compatible.
    All other languages resolve only against themselves.

    Args:
        lang: The source language identifier, or ``None``.

    Returns:
        A list of compatible language identifiers.  Empty when *lang*
        is ``None``.
    """
    if not lang:
        return []
    family = _LANGUAGE_FAMILIES.get(lang)
    if family:
        return [k for k, v in _LANGUAGE_FAMILIES.items() if v == family]
    return [lang]


_REPO_CLASS_CAPS: dict[str, int] = {
    "small": 100,
    "medium": 50,
    "large": 25,
    "xlarge": 15,
    "dangerous": 5,
}


def max_calls_for_repo_class(repo_class: str | None) -> int:
    """Return the max-calls-per-file cap for a repository size class.

    Args:
        repo_class: One of ``small``, ``medium``, ``large``, ``xlarge``,
            ``dangerous``, or ``None`` for the environment default.

    Returns:
        The integer cap to apply per file during CALLS resolution.
    """
    if repo_class and repo_class in _REPO_CLASS_CAPS:
        return _REPO_CLASS_CAPS[repo_class]
    return _MAX_CALLS_PER_FILE


def build_known_callable_names(session: Any) -> frozenset[str]:
    """Query Neo4j for all distinct Function and Class names.

    Args:
        session: An active Neo4j session.

    Returns:
        A frozenset of all callable names in the graph.
    """
    observability = get_observability()
    started = time.perf_counter()
    names: set[str] = set()
    with observability.start_span(
        "pcg.calls.known_name_scan",
        attributes={"pcg.variant": "flat"},
    ):
        for label in ("Function", "Class"):
            rows = _iter_query_rows(
                session.run(
                    f"MATCH (n:{label}) RETURN DISTINCT n.name AS name",
                )
            )
            for row in rows:
                name = row.get("name")
                if name:
                    names.add(name)
    observability.record_call_prefilter_known_name_scan(
        component=observability.component,
        variant="flat",
        duration_seconds=time.perf_counter() - started,
    )
    return frozenset(names)


def build_known_callable_names_by_family(
    session: Any,
) -> dict[str, frozenset[str]]:
    """Query Neo4j for Function/Class names grouped by language family.

    Languages within the same family (e.g. JS/TS) share their callable
    name sets, preventing cross-family false positives during the
    prefilter stage.

    Args:
        session: An active Neo4j session.

    Returns:
        A mapping of language name to the frozenset of callable names
        visible to that language's family.
    """
    observability = get_observability()
    started = time.perf_counter()
    by_lang: dict[str, set[str]] = {}
    with observability.start_span(
        "pcg.calls.known_name_scan",
        attributes={"pcg.variant": "family"},
    ):
        for label in ("Function", "Class"):
            rows = _iter_query_rows(
                session.run(
                    f"MATCH (n:{label}) RETURN DISTINCT n.name AS name, n.lang AS lang",
                )
            )
            for row in rows:
                name = row.get("name")
                lang = row.get("lang")
                if not name or not lang:
                    continue
                by_lang.setdefault(lang, set()).add(name)

    # Merge names within the same family.
    result: dict[str, frozenset[str]] = {}
    seen_families: dict[str, frozenset[str]] = {}
    for lang, names in by_lang.items():
        family = _LANGUAGE_FAMILIES.get(lang, lang)
        if family not in seen_families:
            merged: set[str] = set()
            for other_lang, other_names in by_lang.items():
                if _LANGUAGE_FAMILIES.get(other_lang, other_lang) == family:
                    merged.update(other_names)
            seen_families[family] = frozenset(merged)
        result[lang] = seen_families[family]
    observability.record_call_prefilter_known_name_scan(
        component=observability.component,
        variant="family",
        duration_seconds=time.perf_counter() - started,
    )
    return result


def _iter_query_rows(result: Any) -> Iterable[dict[str, Any]]:
    """Yield Neo4j rows without forcing eager materialization."""

    try:
        return iter(result)
    except TypeError:
        data_fn = getattr(result, "data", None)
        if callable(data_fn):
            return data_fn()
        raise
