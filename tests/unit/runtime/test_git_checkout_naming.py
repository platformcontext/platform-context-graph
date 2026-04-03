"""Unit tests for stable managed-workspace checkout names."""

from __future__ import annotations

import pytest

from platform_context_graph.runtime.ingester.git import repo_checkout_name


def test_repo_checkout_name_uses_stable_slug_for_qualified_repository_ids() -> None:
    """Qualified repository IDs should preserve their nested path shape."""

    assert (
        repo_checkout_name("platformcontext/payments-api")
        == "platformcontext/payments-api"
    )


def test_repo_checkout_name_sanitizes_nested_repository_paths() -> None:
    """Nested repository paths should stay nested in the managed workspace."""

    assert (
        repo_checkout_name("teams/platformcontext/payments-api")
        == "teams/platformcontext/payments-api"
    )


def test_repo_checkout_name_preserves_simple_unqualified_names() -> None:
    """Unqualified filesystem-mode repository IDs should stay readable."""

    assert repo_checkout_name("payments-api") == "payments-api"


def test_repo_checkout_name_rejects_relative_path_segments() -> None:
    """Dangerous relative path segments must not escape the managed workspace."""

    with pytest.raises(ValueError, match="Invalid repository identifier"):
        repo_checkout_name("../payments-api")
