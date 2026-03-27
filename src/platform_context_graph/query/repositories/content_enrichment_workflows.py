"""Workflow enrichment helpers for repository context summaries."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

import yaml

from ...tools.languages.groovy_support import extract_jenkins_pipeline_metadata

_WORKFLOW_SUFFIXES = {".yml", ".yaml"}
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
) -> dict[str, Any]:
    """Extract GitHub Actions and Jenkins workflow hints from one repository."""

    repo_root = _repo_root(repository)
    if repo_root is None:
        return {}

    github_actions = _extract_github_actions(
        repo_root=repo_root,
        resolve_repository=resolve_repository,
    )
    jenkins = _extract_jenkinsfiles(repo_root)
    if not github_actions and not jenkins:
        return {}

    result: dict[str, Any] = {}
    if github_actions:
        result["github_actions"] = github_actions
    if jenkins:
        result["jenkins"] = jenkins
    return result


def _repo_root(repository: dict[str, Any]) -> Path | None:
    """Return the local repository path when it exists on disk."""

    raw_path = repository.get("local_path") or repository.get("path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None
    repo_root = Path(raw_path)
    if not repo_root.exists() or not repo_root.is_dir():
        return None
    return repo_root


def _extract_github_actions(
    *,
    repo_root: Path,
    resolve_repository: Callable[[str], dict[str, Any] | None],
) -> dict[str, Any]:
    """Extract repo-local GitHub Actions workflow and automation handoff hints."""

    workflows_dir = repo_root / ".github" / "workflows"
    if not workflows_dir.exists():
        return {}

    workflow_rows: list[dict[str, Any]] = []
    reusable_rows: list[dict[str, Any]] = []
    command_rows: list[dict[str, Any]] = []

    for workflow_path in sorted(workflows_dir.iterdir()):
        if workflow_path.suffix.lower() not in _WORKFLOW_SUFFIXES:
            continue
        parsed = _load_yaml_file(workflow_path)
        if not isinstance(parsed, dict):
            continue

        reusable_workflows = _extract_reusable_workflows(parsed)
        workflow_rows.append(
            {
                "name": str(parsed.get("name") or workflow_path.name),
                "relative_path": str(workflow_path.relative_to(repo_root)),
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
    repo_root = _repo_root(resolved or {})
    if repo_root is None:
        return []

    automation_file = repo_root / workflow_path
    parsed = _load_yaml_file(automation_file)
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


def _extract_jenkinsfiles(repo_root: Path) -> list[dict[str, Any]]:
    """Extract Jenkins pipeline hints from Jenkinsfile-style files."""

    rows: list[dict[str, Any]] = []
    patterns = ("Jenkinsfile", "Jenkinsfile.*", "jenkinsfile", "jenkinsfile.*")
    for pattern in patterns:
        for file_path in sorted(repo_root.glob(pattern)):
            if not file_path.is_file():
                continue
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            metadata = extract_jenkins_pipeline_metadata(content)
            rows.append(
                {
                    "relative_path": str(file_path.relative_to(repo_root)),
                    **metadata,
                }
            )
    return _dedupe_rows(rows)


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


def _load_yaml_file(path: Path) -> dict[str, Any] | None:
    """Load one YAML file into a dict when possible."""

    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    return document if isinstance(document, dict) else None


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
