"""High-signal Ansible enrichment for controller-driven automation paths."""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

from ...tools.runtime_automation_families import infer_automation_runtime_families
from .content_enrichment_support import (
    flatten_string_values,
    load_yaml_path,
    ordered_unique_strings,
)

_YAML_SUFFIXES = {".yml", ".yaml"}
_SHELL_WRAPPER_SUFFIXES = {".sh"}
_ANSIBLE_PLAYBOOK_RE = re.compile(
    r"ansible-playbook\s+(?P<playbook>[^\s]+)(?:.*?-i\s+(?P<inventory>[^\s]+))?"
)


def extract_ansible_automation_evidence(repo_root: Path) -> dict[str, Any]:
    """Extract high-signal Ansible evidence from one repository root."""

    group_vars = _extract_yaml_var_sets(repo_root / "group_vars", repo_root=repo_root)
    host_vars = _extract_yaml_var_sets(repo_root / "host_vars", repo_root=repo_root)
    playbooks = _extract_top_level_playbooks(repo_root)
    shell_wrappers = _extract_ansible_shell_wrappers(repo_root)
    role_entrypoints = _extract_role_task_entrypoints(repo_root)
    inventory_targets = _extract_inventory_targets(
        repo_root,
        playbooks=playbooks,
        host_vars=host_vars,
    )
    runtime_hints = infer_automation_runtime_families(
        _collect_runtime_signals(
            playbooks=playbooks,
            group_vars=group_vars,
            host_vars=host_vars,
            shell_wrappers=shell_wrappers,
            role_entrypoints=role_entrypoints,
        )
    )
    return {
        "playbooks": playbooks,
        "inventory_targets": inventory_targets,
        "group_vars": group_vars,
        "host_vars": host_vars,
        "shell_wrappers": shell_wrappers,
        "runtime_hints": runtime_hints,
        "role_entrypoints": role_entrypoints,
    }


def _extract_top_level_playbooks(repo_root: Path) -> list[dict[str, Any]]:
    """Extract high-signal top-level playbooks from the repo root."""

    rows: list[dict[str, Any]] = []
    for candidate in sorted(repo_root.iterdir()):
        if candidate.suffix.lower() not in _YAML_SUFFIXES or not candidate.is_file():
            continue
        document = load_yaml_path(candidate)
        if not isinstance(document, list) or not document:
            continue
        first_play = document[0]
        if not isinstance(first_play, dict):
            continue
        hosts = first_play.get("hosts")
        roles = first_play.get("roles")
        if not isinstance(hosts, str) or not isinstance(roles, list):
            continue
        role_names: list[str] = []
        tags: list[str] = []
        for role in roles:
            if isinstance(role, str):
                role_names.append(role)
                continue
            if not isinstance(role, dict):
                continue
            role_name = role.get("role")
            if isinstance(role_name, str) and role_name.strip():
                role_names.append(role_name.strip())
            role_tags = role.get("tags")
            if isinstance(role_tags, str):
                tags.append(role_tags)
            elif isinstance(role_tags, list):
                tags.extend(str(tag).strip() for tag in role_tags if str(tag).strip())
        rows.append(
            {
                "relative_path": str(candidate.relative_to(repo_root)),
                "hosts": [hosts.strip()],
                "roles": ordered_unique_strings(role_names),
                "tags": sorted(ordered_unique_strings(tags)),
            }
        )
    return rows


def _extract_yaml_var_sets(directory: Path, *, repo_root: Path) -> list[dict[str, Any]]:
    """Extract YAML var-set files under one vars directory."""

    if not directory.exists():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(directory.rglob("*")):
        if path.suffix.lower() not in _YAML_SUFFIXES or not path.is_file():
            continue
        values = load_yaml_path(path)
        if not isinstance(values, dict):
            continue
        rows.append(
            {
                "relative_path": str(path.relative_to(repo_root)),
                "name": path.stem,
                "values": values,
            }
        )
    return rows


def _extract_ansible_shell_wrappers(repo_root: Path) -> list[dict[str, Any]]:
    """Extract shell-wrapper commands that invoke ansible-playbook."""

    rows: list[dict[str, Any]] = []
    for path in sorted(repo_root.rglob("*")):
        if path.suffix.lower() not in _SHELL_WRAPPER_SUFFIXES or not path.is_file():
            continue
        source_text = path.read_text(encoding="utf-8", errors="ignore")
        commands = ordered_unique_strings(
            match.group(0) for match in _ANSIBLE_PLAYBOOK_RE.finditer(source_text)
        )
        if not commands:
            continue
        playbooks: list[str] = []
        inventories: list[str] = []
        for command in commands:
            match = _ANSIBLE_PLAYBOOK_RE.search(command)
            if match is None:
                continue
            playbooks.append(str(match.group("playbook") or "").strip())
            inventories.append(str(match.group("inventory") or "").strip())
        rows.append(
            {
                "relative_path": str(path.relative_to(repo_root)),
                "commands": commands,
                "playbooks": ordered_unique_strings(playbooks),
                "inventories": ordered_unique_strings(inventories),
            }
        )
    return rows


def _extract_role_task_entrypoints(repo_root: Path) -> list[dict[str, Any]]:
    """Extract role task entrypoints from Ansible role task files."""

    rows: list[dict[str, Any]] = []
    for path in sorted((repo_root / "roles").glob("*/tasks/main.y*ml")):
        document = load_yaml_path(path)
        if not isinstance(document, list):
            continue
        task_names = ordered_unique_strings(
            task.get("name")
            for task in document
            if isinstance(task, dict) and isinstance(task.get("name"), str)
        )
        rows.append(
            {
                "relative_path": str(path.relative_to(repo_root)),
                "role": path.parent.parent.name,
                "task_names": task_names,
                "source_text": path.read_text(encoding="utf-8", errors="ignore"),
            }
        )
    return rows


def _extract_inventory_targets(
    repo_root: Path,
    *,
    playbooks: list[dict[str, Any]],
    host_vars: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Extract inventory targets from dynamic inventory and host vars."""

    inventory_hosts, inventory_groups = _extract_dynamic_inventory_hosts(repo_root)
    environments = ordered_unique_strings(
        row.get("values", {}).get("environment")
        for row in host_vars
        if isinstance(row.get("values"), dict)
    )
    rows: list[dict[str, Any]] = []
    for playbook in playbooks:
        for group in playbook.get("hosts", []):
            row: dict[str, Any] = {"group": group}
            matching_hosts = inventory_groups.get(group, [])
            if matching_hosts:
                row["hosts"] = matching_hosts
            elif inventory_hosts:
                row["hosts"] = inventory_hosts
            if environments:
                row["environment"] = environments[0]
            rows.append(row)
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (str(row.get("group") or ""), str(row.get("environment") or ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _extract_dynamic_inventory_hosts(repo_root: Path) -> tuple[list[str], dict[str, list[str]]]:
    """Extract static hosts and groups from Python dynamic inventory when possible."""

    inventory_dir = repo_root / "inventory"
    if not inventory_dir.exists():
        return [], {}
    for path in sorted(inventory_dir.glob("*.py")):
        parsed = _extract_static_python_inventory(path)
        if not isinstance(parsed, dict):
            continue
        groups: dict[str, list[str]] = {}
        all_hosts: list[str] = []
        for key, value in parsed.items():
            if key == "_meta" or not isinstance(value, dict):
                continue
            hosts = value.get("hosts")
            if not isinstance(hosts, list):
                continue
            normalized_hosts = ordered_unique_strings(hosts)
            groups[str(key)] = normalized_hosts
            all_hosts.extend(normalized_hosts)
        return ordered_unique_strings(all_hosts), groups
    return [], {}


def _extract_static_python_inventory(path: Path) -> dict[str, Any] | None:
    """Extract a static inventory dict from a simple Python inventory file."""

    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return None
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "inventory"
            for target in node.targets
        ):
            continue
        try:
            value = ast.literal_eval(node.value)
        except (SyntaxError, ValueError):
            return None
        if isinstance(value, dict):
            return value
    return None


def _collect_runtime_signals(
    *,
    playbooks: list[dict[str, Any]],
    group_vars: list[dict[str, Any]],
    host_vars: list[dict[str, Any]],
    shell_wrappers: list[dict[str, Any]],
    role_entrypoints: list[dict[str, Any]],
) -> list[str]:
    """Collect flattened strings that may identify automation runtime families."""

    signals: list[str] = []
    for playbook in playbooks:
        signals.extend(flatten_string_values(playbook))
    for row in group_vars:
        signals.extend(flatten_string_values(row.get("values")))
    for row in host_vars:
        signals.extend(flatten_string_values(row.get("values")))
    for wrapper in shell_wrappers:
        signals.extend(flatten_string_values(wrapper))
    for entrypoint in role_entrypoints:
        signals.extend(flatten_string_values(entrypoint))
    return ordered_unique_strings(signals)


__all__ = ["extract_ansible_automation_evidence"]
