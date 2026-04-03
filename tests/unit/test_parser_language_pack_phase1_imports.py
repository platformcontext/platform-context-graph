"""Phase 1 import compatibility tests for parser language module ownership."""

from platform_context_graph.parsers.languages.dockerfile import (
    DockerfileTreeSitterParser as NewDockerfileParser,
)
from platform_context_graph.parsers.languages.go import (
    GoTreeSitterParser as NewGoParser,
)
from platform_context_graph.parsers.languages.java import (
    JavaTreeSitterParser as NewJavaParser,
)
from platform_context_graph.parsers.languages.yaml_infra import (
    InfraYAMLParser as NewInfraYamlParser,
)
from platform_context_graph.tools.languages.dockerfile import (
    DockerfileTreeSitterParser as LegacyDockerfileParser,
)
from platform_context_graph.tools.languages.go import (
    GoTreeSitterParser as LegacyGoParser,
)
from platform_context_graph.tools.languages.java import (
    JavaTreeSitterParser as LegacyJavaParser,
)
from platform_context_graph.tools.languages.yaml_infra import (
    InfraYAMLParser as LegacyInfraYamlParser,
)


def test_remaining_language_modules_move_to_parsers_package() -> None:
    """Expose remaining parser entrypoints from canonical parser packages."""
    assert NewGoParser.__module__ == "platform_context_graph.parsers.languages.go"
    assert NewJavaParser.__module__ == "platform_context_graph.parsers.languages.java"
    assert NewDockerfileParser.__module__ == (
        "platform_context_graph.parsers.languages.dockerfile"
    )
    assert NewInfraYamlParser.__module__ == (
        "platform_context_graph.parsers.languages.yaml_infra"
    )


def test_legacy_language_imports_reexport_canonical_modules() -> None:
    """Keep legacy language parser imports working during Phase 1."""
    assert LegacyGoParser is NewGoParser
    assert LegacyJavaParser is NewJavaParser
    assert LegacyDockerfileParser is NewDockerfileParser
    assert LegacyInfraYamlParser is NewInfraYamlParser
