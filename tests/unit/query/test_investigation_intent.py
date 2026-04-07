"""Unit tests for investigation intent helpers."""

from __future__ import annotations

import pytest

from platform_context_graph.query.investigation_evidence_families import (
    INVESTIGATION_EVIDENCE_FAMILIES,
)
from platform_context_graph.query.investigation_intent import (
    infer_investigation_intent,
    normalize_investigation_intent,
)


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Explain the deployment flow for api-node-boats", "deployment"),
        ("What depends on api-node-boats?", "dependencies"),
        ("Explain the network flow for api-node-boats", "network"),
        ("Create an on-call guide for api-node-boats", "support"),
        ("Tell me about api-node-boats", "overview"),
    ],
)
def test_infer_investigation_intent(question: str, expected: str) -> None:
    """Infer one investigation intent from common operator questions."""

    assert infer_investigation_intent(question) == expected


@pytest.mark.parametrize(
    ("provided", "expected"),
    [
        ("deployment", "deployment"),
        ("Network", "network"),
        ("DEPENDENCIES", "dependencies"),
        (None, "overview"),
    ],
)
def test_normalize_investigation_intent(provided: str | None, expected: str) -> None:
    """Normalize user-provided investigation intents."""

    assert normalize_investigation_intent(provided) == expected


def test_investigation_evidence_families_include_ci_cd_pipeline() -> None:
    """Keep CI/CD workflow evidence in the first-class family set."""

    assert INVESTIGATION_EVIDENCE_FAMILIES == (
        "service_runtime",
        "deployment_controller",
        "gitops_config",
        "iac_infrastructure",
        "network_routing",
        "identity_and_iam",
        "dependencies",
        "support_artifacts",
        "monitoring_observability",
        "ci_cd_pipeline",
    )
