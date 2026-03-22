"""Unit tests for stable managed-workspace checkout names."""

from __future__ import annotations

from platform_context_graph.runtime.ingester.git import repo_checkout_name


def test_repo_checkout_name_uses_stable_slug_for_qualified_repository_ids() -> None:
    """Qualified repository IDs should not collide on the final path segment."""

    assert repo_checkout_name("platformcontext/payments-api") == "platformcontext--payments-api"


def test_repo_checkout_name_sanitizes_nested_repository_paths() -> None:
    """Unexpected extra path separators should still produce one stable folder name."""

    assert repo_checkout_name("teams/platformcontext/payments-api") == "teams--platformcontext--payments-api"


def test_repo_checkout_name_preserves_simple_unqualified_names() -> None:
    """Unqualified filesystem-mode repository IDs should stay readable."""

    assert repo_checkout_name("payments-api") == "payments-api"
