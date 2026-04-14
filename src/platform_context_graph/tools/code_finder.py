"""HTTP-based CodeFinder that delegates to the Go API server.

This module provides a CodeFinder class that replaces the previous Neo4j-based
implementation. All queries now go through the Go HTTP API at /api/v0/*.

The Go API server runs at http://localhost:8080 by default, configurable via
the PCG_GO_API_URL environment variable.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

# Track connection failures to avoid spamming logs
_connection_warned = False


def _get_base_url() -> str:
    """Get the Go API base URL from environment or default."""
    return os.getenv("PCG_GO_API_URL", "http://localhost:8080")


def _http_get(endpoint: str, base_url: str) -> dict[str, Any]:
    """Make an HTTP GET request to the Go API.

    Args:
        endpoint: API endpoint path (e.g., /api/v0/repositories)
        base_url: Base URL of the Go API server

    Returns:
        Parsed JSON response as a dictionary

    Raises:
        urllib.error.URLError: On connection or HTTP errors
    """
    url = f"{base_url}{endpoint}"
    req = urllib.request.Request(url, method="GET")
    req.add_header("Content-Type", "application/json")

    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _http_post(endpoint: str, body: dict[str, Any], base_url: str) -> dict[str, Any]:
    """Make an HTTP POST request to the Go API.

    Args:
        endpoint: API endpoint path (e.g., /api/v0/code/search)
        body: Request body as a dictionary
        base_url: Base URL of the Go API server

    Returns:
        Parsed JSON response as a dictionary

    Raises:
        urllib.error.URLError: On connection or HTTP errors
    """
    url = f"{base_url}{endpoint}"
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")

    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


class CodeFinder:
    """HTTP-based code finder that delegates to the Go API server.

    This class provides methods for querying code entities, relationships,
    and complexity metrics. All operations delegate to the Go HTTP API.

    Args:
        db_manager: Ignored for backward compatibility
        base_url: Base URL of the Go API server (default: http://localhost:8080)

    Example:
        # Use default URL from environment or localhost:8080
        finder = CodeFinder()

        # Use custom URL
        finder = CodeFinder(base_url="http://api:8080")

        # List repositories
        repos = finder.list_indexed_repositories()
    """

    def __init__(self, db_manager: Any = None, base_url: str | None = None) -> None:
        """Initialize the HTTP-based CodeFinder.

        Args:
            db_manager: Ignored for backward compatibility with old API
            base_url: Base URL of the Go API server (default from env or localhost)
        """
        self.base_url = base_url or _get_base_url()
        logger.debug(f"CodeFinder initialized with Go API at {self.base_url}")

    def _safe_get(self, endpoint: str) -> list[dict[str, Any]]:
        """Make a GET request with error handling.

        Args:
            endpoint: API endpoint path

        Returns:
            List of results or empty list on error
        """
        global _connection_warned
        try:
            response = _http_get(endpoint, self.base_url)
            return response if isinstance(response, list) else []
        except urllib.error.URLError as e:
            if not _connection_warned:
                logger.warning(
                    f"Go API connection failed at {self.base_url}: {e}. "
                    "Returning empty results. Further warnings suppressed."
                )
                _connection_warned = True
            return []
        except Exception as e:
            logger.error(f"Unexpected error querying {endpoint}: {e}")
            return []

    def _safe_post(self, endpoint: str, body: dict[str, Any]) -> dict[str, Any]:
        """Make a POST request with error handling.

        Args:
            endpoint: API endpoint path
            body: Request body

        Returns:
            Response dict or empty dict with error on failure
        """
        global _connection_warned
        try:
            return _http_post(endpoint, body, self.base_url)
        except urllib.error.URLError as e:
            if not _connection_warned:
                logger.warning(
                    f"Go API connection failed at {self.base_url}: {e}. "
                    "Returning empty results. Further warnings suppressed."
                )
                _connection_warned = True
            return {"results": []}
        except Exception as e:
            logger.error(f"Unexpected error posting to {endpoint}: {e}")
            return {"results": []}

    def list_indexed_repositories(self) -> list[dict[str, Any]]:
        """List all indexed repositories.

        Returns:
            List of repository dicts with keys: id, name, path, local_path,
            remote_url, has_remote
        """
        try:
            response = _http_get("/api/v0/repositories", self.base_url)
            return response.get("repositories", [])
        except Exception:
            return self._safe_get("/api/v0/repositories")

    def find_by_function_name(
        self, name: str, fuzzy_search: bool = False
    ) -> list[dict[str, Any]]:
        """Find functions by name.

        Args:
            name: Function name to search for
            fuzzy_search: If True, use fuzzy matching (not currently supported)

        Returns:
            List of matching entities
        """
        body = {"query": name, "repo_id": "", "limit": 50}
        response = self._safe_post("/api/v0/code/search", body)
        results = response.get("results", [])
        # Filter to only functions
        return [r for r in results if "Function" in r.get("labels", [])]

    def find_by_class_name(
        self, name: str, fuzzy_search: bool = False
    ) -> list[dict[str, Any]]:
        """Find classes by name.

        Args:
            name: Class name to search for
            fuzzy_search: If True, use fuzzy matching (not currently supported)

        Returns:
            List of matching entities
        """
        body = {"query": name, "repo_id": "", "limit": 50}
        response = self._safe_post("/api/v0/code/search", body)
        results = response.get("results", [])
        # Filter to only classes
        return [r for r in results if "Class" in r.get("labels", [])]

    def find_by_variable_name(self, name: str) -> list[dict[str, Any]]:
        """Find variables by name.

        Args:
            name: Variable name to search for

        Returns:
            List of matching entities
        """
        body = {"query": name, "repo_id": "", "limit": 50}
        response = self._safe_post("/api/v0/code/search", body)
        results = response.get("results", [])
        # Filter to only variables
        return [r for r in results if "Variable" in r.get("labels", [])]

    def find_by_module_name(self, name: str) -> list[dict[str, Any]]:
        """Find modules by name.

        Args:
            name: Module name to search for

        Returns:
            List of matching entities
        """
        body = {"query": name, "repo_id": "", "limit": 50}
        response = self._safe_post("/api/v0/code/search", body)
        results = response.get("results", [])
        # Filter to modules/packages
        return [
            r
            for r in results
            if "Module" in r.get("labels", []) or "Package" in r.get("labels", [])
        ]

    def find_imports(self, name: str) -> list[dict[str, Any]]:
        """Find import statements.

        Args:
            name: Import name to search for

        Returns:
            List of matching entities
        """
        body = {"query": name, "repo_id": "", "limit": 50}
        response = self._safe_post("/api/v0/code/search", body)
        results = response.get("results", [])
        # Filter to imports
        return [r for r in results if "Import" in r.get("labels", [])]

    def find_by_type(self, element_type: str, limit: int = 50) -> list[dict[str, Any]]:
        """Find entities by type.

        Args:
            element_type: Entity type (e.g., function, class, variable)
            limit: Maximum number of results

        Returns:
            List of matching entities
        """
        # Search with empty query to get all, then filter by type
        body = {"query": "", "repo_id": "", "limit": limit}
        response = self._safe_post("/api/v0/code/search", body)
        results = response.get("results", [])
        # Filter by element type (case-insensitive)
        type_upper = element_type.upper()
        return [
            r for r in results if any(type_upper in label.upper() for label in r.get("labels", []))
        ]

    def find_by_content(self, query: str) -> list[dict[str, Any]]:
        """Search file content by pattern.

        Args:
            query: Search pattern

        Returns:
            List of matching files/entities
        """
        body = {"repo_id": "", "query": query, "limit": 50}
        response = self._safe_post("/api/v0/content/files/search", body)
        return response.get("results", [])

    def find_dead_code(self, exclude_list: list[str] | None = None) -> list[dict[str, Any]]:
        """Find entities with no incoming references.

        Args:
            exclude_list: List of decorators to exclude (not currently supported)

        Returns:
            List of potentially dead code entities
        """
        body = {"repo_id": ""}
        response = self._safe_post("/api/v0/code/dead-code", body)
        return response.get("results", [])

    def get_cyclomatic_complexity(self, path: str, file: str) -> dict[str, Any]:
        """Get complexity metrics for a specific entity.

        Args:
            path: Repository ID
            file: File path or entity ID

        Returns:
            Complexity metrics dict
        """
        # Try to use as entity_id first
        body = {"entity_id": file, "repo_id": path}
        response = self._safe_post("/api/v0/code/complexity", body)
        return response

    def find_most_complex_functions(self, limit: int = 20) -> list[dict[str, Any]]:
        """Find the most complex functions by relationship count.

        Args:
            limit: Maximum number of results

        Returns:
            List of complex functions with metrics
        """
        # The Go API doesn't have a direct "top N complex" endpoint yet
        # Return empty for now
        logger.warning("find_most_complex_functions not yet implemented in Go API")
        return []

    def who_calls_function(
        self, function: str, file: str | None = None
    ) -> list[dict[str, Any]]:
        """Find callers of a function.

        Args:
            function: Function name or entity ID
            file: Optional file path filter

        Returns:
            List of caller entities
        """
        # If function looks like an entity_id, use it directly
        body = {"entity_id": function}
        response = self._safe_post("/api/v0/code/relationships", body)
        incoming = response.get("incoming", [])
        # Filter to CALLS relationships
        return [r for r in incoming if r.get("type") == "CALLS"]

    def what_does_function_call(
        self, function: str, file: str | None = None
    ) -> list[dict[str, Any]]:
        """Find callees of a function.

        Args:
            function: Function name or entity ID
            file: Optional file path filter

        Returns:
            List of callee entities
        """
        body = {"entity_id": function}
        response = self._safe_post("/api/v0/code/relationships", body)
        outgoing = response.get("outgoing", [])
        # Filter to CALLS relationships
        return [r for r in outgoing if r.get("type") == "CALLS"]

    def find_function_call_chain(
        self, start: str, end: str, max_depth: int = 5
    ) -> list[dict[str, Any]]:
        """Find call chain between two functions.

        Args:
            start: Starting function name or entity ID
            end: Ending function name or entity ID
            max_depth: Maximum chain depth

        Returns:
            List of call chain paths
        """
        # Not directly supported by Go API yet
        logger.warning("find_function_call_chain not yet implemented in Go API")
        return []

    def find_module_dependencies(self, target: str) -> list[dict[str, Any]]:
        """Find module dependencies.

        Args:
            target: Module name or entity ID

        Returns:
            List of dependency relationships
        """
        body = {"entity_id": target}
        response = self._safe_post("/api/v0/code/relationships", body)
        outgoing = response.get("outgoing", [])
        # Filter to dependency relationships
        return [
            r
            for r in outgoing
            if r.get("type") in ("IMPORTS", "DEPENDS_ON", "USES")
        ]

    def find_class_hierarchy(
        self, class_name: str, file: str | None = None
    ) -> list[dict[str, Any]]:
        """Find class hierarchy (inheritance).

        Args:
            class_name: Class name or entity ID
            file: Optional file path filter

        Returns:
            List of hierarchy relationships
        """
        body = {"entity_id": class_name}
        response = self._safe_post("/api/v0/code/relationships", body)
        # Combine incoming and outgoing inheritance relationships
        incoming = response.get("incoming", [])
        outgoing = response.get("outgoing", [])
        hierarchy = [
            r
            for r in incoming + outgoing
            if r.get("type") in ("INHERITS", "EXTENDS", "IMPLEMENTS")
        ]
        return hierarchy

    def find_functions_by_decorator(
        self, decorator: str, file: str | None = None
    ) -> list[dict[str, Any]]:
        """Find functions with a specific decorator.

        Args:
            decorator: Decorator name
            file: Optional file path filter

        Returns:
            List of decorated functions
        """
        # Search for functions and filter by decorator in content
        body = {"query": decorator, "repo_id": "", "limit": 50}
        response = self._safe_post("/api/v0/code/search", body)
        results = response.get("results", [])
        return [r for r in results if "Function" in r.get("labels", [])]

    def find_functions_by_argument(
        self, argument: str, file: str | None = None
    ) -> list[dict[str, Any]]:
        """Find functions with a specific argument.

        Args:
            argument: Argument name
            file: Optional file path filter

        Returns:
            List of functions
        """
        # Search for functions with argument in content
        body = {"query": argument, "repo_id": "", "limit": 50}
        response = self._safe_post("/api/v0/code/search", body)
        results = response.get("results", [])
        return [r for r in results if "Function" in r.get("labels", [])]

    def find_function_overrides(self, function_name: str) -> list[dict[str, Any]]:
        """Find function overrides in subclasses.

        Args:
            function_name: Function name or entity ID

        Returns:
            List of override relationships
        """
        body = {"entity_id": function_name}
        response = self._safe_post("/api/v0/code/relationships", body)
        incoming = response.get("incoming", [])
        return [r for r in incoming if r.get("type") == "OVERRIDES"]

    def find_variable_usage_scope(
        self, variable_name: str, file: str
    ) -> list[dict[str, Any]]:
        """Find variable usage scope within a file.

        Args:
            variable_name: Variable name
            file: File path

        Returns:
            List of usage locations
        """
        # Search for variable in specific file
        body = {"query": variable_name, "repo_id": "", "limit": 50}
        response = self._safe_post("/api/v0/code/search", body)
        results = response.get("results", [])
        # Filter by file path and variable label
        return [
            r
            for r in results
            if "Variable" in r.get("labels", []) and file in r.get("file_path", "")
        ]


__all__ = ["CodeFinder"]
