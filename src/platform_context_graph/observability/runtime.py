"""Runtime primitives for platform observability instrumentation."""

from __future__ import annotations

import contextlib
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from .http_middleware import install_http_middleware
from .metrics import RuntimeMetricsMixin
from .otel import (
    DEFAULT_EXCLUDED_URLS,
    ActiveStateKey,
    FastAPI,
    FastAPIInstrumentor,
    Observation,
    REQUEST_CONTEXT_UNSET,
    MeterProvider,
    MetricReader,
    SpanExporter,
    TracerProvider,
    current_component,
    current_correlation_id,
    current_request_id,
    current_transport,
    request_context_scope,
)

_MEMORY_UNSET = -1


@dataclass(slots=True)
class ObservabilityRuntime(RuntimeMetricsMixin):
    """Hold OpenTelemetry providers, instruments, and request helpers.

    Attributes:
        enabled: Whether observability is active for the current process.
        service_name: The OTEL service name associated with this runtime.
        component: The default platform component label for emitted telemetry.
        tracer_provider: The tracer provider, when tracing is enabled.
        meter_provider: The meter provider, when metrics are enabled.
        trace_exporter: The configured span exporter, if any.
        metric_reader: The configured metric reader, if any.
        excluded_urls: FastAPI routes that should bypass HTTP metrics.
    """

    enabled: bool
    service_name: str
    component: str
    tracer_provider: TracerProvider | None = None
    meter_provider: MeterProvider | None = None
    trace_exporter: SpanExporter | None = None
    metric_reader: MetricReader | None = None
    excluded_urls: tuple[str, ...] = field(
        default_factory=lambda: DEFAULT_EXCLUDED_URLS
    )
    _instrumented_apps: set[int] = field(default_factory=set)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    tracer: Any = field(init=False, default=None)
    meter: Any = field(init=False, default=None)
    _active_runs: dict[ActiveStateKey, int] = field(init=False, default_factory=dict)
    _active_repositories: dict[ActiveStateKey, int] = field(
        init=False,
        default_factory=dict,
    )
    _checkpoint_pending_repositories: dict[ActiveStateKey, int] = field(
        init=False,
        default_factory=dict,
    )
    _index_snapshot_queue_depth: dict[ActiveStateKey, int] = field(
        init=False,
        default_factory=dict,
    )
    _index_parse_tasks_active: dict[ActiveStateKey, int] = field(
        init=False,
        default_factory=dict,
    )
    _process_rss_bytes: int = field(init=False, default=_MEMORY_UNSET)
    _cgroup_memory_bytes: int = field(init=False, default=_MEMORY_UNSET)
    _cgroup_memory_limit_bytes: int = field(init=False, default=_MEMORY_UNSET)
    http_requests_total: Any = field(init=False, default=None)
    http_request_duration: Any = field(init=False, default=None)
    http_request_errors_total: Any = field(init=False, default=None)
    mcp_requests_total: Any = field(init=False, default=None)
    mcp_request_duration: Any = field(init=False, default=None)
    mcp_request_errors_total: Any = field(init=False, default=None)
    mcp_tool_calls_total: Any = field(init=False, default=None)
    mcp_tool_duration: Any = field(init=False, default=None)
    mcp_tool_errors_total: Any = field(init=False, default=None)
    index_runs_total: Any = field(init=False, default=None)
    index_run_duration: Any = field(init=False, default=None)
    index_repositories_total: Any = field(init=False, default=None)
    index_checkpoints_total: Any = field(init=False, default=None)
    index_repository_duration: Any = field(init=False, default=None)
    index_stage_duration: Any = field(init=False, default=None)
    hidden_dirs_skipped_total: Any = field(init=False, default=None)
    index_lock_contention_skips_total: Any = field(init=False, default=None)
    neo4j_query_duration: Any = field(init=False, default=None)
    neo4j_query_errors_total: Any = field(init=False, default=None)
    graph_write_batch_duration: Any = field(init=False, default=None)
    graph_write_batch_rows: Any = field(init=False, default=None)
    content_provider_requests_total: Any = field(init=False, default=None)
    content_provider_duration: Any = field(init=False, default=None)
    content_workspace_fallback_total: Any = field(init=False, default=None)
    ingester_scan_requests_total: Any = field(init=False, default=None)
    index_snapshot_queue_depth: Any = field(init=False, default=None)
    index_parse_tasks_active: Any = field(init=False, default=None)

    def __post_init__(self) -> None:
        """Create the tracer, meter, and metric instruments for the runtime."""

        self.tracer = (
            self.tracer_provider.get_tracer("platform_context_graph")
            if self.enabled and self.tracer_provider is not None
            else None
        )
        self.meter = (
            self.meter_provider.get_meter("platform_context_graph")
            if self.enabled and self.meter_provider is not None
            else None
        )
        self._setup_instruments()

    def _setup_instruments(self) -> None:
        """Initialize counters, histograms, and gauges for this runtime."""

        self.http_requests_total = None
        self.http_request_duration = None
        self.http_request_errors_total = None
        self.mcp_requests_total = None
        self.mcp_request_duration = None
        self.mcp_request_errors_total = None
        self.mcp_tool_calls_total = None
        self.mcp_tool_duration = None
        self.mcp_tool_errors_total = None
        self.index_runs_total = None
        self.index_run_duration = None
        self.index_repositories_total = None
        self.index_checkpoints_total = None
        self.index_repository_duration = None
        self.index_stage_duration = None
        self.hidden_dirs_skipped_total = None
        self.index_lock_contention_skips_total = None
        self.neo4j_query_duration = None
        self.neo4j_query_errors_total = None
        self.graph_write_batch_duration = None
        self.graph_write_batch_rows = None
        self.content_provider_requests_total = None
        self.content_provider_duration = None
        self.content_workspace_fallback_total = None
        self.ingester_scan_requests_total = None
        self.index_snapshot_queue_depth = None
        self.index_parse_tasks_active = None

        if not self.enabled or self.meter is None:
            return

        self.http_requests_total = self.meter.create_counter("pcg_http_requests_total")
        self.http_request_duration = self.meter.create_histogram(
            "pcg_http_request_duration_seconds",
            unit="s",
        )
        self.http_request_errors_total = self.meter.create_counter(
            "pcg_http_request_errors_total"
        )

        self.mcp_requests_total = self.meter.create_counter("pcg_mcp_requests_total")
        self.mcp_request_duration = self.meter.create_histogram(
            "pcg_mcp_request_duration_seconds",
            unit="s",
        )
        self.mcp_request_errors_total = self.meter.create_counter(
            "pcg_mcp_request_errors_total"
        )
        self.mcp_tool_calls_total = self.meter.create_counter(
            "pcg_mcp_tool_calls_total"
        )
        self.mcp_tool_duration = self.meter.create_histogram(
            "pcg_mcp_tool_duration_seconds",
            unit="s",
        )
        self.mcp_tool_errors_total = self.meter.create_counter(
            "pcg_mcp_tool_errors_total"
        )

        self.index_runs_total = self.meter.create_counter("pcg_index_runs_total")
        self.index_run_duration = self.meter.create_histogram(
            "pcg_index_run_duration_seconds",
            unit="s",
        )
        self.index_repositories_total = self.meter.create_counter(
            "pcg_index_repositories_total"
        )
        self.index_checkpoints_total = self.meter.create_counter(
            "pcg_index_checkpoints_total"
        )
        self.index_repository_duration = self.meter.create_histogram(
            "pcg_index_repository_duration_seconds",
            unit="s",
        )
        self.index_stage_duration = self.meter.create_histogram(
            "pcg_index_stage_duration_seconds",
            unit="s",
        )
        self.hidden_dirs_skipped_total = self.meter.create_counter(
            "pcg_hidden_dirs_skipped_total"
        )
        self.index_lock_contention_skips_total = self.meter.create_counter(
            "pcg_index_lock_contention_skips_total"
        )
        self.neo4j_query_duration = self.meter.create_histogram(
            "pcg_neo4j_query_duration_seconds",
            unit="s",
        )
        self.neo4j_query_errors_total = self.meter.create_counter(
            "pcg_neo4j_query_errors_total"
        )
        self.graph_write_batch_duration = self.meter.create_histogram(
            "pcg_graph_write_batch_duration_seconds",
            unit="s",
        )
        self.graph_write_batch_rows = self.meter.create_histogram(
            "pcg_graph_write_batch_rows",
            unit="rows",
        )
        self.content_provider_requests_total = self.meter.create_counter(
            "pcg_content_provider_requests_total"
        )
        self.content_provider_duration = self.meter.create_histogram(
            "pcg_content_provider_duration_seconds",
            unit="s",
        )
        self.content_workspace_fallback_total = self.meter.create_counter(
            "pcg_content_workspace_fallback_total"
        )
        self.ingester_scan_requests_total = self.meter.create_counter(
            "pcg_ingester_scan_requests_total"
        )

        self.meter.create_observable_gauge(
            "pcg_index_active_runs",
            callbacks=[self._observe_active_runs],
        )
        self.meter.create_observable_gauge(
            "pcg_index_active_repositories",
            callbacks=[self._observe_active_repositories],
        )
        self.meter.create_observable_gauge(
            "pcg_index_checkpoint_pending_repositories",
            callbacks=[self._observe_pending_checkpoint_repositories],
        )
        self.meter.create_observable_gauge(
            "pcg_index_snapshot_queue_depth",
            callbacks=[self._observe_index_snapshot_queue_depth],
        )
        self.meter.create_observable_gauge(
            "pcg_index_parse_tasks_active",
            callbacks=[self._observe_index_parse_tasks_active],
        )
        for gauge_name, attr_name, description in (
            (
                "pcg_process_rss_bytes",
                "_process_rss_bytes",
                "Process RSS memory in bytes",
            ),
            (
                "pcg_cgroup_memory_bytes",
                "_cgroup_memory_bytes",
                "Cgroup current memory in bytes",
            ),
            (
                "pcg_cgroup_memory_limit_bytes",
                "_cgroup_memory_limit_bytes",
                "Cgroup memory limit in bytes",
            ),
        ):
            self.meter.create_observable_gauge(
                gauge_name,
                callbacks=[self._make_memory_observer(attr_name)],
                unit="By",
                description=description,
            )

    def record_memory_usage(self, sample: Any) -> None:
        """Store the latest memory sample for gauge observation.

        Args:
            sample: A ``MemoryUsageSample`` instance from memory_diagnostics.
        """

        if sample.rss_bytes is not None:
            self._process_rss_bytes = sample.rss_bytes
        if sample.cgroup_memory_bytes is not None:
            self._cgroup_memory_bytes = sample.cgroup_memory_bytes
        if getattr(sample, "cgroup_memory_limit_bytes", None) is not None:
            self._cgroup_memory_limit_bytes = sample.cgroup_memory_limit_bytes

    def _make_memory_observer(self, attr_name: str) -> Any:
        """Return a gauge callback that reads one memory field by attribute name."""

        def _observe(_options: Any) -> list[Observation]:
            """Yield a single observation for the named memory gauge field."""

            value = getattr(self, attr_name, _MEMORY_UNSET)
            if value == _MEMORY_UNSET:
                return []
            return [Observation(value, {})]

        return _observe

    def shutdown(self) -> None:
        """Shut down the configured meter and tracer providers."""

        if self.meter_provider is not None:
            with contextlib.suppress(Exception):
                self.meter_provider.shutdown()
        if self.tracer_provider is not None:
            with contextlib.suppress(Exception):
                self.tracer_provider.shutdown()

    def instrument_fastapi_app(self, app: FastAPI) -> None:
        """Instrument a FastAPI application exactly once.

        Args:
            app: The FastAPI application to instrument.
        """

        app_id = id(app)
        if app_id in self._instrumented_apps:
            return

        if self.enabled and FastAPIInstrumentor is not None:
            FastAPIInstrumentor.instrument_app(
                app,
                tracer_provider=self.tracer_provider,
                meter_provider=self.meter_provider,
                excluded_urls=",".join(self.excluded_urls),
            )
        install_http_middleware(app, self)
        self._instrumented_apps.add(app_id)

    @contextlib.contextmanager
    def request_context(
        self,
        *,
        component: str,
        transport: str | None = None,
        request_id: str | None | object = REQUEST_CONTEXT_UNSET,
        correlation_id: str | None | object = REQUEST_CONTEXT_UNSET,
    ) -> Iterator[None]:
        """Set the active component and transport while handling a request.

        Args:
            component: The logical component handling the request.
            transport: The transport label for the request, if any.
            request_id: The request identifier, when one exists.
            correlation_id: The correlation identifier, when one exists.

        Yields:
            ``None`` while the request context is active.
        """

        with request_context_scope(
            component=component,
            transport=transport,
            request_id=request_id,
            correlation_id=correlation_id,
        ):
            yield

    @contextlib.contextmanager
    def start_span(
        self,
        name: str,
        *,
        component: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> Iterator[Any]:
        """Start an OTEL span when tracing is enabled.

        Args:
            name: The span name to emit.
            component: The component label to attach to the span.
            attributes: Additional span attributes to merge into the span.

        Yields:
            The created span object, or ``None`` when tracing is disabled.
        """

        if not self.enabled or self.tracer is None:
            yield None
            return

        final_attributes = dict(attributes or {})
        final_attributes.setdefault(
            "pcg.component", component or current_component() or "unknown"
        )
        transport = current_transport()
        if transport:
            final_attributes.setdefault("pcg.transport", transport)
        request_id = current_request_id()
        if request_id:
            final_attributes.setdefault("pcg.request_id", request_id)
        correlation_id = current_correlation_id()
        if correlation_id:
            final_attributes.setdefault("pcg.correlation_id", correlation_id)
        with self.tracer.start_as_current_span(
            name,
            attributes=final_attributes,
        ) as span:
            yield span

    @contextlib.contextmanager
    def index_run(
        self,
        *,
        component: str | None = None,
        mode: str,
        source: str,
        repo_count: int,
        run_id: str | None = None,
        resume: bool = False,
    ) -> Iterator[Any]:
        """Track one repository indexing run.

        Args:
            component: The component label to record, if different from the
                runtime default.
            mode: The indexing mode being executed.
            source: The request source for the indexing run.
            repo_count: The number of repositories included in the run.

        Yields:
            ``None`` while the indexing run is active.
        """

        final_component = component or current_component() or self.component
        attrs = {
            "component": final_component,
            "mode": mode,
            "source": source,
        }
        key = tuple(sorted(attrs.items()))
        start = time.perf_counter()
        scope = _IndexRunScope(status="completed", finalization_status="pending")
        self._adjust_active_state(key, runs_delta=1, repos_delta=repo_count)
        with self.start_span(
            "pcg.index.run",
            component=final_component,
            attributes={
                "pcg.index.mode": mode,
                "pcg.index.source": source,
                "pcg.index.repo_count": repo_count,
                "pcg.index.resume": resume,
                **({"pcg.index.run_id": run_id} if run_id else {}),
            },
        ):
            try:
                yield scope
            except Exception:
                scope.status = "failed"
                scope.finalization_status = "failed"
                raise
            finally:
                self._adjust_active_state(key, runs_delta=-1, repos_delta=-repo_count)
                self.set_index_checkpoint_pending_repositories(
                    component=final_component,
                    mode=mode,
                    source=source,
                    pending_count=0,
                )
                duration = time.perf_counter() - start
                if self.index_runs_total is not None:
                    self.index_runs_total.add(
                        1,
                        {
                            **attrs,
                            "status": scope.status,
                            "resume": str(resume).lower(),
                            "finalization_status": scope.finalization_status,
                        },
                    )
                if self.index_run_duration is not None:
                    self.index_run_duration.record(
                        duration,
                        {
                            **attrs,
                            "status": scope.status,
                            "resume": str(resume).lower(),
                            "finalization_status": scope.finalization_status,
                        },
                    )

    def set_index_checkpoint_pending_repositories(
        self,
        *,
        component: str,
        mode: str,
        source: str,
        pending_count: int,
    ) -> None:
        """Set the observable pending-repository count for a checkpointed run."""

        key = tuple(
            sorted(
                {
                    "component": component,
                    "mode": mode,
                    "source": source,
                }.items()
            )
        )
        with self._lock:
            if pending_count <= 0:
                self._checkpoint_pending_repositories.pop(key, None)
            else:
                self._checkpoint_pending_repositories[key] = pending_count


@dataclass(slots=True)
class _IndexRunScope:
    """Mutable status returned to callers inside an index-run context."""

    status: str
    finalization_status: str
