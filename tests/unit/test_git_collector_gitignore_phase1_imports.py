"""Phase 1 import compatibility tests for Git ignore helpers."""

from platform_context_graph.collectors.git.gitignore import (
    GitIgnoreFilterResult as NewGitIgnoreFilterResult,
)
from platform_context_graph.collectors.git.gitignore import (
    filter_repo_gitignore_files as new_filter_repo_gitignore_files,
)
from platform_context_graph.collectors.git.gitignore import (
    honor_gitignore_enabled as new_honor_gitignore_enabled,
)
from platform_context_graph.collectors.git.gitignore import (
    is_gitignored_in_repo as new_is_gitignored_in_repo,
)
from platform_context_graph.collectors.git.gitignore import (
    summarize_gitignored_paths as new_summarize_gitignored_paths,
)
from platform_context_graph.tools.graph_builder_gitignore import (
    GitIgnoreFilterResult as LegacyGitIgnoreFilterResult,
)
from platform_context_graph.tools.graph_builder_gitignore import (
    filter_repo_gitignore_files as legacy_filter_repo_gitignore_files,
)
from platform_context_graph.tools.graph_builder_gitignore import (
    honor_gitignore_enabled as legacy_honor_gitignore_enabled,
)
from platform_context_graph.tools.graph_builder_gitignore import (
    is_gitignored_in_repo as legacy_is_gitignored_in_repo,
)
from platform_context_graph.tools.graph_builder_gitignore import (
    summarize_gitignored_paths as legacy_summarize_gitignored_paths,
)


def test_gitignore_helpers_move_to_git_collector_package() -> None:
    """Expose Git ignore helpers from the Git collector package."""
    assert NewGitIgnoreFilterResult.__module__ == (
        "platform_context_graph.collectors.git.gitignore"
    )
    assert new_filter_repo_gitignore_files.__module__ == (
        "platform_context_graph.collectors.git.gitignore"
    )
    assert new_honor_gitignore_enabled.__module__ == (
        "platform_context_graph.collectors.git.gitignore"
    )
    assert new_is_gitignored_in_repo.__module__ == (
        "platform_context_graph.collectors.git.gitignore"
    )
    assert new_summarize_gitignored_paths.__module__ == (
        "platform_context_graph.collectors.git.gitignore"
    )


def test_legacy_gitignore_imports_reexport_new_api() -> None:
    """Keep legacy Git ignore imports working during Phase 1."""
    assert LegacyGitIgnoreFilterResult is NewGitIgnoreFilterResult
    assert legacy_filter_repo_gitignore_files is new_filter_repo_gitignore_files
    assert legacy_honor_gitignore_enabled is new_honor_gitignore_enabled
    assert legacy_is_gitignored_in_repo is new_is_gitignored_in_repo
    assert legacy_summarize_gitignored_paths is new_summarize_gitignored_paths
