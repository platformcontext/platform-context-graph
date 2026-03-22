"""Manage the embedded Kuzu backend and re-export its compatibility wrappers."""

from __future__ import annotations

import os
import threading
from pathlib import Path

from platform_context_graph.core.database_kuzu_helpers import (
    KuzuDriverWrapper,
    KuzuRecord,
    KuzuResultWrapper,
    KuzuSessionWrapper,
)
from platform_context_graph.core.database_kuzu_schema import initialize_kuzu_schema
from platform_context_graph.paths import get_app_home
from platform_context_graph.utils.debug_log import error_logger, info_logger


class KuzuDBManager:
    """Manage the singleton Kuzu database connection for local graph storage."""

    _instance = None
    _db = None
    _conn = None
    _lock = threading.Lock()

    def __new__(cls):
        """Return the singleton manager instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(KuzuDBManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize the manager with configured database paths."""
        if hasattr(self, "_initialized"):
            return

        self.name = "kuzudb"
        try:
            from platform_context_graph.cli.config_manager import get_config_value

            config_db_path = get_config_value("KUZUDB_PATH")
        except Exception:
            config_db_path = None

        self.db_path = os.getenv(
            "KUZUDB_PATH", config_db_path or str(get_app_home() / "kuzudb")
        )
        os.makedirs(Path(self.db_path).parent, exist_ok=True)
        self._initialized = True

    def get_driver(self) -> KuzuDriverWrapper:
        """Return a Neo4j-compatible wrapper around the active Kuzu connection.

        Returns:
            A driver wrapper that exposes Neo4j-like session semantics.

        Raises:
            ValueError: If the `kuzu` package is not installed.
            Exception: Propagated if Kuzu initialization fails.
        """
        if self._conn is None:
            with self._lock:
                if self._conn is None:
                    try:
                        import kuzu

                        info_logger(f"Initializing KùzuDB at {self.db_path}")
                        self._db = kuzu.Database(self.db_path)
                        self._conn = kuzu.Connection(self._db)
                        initialize_kuzu_schema(self._conn)
                        info_logger("KùzuDB connection established and schema verified")
                    except ImportError:
                        error_logger("KùzuDB is not installed. Run 'pip install kuzu'")
                        raise ValueError("KùzuDB missing.")
                    except Exception as exc:
                        error_logger(f"Failed to initialize KùzuDB: {exc}")
                        raise

        return KuzuDriverWrapper(self._conn)

    def close_driver(self) -> None:
        """Clear the cached Kuzu connection and database handle."""
        if self._conn is not None:
            info_logger("Closing KùzuDB connection")
            self._conn = None
            self._db = None

    def is_connected(self) -> bool:
        """Check whether the cached Kuzu connection is still usable."""
        if self._conn is None:
            return False
        try:
            self._conn.execute("RETURN 1")
            return True
        except Exception:
            return False

    def get_backend_type(self) -> str:
        """Return the backend identifier for this manager."""
        return "kuzudb"

    @staticmethod
    def validate_config(db_path: str | None = None) -> tuple[bool, str | None]:
        """Validate the configured Kuzu database location.

        Args:
            db_path: Optional override path to validate.

        Returns:
            A tuple of `(is_valid, error_message)`.
        """
        if db_path:
            db_dir = Path(db_path).parent
            if not os.access(db_dir, os.W_OK) and db_dir.exists():
                return False, f"Cannot write to directory: {db_dir}"
        return True, None

    @staticmethod
    def test_connection(db_path: str | None = None) -> tuple[bool, str | None]:
        """Check whether the Kuzu Python package is importable.

        Args:
            db_path: Unused compatibility argument retained for API parity.

        Returns:
            A tuple of `(is_available, error_message)`.
        """
        del db_path
        try:
            import kuzu  # noqa: F401

            return True, None
        except ImportError:
            return False, "KùzuDB is not installed. Run 'pip install kuzu'"


__all__ = [
    "KuzuDBManager",
    "KuzuDriverWrapper",
    "KuzuRecord",
    "KuzuResultWrapper",
    "KuzuSessionWrapper",
]
