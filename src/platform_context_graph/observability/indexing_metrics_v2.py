"""V2 indexing metric helpers with sub-commit and resolution instruments."""

from __future__ import annotations

from typing import Any

from .indexing_metrics import RuntimeIndexMetricsMixin


class RuntimeIndexMetricsV2Mixin(RuntimeIndexMetricsMixin):
    """Extend indexing metrics with sub-commit histograms and resolution counters.

    New instruments added in this mixin:

    - ``index_repo_graph_write_duration``: per-repo graph write histogram.
    - ``index_repo_content_write_duration``: per-repo content write histogram.
    - ``index_fallback_resolution_total``: fallback resolution attempt counter.
    - ``index_ambiguous_resolution_total``: ambiguous resolution counter.

    Additionally, the inherited V1 methods gain an optional ``repo_class``
    attribute dimension so that observability dashboards can aggregate by
    repository size class.
    """

    index_repo_graph_write_duration: Any
    index_repo_content_write_duration: Any
    index_fallback_resolution_total: Any
    index_ambiguous_resolution_total: Any

    # ------------------------------------------------------------------
    # Overrides of V1 methods to add repo_class dimension
    # ------------------------------------------------------------------

    def record_index_repositories(
        self,
        *,
        component: str,
        phase: str,
        count: int,
        mode: str,
        source: str,
        repo_class: str | None = None,
    ) -> None:
        """Record repository counts with optional repo_class dimension."""
        if not self.enabled or self.index_repositories_total is None:
            return
        attrs: dict[str, str] = {
            "component": component,
            "phase": phase,
            "mode": mode,
            "source": source,
        }
        if repo_class is not None:
            attrs["repo_class"] = repo_class
        self.index_repositories_total.add(count, attrs)

    def record_index_checkpoint(
        self,
        *,
        component: str,
        mode: str,
        source: str,
        operation: str,
        status: str,
        repo_class: str | None = None,
    ) -> None:
        """Record checkpoint event with optional repo_class dimension."""
        if not self.enabled or self.index_checkpoints_total is None:
            return
        attrs: dict[str, str] = {
            "component": component,
            "mode": mode,
            "source": source,
            "operation": operation,
            "status": status,
        }
        if repo_class is not None:
            attrs["repo_class"] = repo_class
        self.index_checkpoints_total.add(1, attrs)

    def record_index_repository_duration(
        self,
        *,
        component: str,
        mode: str,
        source: str,
        status: str,
        duration_seconds: float,
        repo_class: str | None = None,
    ) -> None:
        """Record repository duration with optional repo_class dimension."""
        if not self.enabled or self.index_repository_duration is None:
            return
        attrs: dict[str, str | float] = {
            "component": component,
            "mode": mode,
            "source": source,
            "status": status,
        }
        if repo_class is not None:
            attrs["repo_class"] = repo_class
        self.index_repository_duration.record(duration_seconds, attrs)

    def record_index_stage_duration(
        self,
        *,
        component: str,
        mode: str,
        source: str,
        stage: str,
        duration_seconds: float,
        parse_strategy: str,
        parse_workers: int,
        repo_class: str | None = None,
    ) -> None:
        """Record stage duration with optional repo_class dimension."""
        if not self.enabled or self.index_stage_duration is None:
            return
        attrs: dict[str, str] = {
            "component": component,
            "mode": mode,
            "source": source,
            "stage": stage,
            "parse_strategy": parse_strategy,
            "parse_workers": str(parse_workers),
        }
        if repo_class is not None:
            attrs["repo_class"] = repo_class
        self.index_stage_duration.record(duration_seconds, attrs)

    # ------------------------------------------------------------------
    # New V2 instrument methods
    # ------------------------------------------------------------------

    def record_repo_graph_write_duration(
        self,
        *,
        component: str,
        mode: str,
        source: str,
        repo_class: str,
        duration_seconds: float,
    ) -> None:
        """Record per-repository graph write duration.

        Args:
            component: The component label for the metric.
            mode: The indexing mode.
            source: The request source.
            repo_class: The repository size classification.
            duration_seconds: Total graph write duration for this repo.
        """
        if not self.enabled or self.index_repo_graph_write_duration is None:
            return
        self.index_repo_graph_write_duration.record(
            duration_seconds,
            {
                "component": component,
                "mode": mode,
                "source": source,
                "repo_class": repo_class,
            },
        )

    def record_repo_content_write_duration(
        self,
        *,
        component: str,
        mode: str,
        source: str,
        repo_class: str,
        duration_seconds: float,
    ) -> None:
        """Record per-repository content write duration.

        Args:
            component: The component label for the metric.
            mode: The indexing mode.
            source: The request source.
            repo_class: The repository size classification.
            duration_seconds: Total content write duration for this repo.
        """
        if not self.enabled or self.index_repo_content_write_duration is None:
            return
        self.index_repo_content_write_duration.record(
            duration_seconds,
            {
                "component": component,
                "mode": mode,
                "source": source,
                "repo_class": repo_class,
            },
        )

    def record_fallback_resolution(
        self,
        *,
        component: str,
        mode: str,
        source: str,
        repo_class: str,
        count: int,
    ) -> None:
        """Record fallback resolution attempts for a repository.

        Args:
            component: The component label for the metric.
            mode: The indexing mode.
            source: The request source.
            repo_class: The repository size classification.
            count: Number of fallback resolution attempts.
        """
        if not self.enabled or self.index_fallback_resolution_total is None:
            return
        self.index_fallback_resolution_total.add(
            count,
            {
                "component": component,
                "mode": mode,
                "source": source,
                "repo_class": repo_class,
            },
        )

    def record_ambiguous_resolution(
        self,
        *,
        component: str,
        mode: str,
        source: str,
        repo_class: str,
        count: int,
    ) -> None:
        """Record ambiguous resolution outcomes for a repository.

        Args:
            component: The component label for the metric.
            mode: The indexing mode.
            source: The request source.
            repo_class: The repository size classification.
            count: Number of ambiguous resolution outcomes.
        """
        if not self.enabled or self.index_ambiguous_resolution_total is None:
            return
        self.index_ambiguous_resolution_total.add(
            count,
            {
                "component": component,
                "mode": mode,
                "source": source,
                "repo_class": repo_class,
            },
        )


__all__ = [
    "RuntimeIndexMetricsV2Mixin",
]
