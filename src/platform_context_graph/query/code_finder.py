"""Public `CodeFinder` entry point for code search and relationship analysis."""

from __future__ import annotations

from ..core.database import DatabaseManager
from .code_finder_analysis import CodeFinderAnalysisMixin
from .code_finder_dispatch import CodeFinderDispatchMixin
from .code_finder_relationships import CodeFinderRelationshipsMixin
from .code_finder_search import CodeFinderSearchMixin


class CodeFinder(
    CodeFinderSearchMixin,
    CodeFinderRelationshipsMixin,
    CodeFinderAnalysisMixin,
    CodeFinderDispatchMixin,
):
    """Find code snippets and analyze graph relationships from the active database."""

    def __init__(self, db_manager: DatabaseManager):
        """Initialize the finder with a database manager and driver wrapper.

        Args:
            db_manager: Database manager that provides the active driver.
        """
        self.db_manager = db_manager
        self.driver = self.db_manager.get_driver()
        self._is_falkordb = (
            getattr(db_manager, "get_backend_type", lambda: "neo4j")() != "neo4j"
        )
        self._search_warnings: list[str] = []


__all__ = ["CodeFinder"]
