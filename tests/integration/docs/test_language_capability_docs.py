from __future__ import annotations

from pathlib import Path

from platform_context_graph.parsers.capabilities import (
    expected_generated_language_docs,
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
