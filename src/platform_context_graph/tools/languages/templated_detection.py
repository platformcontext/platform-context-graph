"""Dialect detection helpers for templated infrastructure files."""

from dataclasses import dataclass
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
TEXT_SUFFIXES = YAML_SUFFIXES | HCL_SUFFIXES | JINJA_TEMPLATE_SUFFIXES | {
    ".kcl"
} | TERRAFORM_TEMPLATE_SUFFIXES | RAW_CONFIG_SUFFIXES
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


@dataclass(frozen=True, slots=True)
class FileClassification:
    """Describe one authored file classified by dialect heuristics."""

    relative_path: Path
    bucket: str
    dialects: tuple[str, ...]
    ambiguous: bool
    marker_count: int
    marker_density: float
    renderability_hint: str
    artifact_type: str
    raw_ingest_candidate: bool
    iac_relevant: bool


@dataclass(frozen=True, slots=True)
class ContentMetadata:
    """Persisted metadata attached to indexed file and entity content rows."""

    artifact_type: str | None
    template_dialect: str | None
    iac_relevant: bool


def exclusion_reason(relative_path: Path, *, include_generated: bool) -> str | None:
    """Return the generated-directory reason for excluding a file, if any."""

    if include_generated:
        return None
    for part in relative_path.parts:
        if part in GENERATED_DIRS:
            return part
    return None


def infer_content_metadata(*, relative_path: Path, content: str) -> ContentMetadata:
    """Infer persisted content metadata without requiring inventory-only context."""

    if not is_candidate_text_file(relative_path):
        return ContentMetadata(
            artifact_type=None,
            template_dialect=None,
            iac_relevant=False,
        )

    classification = classify_file(
        root_family=_infer_root_family(relative_path, content),
        relative_path=relative_path,
        content=content,
    )
    return ContentMetadata(
        artifact_type=_persisted_artifact_type(classification),
        template_dialect=_persisted_template_dialect(classification),
        iac_relevant=classification.iac_relevant,
    )


def is_candidate_text_file(path: Path) -> bool:
    """Return whether the path should be included in the inventory scan."""

    name = path.name.lower()
    return name in TEXT_FILENAMES or path.suffix.lower() in TEXT_SUFFIXES


def _infer_root_family(relative_path: Path, content: str) -> str:
    """Infer a production classification family from path and content hints."""

    parts = {part.lower() for part in relative_path.parts}
    name = relative_path.name.lower()
    suffixes = _suffixes(relative_path)
    go_expression_match = GO_EXPRESSION_RE.search(content)
    has_tf_markers = bool(
        TF_INTERPOLATION_RE.search(content)
        or TF_DIRECTIVE_RE.search(content)
        or TF_TEMPLATEFILE_RE.search(content)
    )
    if any(suffix in HCL_SUFFIXES for suffix in suffixes):
        return "terraform"
    if has_tf_markers and any(
        suffix in TERRAFORM_TEMPLATE_SUFFIXES | JINJA_TEMPLATE_SUFFIXES
        for suffix in suffixes
    ) and not (go_expression_match or JINJA_STATEMENT_RE.search(content)):
        return "terraform"
    if (
        suffixes
        and suffixes[-1] == ".tpl"
        and "templates" in parts
        and go_expression_match
        and (
            name == "_helpers.tpl"
            or any(
                marker in content
                for marker in (
                    ".Chart",
                    ".Release",
                    ".Values",
                    '{{ include "',
                    '{{- include "',
                    '{{ define "',
                    '{{- define "',
                )
            )
        )
    ):
        return "helm_argo"
    if (
        name == "chart.yaml"
        or name.startswith("values.")
        or ("chart" in parts and "templates" in parts)
        or "argocd" in parts
    ):
        return "helm_argo"
    if {
        "roles",
        "playbooks",
        "handlers",
        "tasks",
        "group_vars",
        "host_vars",
        "inventory",
        "inventories",
    } & parts:
        return "ansible_jinja"
    if {"dagster", "assets", "data_quality", "data_lakehouse"} & parts:
        return "dagster_jinja"
    return "generic"


def _suffixes(relative_path: Path) -> tuple[str, ...]:
    """Return normalized suffixes for a path."""

    return tuple(suffix.lower() for suffix in relative_path.suffixes)


def _artifact_type(root_family: str, relative_path: Path) -> str:
    """Infer a coarse artifact type for reporting."""

    name = relative_path.name.lower()
    parts = {part.lower() for part in relative_path.parts}
    suffixes = _suffixes(relative_path)
    is_template_suffix = bool(
        suffixes
        and suffixes[-1] in JINJA_TEMPLATE_SUFFIXES | TERRAFORM_TEMPLATE_SUFFIXES
    )

    if ".github" in parts and "workflows" in parts:
        return "github_actions_workflow"
    if name == "dockerfile" or name.startswith("dockerfile."):
        return "dockerfile"
    if name in {"compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml"}:
        return "docker_compose"
    if RAW_CONFIG_SUFFIXES.intersection(suffixes):
        if "apache" in parts or "httpd" in parts or "mods-available" in parts:
            return "apache_config_template" if is_template_suffix else "apache_config"
        if "nginx" in parts:
            return "nginx_config_template" if is_template_suffix else "nginx_config"
        return "generic_config_template" if is_template_suffix else "generic_config"
    if any(suffix in YAML_SUFFIXES for suffix in suffixes) and any(
        suffix in JINJA_TEMPLATE_SUFFIXES for suffix in suffixes
    ):
        return "yaml_template"
    if suffixes and suffixes[-1] in JINJA_TEMPLATE_SUFFIXES:
        if root_family == "terraform":
            return "terraform_template_text"
        return "jinja_text_template"
    if suffixes and suffixes[-1] in TERRAFORM_TEMPLATE_SUFFIXES:
        return "terraform_template_text" if root_family == "terraform" else "text_template"
    if any(suffix in HCL_SUFFIXES for suffix in suffixes):
        return "terraform_hcl"
    if any(suffix in YAML_SUFFIXES for suffix in suffixes):
        return "yaml_document"
    return "plain_text"


def _persisted_artifact_type(classification: FileClassification) -> str | None:
    """Map inventory classification buckets to persisted content metadata."""

    if classification.bucket == "helm_helper_tpl":
        return "helm_helper_tpl"
    if classification.bucket == "go_template_yaml":
        return "go_template_yaml"
    if classification.bucket == "jinja_yaml":
        return "jinja_yaml"
    if classification.bucket in {"terraform_hcl", "terraform_hcl_templated"}:
        return "terraform_hcl"
    if classification.artifact_type in {"plain_text", "yaml_document"}:
        return (
            classification.artifact_type
            if classification.iac_relevant or classification.dialects
            else None
        )
    return classification.artifact_type


def _persisted_template_dialect(classification: FileClassification) -> str | None:
    """Normalize detected dialects for persisted content metadata."""

    if classification.ambiguous or not classification.dialects:
        return None
    dialect = classification.dialects[0]
    if dialect == "jinja_template":
        return "jinja"
    return dialect


def _is_raw_ingest_candidate(*, artifact_type: str, bucket: str) -> bool:
    """Return whether the file is a raw-text indexing gap today."""

    return artifact_type in {
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
    } or bucket == "plain_text"


def _is_iac_relevant(
    *,
    root_family: str,
    relative_path: Path,
    artifact_type: str,
    bucket: str,
) -> bool:
    """Return whether the file is IaC-relevant for reporting."""

    if artifact_type == "github_actions_workflow":
        return False
    if root_family in {"helm_argo", "ansible_jinja", "terraform"}:
        return True
    if artifact_type in {
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


def classify_file(
    *,
    root_family: str,
    relative_path: Path,
    content: str,
) -> FileClassification:
    """Classify one file by path and templating heuristics."""

    suffix = relative_path.suffix.lower()
    suffixes = _suffixes(relative_path)
    artifact_type = _artifact_type(root_family, relative_path)
    lowered_content = content.lower()
    if artifact_type in {"generic_config", "generic_config_template"}:
        is_template_config = artifact_type.endswith("_template")
        if any(
            token in lowered_content
            for token in ("server {", "fastcgi_pass", "proxy_pass", "location /")
        ):
            artifact_type = (
                "nginx_config_template" if is_template_config else "nginx_config"
            )
        elif any(
            token in lowered_content
            for token in (
                "<virtualhost",
                "rewriterule",
                "documentroot",
                "servername ",
            )
        ):
            artifact_type = (
                "apache_config_template" if is_template_config else "apache_config"
            )
    yaml_template = (
        len(suffixes) >= 2
        and suffixes[-1] in JINJA_TEMPLATE_SUFFIXES
        and suffixes[-2] in YAML_SUFFIXES
    )
    line_count = max(content.count("\n") + 1, 1)
    go_expressions = GO_EXPRESSION_RE.findall(content)
    go_expression_count = len(go_expressions)
    jinja_statement_count = len(JINJA_STATEMENT_RE.findall(content))
    github_actions_count = len(GITHUB_ACTIONS_EXPR_RE.findall(content))
    go_context_count = len(GO_CONTEXT_RE.findall(content))
    go_line_control_count = len(GO_LINE_CONTROL_RE.findall(content))
    go_hint_count = sum(len(GO_HINT_RE.findall(expr)) for expr in go_expressions)
    tf_interpolation_count = len(TF_INTERPOLATION_RE.findall(content))
    tf_directive_count = len(TF_DIRECTIVE_RE.findall(content))
    tf_templatefile_count = len(TF_TEMPLATEFILE_RE.findall(content))
    tf_marker_count = (
        tf_interpolation_count + tf_directive_count + tf_templatefile_count
    )
    marker_count = (
        go_expression_count
        + jinja_statement_count
        + github_actions_count
        + tf_marker_count
    )
    marker_density = marker_count / line_count

    def build_result(
        *,
        bucket: str,
        dialects: tuple[str, ...],
        ambiguous: bool,
        renderability_hint: str,
        count: int = marker_count,
        density: float = marker_density,
    ) -> FileClassification:
        """Create one classification result with reporting metadata applied."""

        return FileClassification(
            relative_path=relative_path,
            bucket=bucket,
            dialects=dialects,
            ambiguous=ambiguous,
            marker_count=count,
            marker_density=density,
            renderability_hint=renderability_hint,
            artifact_type=artifact_type,
            raw_ingest_candidate=_is_raw_ingest_candidate(
                artifact_type=artifact_type,
                bucket=bucket,
            ),
            iac_relevant=_is_iac_relevant(
                root_family=root_family,
                relative_path=relative_path,
                artifact_type=artifact_type,
                bucket=bucket,
            ),
        )

    if suffix == ".tpl" and root_family == "helm_argo":
        return build_result(
            bucket="helm_helper_tpl",
            dialects=("go_template",),
            ambiguous=False,
            renderability_hint="context_required",
        )

    if yaml_template:
        suffix = suffixes[-2]

    if suffix in JINJA_TEMPLATE_SUFFIXES and root_family == "terraform":
        template_count = max(tf_marker_count, marker_count)
        return build_result(
            bucket="unknown_templated",
            dialects=("terraform_template",),
            ambiguous=False,
            renderability_hint="context_required",
            count=template_count,
            density=template_count / line_count,
        )

    if suffix in JINJA_TEMPLATE_SUFFIXES:
        return build_result(
            bucket="unknown_templated",
            dialects=("jinja_template",),
            ambiguous=False,
            renderability_hint="context_required",
        )

    if suffix in TERRAFORM_TEMPLATE_SUFFIXES and root_family == "terraform":
        template_count = max(tf_marker_count, marker_count)
        return build_result(
            bucket="unknown_templated",
            dialects=("terraform_template",),
            ambiguous=False,
            renderability_hint="context_required",
            count=template_count,
            density=template_count / line_count,
        )

    if suffix in HCL_SUFFIXES:
        bucket = "terraform_hcl_templated" if tf_marker_count else "terraform_hcl"
        dialects = ("terraform_template",) if tf_marker_count else ()
        renderability = "context_required" if tf_marker_count else "raw_only"
        return build_result(
            bucket=bucket,
            dialects=dialects,
            ambiguous=False,
            renderability_hint=renderability,
            count=tf_marker_count,
            density=tf_marker_count / line_count,
        )

    if suffix not in YAML_SUFFIXES and suffix != ".kcl":
        return build_result(
            bucket="unknown_templated" if marker_count else "plain_text",
            dialects=(),
            ambiguous=False,
            renderability_hint="context_required" if marker_count else "raw_only",
        )

    explicit_go = bool(go_line_control_count or go_hint_count or go_context_count)
    explicit_jinja = bool(jinja_statement_count)
    has_curly_expressions = bool(go_expression_count)
    has_github_actions = bool(github_actions_count)

    if has_github_actions and not (explicit_go or explicit_jinja or has_curly_expressions):
        return build_result(
            bucket="unknown_templated",
            dialects=("github_actions",),
            ambiguous=False,
            renderability_hint="context_required",
        )

    if not (explicit_go or explicit_jinja or has_curly_expressions):
        return build_result(
            bucket="plain_yaml",
            dialects=(),
            ambiguous=False,
            renderability_hint="raw_only",
            count=0,
            density=0.0,
        )

    if explicit_go and explicit_jinja:
        return build_result(
            bucket="unknown_templated",
            dialects=("go_template", "jinja"),
            ambiguous=True,
            renderability_hint="raw_only",
        )

    if root_family in {"ansible_jinja", "dagster_jinja"}:
        if explicit_go:
            return build_result(
                bucket="unknown_templated",
                dialects=("go_template", "jinja"),
                ambiguous=True,
                renderability_hint="raw_only",
            )
        return build_result(
            bucket="jinja_yaml",
            dialects=("jinja",),
            ambiguous=False,
            renderability_hint="context_required",
        )

    if root_family == "helm_argo":
        if explicit_jinja:
            return build_result(
                bucket="unknown_templated",
                dialects=("go_template", "jinja"),
                ambiguous=True,
                renderability_hint="raw_only",
            )
        return build_result(
            bucket="go_template_yaml",
            dialects=("go_template",),
            ambiguous=False,
            renderability_hint="context_required",
        )

    if explicit_jinja and has_curly_expressions:
        dialects = ("go_template", "jinja")
    elif explicit_jinja:
        dialects = ("jinja",)
    elif explicit_go:
        dialects = ("go_template",)
    elif has_curly_expressions:
        dialects = ("go_template", "jinja")
    else:
        dialects = ()

    if len(dialects) == 1:
        bucket = "go_template_yaml" if dialects[0] == "go_template" else "jinja_yaml"
        ambiguous = False
        renderability_hint = "context_required"
    else:
        bucket = "unknown_templated"
        ambiguous = True
        renderability_hint = "raw_only"

    return build_result(
        bucket=bucket,
        dialects=dialects,
        ambiguous=ambiguous,
        renderability_hint=renderability_hint,
    )
