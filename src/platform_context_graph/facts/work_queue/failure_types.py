"""Stable failure taxonomy contracts for fact work queue processing."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class FailureClass(StrEnum):
    """Stable high-level classes for resolution and projection failures."""

    INPUT_INVALID = "input_invalid"
    PROJECTION_BUG = "projection_bug"
    DEPENDENCY_UNAVAILABLE = "dependency_unavailable"
    RESOURCE_EXHAUSTED = "resource_exhausted"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


class FailureDisposition(StrEnum):
    """Operator-facing retry guidance for one failed work item."""

    RETRYABLE = "retryable"
    NON_RETRYABLE = "non_retryable"
    MANUAL_REVIEW = "manual_review"


@dataclass(frozen=True, slots=True)
class FailureClassification:
    """Classified failure metadata ready for durable queue persistence."""

    failure_stage: str
    error_class: str
    failure_class: FailureClass
    failure_code: str
    retry_disposition: FailureDisposition
