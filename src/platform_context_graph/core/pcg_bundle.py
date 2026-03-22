"""Bundle import/export facade for PlatformContextGraph bundles."""

from __future__ import annotations

from typing import Any

from .pcg_bundle_export import _BundleExportMixin
from .pcg_bundle_import import _BundleImportMixin


class PCGBundle(_BundleExportMixin, _BundleImportMixin):
    """Handle creation and loading of ``.pcg`` bundle files."""

    VERSION = "0.1.0"

    def __init__(self, db_manager: Any) -> None:
        """Initialize the bundle helper.

        Args:
            db_manager: Database manager used to read and write graph data.
        """

        self.db_manager = db_manager

    def _get_id_function(self) -> str:
        """Return the backend-specific node ID function name.

        Returns:
            ``elementId`` for Neo4j-like backends, otherwise ``id``.
        """

        backend = self.db_manager.get_backend_type()
        if backend == "neo4j":
            return "elementId"
        return "id"
