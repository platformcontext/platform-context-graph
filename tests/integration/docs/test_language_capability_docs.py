from __future__ import annotations

from pathlib import Path

import pytest

from platform_context_graph.parsers.capabilities import (
    expected_generated_language_docs,
    load_language_capability_specs,
    render_feature_matrix,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
DOCS_ROOT = REPO_ROOT / "docs" / "docs" / "languages"


def test_generated_language_docs_are_in_sync_with_specs() -> None:
    """Tracked language docs must match the generated output exactly."""

    expected_docs = expected_generated_language_docs(REPO_ROOT)

    for relative_path, expected_content in expected_docs.items():
        actual_path = REPO_ROOT / relative_path
        assert actual_path.exists(), f"missing generated doc: {relative_path}"
        assert actual_path.read_text(encoding="utf-8") == expected_content


def test_generated_feature_matrix_is_in_sync_with_specs() -> None:
    """The tracked parser feature matrix must be generated from the same specs."""

    expected_docs = expected_generated_language_docs(REPO_ROOT)
    matrix_path = DOCS_ROOT / "feature-matrix.md"

    assert (
        matrix_path.read_text(encoding="utf-8")
        == expected_docs["docs/docs/languages/feature-matrix.md"]
    )


def test_generated_support_maturity_matrix_is_in_sync_with_specs() -> None:
    """The tracked support-maturity matrix must match generated spec output."""

    expected_docs = expected_generated_language_docs(REPO_ROOT)
    matrix_path = DOCS_ROOT / "support-maturity.md"

    assert (
        matrix_path.read_text(encoding="utf-8")
        == expected_docs["docs/docs/languages/support-maturity.md"]
    )


@pytest.mark.parametrize(
    ("language", "entrypoint", "unit_test_file"),
    [
        (
            "python",
            "go/internal/parser/python_language.go",
            "go/internal/parser/engine_python_semantics_test.go",
        ),
        (
            "javascript",
            "go/internal/parser/javascript_language.go",
            "go/internal/parser/engine_javascript_semantics_test.go",
        ),
        (
            "typescript",
            "go/internal/parser/javascript_language.go",
            "go/internal/parser/engine_javascript_semantics_test.go",
        ),
        (
            "typescriptjsx",
            "go/internal/parser/javascript_language.go",
            "go/internal/parser/engine_javascript_semantics_test.go",
        ),
        ("c", "go/internal/parser/c_language.go", "go/internal/parser/engine_systems_test.go"),
        ("argocd", "go/internal/parser/yaml_language.go", "go/internal/parser/engine_yaml_semantics_test.go"),
        ("cloudformation", "go/internal/parser/yaml_language.go", "go/internal/parser/engine_yaml_semantics_test.go"),
        ("crossplane", "go/internal/parser/yaml_language.go", "go/internal/parser/engine_yaml_semantics_test.go"),
        ("helm", "go/internal/parser/yaml_language.go", "go/internal/parser/engine_yaml_semantics_test.go"),
        ("kubernetes", "go/internal/parser/yaml_language.go", "go/internal/parser/engine_infra_test.go"),
        ("kustomize", "go/internal/parser/yaml_language.go", "go/internal/parser/engine_yaml_semantics_test.go"),
        ("terraform", "go/internal/parser/hcl_language.go", "go/internal/parser/engine_infra_test.go"),
        ("terragrunt", "go/internal/parser/hcl_language.go", "go/internal/parser/engine_infra_test.go"),
        (
            "elixir",
            "go/internal/parser/elixir_dart_language.go",
            "go/internal/parser/engine_elixir_semantics_test.go",
        ),
        ("php", "go/internal/parser/php_language.go", "go/internal/parser/php_language_test.go"),
        ("cpp", "go/internal/parser/cpp_language.go", "go/internal/parser/engine_systems_test.go"),
        (
            "dart",
            "go/internal/parser/elixir_dart_language.go",
            "go/internal/parser/engine_long_tail_test.go",
        ),
        ("go", "go/internal/parser/go_language.go", "go/internal/parser/engine_test.go"),
        (
            "haskell",
            "go/internal/parser/perl_haskell_language.go",
            "go/internal/parser/engine_long_tail_test.go",
        ),
        ("java", "go/internal/parser/java_language.go", "go/internal/parser/engine_managed_oo_test.go"),
        ("json", "go/internal/parser/json_language.go", "go/internal/parser/json_language_test.go"),
        (
            "kotlin",
            "go/internal/parser/kotlin_language.go",
            "go/internal/parser/engine_managed_oo_test.go",
        ),
        ("ruby", "go/internal/parser/ruby_language.go", "go/internal/parser/engine_ruby_semantics_test.go"),
        ("sql", "go/internal/parser/sql_language.go", "go/internal/parser/engine_sql_test.go"),
        ("swift", "go/internal/parser/swift_language.go", "go/internal/parser/engine_swift_semantics_test.go"),
    ],
)
def test_parser_family_cutover_specs_are_go_owned(
    language: str, entrypoint: str, unit_test_file: str
) -> None:
    """The first parser-family cutover cluster must point at Go ownership."""

    specs = {
        spec["language"]: spec for spec in load_language_capability_specs(REPO_ROOT)
    }
    spec = specs[language]

    assert spec["parser_entrypoint"] == entrypoint
    assert spec["unit_test_file"] == unit_test_file
