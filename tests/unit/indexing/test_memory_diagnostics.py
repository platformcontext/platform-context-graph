"""Unit tests for indexing memory diagnostics helpers."""

from __future__ import annotations

from pathlib import Path

import platform_context_graph.indexing.memory_diagnostics as memory_diagnostics


def test_read_memory_usage_sample_reads_process_and_cgroup_values(
    monkeypatch, tmp_path: Path
) -> None:
    """Memory diagnostics should parse Linux process and cgroup files."""

    proc_status = tmp_path / "status"
    proc_status.write_text("Name:\tpython\nVmRSS:\t  2048 kB\n", encoding="utf-8")
    cgroup_memory = tmp_path / "memory.current"
    cgroup_memory.write_text("4096\n", encoding="utf-8")
    monkeypatch.setattr(memory_diagnostics, "PROC_STATUS_PATH", proc_status)
    monkeypatch.setattr(
        memory_diagnostics,
        "CGROUP_MEMORY_CURRENT_PATH",
        cgroup_memory,
    )

    sample = memory_diagnostics.read_memory_usage_sample()

    assert sample.rss_bytes == 2048 * 1024
    assert sample.cgroup_memory_bytes == 4096


def test_log_memory_usage_skips_when_diagnostics_are_unavailable(
    monkeypatch, tmp_path: Path
) -> None:
    """Logging should stay quiet when Linux memory files are unavailable."""

    monkeypatch.setattr(memory_diagnostics, "PROC_STATUS_PATH", tmp_path / "missing")
    monkeypatch.setattr(
        memory_diagnostics,
        "CGROUP_MEMORY_CURRENT_PATH",
        tmp_path / "missing.current",
    )
    messages: list[str] = []

    memory_diagnostics.log_memory_usage(
        messages.append,
        context="After finalization stage inheritance",
    )

    assert messages == []


def test_log_memory_usage_formats_memory_values(monkeypatch) -> None:
    """Logging should emit a concise human-readable memory message."""

    monkeypatch.setattr(
        memory_diagnostics,
        "read_memory_usage_sample",
        lambda: memory_diagnostics.MemoryUsageSample(
            rss_bytes=3 * 1024 * 1024,
            cgroup_memory_bytes=5 * 1024 * 1024,
        ),
    )
    messages: list[str] = []

    memory_diagnostics.log_memory_usage(messages.append, context="Repository commit")

    assert messages == ["Repository commit: rss=3.0MiB cgroup_memory=5.0MiB"]
