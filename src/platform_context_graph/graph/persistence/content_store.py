"""Content-store dual-write helpers for graph persistence."""

from __future__ import annotations

from typing import Any, Callable

from ...content.ingest import prepare_content_entries
from ...content.state import get_postgres_content_provider
from ...observability import get_observability
from ...utils.debug_log import emit_log_call

ContentProviderGetter = Callable[[], Any]
PrepareEntriesFn = Callable[[dict[str, Any], dict[str, Any]], tuple[Any, list[Any]]]


def content_dual_write(
    file_data: dict[str, Any],
    file_name: str,
    repository: dict[str, Any],
    warning_logger_fn: Any,
    *,
    get_content_provider: ContentProviderGetter = get_postgres_content_provider,
    prepare_entries: PrepareEntriesFn = prepare_content_entries,
) -> None:
    """Attempt a content-store dual-write for one file."""

    content_provider = get_content_provider()
    if content_provider is None or not content_provider.enabled:
        return
    telemetry = get_observability()
    try:
        with telemetry.start_span(
            "pcg.content.dual_write",
            attributes={
                "pcg.content.repo_id": repository.get("id"),
                "pcg.content.relative_path": str(file_data.get("path", file_name)),
            },
        ):
            file_entry, entity_entries = prepare_entries(
                file_data=file_data,
                repository=repository,
            )
            if file_entry is not None:
                content_provider.upsert_file(file_entry)
            if entity_entries:
                content_provider.upsert_entities(entity_entries)
    except Exception as exc:  # pragma: no cover
        emit_log_call(
            warning_logger_fn,
            f"Content store dual-write failed for {file_name}: {exc}",
            event_name="content.dual_write.failed",
            extra_keys={
                "file_name": file_name,
                "repo_id": repository.get("id"),
            },
            exc_info=exc,
        )


def content_dual_write_batch(
    file_data_list: list[dict[str, Any]],
    repository: dict[str, Any],
    warning_logger_fn: Any,
    *,
    content_batch_size: int | None = None,
    get_content_provider: ContentProviderGetter = get_postgres_content_provider,
    prepare_entries: PrepareEntriesFn = prepare_content_entries,
) -> None:
    """Batch content-store dual-writes for multiple files in one round-trip."""

    content_provider = get_content_provider()
    if content_provider is None or not content_provider.enabled:
        return
    telemetry = get_observability()
    try:
        with telemetry.start_span(
            "pcg.content.dual_write_batch",
            attributes={
                "pcg.content.repo_id": repository.get("id"),
                "pcg.content.file_count": len(file_data_list),
            },
        ):
            file_entries = []
            entity_entries = []
            for file_data in file_data_list:
                file_entry, entities = prepare_entries(
                    file_data=file_data,
                    repository=repository,
                )
                if file_entry is not None:
                    file_entries.append(file_entry)
                entity_entries.extend(entities)
            if file_entries:
                content_provider.upsert_file_batch(file_entries)
            if entity_entries:
                content_provider.upsert_entities_batch(
                    entity_entries,
                    entity_batch_size=content_batch_size,
                )
    except Exception as exc:  # pragma: no cover
        emit_log_call(
            warning_logger_fn,
            f"Content store batch dual-write failed for {len(file_data_list)} files: {exc}",
            event_name="content.dual_write_batch.failed",
            extra_keys={
                "file_count": len(file_data_list),
                "repo_id": repository.get("id"),
            },
            exc_info=exc,
        )


__all__ = ["content_dual_write", "content_dual_write_batch"]
