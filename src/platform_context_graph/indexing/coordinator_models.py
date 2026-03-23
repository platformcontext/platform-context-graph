"""Shared state models for resumable indexing."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ACTIVE_REPO_STATES = {"pending", "running", "parsed", "commit_incomplete", "failed"}
TERMINAL_REPO_STATES = {"completed", "skipped"}
ACTIVE_PROGRESS_REPO_STATES = {"running", "parsed", "commit_incomplete"}


@dataclass(slots=True)
class RepositoryRunState:
    """Checkpoint state for one repository inside a run."""

    repo_path: str
    status: str = "pending"
    file_count: int = 0
    error: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    updated_at: str | None = None
    phase: str | None = None
    phase_started_at: str | None = None
    last_progress_at: str | None = None
    current_file: str | None = None
    commit_started_at: str | None = None
    commit_finished_at: str | None = None
    commit_duration_seconds: float | None = None


@dataclass(slots=True)
class IndexRunState:
    """Durable checkpoint state for one repo-batch indexing run."""

    run_id: str
    root_path: str
    family: str
    source: str
    discovery_signature: str
    is_dependency: bool
    status: str
    finalization_status: str
    created_at: str
    updated_at: str
    finalization_started_at: str | None = None
    finalization_finished_at: str | None = None
    finalization_duration_seconds: float | None = None
    finalization_current_stage: str | None = None
    finalization_stage_started_at: str | None = None
    finalization_stage_durations: dict[str, float] = field(default_factory=dict)
    finalization_stage_details: dict[str, Any] = field(default_factory=dict)
    last_error: str | None = None
    repositories: dict[str, RepositoryRunState] = field(default_factory=dict)

    def pending_repositories(self) -> int:
        """Return the number of repositories still requiring work."""

        return sum(
            1
            for state in self.repositories.values()
            if state.status not in TERMINAL_REPO_STATES
        )

    def completed_repositories(self) -> int:
        """Return the number of repositories completed successfully."""

        return sum(
            1 for state in self.repositories.values() if state.status == "completed"
        )

    def failed_repositories(self) -> int:
        """Return the number of repositories left in a failed-like state."""

        return sum(
            1
            for state in self.repositories.values()
            if state.status in {"failed", "commit_incomplete"}
        )

    def active_repository_state(self) -> RepositoryRunState | None:
        """Return the most recently active repository state for diagnostics."""

        candidates = [
            state
            for state in self.repositories.values()
            if state.status in ACTIVE_PROGRESS_REPO_STATES or state.phase is not None
        ]
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda state: (
                state.last_progress_at
                or state.phase_started_at
                or state.started_at
                or "",
                state.repo_path,
            ),
        )


@dataclass(slots=True)
class IndexExecutionResult:
    """Outcome summary for one coordinated index run."""

    run_id: str
    root_path: Path
    repository_count: int
    completed_repositories: int
    failed_repositories: int
    resumed_repositories: int
    skipped_repositories: int
    finalization_status: str
    status: str


@dataclass(slots=True)
class RepositorySnapshot:
    """Durable staged parse output for one repository."""

    repo_path: str
    file_count: int
    imports_map: dict[str, list[str]]
    file_data: list[dict[str, Any]]
