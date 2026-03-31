"""Evidence-bearing file mutations for the api-node-boats scan phase."""

from __future__ import annotations

from pathlib import Path

_WORKFLOW_MARKER_BLOCK = "\n".join(
    [
        "      pcg_e2e_marker:",
        "        description: synthetic scan-phase marker",
        "        required: false",
        "        default: scan-phase",
    ]
)
_TERRAFORM_MARKER_LINE = '  pcg_e2e_marker = "scan-phase"'


def apply_workflow_mutation(workflow_path: Path) -> None:
    """Inject one workflow-dispatch input marker if it is absent."""

    content = workflow_path.read_text(encoding="utf-8")
    if "pcg_e2e_marker" in content:
        return
    target = "      environment:\n        required: true"
    if target not in content:
        raise ValueError(f"Could not find workflow input anchor in {workflow_path}")
    workflow_path.write_text(
        content.replace(target, f"{target}\n{_WORKFLOW_MARKER_BLOCK}", 1),
        encoding="utf-8",
    )


def apply_terraform_mutation(terraform_path: Path) -> None:
    """Inject one parseable terraform marker inside the api_node_boats module."""

    content = terraform_path.read_text(encoding="utf-8")
    if "pcg_e2e_marker" in content:
        return
    target = '  name = "api-node-boats"'
    if target not in content:
        raise ValueError(f"Could not find terraform module anchor in {terraform_path}")
    terraform_path.write_text(
        content.replace(target, f"{target}\n{_TERRAFORM_MARKER_LINE}", 1),
        encoding="utf-8",
    )
