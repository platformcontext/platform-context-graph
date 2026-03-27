"""Generic runtime-family inference for controller-driven automation paths."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True, slots=True)
class AutomationRuntimeFamily:
    """Describe one generic automation runtime family."""

    kind: str
    display_name: str
    signal_patterns: tuple[str, ...]


_AUTOMATION_RUNTIME_FAMILIES: tuple[AutomationRuntimeFamily, ...] = (
    AutomationRuntimeFamily(
        kind="wordpress_website_fleet",
        display_name="WordPress website fleet",
        signal_patterns=(
            "wp --allow-root",
            "wp-content/uploads",
            "wordpress",
            "portal-configs",
        ),
    ),
    AutomationRuntimeFamily(
        kind="php_web_platform",
        display_name="PHP web platform",
        signal_patterns=("nginx", "php", "memcached", "php_runtime"),
    ),
    AutomationRuntimeFamily(
        kind="ecs_service",
        display_name="ECS service",
        signal_patterns=("aws ecs", "ecs service", "ecs-cluster", "fargate"),
    ),
    AutomationRuntimeFamily(
        kind="kubernetes_gitops",
        display_name="Kubernetes GitOps",
        signal_patterns=("argocd", "helm", "kustomize", "kubernetes"),
    ),
)


def iter_automation_runtime_families() -> tuple[AutomationRuntimeFamily, ...]:
    """Return the registered automation runtime families."""

    return _AUTOMATION_RUNTIME_FAMILIES


def infer_automation_runtime_families(signals: Iterable[str]) -> list[str]:
    """Infer ordered runtime families from a stream of normalized signals."""

    normalized_signals = [
        str(signal).strip().lower() for signal in signals if str(signal).strip()
    ]
    matched: list[str] = []
    for family in _AUTOMATION_RUNTIME_FAMILIES:
        if any(
            pattern in signal
            for signal in normalized_signals
            for pattern in family.signal_patterns
        ):
            matched.append(family.kind)
    return matched


__all__ = [
    "AutomationRuntimeFamily",
    "infer_automation_runtime_families",
    "iter_automation_runtime_families",
]
