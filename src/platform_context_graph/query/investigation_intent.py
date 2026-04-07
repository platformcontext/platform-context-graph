"""Intent helpers for service investigation orchestration."""

from __future__ import annotations

from platform_context_graph.domain.investigation_responses import InvestigationIntent

_INTENT_KEYWORDS: tuple[tuple[InvestigationIntent, tuple[str, ...]], ...] = (
    ("deployment", ("deploy", "deployment", "ci/cd", "release", "build")),
    ("network", ("network", "endpoint", "endpoints", "route", "routing", "hostname")),
    (
        "dependencies",
        ("depend", "dependency", "dependencies", "upstream", "downstream"),
    ),
    ("support", ("support", "on-call", "on call", "runbook", "incident")),
)


def normalize_investigation_intent(value: str | None) -> InvestigationIntent:
    """Normalize a user-supplied intent into one supported investigation intent."""

    normalized = (value or "").strip().lower()
    if not normalized:
        return "overview"

    for intent, _keywords in _INTENT_KEYWORDS:
        if normalized == intent:
            return intent
    return "overview"


def infer_investigation_intent(question: str | None) -> InvestigationIntent:
    """Infer one investigation intent from a natural-language question."""

    normalized_question = (question or "").strip().lower()
    if not normalized_question:
        return "overview"

    for intent, keywords in _INTENT_KEYWORDS:
        if any(keyword in normalized_question for keyword in keywords):
            return intent
    return "overview"


__all__ = ["infer_investigation_intent", "normalize_investigation_intent"]
