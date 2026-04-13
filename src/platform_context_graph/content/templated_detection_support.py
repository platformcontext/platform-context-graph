"""Constants, patterns, and helpers for templated infrastructure file detection."""

from __future__ import annotations

from pathlib import Path
import re

GENERATED_DIRS = frozenset(
    {
        ".git",
        ".terraform",
        ".terragrunt-cache",
        ".venv",
        ".worktrees",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "vendor",
    }
)
YAML_SUFFIXES = {".yaml", ".yml"}
HCL_SUFFIXES = {".hcl", ".tf", ".tfvars"}
JINJA_TEMPLATE_SUFFIXES = {".jinja", ".jinja2", ".j2"}
TERRAFORM_TEMPLATE_SUFFIXES = {".tpl", ".tftpl"}
RAW_CONFIG_SUFFIXES = {".conf", ".cfg", ".cnf"}
TEXT_SUFFIXES = (
    YAML_SUFFIXES
    | HCL_SUFFIXES
    | JINJA_TEMPLATE_SUFFIXES
    | {".kcl"}
    | TERRAFORM_TEMPLATE_SUFFIXES
    | RAW_CONFIG_SUFFIXES
)
TEXT_FILENAMES = {
    "dockerfile",
    "compose.yaml",
    "compose.yml",
    "docker-compose.yaml",
    "docker-compose.yml",
}
GO_EXPRESSION_RE = re.compile(r"(?<!\$)\{\{[-~]?.*?[-~]?\}\}", re.DOTALL)
JINJA_STATEMENT_RE = re.compile(r"\{%-?.*?-?%\}|\{#.*?#\}", re.DOTALL)
GITHUB_ACTIONS_EXPR_RE = re.compile(r"\$\{\{.*?\}\}", re.DOTALL)
GO_CONTEXT_RE = re.compile(r"\{\{[-~]?\s*(?:\.|\$)")
GO_LINE_CONTROL_RE = re.compile(
    r"(?m)^\s*\{\{[-~]?\s*(if|else|end|with|range|define|template|block)\b"
)
GO_HINT_RE = re.compile(r"\b(include|toYaml|nindent|tpl)\b")
TF_INTERPOLATION_RE = re.compile(r"(?<!\$)\$\{")
TF_DIRECTIVE_RE = re.compile(r"(?<!%)%\{")
TF_TEMPLATEFILE_RE = re.compile(r"\btemplatefile\s*\(")


def suffixes(relative_path: Path) -> tuple[str, ...]:
    """Return normalized lowercase suffixes for a path."""
    return tuple(suffix.lower() for suffix in relative_path.suffixes)


def artifact_type(root_family: str, relative_path: Path) -> str:
    """Infer a coarse artifact type for reporting.

    Args:
        root_family: Production classification family of the file's root.
        relative_path: Repo-relative path of the file.

    Returns:
        Coarse artifact type string such as ``"terraform_hcl"`` or
        ``"yaml_document"``.
    """
    name = relative_path.name.lower()
    parts = {part.lower() for part in relative_path.parts}
    sfxs = suffixes(relative_path)
    is_template_suffix = bool(
        sfxs and sfxs[-1] in JINJA_TEMPLATE_SUFFIXES | TERRAFORM_TEMPLATE_SUFFIXES
    )

    if ".github" in parts and "workflows" in parts:
        return "github_actions_workflow"
    if name == "dockerfile" or name.startswith("dockerfile."):
        return "dockerfile"
    if name in {
        "compose.yaml",
        "compose.yml",
        "docker-compose.yaml",
        "docker-compose.yml",
    }:
        return "docker_compose"
    if RAW_CONFIG_SUFFIXES.intersection(sfxs):
        if "apache" in parts or "httpd" in parts or "mods-available" in parts:
            return "apache_config_template" if is_template_suffix else "apache_config"
        if "nginx" in parts:
            return "nginx_config_template" if is_template_suffix else "nginx_config"
        return "generic_config_template" if is_template_suffix else "generic_config"
    if any(s in YAML_SUFFIXES for s in sfxs) and any(
        s in JINJA_TEMPLATE_SUFFIXES for s in sfxs
    ):
        return "yaml_template"
    if sfxs and sfxs[-1] in JINJA_TEMPLATE_SUFFIXES:
        if root_family == "terraform":
            return "terraform_template_text"
        return "jinja_text_template"
    if sfxs and sfxs[-1] in TERRAFORM_TEMPLATE_SUFFIXES:
        return (
            "terraform_template_text" if root_family == "terraform" else "text_template"
        )
    if any(s in HCL_SUFFIXES for s in sfxs):
        return "terraform_hcl"
    if any(s in YAML_SUFFIXES for s in sfxs):
        return "yaml_document"
    return "plain_text"


def is_raw_ingest_candidate(*, artifact_type_val: str, bucket: str) -> bool:
    """Return whether the file is a raw-text indexing gap today.

    Args:
        artifact_type_val: Artifact type assigned during classification.
        bucket: Classification bucket name.

    Returns:
        ``True`` when the file falls into a raw-text indexing gap.
    """
    return (
        artifact_type_val
        in {
            "apache_config",
            "apache_config_template",
            "dockerfile",
            "generic_config_template",
            "generic_config",
            "jinja_text_template",
            "nginx_config",
            "nginx_config_template",
            "terraform_template_text",
            "text_template",
        }
        or bucket == "plain_text"
    )


def is_iac_relevant(
    *,
    root_family: str,
    relative_path: Path,
    artifact_type_val: str,
    bucket: str,
) -> bool:
    """Return whether the file is IaC-relevant for reporting.

    Args:
        root_family: Production classification family.
        relative_path: Repo-relative path of the file.
        artifact_type_val: Artifact type assigned during classification.
        bucket: Classification bucket name.

    Returns:
        ``True`` when the file is considered infrastructure-as-code relevant.
    """
    if artifact_type_val == "github_actions_workflow":
        return False
    if root_family in {"helm_argo", "ansible_jinja", "terraform"}:
        return True
    if artifact_type_val in {
        "apache_config",
        "apache_config_template",
        "docker_compose",
        "dockerfile",
        "nginx_config",
        "nginx_config_template",
        "terraform_template_text",
        "yaml_template",
        "generic_config_template",
    }:
        return True
    if bucket in {
        "go_template_yaml",
        "jinja_yaml",
        "terraform_hcl",
        "terraform_hcl_templated",
    }:
        return True
    return "iac" in {part.lower() for part in relative_path.parts}
