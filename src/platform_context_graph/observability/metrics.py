"""Metric-recording mixins for the observability runtime."""

from __future__ import annotations

import threading
from typing import Any

from .indexing_metrics_v2 import RuntimeIndexMetricsV2Mixin
from .otel import Observation, current_component, status_class


class RuntimeMetricsMixin(RuntimeIndexMetricsV2Mixin):
    """Provide metric-recording helpers for :class:`ObservabilityRuntime`."""

    enabled: bool
    component: str
    _lock: threading.Lock
    _active_runs: dict[tuple[tuple[str, str], ...], int]
    _active_repositories: dict[tuple[tuple[str, str], ...], int]
    _checkpoint_pending_repositories: dict[tuple[tuple[str, str], ...], int]
    _index_snapshot_queue_depth: dict[tuple[tuple[str, str], ...], int]
    _index_parse_tasks_active: dict[tuple[tuple[str, str], ...], int]
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
    index_stage_duration: Any
    hidden_dirs_skipped_total: Any
    index_lock_contention_skips_total: Any
    neo4j_query_duration: Any
    neo4j_query_errors_total: Any
    graph_write_batch_duration: Any
    graph_write_batch_rows: Any
    content_provider_requests_total: Any
    content_provider_duration: Any
    content_workspace_fallback_total: Any
    ingester_scan_requests_total: Any

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

    def record_ingester_scan_request(
        self,
        *,
        ingester: str,
        phase: str,
        requested_by: str | None,
        accepted: bool,
    ) -> None:
        """Record one ingester scan control event."""

        if not self.enabled or self.ingester_scan_requests_total is None:
            return
        self.ingester_scan_requests_total.add(
            1,
            {
                "ingester": ingester,
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

    def record_graph_write_batch(
        self,
        *,
        batch_type: str,
        label: str | None,
        rows: int,
        duration_seconds: float,
    ) -> None:
        """Record graph write batch size and duration telemetry.

        Args:
            batch_type: Logical batch category such as ``entity`` or ``parameters``.
            label: Entity label for entity batches, otherwise ``None``.
            rows: Number of rows written in the batch.
            duration_seconds: Batch execution time in seconds.
        """

        if not self.enabled:
            return
        attrs = {
            "pcg.component": current_component() or self.component,
            "pcg.graph.batch_type": batch_type,
            "pcg.graph.label": label or "none",
        }
        if self.graph_write_batch_duration is not None:
            self.graph_write_batch_duration.record(duration_seconds, attrs)
        if self.graph_write_batch_rows is not None:
            self.graph_write_batch_rows.record(rows, attrs)

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
