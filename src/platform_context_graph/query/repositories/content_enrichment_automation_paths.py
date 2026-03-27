"""Controller-driven automation path assembly for repository context."""

from __future__ import annotations

from typing import Any

from .content_enrichment_support import ordered_unique_strings


def build_controller_driven_paths(
    *,
    workflow_hints: dict[str, Any],
    ansible_hints: dict[str, Any],
    platforms: list[dict[str, Any]],
    provisioned_by: list[dict[str, Any]] | list[str],
) -> list[dict[str, Any]]:
    """Assemble normalized controller-driven automation paths."""

    del platforms  # This slice keeps controller-driven paths runtime-centric, not platform-centric.

    jenkins_rows = [
        row for row in workflow_hints.get("jenkins", []) if isinstance(row, dict)
    ]
    if not jenkins_rows:
        return []

    playbooks = [
        row for row in ansible_hints.get("playbooks", []) if isinstance(row, dict)
    ]
    inventory_targets = [
        row
        for row in ansible_hints.get("inventory_targets", [])
        if isinstance(row, dict)
    ]
    runtime_hints = ordered_unique_strings(ansible_hints.get("runtime_hints", []))
    shell_wrappers = [
        row for row in ansible_hints.get("shell_wrappers", []) if isinstance(row, dict)
    ]
    supporting_repositories = _normalize_repository_names(provisioned_by)

    paths: list[dict[str, Any]] = []
    for jenkins_row in jenkins_rows:
        entry_points = _resolve_ansible_entry_points(
            jenkins_row=jenkins_row,
            playbooks=playbooks,
            shell_wrappers=shell_wrappers,
        )
        target_descriptors = _target_descriptors(inventory_targets)
        runtime_family = runtime_hints[0] if runtime_hints else ""
        confidence = _path_confidence(
            entry_points=entry_points,
            target_descriptors=target_descriptors,
            runtime_family=runtime_family,
        )
        paths.append(
            {
                "controller_kind": "jenkins",
                "controller_repository": None,
                "automation_kind": "ansible",
                "automation_repository": None,
                "entry_points": entry_points,
                "target_descriptors": target_descriptors,
                "runtime_family": runtime_family,
                "supporting_repositories": supporting_repositories,
                "confidence": confidence,
                "explanation": _format_controller_path_explanation(
                    controller_kind="jenkins",
                    controller_path=str(jenkins_row.get("relative_path") or ""),
                    entry_points=entry_points,
                    target_descriptors=target_descriptors,
                    runtime_family=runtime_family,
                    supporting_repositories=supporting_repositories,
                ),
            }
        )
    return [path for path in paths if path.get("entry_points")]


def _resolve_ansible_entry_points(
    *,
    jenkins_row: dict[str, Any],
    playbooks: list[dict[str, Any]],
    shell_wrappers: list[dict[str, Any]],
) -> list[str]:
    """Resolve Ansible entry points from Jenkins hints and shell wrappers."""

    hinted_playbooks = ordered_unique_strings(
        row.get("playbook")
        for row in jenkins_row.get("ansible_playbook_hints", [])
        if isinstance(row, dict)
    )
    if hinted_playbooks:
        return hinted_playbooks

    wrapper_commands = ordered_unique_strings(jenkins_row.get("shell_commands", []))
    wrapper_paths = {
        command.removeprefix("./"): command
        for command in wrapper_commands
        if command.endswith(".sh")
    }
    wrapper_playbooks: list[str] = []
    for wrapper in shell_wrappers:
        relative_path = str(wrapper.get("relative_path") or "").strip()
        if relative_path not in wrapper_paths:
            continue
        wrapper_playbooks.extend(wrapper.get("playbooks", []))
    if wrapper_playbooks:
        return ordered_unique_strings(wrapper_playbooks)

    return ordered_unique_strings(
        row.get("relative_path") for row in playbooks if isinstance(row, dict)
    )


def _target_descriptors(inventory_targets: list[dict[str, Any]]) -> list[str]:
    """Build ordered target descriptors from inventory and environment hints."""

    values: list[str] = []
    for row in inventory_targets:
        values.append(str(row.get("group") or "").strip())
        values.append(str(row.get("environment") or "").strip())
    return ordered_unique_strings(values)


def _normalize_repository_names(rows: list[dict[str, Any]] | list[str]) -> list[str]:
    """Normalize repository references into ordered names."""

    names: list[str] = []
    for row in rows:
        if isinstance(row, dict):
            names.append(str(row.get("name") or "").strip())
        else:
            names.append(str(row).strip())
    return ordered_unique_strings(names)


def _path_confidence(
    *,
    entry_points: list[str],
    target_descriptors: list[str],
    runtime_family: str,
) -> str:
    """Classify confidence for one assembled controller path."""

    if entry_points and target_descriptors and runtime_family:
        return "high"
    if entry_points and runtime_family:
        return "medium"
    return "low"


def _format_controller_path_explanation(
    *,
    controller_kind: str,
    controller_path: str,
    entry_points: list[str],
    target_descriptors: list[str],
    runtime_family: str,
    supporting_repositories: list[str],
) -> str:
    """Render one stable explanation string for a controller-driven path."""

    explanation = (
        f"{controller_kind} controller {controller_path} invokes ansible entry points "
        f"{', '.join(entry_points)}"
    )
    if target_descriptors:
        explanation += f" targeting {', '.join(target_descriptors)}"
    if runtime_family:
        explanation += f" for {runtime_family}"
    if supporting_repositories:
        explanation += f" with support from {', '.join(supporting_repositories)}"
    return explanation + "."


__all__ = ["build_controller_driven_paths"]
