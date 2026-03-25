from __future__ import annotations

from pathlib import Path

from platform_context_graph.tools.dependency_catalog import (
    dependency_roots_by_ecosystem,
    is_dependency_path,
)


def test_dependency_catalog_covers_supported_parser_capabilities() -> None:
    """Every supported parser capability should have an explicit dependency policy."""

    specs_dir = (
        Path(__file__).resolve().parents[3]
        / "src"
        / "platform_context_graph"
        / "tools"
        / "parser_capabilities"
        / "specs"
    )
    supported_ecosystems = {spec.stem for spec in specs_dir.glob("*.yaml")}

    catalog = dependency_roots_by_ecosystem()

    assert supported_ecosystems <= set(catalog)


def test_is_dependency_path_matches_built_in_vendor_roots() -> None:
    """Known vendored and tool-managed roots should match irrespective of depth."""

    assert is_dependency_path("/repo/vendor/acme/client.php")
    assert is_dependency_path("/repo/node_modules/react/index.js")
    assert is_dependency_path("/repo/.build/checkouts/swiftlib/Sources/main.swift")
    assert is_dependency_path("/repo/.terraform/modules/main.tf")
    assert not is_dependency_path("/repo/charts/payments/templates/deployment.yaml")
