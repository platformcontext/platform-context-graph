"""Compatibility facade for canonical `CodeFinder` search helpers."""

from __future__ import annotations

import logging

from ..query import code_finder_search as _canonical_search
from ..query.code_finder_search import CodeFinderSearchMixin
from ..query.code_finder_search import _annotate_search_results
from ..query.code_finder_search import _build_exact_name_query
from ..query.code_finder_search import _escape_lucene_term

logger = logging.getLogger(__name__)
_canonical_search.logger = logger

__all__ = [
    "CodeFinderSearchMixin",
    "_annotate_search_results",
    "_build_exact_name_query",
    "_escape_lucene_term",
    "logger",
]
