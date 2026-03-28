"""Shared story-contract helpers for repository and workload narratives."""

from __future__ import annotations

from .story_repository import build_repository_story_response
from .story_workload import build_workload_story_response

__all__ = [
    "build_repository_story_response",
    "build_workload_story_response",
]
