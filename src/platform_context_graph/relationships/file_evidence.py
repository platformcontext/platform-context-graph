"""Raw file-based repository dependency evidence extraction."""

from __future__ import annotations

from typing import Sequence

from ..observability import get_observability
from ..utils.debug_log import emit_log_call, info_logger
from .evidence_gitops import discover_gitops_evidence
from .evidence_terraform import discover_terraform_evidence
from .file_evidence_support import build_catalog
from .models import RelationshipEvidenceFact, RepositoryCheckout


def discover_checkout_file_evidence(
    checkouts: Sequence[RepositoryCheckout],
) -> list[RelationshipEvidenceFact]:
    """Extract repo dependency evidence directly from portable file semantics."""

    catalog = build_catalog(checkouts)
    if not catalog:
        return []

    observability = get_observability()
    with observability.start_span(
        "pcg.relationships.discover_evidence.file",
        component=observability.component,
        attributes={"pcg.relationships.checkout_count": len(checkouts)},
    ) as root_span:
        terraform = discover_terraform_evidence(checkouts, catalog)
        gitops = discover_gitops_evidence(checkouts, catalog)
        evidence = terraform + gitops
        if root_span is not None:
            root_span.set_attribute(
                "pcg.relationships.terraform_evidence_count", len(terraform)
            )
            root_span.set_attribute(
                "pcg.relationships.gitops_evidence_count", len(gitops)
            )
            root_span.set_attribute(
                "pcg.relationships.file_evidence_count", len(evidence)
            )
        emit_log_call(
            info_logger,
            "Discovered raw file-based repository dependency evidence",
            event_name="relationships.discover_file_evidence.completed",
            extra_keys={
                "terraform_evidence_count": len(terraform),
                "gitops_evidence_count": len(gitops),
                "evidence_count": len(evidence),
            },
        )
        return evidence


__all__ = ["discover_checkout_file_evidence"]
