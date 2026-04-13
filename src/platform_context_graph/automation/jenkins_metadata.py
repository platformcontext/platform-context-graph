"""Helpers for extracting Jenkins pipeline hints from automation sources."""

from __future__ import annotations

import re
from typing import Any

_LIBRARY_RE = re.compile(r"@Library\((['\"])(.*?)\1\)")
_PIPELINE_CALL_RE = re.compile(r"\b(pipeline[A-Za-z0-9_]*)\s*\(")
_SHELL_COMMAND_RE = re.compile(r"sh\s+['\"]([^'\"]+)['\"]")
_ANSIBLE_PLAYBOOK_RE = re.compile(
    r"ansible-playbook\s+(?P<playbook>[^\s]+)(?:.*?-i\s+(?P<inventory>[^\s]+))?"
)
_ENTRY_POINT_RE = re.compile(r"entry_point\s*:\s*['\"]([^'\"]+)['\"]")
_USE_CONFIGD_RE = re.compile(r"use_configd\s*:\s*(true|false)")
_PRE_DEPLOY_RE = re.compile(r"pre_deploy\s*:")


def extract_jenkins_pipeline_metadata(source_text: str) -> dict[str, Any]:
    """Extract portable Jenkins pipeline hints from a Groovy pipeline file."""

    shared_libraries = _ordered_unique(
        match[1].strip() for match in _LIBRARY_RE.findall(source_text)
    )
    pipeline_calls = _ordered_unique(
        match.strip() for match in _PIPELINE_CALL_RE.findall(source_text)
    )
    shell_commands = _ordered_unique(
        match.strip() for match in _SHELL_COMMAND_RE.findall(source_text)
    )
    ansible_playbook_hints: list[dict[str, Any]] = []
    for command in shell_commands:
        match = _ANSIBLE_PLAYBOOK_RE.search(command)
        if match is None:
            continue
        ansible_playbook_hints.append(
            {
                "playbook": match.group("playbook"),
                "inventory": match.group("inventory"),
                "command": command,
            }
        )
    entry_points = _ordered_unique(
        match.strip() for match in _ENTRY_POINT_RE.findall(source_text)
    )
    use_configd_match = _USE_CONFIGD_RE.search(source_text)
    use_configd = None
    if use_configd_match is not None:
        use_configd = use_configd_match.group(1).lower() == "true"

    return {
        "shared_libraries": shared_libraries,
        "pipeline_calls": pipeline_calls,
        "shell_commands": shell_commands,
        "ansible_playbook_hints": ansible_playbook_hints,
        "entry_points": entry_points,
        "use_configd": use_configd,
        "has_pre_deploy": _PRE_DEPLOY_RE.search(source_text) is not None,
    }


def _ordered_unique(values: Any) -> list[str]:
    """Return ordered unique non-empty strings."""

    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = str(value).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


__all__ = ["extract_jenkins_pipeline_metadata"]
