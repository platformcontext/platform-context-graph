"""Tests for process-pool parse worker initialization."""

from __future__ import annotations

from types import SimpleNamespace

from platform_context_graph.collectors.git import parse_worker


def test_init_parse_worker_uses_worker_safe_observability(
    monkeypatch,
) -> None:
    """Parse workers should skip Prometheus listener setup."""

    parse_worker._WORKER_BUILDER = None
    observed_kwargs: list[dict[str, object]] = []

    monkeypatch.setattr(
        parse_worker,
        "initialize_observability",
        lambda **kwargs: observed_kwargs.append(kwargs) or SimpleNamespace(),
    )
    monkeypatch.setattr(
        parse_worker,
        "build_parser_registry",
        lambda _get_config_value: {"python": object()},
    )

    parse_worker.init_parse_worker()

    assert observed_kwargs == [
        {
            "component": "repository",
            "allow_prometheus_scrape": False,
        }
    ]
    assert parse_worker._WORKER_BUILDER is not None
