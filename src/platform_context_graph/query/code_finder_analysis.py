"""Canonical analysis mixins for `CodeFinder` query helpers."""

from __future__ import annotations

from .code_finder_analysis_catalog import CodeFinderCatalogAnalysisMixin
from .code_finder_analysis_graph import CodeFinderGraphAnalysisMixin


class CodeFinderAnalysisMixin(
    CodeFinderGraphAnalysisMixin,
    CodeFinderCatalogAnalysisMixin,
):
    """Combine canonical analysis helpers for `CodeFinder`."""


__all__ = ["CodeFinderAnalysisMixin"]
