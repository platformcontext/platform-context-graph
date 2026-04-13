"""Unit tests for the Dockerfile tree-sitter parser."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from platform_context_graph.parsers.languages.dockerfile import DockerfileTreeSitterParser
from platform_context_graph.utils.tree_sitter_manager import get_tree_sitter_manager


def _parser() -> DockerfileTreeSitterParser:
    """Create the Dockerfile parser through a direct tree-sitter wrapper."""

    manager = get_tree_sitter_manager()
    wrapper = SimpleNamespace(
        language_name="dockerfile",
        language=manager.get_language_safe("dockerfile"),
        parser=manager.create_parser("dockerfile"),
    )
    return DockerfileTreeSitterParser(wrapper)


def test_parse_dockerfile_extracts_stage_metadata(tmp_path: Path) -> None:
    """Dockerfile parser should extract stage, entrypoint, cmd, and healthcheck data."""

    file_path = tmp_path / "Dockerfile"
    file_path.write_text(
        "\n".join(
            [
                "FROM python:3.12-slim AS base",
                "WORKDIR /app",
                "COPY --from=builder /src /app",
                'ENTRYPOINT ["python", "app.py"]',
                'CMD ["--port", "8080"]',
                "USER app",
                "HEALTHCHECK CMD curl -f http://localhost:8080/health || exit 1",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = _parser().parse(file_path)

    assert result["lang"] == "dockerfile"
    assert len(result["dockerfile_stages"]) == 1
    stage = result["dockerfile_stages"][0]
    assert stage["name"] == "base"
    assert stage["base_image"] == "python"
    assert stage["base_tag"] == "3.12-slim"
    assert stage["workdir"] == "/app"
    assert stage["copies_from"] == "builder"
    assert stage["entrypoint"] == '["python", "app.py"]'
    assert stage["cmd"] == '["--port", "8080"]'
    assert stage["user"] == "app"
    assert stage["healthcheck"] == "CMD curl -f http://localhost:8080/health || exit 1"


def test_parse_dockerfile_extracts_ports_args_envs_and_labels(tmp_path: Path) -> None:
    """Dockerfile parser should extract common instruction payloads."""

    file_path = tmp_path / "Dockerfile.prod"
    file_path.write_text(
        "\n".join(
            [
                "FROM node:22-alpine AS runtime",
                "ARG APP_ENV=prod",
                "ENV PORT=8080 DEBUG=false",
                "EXPOSE 8080/tcp 9090",
                'LABEL maintainer="pcg" org.opencontainers.image.source="https://github.com/platformcontext/platform-context-graph"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = _parser().parse(file_path)

    assert [item["name"] for item in result["dockerfile_args"]] == ["APP_ENV"]
    assert result["dockerfile_args"][0]["default_value"] == "prod"
    assert {(item["name"], item["value"]) for item in result["dockerfile_envs"]} == {
        ("PORT", "8080"),
        ("DEBUG", "false"),
    }
    assert {
        (item["name"], item["port"], item["protocol"])
        for item in result["dockerfile_ports"]
    } == {
        ("runtime:8080", "8080", "tcp"),
        ("runtime:9090", "9090", "tcp"),
    }
    assert {(item["name"], item["value"]) for item in result["dockerfile_labels"]} == {
        ("maintainer", "pcg"),
        (
            "org.opencontainers.image.source",
            "https://github.com/platformcontext/platform-context-graph",
        ),
    }
