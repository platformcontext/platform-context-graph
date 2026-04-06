from __future__ import annotations

from platform_context_graph.query.repositories.content_enrichment_local_delivery import (
    _split_image_reference,
)


def test_split_image_reference_preserves_digest_suffix() -> None:
    """Digest image references should not be misparsed as tag-only images."""

    repository, tag = _split_image_reference(
        "ghcr.io/example/service-edge-api:modern@sha256:abc123"
    )

    assert repository == "ghcr.io/example/service-edge-api@sha256:abc123"
    assert tag == "modern"
