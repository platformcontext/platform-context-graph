"""Compatibility exports for fact provenance helpers."""

from .models.base import FactProvenance
from .models.base import utc_now

__all__ = [
    "FactProvenance",
    "utc_now",
]
