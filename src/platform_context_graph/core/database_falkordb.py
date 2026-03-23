"""Manage the embedded FalkorDB backend and re-export compatibility wrappers."""

from __future__ import annotations

import atexit
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from platform_context_graph.core.database_falkordb_helpers import (
    FalkorDBDriverWrapper,
    FalkorDBRecord,
    FalkorDBResultWrapper,
    FalkorDBSessionWrapper,
    apply_unix_socket_connection_patch,
)
from platform_context_graph.core.database import graph_store_capabilities_for_backend
from platform_context_graph.paths import get_app_home
from platform_context_graph.utils.debug_log import error_logger, info_logger

apply_unix_socket_connection_patch()

WINDOWS_UNSUPPORTED_MESSAGE = (
    "PlatformContextGraph uses redislite/FalkorDB, which does not support Windows.\n"
    "Please run the project using WSL or Docker."
)


class FalkorDBUnavailableError(RuntimeError):
    """Signal that the embedded FalkorDB backend cannot run in this environment."""


class FalkorDBManager:
    """Manage the singleton FalkorDB Lite subprocess and graph connection."""

    _instance = None
    _process = None
    _driver = None
    _graph = None
    _lock = threading.Lock()

    def __new__(cls):
        """Return the singleton manager instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(FalkorDBManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize backend paths and register shutdown hooks."""
        if hasattr(self, "_initialized"):
            return

        try:
            from platform_context_graph.cli.config_manager import get_config_value

            config_db_path = get_config_value("FALKORDB_PATH")
            config_socket_path = get_config_value("FALKORDB_SOCKET_PATH")
        except Exception:
            config_db_path = None
            config_socket_path = None

        self.db_path = os.getenv(
            "FALKORDB_PATH", config_db_path or str(get_app_home() / "falkordb.db")
        )
        self.socket_path = os.getenv(
            "FALKORDB_SOCKET_PATH",
            config_socket_path or str(get_app_home() / "falkordb.sock"),
        )
        self.graph_name = os.getenv("FALKORDB_GRAPH_NAME", "codegraph")
        self._initialized = True
        atexit.register(self.shutdown)

    def get_driver(self) -> FalkorDBDriverWrapper:
        """Return a Neo4j-compatible wrapper around the active FalkorDB graph.

        Returns:
            A driver wrapper that exposes Neo4j-like session semantics.

        Raises:
            RuntimeError: If the platform is unsupported.
            ValueError: If Python or package requirements are not met.
            FalkorDBUnavailableError: If the embedded worker cannot start.
        """
        if platform.system() == "Windows":
            raise RuntimeError(WINDOWS_UNSUPPORTED_MESSAGE)

        if self._driver is None:
            if sys.version_info < (3, 12):
                raise ValueError("FalkorDB Lite is not supported on Python < 3.12.")

            with self._lock:
                if self._driver is None:
                    if sys.path and sys.path[0]:
                        potential_shadow = os.path.join(sys.path[0], "falkordb.so")
                        if os.path.exists(potential_shadow):
                            info_logger(
                                "Detected 'falkordb.so' in sys.path[0]. Removing path "
                                "to prevent import shadowing."
                            )
                            sys.path.pop(0)

                    try:
                        self._ensure_server_running()
                        from falkordb import FalkorDB

                        info_logger(
                            f"Connecting to FalkorDB Lite at {self.socket_path}"
                        )
                        self._driver = FalkorDB(unix_socket_path=self.socket_path)
                        self._graph = self._driver.select_graph(self.graph_name)
                        try:
                            self._graph.query("RETURN 1")
                            info_logger(
                                "FalkorDB Lite connection established successfully"
                            )
                            info_logger(f"Graph name: {self.graph_name}")
                        except Exception as exc:
                            info_logger(f"Initial ping check: {exc}")
                    except ImportError as exc:
                        error_logger(
                            "FalkorDB client is not installed. Install it with:\n"
                            "  pip install falkordblite"
                        )
                        raise ValueError("FalkorDB client missing.") from exc
                    except Exception as exc:
                        error_logger(f"Failed to initialize FalkorDB: {exc}")
                        raise

        return FalkorDBDriverWrapper(self._graph)

    def _ensure_server_running(self) -> None:
        """Start the FalkorDB worker subprocess if no healthy socket exists.

        Raises:
            RuntimeError: If the platform is unsupported or startup times out.
            FalkorDBUnavailableError: If the worker exits during startup.
        """
        if platform.system() == "Windows":
            raise RuntimeError(WINDOWS_UNSUPPORTED_MESSAGE)

        if os.path.exists(self.socket_path):
            try:
                from falkordb import FalkorDB

                driver = FalkorDB(unix_socket_path=self.socket_path)
                test_graph = driver.select_graph("__pcg_health_check")
                test_graph.query("RETURN 1")
                info_logger("Connected to existing (functional) FalkorDB Lite process.")
                return
            except Exception as exc:
                info_logger(
                    "Existing FalkorDB process at "
                    f"{self.socket_path} is stale or non-functional: {exc}"
                )
                info_logger("Cleaning up and attempting fresh start...")
                try:
                    os.remove(self.socket_path)
                except OSError:
                    pass

        env = os.environ.copy()
        env["FALKORDB_PATH"] = self.db_path
        env["FALKORDB_SOCKET_PATH"] = self.socket_path

        python_exe = sys.executable
        if getattr(sys, "frozen", False):
            env["PCG_RUN_FALKOR_WORKER"] = "true"
            cmd = [python_exe]
        else:
            exe_name = os.path.basename(python_exe).lower()
            if not any(name in exe_name for name in ["python", "py.exe", "pypy"]):
                python_exe = (
                    shutil.which("python3") or shutil.which("python") or sys.executable
                )
            cmd = [python_exe, "-m", "platform_context_graph.core.falkor_worker"]

        info_logger("Starting FalkorDB Lite worker subprocess...")
        self._process = subprocess.Popen(
            cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )

        start_time = time.time()
        timeout = 20
        while time.time() - start_time < timeout:
            if os.path.exists(self.socket_path):
                time.sleep(0.2)
                return

            if self._process.poll() is not None:
                stdout, stderr = self._process.communicate()
                raise FalkorDBUnavailableError(
                    "FalkorDB Lite worker failed to start "
                    f"(Exit Code {self._process.returncode}).\n"
                    f"STDOUT: {stdout.decode().strip()}\n"
                    f"STDERR: {stderr.decode().strip()}"
                )

            time.sleep(0.5)

        raise RuntimeError("Timed out waiting for FalkorDB Lite to start.")

    def close_driver(self) -> None:
        """Clear the cached FalkorDB client and graph handles."""
        if self._driver is not None:
            info_logger("Closing FalkorDB Lite connection")
            self._driver = None
            self._graph = None

    def shutdown(self) -> None:
        """Terminate the worker subprocess during process shutdown."""
        if self._process and self._process.poll() is None:
            info_logger("Stopping FalkorDB subprocess...")
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()

    def is_connected(self) -> bool:
        """Check whether the cached FalkorDB graph is still usable."""
        if self._graph is None:
            return False
        try:
            self._graph.query("RETURN 1")
            return True
        except Exception:
            return False

    def get_backend_type(self) -> str:
        """Return the backend identifier for this manager."""
        return "falkordb"

    def graph_store_capabilities(self):
        """Return the graph-store capability contract for this backend."""

        return graph_store_capabilities_for_backend(self.get_backend_type())

    @staticmethod
    def validate_config(db_path: str | None = None) -> tuple[bool, str | None]:
        """Validate the configured FalkorDB database location.

        Args:
            db_path: Optional override path to validate.

        Returns:
            A tuple of `(is_valid, error_message)`.
        """
        if db_path:
            db_dir = Path(db_path).parent
            if not os.access(db_dir, os.W_OK) and db_dir.exists():
                return (
                    False,
                    f"Cannot write to directory: {db_dir}\n"
                    "Please ensure you have write permissions.",
                )
        return True, None

    @staticmethod
    def test_connection(db_path: str | None = None) -> tuple[bool, str | None]:
        """Check whether FalkorDB Lite is available in the current runtime.

        Args:
            db_path: Unused compatibility argument retained for API parity.

        Returns:
            A tuple of `(is_available, error_message)`.
        """
        del db_path
        try:
            if sys.version_info < (3, 12):
                return (
                    False,
                    "FalkorDB Lite is not supported on Python < 3.12. Please "
                    "upgrade or use Neo4j.",
                )

            import falkordb  # noqa: F401

            return True, None
        except ImportError:
            return (
                False,
                "FalkorDB client is not installed.\n"
                "Install it with: pip install falkordblite",
            )


__all__ = [
    "FalkorDBDriverWrapper",
    "FalkorDBManager",
    "FalkorDBRecord",
    "FalkorDBResultWrapper",
    "FalkorDBSessionWrapper",
    "FalkorDBUnavailableError",
]
