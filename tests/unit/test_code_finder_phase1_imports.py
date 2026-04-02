"""Phase 1 import checks for canonical CodeFinder query modules."""

from __future__ import annotations

from platform_context_graph.query.code_finder import CodeFinder as canonical_code_finder
from platform_context_graph.query.code_finder_analysis import (
    CodeFinderAnalysisMixin as canonical_analysis_mixin,
)
from platform_context_graph.query.code_finder_dispatch import (
    CodeFinderDispatchMixin as canonical_dispatch_mixin,
)
from platform_context_graph.query.code_finder_relationships import (
    CodeFinderRelationshipsMixin as canonical_relationships_mixin,
)
from platform_context_graph.query.code_finder_search import (
    CodeFinderSearchMixin as canonical_search_mixin,
)
from platform_context_graph.query import code_support
from platform_context_graph.tools.code_finder import CodeFinder as legacy_code_finder
from platform_context_graph.tools.code_finder_analysis import (
    CodeFinderAnalysisMixin as legacy_analysis_mixin,
)
from platform_context_graph.tools.code_finder_dispatch import (
    CodeFinderDispatchMixin as legacy_dispatch_mixin,
)
from platform_context_graph.tools.code_finder_relationships import (
    CodeFinderRelationshipsMixin as legacy_relationships_mixin,
)
from platform_context_graph.tools.code_finder_search import (
    CodeFinderSearchMixin as legacy_search_mixin,
)


def test_legacy_code_finder_modules_point_at_query_canonical_modules() -> None:
    """Legacy CodeFinder modules should re-export canonical query modules."""

    assert legacy_code_finder is canonical_code_finder
    assert legacy_analysis_mixin is canonical_analysis_mixin
    assert legacy_dispatch_mixin is canonical_dispatch_mixin
    assert legacy_relationships_mixin is canonical_relationships_mixin
    assert legacy_search_mixin is canonical_search_mixin


def test_code_support_uses_query_canonical_code_finder() -> None:
    """Query support should instantiate the canonical CodeFinder class."""

    assert code_support.CodeFinder is canonical_code_finder
