"""Identity helpers for repository relationship resolution."""

from __future__ import annotations

import hashlib
from pathlib import Path

__all__ = ["canonical_checkout_id"]


def canonical_checkout_id(
    *, logical_repo_id: str, checkout_path: str | Path | None
) -> str:
    """Build a stable checkout identifier for one logical repository path."""

    normalized_path = (
        str(Path(checkout_path).expanduser().resolve())
        if checkout_path is not None
        else ""
    )
    digest = hashlib.sha1(
        f"{logical_repo_id}\n{normalized_path}".encode("utf-8")
    ).hexdigest()[:12]
    return f"checkout:c_{digest}"
