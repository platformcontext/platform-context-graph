"""Framework-aware investigation helpers."""

from __future__ import annotations

from typing import Any

from platform_context_graph.domain.framework_responses import FrameworkSummary
from platform_context_graph.domain.investigation_responses import InvestigationFinding

from .story_frameworks import summarize_framework_overview


def framework_summary_from_context(
    primary_repo_context: dict[str, Any] | None,
) -> FrameworkSummary | None:
    """Return a typed framework summary from one repository context payload."""

    if not isinstance(primary_repo_context, dict):
        return None
    framework_summary = primary_repo_context.get("framework_summary")
    if not isinstance(framework_summary, dict):
        return None
    return FrameworkSummary.model_validate(framework_summary)


def summarize_investigation_frameworks(
    framework_summary: FrameworkSummary | None,
) -> str:
    """Return one human-readable investigation summary line for frameworks."""

    if framework_summary is None:
        return ""
    return summarize_framework_overview(framework_summary.model_dump(mode="json"))


def build_framework_investigation_finding(
    framework_summary: FrameworkSummary | None,
) -> InvestigationFinding | None:
    """Return one framework-focused finding when summary evidence exists."""

    summary = summarize_investigation_frameworks(framework_summary)
    if not summary:
        return None
    return InvestigationFinding(
        title="Framework profile detected",
        summary=summary,
    )


__all__ = [
    "build_framework_investigation_finding",
    "framework_summary_from_context",
    "summarize_investigation_frameworks",
]
