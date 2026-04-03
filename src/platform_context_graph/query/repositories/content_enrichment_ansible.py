"""High-signal Ansible enrichment for controller-driven automation paths."""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

from ...platform.automation_families import infer_automation_runtime_families
from .content_enrichment_support import (
    flatten_string_values,
    load_yaml_path,
    ordered_unique_strings,
)
from .indexed_file_discovery import (
    discover_repo_files,
    read_file_content,
    read_yaml_document,
    read_yaml_file,
)

_YAML_SUFFIXES = {".yml", ".yaml"}
_SHELL_WRAPPER_SUFFIXES = {".sh"}
_ANSIBLE_PLAYBOOK_RE = re.compile(
    r"ansible-playbook\s+(?P<playbook>[^\s]+)(?:.*?-i\s+(?P<inventory>[^\s]+))?"
)


def extract_ansible_automation_evidence(
    repo_root: Path | None = None,
    *,
    database: Any = None,
    repo_id: str | None = None,
) -> dict[str, Any]:
    """Extract high-signal Ansible evidence from one repository.

    Supports two modes:

    * **Filesystem mode** (legacy/CLI): pass ``repo_root``.
    * **Indexed mode** (API): pass ``database`` and ``repo_id``.

    When ``database`` is provided the indexed path is used; otherwise the
    filesystem path is used.
    """

    use_indexed = database is not None and repo_id is not None

    if use_indexed:
        group_vars = _extract_yaml_var_sets_indexed(database, repo_id, "group_vars/")
        host_vars = _extract_yaml_var_sets_indexed(database, repo_id, "host_vars/")
        playbooks = _extract_top_level_playbooks_indexed(database, repo_id)
        shell_wrappers = _extract_shell_wrappers_indexed(database, repo_id)
        role_entrypoints = _extract_role_entrypoints_indexed(database, repo_id)
        inv_hosts, inv_groups = _extract_inventory_indexed(database, repo_id)
    elif repo_root is not None:
        group_vars = _extract_yaml_var_sets_fs(repo_root / "group_vars", repo_root)
        host_vars = _extract_yaml_var_sets_fs(repo_root / "host_vars", repo_root)
        playbooks = _extract_top_level_playbooks_fs(repo_root)
        shell_wrappers = _extract_shell_wrappers_fs(repo_root)
        role_entrypoints = _extract_role_entrypoints_fs(repo_root)
        inv_hosts, inv_groups = _extract_inventory_fs(repo_root)
    else:
        return {}

    environments = ordered_unique_strings(
        row.get("values", {}).get("environment")
        for row in host_vars
        if isinstance(row.get("values"), dict)
    )
    inventory_targets = _build_inventory_target_rows(
        playbooks, inv_hosts, inv_groups, environments
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


# ── Playbook parsing (shared logic) ────────────────────────────────────


def _parse_playbook_row(document: Any, rel_path: str) -> dict[str, Any] | None:
    """Parse a YAML playbook document into a playbook evidence row."""

    if not isinstance(document, list) or not document:
        return None
    first_play = document[0]
    if not isinstance(first_play, dict):
        return None
    hosts = first_play.get("hosts")
    roles = first_play.get("roles")
    if not isinstance(hosts, str) or not isinstance(roles, list):
        return None
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
            tags.extend(str(t).strip() for t in role_tags if str(t).strip())
    return {
        "relative_path": rel_path,
        "hosts": [hosts.strip()],
        "roles": ordered_unique_strings(role_names),
        "tags": sorted(ordered_unique_strings(tags)),
    }


def _parse_shell_wrapper(source_text: str, rel_path: str) -> dict[str, Any] | None:
    """Parse a shell script for ansible-playbook invocations."""

    commands = ordered_unique_strings(
        m.group(0) for m in _ANSIBLE_PLAYBOOK_RE.finditer(source_text)
    )
    if not commands:
        return None
    playbooks: list[str] = []
    inventories: list[str] = []
    for cmd in commands:
        m = _ANSIBLE_PLAYBOOK_RE.search(cmd)
        if m is None:
            continue
        playbooks.append(str(m.group("playbook") or "").strip())
        inventories.append(str(m.group("inventory") or "").strip())
    return {
        "relative_path": rel_path,
        "commands": commands,
        "playbooks": ordered_unique_strings(playbooks),
        "inventories": ordered_unique_strings(inventories),
    }


# ── Indexed-mode helpers ────────────────────────────────────────────────


def _extract_top_level_playbooks_indexed(
    database: Any, repo_id: str
) -> list[dict[str, Any]]:
    """Extract top-level playbooks via indexed reads."""

    rows: list[dict[str, Any]] = []
    for rp in discover_repo_files(database, repo_id, pattern=r"[^/]+\.ya?ml"):
        doc = read_yaml_document(database, repo_id, rp)
        row = _parse_playbook_row(doc, rp)
        if row is not None:
            rows.append(row)
    return rows


def _extract_yaml_var_sets_indexed(
    database: Any, repo_id: str, prefix: str
) -> list[dict[str, Any]]:
    """Extract YAML var-set files under a vars directory prefix."""

    rows: list[dict[str, Any]] = []
    for rp in discover_repo_files(database, repo_id, prefix=prefix):
        if not rp.lower().endswith((".yml", ".yaml")):
            continue
        values = read_yaml_file(database, repo_id, rp)
        if not isinstance(values, dict):
            continue
        rows.append({"relative_path": rp, "name": Path(rp).stem, "values": values})
    return rows


def _extract_shell_wrappers_indexed(
    database: Any, repo_id: str
) -> list[dict[str, Any]]:
    """Extract shell-wrapper commands via indexed reads."""

    rows: list[dict[str, Any]] = []
    for rp in discover_repo_files(database, repo_id, suffix=".sh"):
        text = read_file_content(database, repo_id, rp)
        if text is None:
            continue
        row = _parse_shell_wrapper(text, rp)
        if row is not None:
            rows.append(row)
    return rows


def _extract_role_entrypoints_indexed(
    database: Any, repo_id: str
) -> list[dict[str, Any]]:
    """Extract role task entrypoints via indexed reads."""

    rows: list[dict[str, Any]] = []
    pattern = r"roles/[^/]+/tasks/main\.ya?ml"
    for rp in discover_repo_files(database, repo_id, pattern=pattern):
        doc = read_yaml_document(database, repo_id, rp)
        if not isinstance(doc, list):
            continue
        task_names = ordered_unique_strings(
            t.get("name")
            for t in doc
            if isinstance(t, dict) and isinstance(t.get("name"), str)
        )
        text = read_file_content(database, repo_id, rp) or ""
        rows.append(
            {
                "relative_path": rp,
                "role": Path(rp).parent.parent.name,
                "task_names": task_names,
                "source_text": text,
            }
        )
    return rows


def _extract_inventory_indexed(
    database: Any, repo_id: str
) -> tuple[list[str], dict[str, list[str]]]:
    """Extract hosts/groups from Python dynamic inventory via indexed reads."""

    for rp in discover_repo_files(database, repo_id, prefix="inventory/", suffix=".py"):
        text = read_file_content(database, repo_id, rp)
        if text is None:
            continue
        parsed = _parse_inventory_ast(text)
        if parsed is not None:
            return _hosts_and_groups_from_inventory(parsed)
    return [], {}


# ── Filesystem-mode helpers (legacy/CLI) ────────────────────────────────


def _extract_top_level_playbooks_fs(repo_root: Path) -> list[dict[str, Any]]:
    """Extract high-signal top-level playbooks from the repo root."""

    rows: list[dict[str, Any]] = []
    for candidate in sorted(repo_root.iterdir()):
        if candidate.suffix.lower() not in _YAML_SUFFIXES or not candidate.is_file():
            continue
        doc = load_yaml_path(candidate)
        row = _parse_playbook_row(doc, str(candidate.relative_to(repo_root)))
        if row is not None:
            rows.append(row)
    return rows


def _extract_yaml_var_sets_fs(directory: Path, repo_root: Path) -> list[dict[str, Any]]:
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


def _extract_shell_wrappers_fs(repo_root: Path) -> list[dict[str, Any]]:
    """Extract shell-wrapper commands that invoke ansible-playbook."""

    rows: list[dict[str, Any]] = []
    for path in sorted(repo_root.rglob("*")):
        if path.suffix.lower() not in _SHELL_WRAPPER_SUFFIXES or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        row = _parse_shell_wrapper(text, str(path.relative_to(repo_root)))
        if row is not None:
            rows.append(row)
    return rows


def _extract_role_entrypoints_fs(repo_root: Path) -> list[dict[str, Any]]:
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


def _extract_inventory_fs(
    repo_root: Path,
) -> tuple[list[str], dict[str, list[str]]]:
    """Extract static hosts and groups from Python dynamic inventory."""

    inventory_dir = repo_root / "inventory"
    if not inventory_dir.exists():
        return [], {}
    for path in sorted(inventory_dir.glob("*.py")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        parsed = _parse_inventory_ast(text)
        if parsed is not None:
            return _hosts_and_groups_from_inventory(parsed)
    return [], {}


# ── Shared helpers ──────────────────────────────────────────────────────


def _build_inventory_target_rows(
    playbooks: list[dict[str, Any]],
    inventory_hosts: list[str],
    inventory_groups: dict[str, list[str]],
    environments: list[str],
) -> list[dict[str, Any]]:
    """Build deduplicated inventory target rows from playbooks and hosts."""

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


def _parse_inventory_ast(source_text: str) -> dict[str, Any] | None:
    """Parse Python source and extract ``inventory = {...}``."""

    try:
        tree = ast.parse(source_text)
    except SyntaxError:
        return None
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(t, ast.Name) and t.id == "inventory" for t in node.targets
        ):
            continue
        try:
            value = ast.literal_eval(node.value)
        except (SyntaxError, ValueError):
            return None
        if isinstance(value, dict):
            return value
    return None


def _hosts_and_groups_from_inventory(
    parsed: dict[str, Any],
) -> tuple[list[str], dict[str, list[str]]]:
    """Extract hosts list and groups dict from a parsed inventory dict."""

    groups: dict[str, list[str]] = {}
    all_hosts: list[str] = []
    for key, value in parsed.items():
        if key == "_meta" or not isinstance(value, dict):
            continue
        hosts = value.get("hosts")
        if not isinstance(hosts, list):
            continue
        normalized = ordered_unique_strings(hosts)
        groups[str(key)] = normalized
        all_hosts.extend(normalized)
    return ordered_unique_strings(all_hosts), groups


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
