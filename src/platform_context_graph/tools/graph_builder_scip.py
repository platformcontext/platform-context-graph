"""SCIP-specific indexing helpers for ``GraphBuilder``."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from .scip_indexer import ScipIndexParser, ScipIndexer


def _supplement_scip_file_data(
    builder: Any,
    file_path: Path,
    file_data: dict[str, Any],
    is_dependency: bool,
    *,
    debug_log_fn: Any,
) -> None:
    """Fill SCIP results with Tree-sitter source, complexity, and imports.

    Args:
        builder: ``GraphBuilder`` facade instance.
        file_path: File being supplemented.
        file_data: Parsed SCIP payload for the file.
        is_dependency: Whether the file belongs to a dependency repository.
        debug_log_fn: Debug logger callable.
    """
    if not file_path.exists() or file_path.suffix not in builder.parsers:
        return

    try:
        ts_parser = builder.parsers[file_path.suffix]
        ts_data = ts_parser.parse(file_path, is_dependency, index_source=True)
        if "error" in ts_data:
            return

        ts_funcs = {func["name"]: func for func in ts_data.get("functions", [])}
        for func in file_data.get("functions", []):
            ts_func = ts_funcs.get(func["name"])
            if ts_func:
                func.update(
                    {
                        "source": ts_func.get("source"),
                        "cyclomatic_complexity": ts_func.get(
                            "cyclomatic_complexity", 1
                        ),
                        "decorators": ts_func.get("decorators", []),
                    }
                )

        ts_classes = {cls["name"]: cls for cls in ts_data.get("classes", [])}
        for cls in file_data.get("classes", []):
            ts_class = ts_classes.get(cls["name"])
            if ts_class:
                cls["bases"] = ts_class.get("bases", [])

        file_data["imports"] = ts_data.get("imports", [])
        file_data["variables"] = ts_data.get("variables", [])
    except Exception as exc:
        debug_log_fn(f"Tree-sitter supplement failed for {file_path}: {exc}")


def _write_scip_call_edges(builder: Any, files_data: dict[str, Any]) -> None:
    """Persist precise SCIP-derived ``CALLS`` relationships.

    Args:
        builder: ``GraphBuilder`` facade instance.
        files_data: Parsed SCIP payload keyed by absolute file path.
    """
    with builder.driver.session() as session:
        for file_data in files_data.values():
            for edge in file_data.get("function_calls_scip", []):
                try:
                    session.run(
                        """
                        MATCH (caller:Function {name: $caller_name, path: $caller_file, line_number: $caller_line})
                        MATCH (callee:Function {name: $callee_name, path: $callee_file, line_number: $callee_line})
                        MERGE (caller)-[:CALLS {line_number: $ref_line, source: 'scip'}]->(callee)
                    """,
                        caller_name=builder._name_from_symbol(edge["caller_symbol"]),
                        caller_file=edge["caller_file"],
                        caller_line=edge["caller_line"],
                        callee_name=edge["callee_name"],
                        callee_file=edge["callee_file"],
                        callee_line=edge["callee_line"],
                        ref_line=edge["ref_line"],
                    )
                except Exception:
                    pass


async def build_graph_from_scip(
    builder: Any,
    path: Path,
    is_dependency: bool,
    job_id: str | None,
    lang: str,
    *,
    asyncio_module: Any,
    datetime_cls: Any,
    debug_log_fn: Any,
    error_logger_fn: Any,
    warning_logger_fn: Any,
    job_status_enum: Any,
) -> None:
    """Index a repository using SCIP output plus Tree-sitter supplementation.

    Args:
        builder: ``GraphBuilder`` facade instance.
        path: Repository or project path to index.
        is_dependency: Whether the path is being indexed as a dependency.
        job_id: Optional background job identifier.
        lang: SCIP language identifier.
        asyncio_module: Asyncio module used for cooperative yielding.
        datetime_cls: ``datetime`` class used for timestamps.
        debug_log_fn: Debug logger callable.
        error_logger_fn: Error logger callable.
        warning_logger_fn: Warning logger callable.
        job_status_enum: Job status enum with ``RUNNING``, ``COMPLETED``, and ``FAILED``.
    """
    if job_id:
        builder.job_manager.update_job(job_id, status=job_status_enum.RUNNING)

    builder.add_repository_to_graph(path, is_dependency)
    repo_name = path.name

    try:
        with tempfile.TemporaryDirectory(prefix="pcg_scip_") as tmpdir:
            scip_file = ScipIndexer().run(path, lang, Path(tmpdir))
            if not scip_file:
                warning_logger_fn(
                    f"SCIP indexer produced no output for {path}. Falling back to Tree-sitter."
                )
                raise RuntimeError(
                    "SCIP produced no index — triggering Tree-sitter fallback"
                )

            scip_data = ScipIndexParser().parse(scip_file, path)

        if not scip_data:
            raise RuntimeError("SCIP parse returned empty result")

        files_data = scip_data.get("files", {})
        file_paths = [
            Path(file_path)
            for file_path in files_data.keys()
            if Path(file_path).exists()
        ]
        imports_map = builder._pre_scan_for_imports(file_paths)

        if job_id:
            builder.job_manager.update_job(job_id, total_files=len(files_data))

        processed = 0
        for abs_path_str, file_data in files_data.items():
            file_data["repo_path"] = str(path.resolve())
            if job_id:
                builder.job_manager.update_job(job_id, current_file=abs_path_str)

            _supplement_scip_file_data(
                builder,
                Path(abs_path_str),
                file_data,
                is_dependency,
                debug_log_fn=debug_log_fn,
            )
            builder.add_file_to_graph(file_data, repo_name, imports_map)

            processed += 1
            if job_id:
                builder.job_manager.update_job(job_id, processed_files=processed)
            await asyncio_module.sleep(0.01)

        builder._create_all_inheritance_links(list(files_data.values()), imports_map)
        _write_scip_call_edges(builder, files_data)

        if job_id:
            builder.job_manager.update_job(
                job_id,
                status=job_status_enum.COMPLETED,
                end_time=datetime_cls.now(),
            )
    except RuntimeError as exc:
        warning_logger_fn(f"SCIP path failed ({exc}), re-running with Tree-sitter...")
        if job_id:
            builder.job_manager.update_job(job_id, status=job_status_enum.RUNNING)
        raise
    except Exception as exc:
        error_logger_fn(f"SCIP indexing failed for {path}: {exc}")
        if job_id:
            builder.job_manager.update_job(
                job_id,
                status=job_status_enum.FAILED,
                end_time=datetime_cls.now(),
                errors=[str(exc)],
            )


__all__ = ["build_graph_from_scip"]
