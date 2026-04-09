"""Unit tests for parser support-maturity rendering."""

from __future__ import annotations

from pathlib import Path

from platform_context_graph.parsers.capabilities import (
    load_language_capability_specs,
    render_language_doc,
    render_support_maturity_matrix,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_render_language_doc_includes_support_maturity_when_declared() -> None:
    """Generated language docs should include support maturity metadata."""

    specs = load_language_capability_specs(REPO_ROOT)
    spec = next(spec for spec in specs if spec["language"] == "typescriptjsx")

    rendered = render_language_doc(spec)

    assert "## Support Maturity" in rendered
    assert "- Grammar routing: `supported`" in rendered
    assert "- Framework packs: `react-base`, `nextjs-app-router-base`" in rendered


def test_render_support_maturity_matrix_shows_declared_and_unassessed_rows() -> None:
    """Support matrix should show declared maturity and blanks for unassessed rows."""

    rendered = render_support_maturity_matrix(
        [
            {
                "language": "demo",
                "title": "Demo Parser",
                "family": "language",
                "parser": "DemoParser",
                "fixture_repo": "tests/fixtures/ecosystems/demo/",
                "capabilities": [],
                "support_maturity": {
                    "grammar_routing": "supported",
                    "normalization": "supported",
                    "framework_packs": "partial",
                    "framework_pack_names": ["react-base"],
                    "query_surfacing": "supported",
                    "real_repo_validation": "partial",
                    "end_to_end_indexing": "unsupported",
                },
            },
            {
                "language": "other",
                "title": "Other Parser",
                "family": "language",
                "parser": "OtherParser",
                "fixture_repo": "tests/fixtures/ecosystems/other/",
                "capabilities": [],
            },
        ]
    )

    assert "# Parser Support Maturity Matrix" in rendered
    assert (
        "| Demo | `DemoParser` | supported | supported | partial | `react-base` | supported | partial | unsupported |"
        in rendered
    )
    assert "| Other | `OtherParser` | - | - | - | - | - | - | - |" in rendered
