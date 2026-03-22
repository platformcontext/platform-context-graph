"""CloudFormation template classification and parsing."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ...utils.debug_log import warning_logger

_AWS_TYPE_PATTERN = re.compile(r"^AWS::\w+::\w+")


def is_cloudformation_template(doc: dict[str, Any]) -> bool:
    """Return whether the YAML document is a CloudFormation template.

    Detection rules (checked in order):
    1. Document has ``AWSTemplateFormatVersion`` key.
    2. Document has ``Resources`` key where at least one value has a
       ``Type`` matching ``AWS::*::*``.

    Args:
        doc: Parsed YAML document.

    Returns:
        ``True`` when the document looks like a CloudFormation template.
    """
    if "AWSTemplateFormatVersion" in doc:
        return True

    resources = doc.get("Resources")
    if not isinstance(resources, dict):
        return False

    return any(
        isinstance(v, dict) and isinstance(v.get("Type"), str) and _AWS_TYPE_PATTERN.match(v["Type"])
        for v in resources.values()
    )


def parse_cloudformation_template(
    doc: dict[str, Any],
    path: str,
    line_number: int,
    language_name: str,
) -> dict[str, Any]:
    """Parse a CloudFormation template into resource/parameter/output lists.

    Args:
        doc: Parsed YAML or JSON document.
        path: Source file path.
        line_number: 1-based document start line.
        language_name: Language name for the result.

    Returns:
        Dict with ``cloudformation_resources``, ``cloudformation_parameters``,
        and ``cloudformation_outputs`` lists.
    """
    resources = _parse_resources(doc, path, line_number, language_name)
    parameters = _parse_parameters(doc, path, line_number, language_name)
    outputs = _parse_outputs(doc, path, line_number, language_name)

    return {
        "cloudformation_resources": resources,
        "cloudformation_parameters": parameters,
        "cloudformation_outputs": outputs,
    }


def _parse_resources(
    doc: dict[str, Any],
    path: str,
    line_number: int,
    language_name: str,
) -> list[dict[str, Any]]:
    """Extract CloudFormation resources."""
    resources_section = doc.get("Resources")
    if not isinstance(resources_section, dict):
        return []

    result: list[dict[str, Any]] = []
    for logical_id, body in resources_section.items():
        if not isinstance(body, dict):
            continue
        resource_type = body.get("Type", "")
        if not isinstance(resource_type, str):
            continue

        node: dict[str, Any] = {
            "name": logical_id,
            "resource_type": resource_type,
            "line_number": line_number,
            "path": path,
            "lang": language_name,
        }

        # Extract condition if present
        condition = body.get("Condition")
        if condition:
            node["condition"] = str(condition)

        # Summarize DependsOn
        depends_on = body.get("DependsOn")
        if depends_on:
            if isinstance(depends_on, list):
                node["depends_on"] = ",".join(str(d) for d in depends_on)
            else:
                node["depends_on"] = str(depends_on)

        result.append(node)

    return result


def _parse_parameters(
    doc: dict[str, Any],
    path: str,
    line_number: int,
    language_name: str,
) -> list[dict[str, Any]]:
    """Extract CloudFormation parameters."""
    params_section = doc.get("Parameters")
    if not isinstance(params_section, dict):
        return []

    result: list[dict[str, Any]] = []
    for name, body in params_section.items():
        if not isinstance(body, dict):
            continue

        node: dict[str, Any] = {
            "name": name,
            "line_number": line_number,
            "path": path,
            "lang": language_name,
            "param_type": body.get("Type", "String"),
        }

        description = body.get("Description")
        if description:
            node["description"] = str(description)

        default = body.get("Default")
        if default is not None:
            node["default"] = str(default)

        allowed_values = body.get("AllowedValues")
        if allowed_values and isinstance(allowed_values, list):
            node["allowed_values"] = ",".join(str(v) for v in allowed_values)

        result.append(node)

    return result


def _parse_outputs(
    doc: dict[str, Any],
    path: str,
    line_number: int,
    language_name: str,
) -> list[dict[str, Any]]:
    """Extract CloudFormation outputs."""
    outputs_section = doc.get("Outputs")
    if not isinstance(outputs_section, dict):
        return []

    result: list[dict[str, Any]] = []
    for name, body in outputs_section.items():
        if not isinstance(body, dict):
            continue

        node: dict[str, Any] = {
            "name": name,
            "line_number": line_number,
            "path": path,
            "lang": language_name,
        }

        description = body.get("Description")
        if description:
            node["description"] = str(description)

        value = body.get("Value")
        if value is not None:
            node["value"] = str(value)

        export = body.get("Export")
        if isinstance(export, dict):
            export_name = export.get("Name")
            if export_name is not None:
                node["export_name"] = str(export_name)

        condition = body.get("Condition")
        if condition:
            node["condition"] = str(condition)

        result.append(node)

    return result


def parse_cloudformation_json(
    path: Path,
    language_name: str,
) -> dict[str, Any] | None:
    """Parse a JSON CloudFormation template.

    Args:
        path: File path to the JSON template.
        language_name: Language name for the result.

    Returns:
        Parsed template data, or ``None`` when the file is not a
        CloudFormation JSON template.
    """
    try:
        content = path.read_text(encoding="utf-8")
        doc = json.loads(content)
    except (OSError, json.JSONDecodeError) as exc:
        warning_logger(f"Cannot parse JSON CFN template {path}: {exc}")
        return None

    if not isinstance(doc, dict):
        return None

    if not is_cloudformation_template(doc):
        return None

    return parse_cloudformation_template(doc, str(path), 1, language_name)
