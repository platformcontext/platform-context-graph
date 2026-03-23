from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import logging
from pathlib import Path
import threading

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
