"""Metric-recording mixins for the observability runtime."""

from __future__ import annotations

import threading
from typing import Any

from .otel import Observation, current_component, status_class


class RuntimeMetricsMixin:
    """Provide metric-recording helpers for :class:`ObservabilityRuntime`."""

    enabled: bool
    component: str
    _lock: threading.Lock
    _active_runs: dict[tuple[tuple[str, str], ...], int]
    _active_repositories: dict[tuple[tuple[str, str], ...], int]
    _checkpoint_pending_repositories: dict[tuple[tuple[str, str], ...], int]
    http_requests_total: Any
    http_request_duration: Any
    http_request_errors_total: Any
    mcp_requests_total: Any
    mcp_request_duration: Any
    mcp_request_errors_total: Any
    mcp_tool_calls_total: Any
    mcp_tool_duration: Any
    mcp_tool_errors_total: Any
    index_runs_total: Any
    index_run_duration: Any
    index_repositories_total: Any
    index_checkpoints_total: Any
    index_repository_duration: Any
    hidden_dirs_skipped_total: Any
    index_lock_contention_skips_total: Any
    neo4j_query_duration: Any
    neo4j_query_errors_total: Any
    content_provider_requests_total: Any
    content_provider_duration: Any
    content_workspace_fallback_total: Any
    worker_scan_requests_total: Any

    def record_http_request(
        self,
        *,
        method: str,
        route: str,
        status_code: int,
        duration_seconds: float,
    ) -> None:
        """Record HTTP request metrics.

        Args:
            method: The HTTP method for the request.
            route: The matched route pattern.
            status_code: The resulting HTTP status code.
            duration_seconds: The request duration in seconds.
        """

        if not self.enabled:
            return
        attrs = {
            "pcg.component": "api",
            "http.method": method,
            "http.route": route,
            "http.status_class": status_class(status_code),
        }
        if self.http_requests_total is not None:
            self.http_requests_total.add(1, attrs)
        if self.http_request_duration is not None:
            self.http_request_duration.record(duration_seconds, attrs)
        if status_code >= 400 and self.http_request_errors_total is not None:
            self.http_request_errors_total.add(1, attrs)

    def record_mcp_request(
        self,
        *,
        method: str,
        transport: str,
        duration_seconds: float,
        success: bool,
    ) -> None:
        """Record MCP JSON-RPC request metrics.

        Args:
            method: The JSON-RPC method name.
            transport: The transport used for the request.
            duration_seconds: The request duration in seconds.
            success: Whether the request completed successfully.
        """

        if not self.enabled:
            return
        attrs = {
            "pcg.component": "mcp",
            "pcg.jsonrpc.method": method,
            "pcg.transport": transport,
        }
        if self.mcp_requests_total is not None:
            self.mcp_requests_total.add(1, attrs)
        if self.mcp_request_duration is not None:
            self.mcp_request_duration.record(duration_seconds, attrs)
        if not success and self.mcp_request_errors_total is not None:
            self.mcp_request_errors_total.add(1, attrs)

    def record_mcp_tool(
        self,
        *,
        tool_name: str,
        transport: str,
        duration_seconds: float,
        success: bool,
    ) -> None:
        """Record MCP tool invocation metrics.

        Args:
            tool_name: The MCP tool name.
            transport: The transport used for the request.
            duration_seconds: The tool duration in seconds.
            success: Whether the tool invocation completed successfully.
        """

        if not self.enabled:
            return
        attrs = {
            "pcg.component": "mcp",
            "pcg.tool.name": tool_name,
            "pcg.transport": transport,
        }
        if self.mcp_tool_calls_total is not None:
            self.mcp_tool_calls_total.add(1, attrs)
        if self.mcp_tool_duration is not None:
            self.mcp_tool_duration.record(duration_seconds, attrs)
        if not success and self.mcp_tool_errors_total is not None:
            self.mcp_tool_errors_total.add(1, attrs)

    def record_index_repositories(
        self,
        *,
        component: str,
        phase: str,
        count: int,
        mode: str,
        source: str,
    ) -> None:
        """Record repository counts for a phase of an index run.

        Args:
            component: The component label for the metric.
            phase: The indexing phase being measured.
            count: The repository count to add.
            mode: The indexing mode being executed.
            source: The request source for the indexing run.
        """

        if not self.enabled or self.index_repositories_total is None:
            return
        self.index_repositories_total.add(
            count,
            {
                "component": component,
                "phase": phase,
                "mode": mode,
                "source": source,
            },
        )

    def record_index_checkpoint(
        self,
        *,
        component: str,
        mode: str,
        source: str,
        operation: str,
        status: str,
    ) -> None:
        """Record a checkpoint lifecycle event for an index run."""

        if not self.enabled or self.index_checkpoints_total is None:
            return
        self.index_checkpoints_total.add(
            1,
            {
                "component": component,
                "mode": mode,
                "source": source,
                "operation": operation,
                "status": status,
            },
        )

    def record_index_repository_duration(
        self,
        *,
        component: str,
        mode: str,
        source: str,
        status: str,
        duration_seconds: float,
    ) -> None:
        """Record the duration of one repository parse/commit attempt."""

        if not self.enabled or self.index_repository_duration is None:
            return
        self.index_repository_duration.record(
            duration_seconds,
            {
                "component": component,
                "mode": mode,
                "source": source,
                "status": status,
            },
        )

    def record_hidden_directory_skip(
        self,
        kind: str,
        *,
        component: str | None = None,
    ) -> None:
        """Record a skipped hidden-directory classification.

        Args:
            kind: The hidden-directory name that was skipped.
            component: The component label to record, if different from the
                current request context.
        """

        if not self.enabled or self.hidden_dirs_skipped_total is None:
            return
        self.hidden_dirs_skipped_total.add(
            1,
            {
                "component": component or current_component() or self.component,
                "kind": kind,
            },
        )

    def record_lock_contention_skip(
        self,
        *,
        component: str,
        mode: str,
        source: str,
    ) -> None:
        """Record a skipped index run due to lock contention.

        Args:
            component: The component label for the metric.
            mode: The indexing mode being executed.
            source: The request source for the indexing run.
        """

        if not self.enabled or self.index_lock_contention_skips_total is None:
            return
        self.index_lock_contention_skips_total.add(
            1,
            {
                "component": component,
                "mode": mode,
                "source": source,
            },
        )

    def record_worker_scan_request(
        self,
        *,
        component: str,
        phase: str,
        requested_by: str | None,
        accepted: bool,
    ) -> None:
        """Record one worker scan control event."""

        if not self.enabled or self.worker_scan_requests_total is None:
            return
        self.worker_scan_requests_total.add(
            1,
            {
                "component": component,
                "phase": phase,
                "requested_by": requested_by or "unknown",
                "accepted": str(accepted).lower(),
            },
        )

    def record_neo4j_query(
        self,
        *,
        query_kind: str,
        duration_seconds: float,
        success: bool,
    ) -> None:
        """Record Neo4j query timings and failures.

        Args:
            query_kind: The logical database operation name.
            duration_seconds: The query duration in seconds.
            success: Whether the query completed successfully.
        """

        if not self.enabled:
            return
        attrs = {
            "pcg.component": current_component() or "unknown",
            "db.system": "neo4j",
            "db.operation": query_kind,
        }
        if self.neo4j_query_duration is not None:
            self.neo4j_query_duration.record(duration_seconds, attrs)
        if not success and self.neo4j_query_errors_total is not None:
            self.neo4j_query_errors_total.add(1, attrs)

    def record_content_provider_result(
        self,
        *,
        operation: str,
        backend: str,
        success: bool,
        hit: bool,
        duration_seconds: float,
    ) -> None:
        """Record one content-provider call across Postgres or workspace.

        Args:
            operation: Logical content operation name.
            backend: Backend used to satisfy the call.
            success: Whether the provider call completed successfully.
            hit: Whether the provider returned content for the lookup.
            duration_seconds: Provider latency in seconds.
        """

        if not self.enabled:
            return
        attrs = {
            "pcg.component": current_component() or self.component,
            "pcg.content.operation": operation,
            "pcg.content.backend": backend,
            "pcg.content.success": str(success).lower(),
            "pcg.content.hit": str(hit).lower(),
        }
        if self.content_provider_requests_total is not None:
            self.content_provider_requests_total.add(1, attrs)
        if self.content_provider_duration is not None:
            self.content_provider_duration.record(duration_seconds, attrs)

    def record_content_workspace_fallback(self, *, operation: str) -> None:
        """Record when a content request falls back from Postgres to workspace.

        Args:
            operation: Logical content operation that used workspace fallback.
        """

        if not self.enabled or self.content_workspace_fallback_total is None:
            return
        self.content_workspace_fallback_total.add(
            1,
            {
                "pcg.component": current_component() or self.component,
                "pcg.content.operation": operation,
            },
        )

    def _adjust_active_state(
        self,
        key: tuple[tuple[str, str], ...],
        *,
        runs_delta: int = 0,
        repos_delta: int = 0,
    ) -> None:
        """Update the active-run and active-repository gauge state.

        Args:
            key: The metric attribute key for the active state bucket.
            runs_delta: The amount to add to the active-run count.
            repos_delta: The amount to add to the active-repository count.
        """

        with self._lock:
            if runs_delta:
                new_runs = self._active_runs.get(key, 0) + runs_delta
                if new_runs <= 0:
                    self._active_runs.pop(key, None)
                else:
                    self._active_runs[key] = new_runs
            if repos_delta:
                new_repos = self._active_repositories.get(key, 0) + repos_delta
                if new_repos <= 0:
                    self._active_repositories.pop(key, None)
                else:
                    self._active_repositories[key] = new_repos

    def _observe_active_runs(self, _options: Any) -> list[Observation]:
        """Produce current active-run gauge observations.

        Args:
            _options: The OpenTelemetry callback options.

        Returns:
            The active-run observations for the runtime.
        """

        with self._lock:
            return [
                Observation(value, dict(key))
                for key, value in sorted(self._active_runs.items())
            ]

    def _observe_active_repositories(self, _options: Any) -> list[Observation]:
        """Produce current active-repository gauge observations.

        Args:
            _options: The OpenTelemetry callback options.

        Returns:
            The active-repository observations for the runtime.
        """

        with self._lock:
            return [
                Observation(value, dict(key))
                for key, value in sorted(self._active_repositories.items())
            ]

    def _observe_pending_checkpoint_repositories(
        self, _options: Any
    ) -> list[Observation]:
        """Produce current pending-checkpoint repository gauge observations."""

        with self._lock:
            return [
                Observation(value, dict(key))
                for key, value in sorted(self._checkpoint_pending_repositories.items())
            ]
