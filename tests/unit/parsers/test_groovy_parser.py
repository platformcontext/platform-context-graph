"""Unit tests for the Groovy tree-sitter parser."""

from __future__ import annotations

from pathlib import Path

from platform_context_graph.tools.graph_builder_parsers import TreeSitterParser
from platform_context_graph.tools.languages.groovy import GroovyTreeSitterParser


def _parser() -> GroovyTreeSitterParser:
    """Create the Groovy parser through the shared tree-sitter wrapper."""

    return GroovyTreeSitterParser(TreeSitterParser("groovy"))


def test_parse_jenkinsfile_extracts_pipeline_metadata(tmp_path: Path) -> None:
    """Groovy parser should extract high-signal Jenkins deployment metadata."""

    file_path = tmp_path / "Jenkinsfile"
    file_path.write_text(
        "\n".join(
            [
                "@Library('pipelines') _",
                "",
                "pipelinePM2(",
                "  use_configd: true,",
                "  entry_point: 'dist/api-node-whisper.js',",
                "  pre_deploy: { pipe, params ->",
                "    sh 'echo migrate'",
                "  }",
                ")",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = _parser().parse(file_path)

    assert result["lang"] == "groovy"
    assert result["shared_libraries"] == ["pipelines"]
    assert result["pipeline_calls"] == ["pipelinePM2"]
    assert result["entry_points"] == ["dist/api-node-whisper.js"]
    assert result["use_configd"] is True
    assert result["has_pre_deploy"] is True
