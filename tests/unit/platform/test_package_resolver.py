"""Unit tests for canonical package resolution dispatch."""

from platform_context_graph.platform import package_resolver


def test_get_local_package_path_dispatches_to_language_specific_finder(
    monkeypatch,
) -> None:
    """Dispatch package resolution through the registered language finder."""

    monkeypatch.setattr(
        package_resolver,
        "_get_python_package_path",
        lambda package_name: f"/resolved/{package_name}",
    )

    assert (
        package_resolver.get_local_package_path("requests", "python")
        == "/resolved/requests"
    )


def test_get_local_package_path_returns_none_for_unknown_language() -> None:
    """Return ``None`` for unsupported ecosystems."""

    assert package_resolver.get_local_package_path("requests", "unknown") is None
