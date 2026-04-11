"""Unit tests for parser capability specifications and rendering."""

from __future__ import annotations

from pathlib import Path

import yaml

from platform_context_graph.parsers.capabilities import (
    load_language_capability_specs,
    render_feature_matrix,
    render_language_doc,
    validate_language_capability_specs,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_load_language_capability_specs_exposes_known_languages() -> None:
    """Load canonical capability specs for code and IaC parsers."""

    specs = load_language_capability_specs(REPO_ROOT)
    names = {spec["language"] for spec in specs}

    assert "python" in names
    assert "sql" in names
    assert "typescript" in names
    assert "terraform" in names
    assert "kubernetes" in names


def test_validate_language_capability_specs_has_no_errors() -> None:
    """Capability specs must reference real fixtures, docs, and tests."""

    errors = validate_language_capability_specs(REPO_ROOT)

    assert errors == []


def test_validate_language_capability_specs_allows_generated_doc_targets(
    tmp_path: Path,
) -> None:
    """Specs should validate before the generated Markdown file exists."""

    spec_root = (
        tmp_path
        / "src"
        / "platform_context_graph"
        / "parsers"
        / "capabilities"
        / "specs"
    )
    spec_root.mkdir(parents=True)
    (tmp_path / "docs" / "docs" / "languages").mkdir(parents=True)
    (tmp_path / "tests" / "fixtures" / "ecosystems" / "demo").mkdir(parents=True)
    unit_test = tmp_path / "tests" / "unit" / "parsers" / "test_demo_parser.py"
    unit_test.parent.mkdir(parents=True)
    unit_test.write_text(
        "def test_demo_capability():\n    assert True\n", encoding="utf-8"
    )
    integration_test = tmp_path / "tests" / "integration" / "test_demo_graph.py"
    integration_test.parent.mkdir(parents=True)
    integration_test.write_text(
        (
            "class TestDemoGraph:\n"
            "    def test_demo_capability(self):\n"
            "        assert True\n"
        ),
        encoding="utf-8",
    )
    spec_path = spec_root / "demo.yaml"
    spec_path.write_text(
        yaml.safe_dump(
            {
                "language": "demo",
                "title": "Demo Parser",
                "family": "language",
                "parser": "DemoParser",
                "parser_entrypoint": "src/platform_context_graph/parsers/languages/demo.py",
                "doc_path": "docs/docs/languages/demo.md",
                "fixture_repo": "tests/fixtures/ecosystems/demo",
                "unit_test_file": "tests/unit/parsers/test_demo_parser.py",
                "integration_test_suite": "tests/integration/test_demo_graph.py::TestDemoGraph",
                "capabilities": [
                    {
                        "id": "functions",
                        "name": "Functions",
                        "status": "supported",
                        "extracted_bucket": "functions",
                        "required_fields": ["name", "line_number"],
                        "graph_surface": {"kind": "node", "target": "Function"},
                        "unit_test": "tests/unit/parsers/test_demo_parser.py::test_demo_capability",
                        "integration_test": "tests/integration/test_demo_graph.py::TestDemoGraph::test_demo_capability",
                    }
                ],
                "known_limitations": [],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    errors = validate_language_capability_specs(tmp_path)

    assert errors == []


def test_validate_language_capability_specs_rejects_fixture_refs(
    tmp_path: Path,
) -> None:
    """Capability refs must point to concrete test functions, not fixtures."""

    spec_root = (
        tmp_path
        / "src"
        / "platform_context_graph"
        / "parsers"
        / "capabilities"
        / "specs"
    )
    spec_root.mkdir(parents=True)
    (tmp_path / "docs" / "docs" / "languages").mkdir(parents=True)
    (tmp_path / "tests" / "fixtures" / "ecosystems" / "demo").mkdir(parents=True)
    unit_test = tmp_path / "tests" / "unit" / "parsers" / "test_demo_parser.py"
    unit_test.parent.mkdir(parents=True)
    unit_test.write_text(
        (
            "import pytest\n\n"
            "@pytest.fixture\n"
            "def demo_parser():\n"
            "    return object()\n\n"
            "def test_demo_capability(demo_parser):\n"
            "    assert demo_parser is not None\n"
        ),
        encoding="utf-8",
    )
    integration_test = tmp_path / "tests" / "integration" / "test_demo_graph.py"
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
                "parser": "DemoParser",
                "parser_entrypoint": "src/platform_context_graph/parsers/languages/demo.py",
                "doc_path": "docs/docs/languages/demo.md",
                "fixture_repo": "tests/fixtures/ecosystems/demo",
                "unit_test_file": "tests/unit/parsers/test_demo_parser.py",
                "integration_test_suite": "tests/integration/test_demo_graph.py::TestDemoGraph",
                "capabilities": [
                    {
                        "id": "functions",
                        "name": "Functions",
                        "status": "supported",
                        "extracted_bucket": "functions",
                        "required_fields": ["name", "line_number"],
                        "graph_surface": {"kind": "node", "target": "Function"},
                        "unit_test": "tests/unit/parsers/test_demo_parser.py::demo_parser",
                        "integration_test": "tests/integration/test_demo_graph.py::TestDemoGraph::test_demo_capability",
                    }
                ],
                "known_limitations": [],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    errors = validate_language_capability_specs(tmp_path)

    assert (
        "src/platform_context_graph/parsers/capabilities/specs/demo.yaml:functions: "
        "unit_test must reference a concrete test function tests/unit/parsers/test_demo_parser.py::demo_parser"
    ) in errors


def test_validate_language_capability_specs_rejects_supported_capability_without_surface(
    tmp_path: Path,
) -> None:
    """Supported capabilities must declare a real graph surface target."""

    spec_root = (
        tmp_path
        / "src"
        / "platform_context_graph"
        / "parsers"
        / "capabilities"
        / "specs"
    )
    spec_root.mkdir(parents=True)
    (tmp_path / "docs" / "docs" / "languages").mkdir(parents=True)
    (tmp_path / "tests" / "fixtures" / "ecosystems" / "demo").mkdir(parents=True)
    unit_test = tmp_path / "tests" / "unit" / "parsers" / "test_demo_parser.py"
    unit_test.parent.mkdir(parents=True)
    unit_test.write_text(
        "def test_demo_capability():\n    assert True\n", encoding="utf-8"
    )
    integration_test = tmp_path / "tests" / "integration" / "test_demo_graph.py"
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
                "parser": "DemoParser",
                "parser_entrypoint": "src/platform_context_graph/parsers/languages/demo.py",
                "doc_path": "docs/docs/languages/demo.md",
                "fixture_repo": "tests/fixtures/ecosystems/demo",
                "unit_test_file": "tests/unit/parsers/test_demo_parser.py",
                "integration_test_suite": "tests/integration/test_demo_graph.py::TestDemoGraph",
                "capabilities": [
                    {
                        "id": "functions",
                        "name": "Functions",
                        "status": "supported",
                        "extracted_bucket": "functions",
                        "required_fields": ["name", "line_number"],
                        "graph_surface": {},
                        "unit_test": "tests/unit/parsers/test_demo_parser.py::test_demo_capability",
                        "integration_test": "tests/integration/test_demo_graph.py::TestDemoGraph::test_demo_capability",
                    }
                ],
                "known_limitations": [],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    errors = validate_language_capability_specs(tmp_path)

    assert (
        "src/platform_context_graph/parsers/capabilities/specs/demo.yaml:functions: "
        "supported capability must declare graph surface"
    ) in errors


def test_validate_language_capability_specs_reports_missing_language_key(
    tmp_path: Path,
) -> None:
    """Malformed specs should produce validation errors instead of crashing."""

    spec_root = (
        tmp_path
        / "src"
        / "platform_context_graph"
        / "parsers"
        / "capabilities"
        / "specs"
    )
    spec_root.mkdir(parents=True)
    (tmp_path / "docs" / "docs" / "languages").mkdir(parents=True)
    (tmp_path / "tests" / "fixtures" / "ecosystems" / "demo").mkdir(parents=True)
    unit_test = tmp_path / "tests" / "unit" / "parsers" / "test_demo_parser.py"
    unit_test.parent.mkdir(parents=True)
    unit_test.write_text(
        "def test_demo_capability():\n    assert True\n", encoding="utf-8"
    )
    integration_test = tmp_path / "tests" / "integration" / "test_demo_graph.py"
    integration_test.parent.mkdir(parents=True)
    integration_test.write_text(
        (
            "class TestDemoGraph:\n"
            "    def test_demo_capability(self):\n"
            "        assert True\n"
        ),
        encoding="utf-8",
    )
    spec_root.joinpath("broken.yaml").write_text(
        yaml.safe_dump(
            {
                "title": "Broken Parser",
                "family": "language",
                "parser": "BrokenParser",
                "parser_entrypoint": "src/platform_context_graph/parsers/languages/broken.py",
                "doc_path": "docs/docs/languages/broken.md",
                "fixture_repo": "tests/fixtures/ecosystems/demo",
                "unit_test_file": "tests/unit/parsers/test_demo_parser.py",
                "integration_test_suite": "tests/integration/test_demo_graph.py::TestDemoGraph",
                "capabilities": [
                    {
                        "id": "functions",
                        "name": "Functions",
                        "status": "supported",
                        "extracted_bucket": "functions",
                        "required_fields": ["name", "line_number"],
                        "graph_surface": {"kind": "node", "target": "Function"},
                        "unit_test": "tests/unit/parsers/test_demo_parser.py::test_demo_capability",
                        "integration_test": "tests/integration/test_demo_graph.py::TestDemoGraph::test_demo_capability",
                    }
                ],
                "known_limitations": [],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    errors = validate_language_capability_specs(tmp_path)

    assert (
        "src/platform_context_graph/parsers/capabilities/specs/broken.yaml: "
        "missing keys ['language']"
    ) in errors


def test_render_language_doc_contains_generated_contract_sections() -> None:
    """Rendered language docs must expose capabilities and test coverage."""

    specs = load_language_capability_specs(REPO_ROOT)
    python_spec = next(spec for spec in specs if spec["language"] == "python")

    rendered = render_language_doc(python_spec)

    assert "This file is auto-generated. Do not edit manually." in rendered
    assert "# Python Parser" in rendered
    assert "## Capability Checklist" in rendered
    assert "## Known Limitations" in rendered
    assert "unit_test" not in rendered
    assert "Functions" in rendered


def test_render_feature_matrix_includes_capability_coverage_columns() -> None:
    """Rendered feature matrix must summarize support and coverage per parser."""

    specs = load_language_capability_specs(REPO_ROOT)

    rendered = render_feature_matrix(specs)

    assert "This file is auto-generated. Do not edit manually." in rendered
    assert "# Parser Feature Matrix" in rendered
    assert "Unit Coverage" in rendered
    assert "Integration Coverage" in rendered
    assert "| Python |" in rendered


def test_render_feature_matrix_counts_supported_capabilities_only() -> None:
    """Coverage counts should not treat partial capabilities as fully covered."""

    rendered = render_feature_matrix(
        [
            {
                "language": "demo",
                "title": "Demo Parser",
                "family": "language",
                "parser": "DemoParser",
                "fixture_repo": "tests/fixtures/ecosystems/demo/",
                "capabilities": [
                    {
                        "id": "functions",
                        "name": "Functions",
                        "status": "supported",
                        "extracted_bucket": "functions",
                        "required_fields": ["name", "line_number"],
                        "graph_surface": {"kind": "node", "target": "Function"},
                        "unit_test": "tests/unit/parsers/test_demo_parser.py::test_demo_functions",
                        "integration_test": "tests/integration/test_demo_graph.py::TestDemoGraph::test_demo_functions",
                    },
                    {
                        "id": "type-aliases",
                        "name": "Type aliases",
                        "status": "partial",
                        "extracted_bucket": "type_aliases",
                        "required_fields": ["name", "line_number"],
                        "graph_surface": {"kind": "none", "target": "not_persisted"},
                        "unit_test": "tests/unit/parsers/test_demo_parser.py::test_demo_type_aliases",
                        "integration_test": "tests/integration/test_demo_graph.py::TestDemoGraph::test_demo_type_aliases",
                        "rationale": "Not persisted.",
                    },
                ],
            }
        ]
    )

    assert (
        "| Demo | `DemoParser` | Y | - | - | - | - | - | - | - | - | - | 1/1 | 1/1 | `tests/fixtures/ecosystems/demo/` |"
        in rendered
    )


def test_render_feature_matrix_keeps_structs_out_of_classes_column() -> None:
    """Shared storage buckets should not imply support for another construct."""

    rendered = render_feature_matrix(
        [
            {
                "language": "demo",
                "title": "Demo Parser",
                "family": "language",
                "parser": "DemoParser",
                "fixture_repo": "tests/fixtures/ecosystems/demo/",
                "capabilities": [
                    {
                        "id": "structs",
                        "name": "Structs",
                        "status": "supported",
                        "extracted_bucket": "classes",
                        "required_fields": ["name", "line_number"],
                        "graph_surface": {"kind": "node", "target": "Class"},
                        "unit_test": "tests/unit/parsers/test_demo_parser.py::test_demo_structs",
                        "integration_test": "tests/integration/test_demo_graph.py::TestDemoGraph::test_demo_structs",
                    },
                    {
                        "id": "enums",
                        "name": "Enums",
                        "status": "supported",
                        "extracted_bucket": "classes",
                        "required_fields": ["name", "line_number"],
                        "graph_surface": {"kind": "node", "target": "Class"},
                        "unit_test": "tests/unit/parsers/test_demo_parser.py::test_demo_enums",
                        "integration_test": "tests/integration/test_demo_graph.py::TestDemoGraph::test_demo_enums",
                    },
                ],
            }
        ]
    )

    assert (
        "| Demo | `DemoParser` | - | - | - | - | - | - | - | Y | Y | - | 2/2 | 2/2 | `tests/fixtures/ecosystems/demo/` |"
        in rendered
    )
