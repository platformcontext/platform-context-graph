"""Regression tests for Go-owned parser capability test references."""

from __future__ import annotations

from pathlib import Path

import yaml

from platform_context_graph.parsers.capabilities import (
    validate_language_capability_specs,
)


def test_validate_language_capability_specs_accepts_go_unit_test_refs(
    tmp_path: Path,
) -> None:
    """Specs may point unit coverage at concrete Go `Test*` functions."""

    _write_spec_fixture(
        tmp_path,
        unit_test_body=(
            "package parser\n\n"
            "import \"testing\"\n\n"
            "func TestDemoCapability(t *testing.T) {}\n"
        ),
        unit_test_ref="go/internal/parser/demo_language_test.go::TestDemoCapability",
    )

    errors = validate_language_capability_specs(tmp_path)

    assert errors == []


def test_validate_language_capability_specs_rejects_missing_go_unit_test_refs(
    tmp_path: Path,
) -> None:
    """Go-owned test refs must still point at a concrete `Test*` function."""

    _write_spec_fixture(
        tmp_path,
        unit_test_body=(
            "package parser\n\n"
            "import \"testing\"\n\n"
            "func TestOtherCapability(t *testing.T) {}\n"
        ),
        unit_test_ref="go/internal/parser/demo_language_test.go::TestDemoCapability",
    )

    errors = validate_language_capability_specs(tmp_path)

    assert (
        "src/platform_context_graph/parsers/capabilities/specs/demo.yaml:functions: "
        "unit_test must reference a concrete test function "
        "go/internal/parser/demo_language_test.go::TestDemoCapability"
    ) in errors


def _write_spec_fixture(
    root: Path,
    *,
    unit_test_body: str,
    unit_test_ref: str,
) -> None:
    """Write a minimal parser capability fixture rooted at `root`."""

    spec_root = (
        root
        / "src"
        / "platform_context_graph"
        / "parsers"
        / "capabilities"
        / "specs"
    )
    spec_root.mkdir(parents=True)
    (root / "docs" / "docs" / "languages").mkdir(parents=True)
    (root / "tests" / "fixtures" / "ecosystems" / "demo").mkdir(parents=True)
    unit_test = root / "go" / "internal" / "parser" / "demo_language_test.go"
    unit_test.parent.mkdir(parents=True)
    unit_test.write_text(unit_test_body, encoding="utf-8")
    integration_test = root / "tests" / "integration" / "test_demo_graph.py"
    integration_test.parent.mkdir(parents=True)
    integration_test.write_text(
        (
            "class TestDemoGraph:\n"
            "    def test_demo_capability(self):\n"
            "        assert True\n"
        ),
        encoding="utf-8",
    )
    spec_root.joinpath("demo.yaml").write_text(
        yaml.safe_dump(
            {
                "language": "demo",
                "title": "Demo Parser",
                "family": "language",
                "parser": "DefaultEngine (demo)",
                "parser_entrypoint": "go/internal/parser/demo_language.go",
                "doc_path": "docs/docs/languages/demo.md",
                "fixture_repo": "tests/fixtures/ecosystems/demo",
                "unit_test_file": "go/internal/parser/demo_language_test.go",
                "integration_test_suite": "tests/integration/test_demo_graph.py::TestDemoGraph",
                "capabilities": [
                    {
                        "id": "functions",
                        "name": "Functions",
                        "status": "supported",
                        "extracted_bucket": "functions",
                        "required_fields": ["name", "line_number"],
                        "graph_surface": {"kind": "node", "target": "Function"},
                        "unit_test": unit_test_ref,
                        "integration_test": (
                            "tests/integration/test_demo_graph.py::"
                            "TestDemoGraph::test_demo_capability"
                        ),
                    }
                ],
                "known_limitations": [],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
