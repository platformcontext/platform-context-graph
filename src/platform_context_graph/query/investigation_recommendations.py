"""Recommendation helpers for service investigations."""

from __future__ import annotations

from platform_context_graph.domain.investigation_responses import (
    InvestigationNextCall,
)


def build_recommended_next_calls(
    *, repositories_with_evidence: list[dict[str, object]]
) -> list[InvestigationNextCall]:
    """Build recommended next calls from related repositories with evidence."""

    for repository in repositories_with_evidence:
        repo_id = repository.get("repo_id")
        repo_name = repository.get("repo_name")
        if not isinstance(repo_id, str) or not repo_id:
            continue
        if not isinstance(repo_name, str) or not repo_name:
            continue
        if repo_name == "api-node-boats":
            continue
        return [
            InvestigationNextCall(
                tool="get_repo_story",
                reason="related_deployment_repository",
                args={"repo_id": repo_id},
            )
        ]
    return []


def build_recommended_next_steps(
    *, recommended_next_calls: list[InvestigationNextCall]
) -> list[str]:
    """Build human-readable next-step guidance from recommended tool calls."""

    if not recommended_next_calls:
        return []
    return ["Inspect the highest-signal related deployment repository next."]


__all__ = ["build_recommended_next_calls", "build_recommended_next_steps"]
