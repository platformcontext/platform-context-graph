from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import logging
from pathlib import Path
import threading
from types import SimpleNamespace

from platform_context_graph.tools import graph_builder_parsers


def test_build_parser_registry_skips_unavailable_language(monkeypatch, caplog) -> None:
    """Service startup should degrade cleanly if one optional grammar is missing."""

    class FakeTreeSitterParser:
        def __init__(self, language_name: str) -> None:
            if language_name == "c_sharp":
                raise ValueError("Language 'c_sharp' is not available")
            self.language_name = language_name

    monkeypatch.setattr(graph_builder_parsers, "TreeSitterParser", FakeTreeSitterParser)
    caplog.set_level(logging.WARNING, logger=graph_builder_parsers.__name__)

    registry = graph_builder_parsers.build_parser_registry(lambda _key: "false")

    assert ".cs" not in registry
    assert registry[".py"].language_name == "python"
    assert (
        "Skipping parser for extension .cs because language c_sharp is unavailable"
        in caplog.text
    )


def test_build_parser_registry_keeps_available_language() -> None:
    """Known-good languages should still be registered normally."""

    registry = graph_builder_parsers.build_parser_registry(lambda _key: "false")

    assert ".py" in registry
    assert ".js" in registry


def test_build_parser_registry_uses_dedicated_tsx_parser() -> None:
    """TSX files should use the JSX-aware parser rather than plain TypeScript."""

    registry = graph_builder_parsers.build_parser_registry(lambda _key: "false")

    assert ".tsx" in registry
    assert (
        registry[".tsx"].language_specific_parser.__class__.__name__
        == "TypescriptJSXTreeSitterParser"
    )


def test_build_parser_registry_registers_common_extension_aliases(monkeypatch) -> None:
    """Common extension aliases should resolve to the expected parser language."""

    class FakeTreeSitterParser:
        def __init__(self, language_name: str) -> None:
            self.language_name = language_name

    monkeypatch.setattr(graph_builder_parsers, "TreeSitterParser", FakeTreeSitterParser)

    registry = graph_builder_parsers.build_parser_registry(lambda _key: "false")

    assert registry[".cc"].language_name == "cpp"
    assert registry[".cxx"].language_name == "cpp"
    assert registry[".mts"].language_name == "typescript"
    assert registry[".cts"].language_name == "typescript"
    assert registry[".pyw"].language_name == "python"
    assert registry[".csx"].language_name == "c_sharp"


def test_tree_sitter_parser_creates_distinct_parsers_per_thread(
    monkeypatch,
) -> None:
    """Concurrent parse calls must not share the same parser instance."""

    created_tokens = iter(("parser-a", "parser-b", "parser-c", "parser-d"))
    barrier = threading.Barrier(2)

    class FakeManager:
        def get_language_safe(self, _language_name: str) -> object:
            return object()

    class FakeLanguageParser:
        def __init__(self, wrapper) -> None:
            self.parser = wrapper.parser

        def parse(self, path: Path, is_dependency: bool = False, **kwargs) -> dict:
            del path, is_dependency, kwargs
            barrier.wait(timeout=1.0)
            return {"parser_token": self.parser["token"]}

    monkeypatch.setattr(
        graph_builder_parsers,
        "get_tree_sitter_manager",
        lambda: FakeManager(),
    )
    monkeypatch.setattr(
        graph_builder_parsers,
        "Parser",
        lambda _language: {"token": next(created_tokens)},
    )
    monkeypatch.setattr(
        graph_builder_parsers,
        "_load_attribute",
        lambda *_args, **_kwargs: FakeLanguageParser,
    )
    monkeypatch.setattr(
        graph_builder_parsers,
        "_LANGUAGE_SPECIFIC_PARSERS",
        {"python": (".languages.python", "PythonTreeSitterParser")},
    )

    parser = graph_builder_parsers.TreeSitterParser("python")
    sample_path = Path("sample.py")

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(parser.parse, sample_path)
        second = executor.submit(parser.parse, sample_path)
        results = [first.result(timeout=1.0), second.result(timeout=1.0)]

    assert {result["parser_token"] for result in results} == {"parser-a", "parser-b"}


def test_build_parser_registry_registers_raw_text_search_parsers() -> None:
    """Registry should include non-code search handlers and Dockerfile parsing."""

    registry = graph_builder_parsers.build_parser_registry(lambda _key: "false")

    assert ".j2" in registry
    assert ".tpl" in registry
    assert ".conf" in registry
    assert "__dockerfile__" in registry
    assert "__jenkinsfile__" in registry
    assert registry["__dockerfile__"].language_name == "dockerfile"
    assert registry["__jenkinsfile__"].language_name == "groovy"


def test_parse_file_for_indexing_worker_uses_local_parser_registry(
    tmp_path: Path,
) -> None:
    """The worker entrypoint should parse without needing a GraphBuilder instance."""

    repo_path = tmp_path / "service"
    repo_path.mkdir()
    dockerfile = repo_path / "Dockerfile"
    dockerfile.write_text("FROM python:3.12-slim\n", encoding="utf-8")

    result = graph_builder_parsers.parse_file_for_indexing_worker(
        repo_path,
        dockerfile,
        False,
        get_config_value_fn=lambda _key: "false",
        debug_log_fn=lambda *_args, **_kwargs: None,
        error_logger_fn=lambda *_args, **_kwargs: None,
        warning_logger_fn=lambda *_args, **_kwargs: None,
    )

    assert result["path"] == str(dockerfile)
    assert result["repo_path"] == str(repo_path)
    assert result["lang"] == "dockerfile"


def test_build_parser_registry_uses_tree_sitter_for_hcl() -> None:
    """Terraform files should be registered through the tree-sitter wrapper."""

    registry = graph_builder_parsers.build_parser_registry(lambda _key: "true")

    assert ".tf" in registry
    assert ".hcl" in registry
    assert registry[".tf"].__class__.__name__ == "TreeSitterParser"
    assert registry[".tf"].language_name == "hcl"


def test_build_parser_registry_uses_tree_sitter_for_json() -> None:
    """JSON config files should be registered through the tree-sitter wrapper."""

    registry = graph_builder_parsers.build_parser_registry(lambda key: "true")

    assert ".json" in registry
    assert registry[".json"].__class__.__name__ == "TreeSitterParser"
    assert registry[".json"].language_name == "json"


def test_parse_file_uses_structured_parser_for_dockerfile(tmp_path: Path) -> None:
    """Direct parsing should extract Dockerfile structure and keep dockerfile language."""

    repo_path = tmp_path / "service"
    repo_path.mkdir()
    dockerfile = repo_path / "Dockerfile"
    dockerfile.write_text(
        'FROM python:3.12-slim\nENTRYPOINT ["python", "app.py"]\n',
        encoding="utf-8",
    )
    builder = SimpleNamespace(
        parsers=graph_builder_parsers.build_parser_registry(lambda _key: "false")
    )

    result = graph_builder_parsers.parse_file(
        builder,
        repo_path,
        dockerfile,
        False,
        get_config_value_fn=lambda _key: "false",
        debug_log_fn=lambda *_args, **_kwargs: None,
        error_logger_fn=lambda *_args, **_kwargs: None,
        warning_logger_fn=lambda *_args, **_kwargs: None,
    )

    assert result["path"] == str(dockerfile)
    assert result["repo_path"] == str(repo_path)
    assert result["lang"] == "dockerfile"
    assert result["dockerfile_stages"][0]["base_image"] == "python"
    assert result["dockerfile_stages"][0]["entrypoint"] == '["python", "app.py"]'


def test_parse_file_uses_structured_parser_for_jenkinsfile(tmp_path: Path) -> None:
    """Special Jenkinsfile names should use the Groovy parser rather than raw text."""

    repo_path = tmp_path / "service"
    repo_path.mkdir()
    jenkinsfile = repo_path / "Jenkinsfile"
    jenkinsfile.write_text(
        "\n".join(
            [
                "@Library('pipelines') _",
                "",
                "pipelinePM2(",
                "  use_configd: true,",
                "  entry_point: 'dist/api-node-myboats.js'",
                ")",
                "",
            ]
        ),
        encoding="utf-8",
    )
    builder = SimpleNamespace(
        parsers=graph_builder_parsers.build_parser_registry(lambda _key: "false")
    )

    result = graph_builder_parsers.parse_file(
        builder,
        repo_path,
        jenkinsfile,
        False,
        get_config_value_fn=lambda _key: "false",
        debug_log_fn=lambda *_args, **_kwargs: None,
        error_logger_fn=lambda *_args, **_kwargs: None,
        warning_logger_fn=lambda *_args, **_kwargs: None,
    )

    assert result["path"] == str(jenkinsfile)
    assert result["repo_path"] == str(repo_path)
    assert result["lang"] == "groovy"
    assert result["pipeline_calls"] == ["pipelinePM2"]
    assert result["entry_points"] == ["dist/api-node-myboats.js"]


def test_parse_file_uses_raw_text_parser_for_conf_j2(tmp_path: Path) -> None:
    """Templated config files should parse as searchable raw text, not error out."""

    repo_path = tmp_path / "infra"
    repo_path.mkdir()
    file_path = repo_path / "templates" / "site.conf.j2"
    file_path.parent.mkdir()
    file_path.write_text("ServerName {{ host_name }}\n", encoding="utf-8")
    builder = SimpleNamespace(
        parsers=graph_builder_parsers.build_parser_registry(lambda _key: "false")
    )

    result = graph_builder_parsers.parse_file(
        builder,
        repo_path,
        file_path,
        False,
        get_config_value_fn=lambda _key: "false",
        debug_log_fn=lambda *_args, **_kwargs: None,
        error_logger_fn=lambda *_args, **_kwargs: None,
        warning_logger_fn=lambda *_args, **_kwargs: None,
    )

    assert result["path"] == str(file_path)
    assert result["lang"] == "config_template"
    assert "error" not in result


def test_pre_scan_for_imports_includes_c_java_ruby_and_csharp_together(
    monkeypatch,
) -> None:
    """Mixed-language repos should not let C files short-circuit other prescans."""

    c_file = Path("hello.c")
    java_file = Path("Main.java")
    ruby_file = Path("app.rb")
    csharp_file = Path("Program.cs")
    builder = SimpleNamespace(
        parsers={
            ".c": object(),
            ".java": object(),
            ".rb": object(),
            ".cs": object(),
        }
    )

    monkeypatch.setattr(
        "platform_context_graph.tools.languages.c.pre_scan_c",
        lambda files, _parser: {"c": [str(path) for path in files]},
    )
    monkeypatch.setattr(
        "platform_context_graph.tools.languages.java.pre_scan_java",
        lambda files, _parser: {"java": [str(path) for path in files]},
    )
    monkeypatch.setattr(
        "platform_context_graph.tools.languages.ruby.pre_scan_ruby",
        lambda files, _parser: {"ruby": [str(path) for path in files]},
    )
    monkeypatch.setattr(
        "platform_context_graph.tools.languages.csharp.pre_scan_csharp",
        lambda files, _parser: {"csharp": [str(path) for path in files]},
    )

    imports_map = graph_builder_parsers.pre_scan_for_imports(
        builder,
        [c_file, java_file, ruby_file, csharp_file],
    )

    assert imports_map == {
        "c": ["hello.c"],
        "java": ["Main.java"],
        "ruby": ["app.rb"],
        "csharp": ["Program.cs"],
    }
