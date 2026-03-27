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


def test_parse_jenkinsfile_extracts_ansible_and_shell_hints(tmp_path: Path) -> None:
    file_path = tmp_path / "Jenkinsfile"
    file_path.write_text(
        "@Library('pipelines') _\n"
        "pipelineDeploy(entry_point: 'deploy.sh')\n"
        "sh 'ansible-playbook deploy.yml -i inventory/dynamic_hosts.py --limit prod'\n",
        encoding="utf-8",
    )
    result = _parser().parse(file_path)
    assert result["pipeline_calls"] == ["pipelineDeploy"]
    assert result["shell_commands"] == [
        "ansible-playbook deploy.yml -i inventory/dynamic_hosts.py --limit prod"
    ]
    assert result["ansible_playbook_hints"][0]["playbook"] == "deploy.yml"
