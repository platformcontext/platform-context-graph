"""CloudFormation template classification and parsing."""

from __future__ import annotations

import re
from typing import Any

_AWS_TYPE_PATTERN = re.compile(r"^AWS::\w+::\w+")
_SAM_SERVERLESS_PATTERN = re.compile(r"^AWS::Serverless::\w+")
_SAM_TRANSFORM = "AWS::Serverless-2016-10-31"


def is_cloudformation_template(doc: dict[str, Any]) -> bool:
    """Return whether the YAML document is a CloudFormation template.

    Detection rules (checked in order):
    1. Document has ``AWSTemplateFormatVersion`` key.
    2. Document has a ``Transform`` value of ``AWS::Serverless-2016-10-31``
       (SAM template).
    3. Document has ``Resources`` key where at least one value has a
       ``Type`` matching ``AWS::*::*`` or ``AWS::Serverless::*``.

    Args:
        doc: Parsed YAML document.

    Returns:
        ``True`` when the document looks like a CloudFormation or SAM template.
    """
    if "AWSTemplateFormatVersion" in doc:
        return True

    transform = doc.get("Transform")
    if transform == _SAM_TRANSFORM:
        return True
    if isinstance(transform, list) and _SAM_TRANSFORM in transform:
        return True

    resources = doc.get("Resources")
    if not isinstance(resources, dict):
        return False

    return any(
        isinstance(v, dict)
        and isinstance(v.get("Type"), str)
        and (
            _AWS_TYPE_PATTERN.match(v["Type"])
            or _SAM_SERVERLESS_PATTERN.match(v["Type"])
        )
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
        ``cloudformation_outputs``, ``cloudformation_cross_stack_imports``,
        and ``cloudformation_cross_stack_exports`` lists.
    """
    resources = _parse_resources(doc, path, line_number, language_name)
    parameters = _parse_parameters(doc, path, line_number, language_name)
    outputs = _parse_outputs(doc, path, line_number, language_name)
    cross_stack_imports, cross_stack_exports = _parse_cross_stack_references(
        doc, path, line_number, language_name
    )

    return {
        "cloudformation_resources": resources,
        "cloudformation_parameters": parameters,
        "cloudformation_outputs": outputs,
        "cloudformation_cross_stack_imports": cross_stack_imports,
        "cloudformation_cross_stack_exports": cross_stack_exports,
    }


def _parse_resources(
    doc: dict[str, Any],
    path: str,
    line_number: int,
    language_name: str,
) -> list[dict[str, Any]]:
    """Extract CloudFormation resources, including Lambda and SAM specifics."""
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

        props = body.get("Properties") or {}
        if isinstance(props, dict):
            if resource_type == "AWS::Lambda::Function":
                _extract_lambda_function_props(node, props)
            elif resource_type == "AWS::Serverless::Function":
                _extract_sam_function_props(node, props)
            elif resource_type in (
                "AWS::ApiGateway::Method",
                "AWS::ApiGatewayV2::Integration",
            ):
                _extract_apigw_integration_props(node, props)

        result.append(node)

    return result


def _extract_lambda_function_props(node: dict[str, Any], props: dict[str, Any]) -> None:
    """Populate ``node`` with Lambda-specific properties from ``props``.

    Handles ``AWS::Lambda::Function`` resource properties.

    Args:
        node: Resource node dict to mutate in place.
        props: The ``Properties`` sub-dict from the resource body.
    """
    handler = props.get("Handler")
    if handler is not None:
        node["handler"] = str(handler)

    runtime = props.get("Runtime")
    if runtime is not None:
        node["runtime"] = str(runtime)

    code = props.get("Code")
    if isinstance(code, dict):
        s3_key = code.get("S3Key")
        s3_bucket = code.get("S3Bucket")
        if s3_bucket is not None and s3_key is not None:
            node["code_uri"] = f"s3://{s3_bucket}/{s3_key}"
        elif s3_key is not None:
            node["code_uri"] = str(s3_key)

    memory_size = props.get("MemorySize")
    if memory_size is not None:
        node["memory_size"] = str(memory_size)

    timeout = props.get("Timeout")
    if timeout is not None:
        node["timeout"] = str(timeout)

    environment = props.get("Environment")
    if isinstance(environment, dict):
        variables = environment.get("Variables")
        if isinstance(variables, dict) and variables:
            node["environment_variables"] = ",".join(sorted(str(k) for k in variables))

    layers = props.get("Layers")
    if isinstance(layers, list) and layers:
        node["layers"] = ",".join(sorted(str(layer) for layer in layers))


def _extract_sam_function_props(node: dict[str, Any], props: dict[str, Any]) -> None:
    """Populate ``node`` with SAM function properties from ``props``.

    Handles ``AWS::Serverless::Function`` resource properties per the SAM
    specification (``Transform: AWS::Serverless-2016-10-31``).

    Args:
        node: Resource node dict to mutate in place.
        props: The ``Properties`` sub-dict from the resource body.
    """
    handler = props.get("Handler")
    if handler is not None:
        node["handler"] = str(handler)

    runtime = props.get("Runtime")
    if runtime is not None:
        node["runtime"] = str(runtime)

    code_uri = props.get("CodeUri")
    if code_uri is not None:
        node["code_uri"] = str(code_uri)

    memory_size = props.get("MemorySize")
    if memory_size is not None:
        node["memory_size"] = str(memory_size)

    timeout = props.get("Timeout")
    if timeout is not None:
        node["timeout"] = str(timeout)

    environment = props.get("Environment")
    if isinstance(environment, dict):
        variables = environment.get("Variables")
        if isinstance(variables, dict) and variables:
            node["environment_variables"] = ",".join(sorted(str(k) for k in variables))

    events = props.get("Events")
    if isinstance(events, dict) and events:
        event_types = []
        for _event_id, event_body in events.items():
            if isinstance(event_body, dict):
                event_type = event_body.get("Type")
                if event_type is not None:
                    event_types.append(str(event_type))
        if event_types:
            node["events"] = ",".join(sorted(event_types))


def _extract_apigw_integration_props(
    node: dict[str, Any], props: dict[str, Any]
) -> None:
    """Populate ``node`` with API Gateway integration URI from ``props``.

    Handles both ``AWS::ApiGateway::Method`` (REST API) and
    ``AWS::ApiGatewayV2::Integration`` (HTTP/WebSocket API) resources.

    For ``AWS::ApiGateway::Method``, the URI lives at
    ``Properties.Integration.Uri``.
    For ``AWS::ApiGatewayV2::Integration``, it lives at
    ``Properties.IntegrationUri``.

    Args:
        node: Resource node dict to mutate in place.
        props: The ``Properties`` sub-dict from the resource body.
    """
    integration = props.get("Integration")
    if isinstance(integration, dict):
        uri = integration.get("Uri")
        if uri is not None:
            node["integration_uri"] = str(uri)

    integration_uri = props.get("IntegrationUri")
    if integration_uri is not None:
        node["integration_uri"] = str(integration_uri)


def _collect_import_values(obj: Any, collected: list[str]) -> None:
    """Recursively walk ``obj`` and collect all ``Fn::ImportValue`` operands.

    Args:
        obj: Arbitrary nested structure (dict, list, or scalar).
        collected: List to append found import values to (mutated in place).
    """
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == "Fn::ImportValue":
                collected.append(str(value))
            else:
                _collect_import_values(value, collected)
    elif isinstance(obj, list):
        for item in obj:
            _collect_import_values(item, collected)


def _parse_cross_stack_references(
    doc: dict[str, Any],
    path: str,
    line_number: int,
    language_name: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Extract cross-stack import and export references from the template.

    Imports are ``Fn::ImportValue`` intrinsic function calls found anywhere
    inside the ``Resources`` section.  Exports are ``Export.Name`` values
    declared in the ``Outputs`` section.

    Args:
        doc: Parsed YAML or JSON document.
        path: Source file path.
        line_number: 1-based document start line.
        language_name: Language name for the result.

    Returns:
        A 2-tuple of ``(imports, exports)`` where each element is a list of
        dicts with at least ``name``, ``path``, ``line_number``, and ``lang``
        keys.
    """
    imports: list[dict[str, Any]] = []
    exports: list[dict[str, Any]] = []

    resources_section = doc.get("Resources")
    if isinstance(resources_section, dict):
        raw_imports: list[str] = []
        _collect_import_values(resources_section, raw_imports)
        for import_name in raw_imports:
            imports.append(
                {
                    "name": import_name,
                    "path": path,
                    "line_number": line_number,
                    "lang": language_name,
                }
            )

    outputs_section = doc.get("Outputs")
    if isinstance(outputs_section, dict):
        for _output_id, body in outputs_section.items():
            if not isinstance(body, dict):
                continue
            export = body.get("Export")
            if not isinstance(export, dict):
                continue
            export_name = export.get("Name")
            if export_name is None:
                continue
            exports.append(
                {
                    "name": str(export_name),
                    "path": path,
                    "line_number": line_number,
                    "lang": language_name,
                }
            )

    return imports, exports


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
