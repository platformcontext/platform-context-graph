"""Workflow enrichment helpers for repository context summaries."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

import yaml

from ...tools.languages.groovy_support import extract_jenkins_pipeline_metadata
from .indexed_file_discovery import (
    discover_repo_files,
    read_file_content,
    read_yaml_file,
)

_REUSABLE_WORKFLOW_RE = re.compile(
    r"^(?P<owner>[^/]+)/(?P<repo>[^/]+)/(?P<workflow_path>\.github/workflows/[^@]+)@(?P<ref>.+)$"
)
_COMMAND_GUARD_RE = re.compile(
    r"needs\.parse-command\.outputs\.command\s*==\s*'([^']+)'"
)


def extract_delivery_workflows(
    *,
    repository: dict[str, Any],
    resolve_repository: Callable[[str], dict[str, Any] | None],
    database: Any = None,
) -> dict[str, Any]:
    """Extract GitHub Actions and Jenkins workflow hints from one repository."""

    repo_id = _repo_id(repository)
    if database is None or repo_id is None:
        return {}

    github_actions = _extract_github_actions(
        database=database,
        repo_id=repo_id,
        resolve_repository=resolve_repository,
    )
    jenkins = _extract_jenkinsfiles(database=database, repo_id=repo_id)
    if not github_actions and not jenkins:
        return {}

    result: dict[str, Any] = {}
    if github_actions:
        result["github_actions"] = github_actions
    if jenkins:
        result["jenkins"] = jenkins
    return result


def _repo_id(repository: dict[str, Any]) -> str | None:
    """Return the canonical repo_id from a repository dict."""

    repo_id = repository.get("id")
    if isinstance(repo_id, str) and repo_id.strip():
        return repo_id.strip()
    return None


def _extract_github_actions(
    *,
    database: Any,
    repo_id: str,
    resolve_repository: Callable[[str], dict[str, Any] | None],
) -> dict[str, Any]:
    """Extract repo-local GitHub Actions workflow and automation handoff hints."""

    workflow_paths = discover_repo_files(
        database, repo_id, prefix=".github/workflows/", suffix=".yml"
    ) + discover_repo_files(
        database, repo_id, prefix=".github/workflows/", suffix=".yaml"
    )
    workflow_paths = sorted(set(workflow_paths))
    if not workflow_paths:
        return {}

    workflow_rows: list[dict[str, Any]] = []
    reusable_rows: list[dict[str, Any]] = []
    command_rows: list[dict[str, Any]] = []

    for relative_path in workflow_paths:
        parsed = read_yaml_file(database, repo_id, relative_path)
        if not isinstance(parsed, dict):
            continue

        reusable_workflows = _extract_reusable_workflows(parsed)
        workflow_rows.append(
            {
                "name": str(parsed.get("name") or Path(relative_path).name),
                "relative_path": relative_path,
                "triggers": _extract_trigger_names(parsed),
                "reusable_workflows": reusable_workflows,
            }
        )
        reusable_rows.extend(reusable_workflows)
        for reusable in reusable_workflows:
            command_rows.extend(
                _extract_deep_command_rows(
                    reusable_workflow=reusable,
                    resolve_repository=resolve_repository,
                    database=database,
                )
            )

    if not workflow_rows:
        return {}

    return {
        "workflows": workflow_rows,
        "automation_repositories": _dedupe_rows(
            [
                {
                    "repository": row["repository"],
                    "owner": row["owner"],
                    "name": row["name"],
                    "ref": row.get("ref"),
                }
                for row in reusable_rows
            ]
        ),
        "commands": _dedupe_rows(command_rows),
    }


def _extract_reusable_workflows(document: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract reusable workflow calls from one GitHub Actions workflow document."""

    jobs = document.get("jobs")
    if not isinstance(jobs, dict):
        return []

    rows: list[dict[str, Any]] = []
    for job_name, job in jobs.items():
        if not isinstance(job_name, str) or not isinstance(job, dict):
            continue
        uses = job.get("uses")
        if not isinstance(uses, str):
            continue
        parsed = _parse_reusable_workflow_ref(uses)
        if parsed is None:
            continue
        with_inputs = job.get("with") if isinstance(job.get("with"), dict) else {}
        rows.append(
            {
                "job": job_name,
                "repository": parsed["repository"],
                "owner": parsed["owner"],
                "name": parsed["name"],
                "workflow_path": parsed["workflow_path"],
                "workflow": Path(parsed["workflow_path"]).name,
                "ref": parsed["ref"],
                "environment_name": with_inputs.get("environment-name"),
            }
        )
    return rows


def _extract_deep_command_rows(
    *,
    reusable_workflow: dict[str, Any],
    resolve_repository: Callable[[str], dict[str, Any] | None],
    database: Any,
) -> list[dict[str, Any]]:
    """Extract command-to-workflow mappings from a reusable automation workflow."""

    workflow_path = reusable_workflow.get("workflow_path")
    repository_name = reusable_workflow.get("name")
    if not isinstance(workflow_path, str) or not isinstance(repository_name, str):
        return []
    if Path(workflow_path).name != "node-api-command-processing.yml":
        return []

    resolved = resolve_repository(str(reusable_workflow["repository"]))
    if resolved is None:
        resolved = resolve_repository(repository_name)
    if resolved is None:
        return []
    resolved_repo_id = _repo_id(resolved)
    if resolved_repo_id is None:
        return []

    parsed = read_yaml_file(database, resolved_repo_id, workflow_path)
    if not isinstance(parsed, dict):
        return []

    descriptions = _extract_command_descriptions(parsed)
    jobs = parsed.get("jobs")
    if not isinstance(jobs, dict):
        return []

    rows: list[dict[str, Any]] = []
    for job_name, job in jobs.items():
        if not isinstance(job_name, str) or not isinstance(job, dict):
            continue
        uses = job.get("uses")
        if not isinstance(uses, str) or not uses.startswith("./.github/workflows/"):
            continue
        commands = _extract_commands_from_if(job.get("if"))
        if not commands:
            continue
        workflow_file = Path(uses).name
        for command in commands:
            rows.append(
                {
                    "command": command,
                    "description": descriptions.get(command),
                    "workflow": workflow_file,
                    "workflow_path": uses.removeprefix("./"),
                    "delivery_mode": _classify_delivery_mode(workflow_file),
                    "automation_repository": reusable_workflow["repository"],
                }
            )
    return rows


def _extract_command_descriptions(document: dict[str, Any]) -> dict[str, str]:
    """Extract command descriptions from the reusable command workflow."""

    raw_commands = _find_valid_commands_data(document)
    if not isinstance(raw_commands, str) or not raw_commands.strip():
        return {}
    try:
        parsed = yaml.safe_load(raw_commands)
    except yaml.YAMLError:
        try:
            parsed = json.loads(raw_commands)
        except json.JSONDecodeError:
            return {}
    if not isinstance(parsed, list):
        return {}
    descriptions: dict[str, str] = {}
    for row in parsed:
        if not isinstance(row, dict):
            continue
        command = row.get("name")
        description = row.get("description")
        if isinstance(command, str) and isinstance(description, str):
            descriptions[command] = description
    return descriptions


def _find_valid_commands_data(node: Any) -> str | None:
    """Find the first VALID_COMMANDS_DATA string anywhere in a workflow document."""

    if isinstance(node, dict):
        value = node.get("VALID_COMMANDS_DATA")
        if isinstance(value, str) and value.strip():
            return value
        for child in node.values():
            found = _find_valid_commands_data(child)
            if found is not None:
                return found
        return None
    if isinstance(node, list):
        for child in node:
            found = _find_valid_commands_data(child)
            if found is not None:
                return found
    return None


def _extract_commands_from_if(value: Any) -> list[str]:
    """Extract command tokens guarded in a GitHub Actions job condition."""

    if not isinstance(value, str):
        return []
    seen: set[str] = set()
    ordered: list[str] = []
    for match in _COMMAND_GUARD_RE.findall(value):
        if match in seen:
            continue
        seen.add(match)
        ordered.append(match)
    return ordered


def _classify_delivery_mode(workflow_file: str) -> str:
    """Classify one reusable workflow filename into a portable delivery mode."""

    normalized = workflow_file.strip().lower()
    if normalized == "node-api-deploy-eks.yml":
        return "eks_gitops"
    if normalized == "node-api-rollback-eks.yml":
        return "eks_gitops_rollback"
    if normalized == "node-api-cd.yml":
        return "continuous_deployment"
    if normalized == "node-api-ci.yml":
        return "continuous_integration"
    if normalized == "node-api-ecr-push.yml":
        return "image_build_push"
    if normalized == "node-api-deployment-verification.yml":
        return "deployment_verification"
    return "workflow_dispatch"


def _extract_jenkinsfiles(*, database: Any, repo_id: str) -> list[dict[str, Any]]:
    """Extract Jenkins pipeline hints from Jenkinsfile-style files."""

    rows: list[dict[str, Any]] = []
    for relative_path in _iter_jenkins_entrypoint_paths(
        database=database, repo_id=repo_id
    ):
        content = read_file_content(database, repo_id, relative_path)
        if content is None:
            continue
        metadata = extract_jenkins_pipeline_metadata(content)
        jenkins_row = {
            "relative_path": relative_path,
            **metadata,
        }
        rows.append(jenkins_row)
    return _dedupe_rows(rows)


def _iter_jenkins_entrypoint_paths(*, database: Any, repo_id: str) -> list[str]:
    """Return repo-local Jenkins entrypoint paths, including nested Groovy helpers."""

    candidates: dict[str, str] = {}

    jenkinsfile_paths = discover_repo_files(
        database,
        repo_id,
        pattern=r"^[Jj]enkinsfile($|\..*)",
    )
    for relative_path in jenkinsfile_paths:
        key = relative_path.lower()
        candidates.setdefault(key, relative_path)

    groovy_paths = discover_repo_files(database, repo_id, suffix=".groovy")
    for relative_path in groovy_paths:
        normalized_name = Path(relative_path).name.strip().lower()
        if "jenkins" not in normalized_name:
            continue
        candidates[relative_path] = relative_path

    return [candidates[key] for key in sorted(candidates)]


def _parse_reusable_workflow_ref(value: str) -> dict[str, str] | None:
    """Parse an external reusable-workflow reference."""

    match = _REUSABLE_WORKFLOW_RE.match(value.strip())
    if match is None:
        return None
    owner = match.group("owner")
    name = match.group("repo")
    return {
        "repository": f"{owner}/{name}",
        "owner": owner,
        "name": name,
        "workflow_path": match.group("workflow_path"),
        "ref": match.group("ref"),
    }


def _extract_trigger_names(document: dict[str, Any]) -> list[str]:
    """Extract normalized trigger names from a GitHub Actions workflow document."""

    trigger_node = document.get("on")
    if trigger_node is None:
        trigger_node = document.get(True)
    if isinstance(trigger_node, str):
        return [trigger_node]
    if isinstance(trigger_node, list):
        return [item for item in trigger_node if isinstance(item, str)]
    if isinstance(trigger_node, dict):
        return [str(key) for key in trigger_node.keys()]
    return []


def _dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return unique mapping rows in input order."""

    seen: set[tuple[tuple[str, str], ...]] = set()
    deduped: list[dict[str, Any]] = []
    for row in rows:
        key = tuple(sorted((str(k), repr(v)) for k, v in row.items()))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped
