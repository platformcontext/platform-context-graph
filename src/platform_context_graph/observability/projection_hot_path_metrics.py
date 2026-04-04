"""Telemetry helpers for projection and large-repository hot paths."""

from __future__ import annotations

from typing import Any


class RuntimeProjectionHotPathMetricsMixin:
    """Provide low-cardinality metrics for projection hot paths."""

    enabled: bool
    _fact_resolution_instruments: dict[str, Any]

    def record_resolution_file_projection_batch(
        self,
        *,
        component: str,
        file_count: int,
        duration_seconds: float,
    ) -> None:
        """Record one bounded file-projection batch."""

        if not self.enabled:
            return
        duration = self._fact_resolution_instruments.get(
            "resolution_file_projection_batch_duration"
        )
        files_total = self._fact_resolution_instruments.get(
            "resolution_file_projection_batch_files_total"
        )
        attrs = {"pcg.component": component}
        if duration is not None:
            duration.record(duration_seconds, attrs)
        if files_total is not None:
            files_total.add(file_count, attrs)

    def record_resolution_directory_flush_rows(
        self,
        *,
        component: str,
        row_kind: str,
        row_count: int,
    ) -> None:
        """Record how many directory or containment rows were flushed."""

        if not self.enabled or row_count <= 0:
            return
        rows_total = self._fact_resolution_instruments.get(
            "resolution_directory_flush_rows_total"
        )
        if rows_total is not None:
            rows_total.add(
                row_count,
                {
                    "pcg.component": component,
                    "pcg.row_kind": row_kind,
                },
            )

    def record_content_file_batch_upsert(
        self,
        *,
        component: str,
        outcome: str,
        row_count: int,
        duration_seconds: float,
    ) -> None:
        """Record a chunked file-content upsert batch."""

        if not self.enabled:
            return
        duration = self._fact_resolution_instruments.get(
            "content_file_batch_upsert_duration"
        )
        rows_total = self._fact_resolution_instruments.get(
            "content_file_batch_upsert_rows_total"
        )
        attrs = {
            "pcg.component": component,
            "pcg.outcome": outcome,
        }
        if duration is not None:
            duration.record(duration_seconds, attrs)
        if rows_total is not None:
            rows_total.add(row_count, attrs)

    def record_call_prefilter_known_name_scan(
        self,
        *,
        component: str,
        variant: str,
        duration_seconds: float,
    ) -> None:
        """Record one known-callable-name scan duration."""

        if not self.enabled:
            return
        duration = self._fact_resolution_instruments.get(
            "call_prefilter_known_name_scan_duration"
        )
        if duration is not None:
            duration.record(
                duration_seconds,
                {
                    "pcg.component": component,
                    "pcg.variant": variant,
                },
            )

    def record_call_prep_counts(
        self,
        *,
        component: str,
        language: str,
        inspected_count: int,
        capped_count: int,
    ) -> None:
        """Record inspected and capped raw call counts for one file."""

        if not self.enabled:
            return
        attrs = {
            "pcg.component": component,
            "pcg.language": language,
        }
        inspected_total = self._fact_resolution_instruments.get(
            "call_prep_calls_inspected_total"
        )
        capped_total = self._fact_resolution_instruments.get(
            "call_prep_calls_capped_total"
        )
        if inspected_total is not None and inspected_count > 0:
            inspected_total.add(inspected_count, attrs)
        if capped_total is not None and capped_count > 0:
            capped_total.add(capped_count, attrs)

    def record_inheritance_batch(
        self,
        *,
        component: str,
        mode: str,
        row_count: int,
        duration_seconds: float,
    ) -> None:
        """Record one inheritance flush batch."""

        if not self.enabled or row_count <= 0:
            return
        duration = self._fact_resolution_instruments.get("inheritance_batch_duration")
        rows_total = self._fact_resolution_instruments.get(
            "inheritance_batch_rows_total"
        )
        attrs = {
            "pcg.component": component,
            "pcg.mode": mode,
        }
        if duration is not None:
            duration.record(duration_seconds, attrs)
        if rows_total is not None:
            rows_total.add(row_count, attrs)


def setup_projection_hot_path_instruments(runtime: Any) -> None:
    """Register low-cardinality instruments for projection hot paths."""

    if not runtime.enabled or runtime.meter is None:
        return

    instruments = runtime._fact_resolution_instruments
    instruments["resolution_file_projection_batch_duration"] = (
        runtime.meter.create_histogram(
            "pcg_resolution_file_projection_batch_duration_seconds",
            unit="s",
        )
    )
    instruments["resolution_file_projection_batch_files_total"] = (
        runtime.meter.create_counter("pcg_resolution_file_projection_batch_files_total")
    )
    instruments["resolution_directory_flush_rows_total"] = runtime.meter.create_counter(
        "pcg_resolution_directory_flush_rows_total"
    )
    instruments["content_file_batch_upsert_duration"] = runtime.meter.create_histogram(
        "pcg_content_file_batch_upsert_duration_seconds",
        unit="s",
    )
    instruments["content_file_batch_upsert_rows_total"] = runtime.meter.create_counter(
        "pcg_content_file_batch_upsert_rows_total"
    )
    instruments["call_prefilter_known_name_scan_duration"] = (
        runtime.meter.create_histogram(
            "pcg_call_prefilter_known_name_scan_duration_seconds",
            unit="s",
        )
    )
    instruments["call_prep_calls_inspected_total"] = runtime.meter.create_counter(
        "pcg_call_prep_calls_inspected_total"
    )
    instruments["call_prep_calls_capped_total"] = runtime.meter.create_counter(
        "pcg_call_prep_calls_capped_total"
    )
    instruments["inheritance_batch_duration"] = runtime.meter.create_histogram(
        "pcg_inheritance_batch_duration_seconds",
        unit="s",
    )
    instruments["inheritance_batch_rows_total"] = runtime.meter.create_counter(
        "pcg_inheritance_batch_rows_total"
    )


__all__ = [
    "RuntimeProjectionHotPathMetricsMixin",
    "setup_projection_hot_path_instruments",
]
