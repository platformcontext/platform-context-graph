"""Canonical parser registry and parse helpers."""

from __future__ import annotations

import logging
from pathlib import Path
import threading
from types import SimpleNamespace
from typing import Any
from tree_sitter import Language, Parser
import importlib

from ..tools.graph_builder_raw_text import (
    DOCKERFILE_PARSER_KEY,
    JENKINSFILE_PARSER_KEY,
    parser_key_for_path,
    register_raw_text_parsers,
)
from ..utils.tree_sitter_manager import get_tree_sitter_manager

logger = logging.getLogger(__name__)

_LANGUAGE_SPECIFIC_PARSERS: dict[str, tuple[str, str]] = {
    "python": (
        "platform_context_graph.parsers.languages.python",
        "PythonTreeSitterParser",
    ),
    "javascript": (
        "platform_context_graph.parsers.languages.javascript",
        "JavascriptTreeSitterParser",
    ),
    "go": ("platform_context_graph.tools.languages.go", "GoTreeSitterParser"),
    "typescript": (
        "platform_context_graph.parsers.languages.typescript",
        "TypescriptTreeSitterParser",
    ),
    "cpp": ("platform_context_graph.tools.languages.cpp", "CppTreeSitterParser"),
    "rust": ("platform_context_graph.tools.languages.rust", "RustTreeSitterParser"),
    "c": ("platform_context_graph.tools.languages.c", "CTreeSitterParser"),
    "java": ("platform_context_graph.tools.languages.java", "JavaTreeSitterParser"),
    "ruby": ("platform_context_graph.tools.languages.ruby", "RubyTreeSitterParser"),
    "c_sharp": (
        "platform_context_graph.tools.languages.csharp",
        "CSharpTreeSitterParser",
    ),
    "php": ("platform_context_graph.tools.languages.php", "PhpTreeSitterParser"),
    "kotlin": (
        "platform_context_graph.tools.languages.kotlin",
        "KotlinTreeSitterParser",
    ),
    "scala": (
        "platform_context_graph.tools.languages.scala",
        "ScalaTreeSitterParser",
    ),
    "swift": (
        "platform_context_graph.tools.languages.swift",
        "SwiftTreeSitterParser",
    ),
    "haskell": (
        "platform_context_graph.tools.languages.haskell",
        "HaskellTreeSitterParser",
    ),
    "dart": ("platform_context_graph.tools.languages.dart", "DartTreeSitterParser"),
    "perl": ("platform_context_graph.tools.languages.perl", "PerlTreeSitterParser"),
    "elixir": (
        "platform_context_graph.tools.languages.elixir",
        "ElixirTreeSitterParser",
    ),
    "groovy": (
        "platform_context_graph.tools.languages.groovy",
        "GroovyTreeSitterParser",
    ),
    "hcl": (
        "platform_context_graph.tools.languages.hcl_terraform",
        "HCLTerraformParser",
    ),
    "json": (
        "platform_context_graph.tools.languages.json_config",
        "JSONConfigTreeSitterParser",
    ),
    "dockerfile": (
        "platform_context_graph.tools.languages.dockerfile",
        "DockerfileTreeSitterParser",
    ),
}
_EXTENSION_SPECIFIC_PARSERS: dict[str, tuple[str, str]] = {
    ".tsx": (
        "platform_context_graph.parsers.languages.typescriptjsx",
        "TypescriptJSXTreeSitterParser",
    ),
}
_TREE_SITTER_PARSER_EXTENSIONS: tuple[tuple[str, str], ...] = (
    (".py", "python"),
    (".pyw", "python"),
    (".ipynb", "python"),
    (".js", "javascript"),
    (".jsx", "javascript"),
    (".mjs", "javascript"),
    (".cjs", "javascript"),
    (".go", "go"),
    (".ts", "typescript"),
    (".cts", "typescript"),
    (".mts", "typescript"),
    (".tsx", "typescript"),
    (".cpp", "cpp"),
    (".cc", "cpp"),
    (".cxx", "cpp"),
    (".h", "cpp"),
    (".hpp", "cpp"),
    (".hh", "cpp"),
    (".rs", "rust"),
    (".c", "c"),
    (".java", "java"),
    (".rb", "ruby"),
    (".cs", "c_sharp"),
    (".csx", "c_sharp"),
    (".php", "php"),
    (".kt", "kotlin"),
    (".scala", "scala"),
    (".sc", "scala"),
    (".swift", "swift"),
    (".hs", "haskell"),
    (".dart", "dart"),
    (".pl", "perl"),
    (".pm", "perl"),
    (".ex", "elixir"),
    (".exs", "elixir"),
    (".groovy", "groovy"),
)
_PRE_SCAN_HANDLER_GROUPS: tuple[tuple[tuple[str, ...], tuple[str, str]], ...] = (
    (
        (".py", ".pyw", ".ipynb"),
        ("platform_context_graph.parsers.languages.python", "pre_scan_python"),
    ),
    (
        (".js", ".jsx", ".mjs", ".cjs"),
        (
            "platform_context_graph.parsers.languages.javascript",
            "pre_scan_javascript",
        ),
    ),
    ((".go",), ("platform_context_graph.tools.languages.go", "pre_scan_go")),
    (
        (".ts", ".cts", ".mts"),
        (
            "platform_context_graph.parsers.languages.typescript",
            "pre_scan_typescript",
        ),
    ),
    (
        (".tsx",),
        (
            "platform_context_graph.parsers.languages.typescriptjsx",
            "pre_scan_typescript",
        ),
    ),
    (
        (".cpp", ".cc", ".cxx", ".h", ".hpp", ".hh"),
        ("platform_context_graph.tools.languages.cpp", "pre_scan_cpp"),
    ),
    ((".rs",), ("platform_context_graph.tools.languages.rust", "pre_scan_rust")),
    ((".c",), ("platform_context_graph.tools.languages.c", "pre_scan_c")),
    ((".java",), ("platform_context_graph.tools.languages.java", "pre_scan_java")),
    ((".rb",), ("platform_context_graph.tools.languages.ruby", "pre_scan_ruby")),
    (
        (".cs", ".csx"),
        ("platform_context_graph.tools.languages.csharp", "pre_scan_csharp"),
    ),
    (
        (".kt",),
        ("platform_context_graph.tools.languages.kotlin", "pre_scan_kotlin"),
    ),
    (
        (".scala", ".sc"),
        ("platform_context_graph.tools.languages.scala", "pre_scan_scala"),
    ),
    (
        (".swift",),
        ("platform_context_graph.tools.languages.swift", "pre_scan_swift"),
    ),
    ((".dart",), ("platform_context_graph.tools.languages.dart", "pre_scan_dart")),
    ((".pl", ".pm"), ("platform_context_graph.tools.languages.perl", "pre_scan_perl")),
    (
        (".ex", ".exs"),
        ("platform_context_graph.tools.languages.elixir", "pre_scan_elixir"),
    ),
)


def _load_attribute(module_name: str, attribute_name: str) -> Any:
    """Load an attribute from a module path.

    Args:
        module_name: Absolute module path for the imported module.
        attribute_name: Attribute name to load from the imported module.

    Returns:
        The resolved attribute object.
    """
    module = importlib.import_module(module_name)
    return getattr(module, attribute_name)


class TreeSitterParser:
    """Wrap a language-specific Tree-sitter parser implementation."""

    def __init__(self, language_name: str):
        """Initialize a parser wrapper for one language.

        Args:
            language_name: Canonical language name used by the Tree-sitter manager.
        """
        self.language_name = language_name
        self.ts_manager = get_tree_sitter_manager()
        self.language: Language = self.ts_manager.get_language_safe(language_name)
        self._parser_local = threading.local()
        self._language_specific_parser_cls = None

        parser_spec = _LANGUAGE_SPECIFIC_PARSERS.get(self.language_name)
        if parser_spec is not None:
            parser_cls = _load_attribute(*parser_spec)
            self._language_specific_parser_cls = parser_cls

    @property
    def parser(self) -> Parser:
        """Return the parser instance bound to the current thread."""

        parser = getattr(self._parser_local, "parser", None)
        if parser is None:
            create_parser = getattr(self.ts_manager, "create_parser", None)
            if callable(create_parser):
                parser = create_parser(self.language_name)
            else:
                parser = Parser(self.language)
            self._parser_local.parser = parser
        return parser

    @property
    def language_specific_parser(self) -> Any:
        """Return a fresh language-specific parser bound to the current thread."""

        if self._language_specific_parser_cls is None:
            return None
        return self._language_specific_parser_cls(self)

    def override_language_specific_parser(self, parser_cls: Any) -> None:
        """Override the language-specific parser class for this registry entry."""

        self._language_specific_parser_cls = parser_cls

    def parse(self, path: Path, is_dependency: bool = False, **kwargs: Any) -> dict:
        """Parse a file with the language-specific parser.

        Args:
            path: File path to parse.
            is_dependency: Whether the file belongs to a dependency repository.
            **kwargs: Additional parser-specific keyword arguments.

        Returns:
            Parsed file data emitted by the language-specific parser.

        Raises:
            NotImplementedError: If the language has no registered parser.
        """
        language_specific_parser = self.language_specific_parser
        if language_specific_parser is not None:
            return language_specific_parser.parse(path, is_dependency, **kwargs)

        raise NotImplementedError(
            f"No language-specific parser implemented for {self.language_name}"
        )


def _add_tree_sitter_parser(
    parsers: dict[str, Any], extension: str, language_name: str
) -> None:
    """Add one Tree-sitter parser to the registry when its grammar is available."""

    try:
        parser = TreeSitterParser(language_name)
        parser_spec = _EXTENSION_SPECIFIC_PARSERS.get(extension)
        if (
            parser_spec is not None
            and hasattr(parser, "language")
            and hasattr(parser, "parser")
        ):
            parser_cls = _load_attribute(*parser_spec)
            parser.override_language_specific_parser(parser_cls)
        parsers[extension] = parser
    except ValueError as exc:
        logger.warning(
            "Skipping parser for extension %s because language %s is unavailable: %s",
            extension,
            language_name,
            exc,
        )


def build_parser_registry(get_config_value_fn: Any) -> dict[str, Any]:
    """Create the extension-to-parser registry used by ``GraphBuilder``.

    Args:
        get_config_value_fn: Callable that resolves runtime config keys.

    Returns:
        A mapping of file extensions to parser instances.
    """
    from ..tools.languages.yaml_infra import InfraYAMLParser

    parsers: dict[str, Any] = {}
    for extension, language_name in _TREE_SITTER_PARSER_EXTENSIONS:
        _add_tree_sitter_parser(parsers, extension, language_name)

    if (get_config_value_fn("INDEX_YAML") or "true").lower() == "true":
        yaml_parser = InfraYAMLParser("yaml")
        parsers[".yaml"] = yaml_parser
        parsers[".yml"] = yaml_parser

    if (get_config_value_fn("INDEX_HCL") or "true").lower() == "true":
        _add_tree_sitter_parser(parsers, ".tf", "hcl")
        _add_tree_sitter_parser(parsers, ".hcl", "hcl")
    if (get_config_value_fn("INDEX_JSON") or "true").lower() == "true":
        _add_tree_sitter_parser(parsers, ".json", "json")
    try:
        parsers[DOCKERFILE_PARSER_KEY] = TreeSitterParser("dockerfile")
    except ValueError as exc:
        logger.warning(
            "Skipping parser for special filename %s because language dockerfile "
            "is unavailable: %s",
            DOCKERFILE_PARSER_KEY,
            exc,
        )
    try:
        parsers[JENKINSFILE_PARSER_KEY] = TreeSitterParser("groovy")
    except ValueError as exc:
        logger.warning(
            "Skipping parser for special filename %s because language groovy "
            "is unavailable: %s",
            JENKINSFILE_PARSER_KEY,
            exc,
        )
    register_raw_text_parsers(parsers)
    return parsers


def pre_scan_for_imports(builder: Any, files: list[Path]) -> dict[str, Any]:
    """Pre-scan files for import resolution hints.

    Args:
        builder: ``GraphBuilder`` facade instance with a populated parser registry.
        files: Files queued for indexing.

    Returns:
        A symbol-to-file-paths import resolution map.
    """
    imports_map: dict[str, Any] = {}
    files_by_lang: dict[str, list[Path]] = {}

    for file in files:
        if file.suffix in builder.parsers:
            files_by_lang.setdefault(file.suffix, []).append(file)

    for extensions, parser_spec in _PRE_SCAN_HANDLER_GROUPS:
        pre_scan = None
        for extension in extensions:
            files_for_extension = files_by_lang.get(extension)
            if not files_for_extension:
                continue
            if pre_scan is None:
                pre_scan = _load_attribute(*parser_spec)
            imports_map.update(
                pre_scan(files_for_extension, builder.parsers[extension])
            )

    return imports_map


def parse_file(
    builder: Any,
    repo_path: Path,
    path: Path,
    is_dependency: bool,
    *,
    get_config_value_fn: Any,
    debug_log_fn: Any,
    error_logger_fn: Any,
    warning_logger_fn: Any,
) -> dict[str, Any]:
    """Parse one file using the registered parser for its extension.

    Args:
        builder: ``GraphBuilder`` facade instance.
        repo_path: Repository root associated with the file.
        path: File to parse.
        is_dependency: Whether the file belongs to a dependency repository.
        get_config_value_fn: Runtime config resolver.
        debug_log_fn: Debug logging callable.
        error_logger_fn: Error logging callable.
        warning_logger_fn: Warning logging callable.

    Returns:
        Parsed file data or an error payload if parsing fails.
    """
    parser_key = parser_key_for_path(path, builder.parsers)
    parser = builder.parsers.get(parser_key) if parser_key is not None else None
    if not parser:
        warning_logger_fn(f"No parser found for file {path}. Skipping")
        return {"path": str(path), "error": f"No parser for {path.name}"}

    debug_log_fn(
        f"[parse_file] Starting parsing for: {path} with {parser.language_name} parser"
    )
    try:
        index_source = (
            get_config_value_fn("INDEX_SOURCE") or "false"
        ).lower() == "true"
        if parser.language_name == "python":
            is_notebook = path.suffix == ".ipynb"
            file_data = parser.parse(
                path,
                is_dependency,
                is_notebook=is_notebook,
                index_source=index_source,
            )
        else:
            file_data = parser.parse(path, is_dependency, index_source=index_source)

        file_data["repo_path"] = str(repo_path)
        return file_data
    except Exception as exc:
        error_logger_fn(
            f"Error parsing {path} with {parser.language_name} parser: {exc}"
        )
        debug_log_fn(f"[parse_file] Error parsing {path}: {exc}")
        return {"path": str(path), "error": str(exc)}


def parse_file_for_indexing_worker(
    repo_path: Path,
    path: Path,
    is_dependency: bool,
    *,
    get_config_value_fn: Any,
    debug_log_fn: Any,
    error_logger_fn: Any,
    warning_logger_fn: Any,
) -> dict[str, Any]:
    """Parse one file in a worker-friendly context with a local parser registry."""

    worker_builder = SimpleNamespace(parsers=build_parser_registry(get_config_value_fn))
    return parse_file(
        worker_builder,
        repo_path,
        path,
        is_dependency,
        get_config_value_fn=get_config_value_fn,
        debug_log_fn=debug_log_fn,
        error_logger_fn=error_logger_fn,
        warning_logger_fn=warning_logger_fn,
    )


__all__ = [
    "TreeSitterParser",
    "build_parser_registry",
    "parse_file_for_indexing_worker",
    "parse_file",
    "pre_scan_for_imports",
]
