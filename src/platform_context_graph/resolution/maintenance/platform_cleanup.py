"""Global platform cleanup helpers kept out of per-repo projection paths."""

from __future__ import annotations

from typing import Any

from platform_context_graph.resolution.workloads.batches import (
    delete_orphan_platform_rows,
)


def cleanup_orphan_platform_state(
    session: Any,
    *,
    evidence_source: str,
) -> dict[str, int]:
    """Delete orphaned platform nodes for one evidence source.

    This helper is intentionally scoped as global maintenance work rather than
    a per-repository projection step so repo-local projection can stay
    parallel without contending on shared ``Platform`` nodes.
    """

    return delete_orphan_platform_rows(
        session,
        evidence_source=evidence_source,
    )


__all__ = ["cleanup_orphan_platform_state"]
