"""Tree-sitter helpers for HCL, Terraform, and Terragrunt parsing."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def parse_hcl_document(
    root_node: Any,
    source_bytes: bytes,
    *,
    path: str,
    is_terragrunt: bool,
) -> dict[str, Any]:
    """Parse one HCL syntax tree into normalized Terraform/Terragrunt buckets."""

    result = _base_result(path)
    body = _body_node(root_node)
    if body is None:
        return result

    blocks = [child for child in body.children if child.type == "block"]
    attributes = [child for child in body.children if child.type == "attribute"]

    if is_terragrunt:
        result["terragrunt_configs"].append(
            _parse_terragrunt_config(blocks, attributes, source_bytes, path)
        )
        return result

    provider_metadata = _collect_required_provider_metadata(blocks, source_bytes)

    for block in blocks:
        identifier = _block_identifier(block, source_bytes)
        if identifier == "resource":
            resource = _parse_resource_block(block, source_bytes, path)
            if resource is not None:
                result["terraform_resources"].append(resource)
        elif identifier == "variable":
            variable = _parse_variable_block(block, source_bytes, path)
            if variable is not None:
                result["terraform_variables"].append(variable)
        elif identifier == "output":
            output = _parse_output_block(block, source_bytes, path)
            if output is not None:
                result["terraform_outputs"].append(output)
        elif identifier == "module":
            module = _parse_module_block(block, source_bytes, path)
            if module is not None:
                result["terraform_modules"].append(module)
        elif identifier == "data":
            data_source = _parse_data_block(block, source_bytes, path)
            if data_source is not None:
                result["terraform_data_sources"].append(data_source)
        elif identifier == "provider":
            provider = _parse_provider_block(block, source_bytes, path, provider_metadata)
            if provider is not None:
                result["terraform_providers"].append(provider)
        elif identifier == "locals":
            result["terraform_locals"].extend(
                _parse_locals_block(block, source_bytes, path)
            )

    return result


def _base_result(path: str) -> dict[str, Any]:
    """Return the standard parser result shape for one HCL file."""

    return {
        "path": path,
        "lang": "hcl",
        "functions": [],
        "classes": [],
        "imports": [],
        "function_calls": [],
        "variables": [],
        "terraform_resources": [],
        "terraform_variables": [],
        "terraform_outputs": [],
        "terraform_modules": [],
        "terraform_data_sources": [],
        "terraform_providers": [],
        "terraform_locals": [],
        "terragrunt_configs": [],
    }


def _body_node(root_node: Any) -> Any | None:
    """Return the top-level body node for one parsed HCL document."""

    for child in root_node.children:
        if child.type == "body":
            return child
    return None


def _parse_resource_block(block: Any, source_bytes: bytes, path: str) -> dict[str, Any] | None:
    """Parse one Terraform ``resource`` block into a graph entity payload."""

    labels = _block_labels(block, source_bytes)
    if len(labels) < 2:
        return None
    resource_type, resource_name = labels[:2]
    return {
        "name": f"{resource_type}.{resource_name}",
        "line_number": block.start_point.row + 1,
        "resource_type": resource_type,
        "resource_name": resource_name,
        "path": path,
        "lang": "hcl",
    }


def _parse_variable_block(block: Any, source_bytes: bytes, path: str) -> dict[str, Any] | None:
    """Parse one Terraform ``variable`` block into a graph entity payload."""

    labels = _block_labels(block, source_bytes)
    if not labels:
        return None
    attrs = _attribute_map(block, source_bytes)
    return {
        "name": labels[0],
        "line_number": block.start_point.row + 1,
        "var_type": attrs.get("type", ""),
        "default": attrs.get("default", ""),
        "description": attrs.get("description", ""),
        "path": path,
        "lang": "hcl",
    }


def _parse_output_block(block: Any, source_bytes: bytes, path: str) -> dict[str, Any] | None:
    """Parse one Terraform ``output`` block into a graph entity payload."""

    labels = _block_labels(block, source_bytes)
    if not labels:
        return None
    attrs = _attribute_map(block, source_bytes)
    return {
        "name": labels[0],
        "line_number": block.start_point.row + 1,
        "description": attrs.get("description", ""),
        "value": attrs.get("value", ""),
        "path": path,
        "lang": "hcl",
    }


def _parse_module_block(block: Any, source_bytes: bytes, path: str) -> dict[str, Any] | None:
    """Parse one Terraform ``module`` block into a graph entity payload."""

    labels = _block_labels(block, source_bytes)
    if not labels:
        return None
    attrs = _attribute_map(block, source_bytes)
    return {
        "name": labels[0],
        "line_number": block.start_point.row + 1,
        "source": attrs.get("source", ""),
        "version": attrs.get("version", ""),
        "path": path,
        "lang": "hcl",
    }


def _parse_data_block(block: Any, source_bytes: bytes, path: str) -> dict[str, Any] | None:
    """Parse one Terraform ``data`` block into a graph entity payload."""

    labels = _block_labels(block, source_bytes)
    if len(labels) < 2:
        return None
    data_type, data_name = labels[:2]
    return {
        "name": f"{data_type}.{data_name}",
        "line_number": block.start_point.row + 1,
        "data_type": data_type,
        "data_name": data_name,
        "path": path,
        "lang": "hcl",
    }


def _parse_provider_block(
    block: Any,
    source_bytes: bytes,
    path: str,
    provider_metadata: dict[str, dict[str, str]],
) -> dict[str, Any] | None:
    """Parse one Terraform ``provider`` block with required-provider metadata."""

    labels = _block_labels(block, source_bytes)
    if not labels:
        return None
    name = labels[0]
    attrs = _attribute_map(block, source_bytes)
    metadata = provider_metadata.get(name, {})
    return {
        "name": name,
        "line_number": block.start_point.row + 1,
        "source": metadata.get("source", ""),
        "version": metadata.get("version", ""),
        "alias": attrs.get("alias", ""),
        "region": attrs.get("region", ""),
        "path": path,
        "lang": "hcl",
    }


def _parse_locals_block(block: Any, source_bytes: bytes, path: str) -> list[dict[str, Any]]:
    """Parse a Terraform or Terragrunt ``locals`` block into local rows."""

    rows: list[dict[str, Any]] = []
    body = _body_node(block)
    if body is None:
        return rows
    for child in body.children:
        if child.type != "attribute":
            continue
        name, value = _attribute_pair(child, source_bytes)
        if not name:
            continue
        rows.append(
            {
                "name": name,
                "line_number": child.start_point.row + 1,
                "value": value,
                "path": path,
                "lang": "hcl",
            }
        )
    return rows


def _parse_terragrunt_config(
    blocks: list[Any],
    attributes: list[Any],
    source_bytes: bytes,
    path: str,
) -> dict[str, Any]:
    """Parse one Terragrunt file into its config node payload."""

    terraform_source = ""
    include_names: list[str] = []
    locals_keys: list[str] = []

    for block in blocks:
        identifier = _block_identifier(block, source_bytes)
        if identifier == "terraform":
            terraform_source = _attribute_map(block, source_bytes).get("source", "")
        elif identifier == "include":
            include_names.extend(_block_labels(block, source_bytes))
        elif identifier == "locals":
            locals_keys.extend(item["name"] for item in _parse_locals_block(block, source_bytes, path))

    inputs_keys: list[str] = []
    for attribute in attributes:
        name, value = _attribute_pair(attribute, source_bytes)
        if name == "inputs":
            inputs_keys = _object_keys(attribute)
        elif name == "locals" and not locals_keys:
            locals_keys = _object_keys(attribute)
        del value

    return {
        "name": Path(path).stem or "terragrunt",
        "line_number": 1,
        "terraform_source": terraform_source,
        "includes": ",".join(include_names),
        "inputs": ",".join(inputs_keys),
        "locals": ",".join(locals_keys),
        "path": path,
        "lang": "hcl",
    }


def _collect_required_provider_metadata(
    blocks: list[Any], source_bytes: bytes
) -> dict[str, dict[str, str]]:
    """Extract provider source/version data from terraform.required_providers."""

    metadata: dict[str, dict[str, str]] = {}
    terraform_blocks = [
        block for block in blocks if _block_identifier(block, source_bytes) == "terraform"
    ]
    for terraform_block in terraform_blocks:
        terraform_body = _body_node(terraform_block)
        if terraform_body is None:
            continue
        for child in terraform_body.children:
            if child.type != "block" or _block_identifier(child, source_bytes) != "required_providers":
                continue
            providers_body = _body_node(child)
            if providers_body is None:
                continue
            for attribute in providers_body.children:
                if attribute.type != "attribute":
                    continue
                provider_name, _ = _attribute_pair(attribute, source_bytes)
                if not provider_name:
                    continue
                metadata[provider_name] = _object_attribute_map(attribute, source_bytes)
    return metadata


def _object_attribute_map(attribute: Any, source_bytes: bytes) -> dict[str, str]:
    """Return key/value pairs from an object-valued HCL attribute."""

    object_node = _object_node_from_attribute(attribute)
    if object_node is None:
        return {}
    result: dict[str, str] = {}
    for child in object_node.children:
        if child.type != "object_elem":
            continue
        name_node, value_node = _object_elem_nodes(child)
        if name_node is None or value_node is None:
            continue
        result[_expression_text(name_node, source_bytes)] = _expression_text(
            value_node, source_bytes
        )
    return result


def _object_keys(attribute: Any) -> list[str]:
    """Return top-level object keys from one attribute node."""

    object_node = _object_node_from_attribute(attribute)
    if object_node is None:
        return []
    keys: list[str] = []
    for child in object_node.children:
        if child.type != "object_elem":
            continue
        name_node, _ = _object_elem_nodes(child)
        if name_node is None:
            continue
        keys.append(name_node.text.decode("utf-8", "ignore"))
    return keys


def _attribute_map(block: Any, source_bytes: bytes) -> dict[str, str]:
    """Return top-level attribute values from one block body."""

    body = _body_node(block)
    if body is None:
        return {}
    result: dict[str, str] = {}
    for child in body.children:
        if child.type != "attribute":
            continue
        name, value = _attribute_pair(child, source_bytes)
        if name:
            result[name] = value
    return result


def _attribute_pair(attribute: Any, source_bytes: bytes) -> tuple[str, str]:
    """Return one HCL attribute key/value pair."""

    identifier = ""
    value = ""
    named_children = [child for child in attribute.children if child.is_named]
    if named_children:
        identifier = _expression_text(named_children[0], source_bytes)
    if len(named_children) >= 2:
        value = _expression_text(named_children[1], source_bytes)
    return identifier, value


def _block_identifier(block: Any, source_bytes: bytes) -> str:
    """Return the primary identifier for one HCL block."""

    for child in block.children:
        if child.type == "identifier":
            return _node_text(child, source_bytes)
    return ""


def _block_labels(block: Any, source_bytes: bytes) -> list[str]:
    """Return string labels for one HCL block."""

    return [
        _expression_text(child, source_bytes)
        for child in block.children
        if child.type == "string_lit"
    ]


def _object_node_from_attribute(attribute: Any) -> Any | None:
    """Return an object node from an object-valued attribute expression."""

    named_children = [child for child in attribute.children if child.is_named]
    if len(named_children) < 2:
        return None
    expression = named_children[1]
    stack = [expression]
    while stack:
        current = stack.pop()
        if current.type == "object":
            return current
        stack.extend(reversed(list(current.children)))
    return None


def _object_elem_nodes(node: Any) -> tuple[Any | None, Any | None]:
    """Return the key/value nodes for one object element."""

    named_children = [child for child in node.children if child.is_named]
    if len(named_children) < 2:
        return None, None
    return named_children[0], named_children[-1]


def _expression_text(node: Any, source_bytes: bytes) -> str:
    """Normalize an expression node into a useful string value."""

    if node.type in {"expression", "literal_value", "collection_value"}:
        named_children = [child for child in node.children if child.is_named]
        if len(named_children) == 1:
            return _expression_text(named_children[0], source_bytes)
    if node.type == "string_lit":
        return _string_literal_text(node, source_bytes)
    return _node_text(node, source_bytes).strip()


def _string_literal_text(node: Any, source_bytes: bytes) -> str:
    """Return the user-facing text for one HCL string literal."""

    template_parts = [
        _node_text(child, source_bytes)
        for child in node.children
        if child.type in {"template_literal", "template_interpolation"}
    ]
    if template_parts:
        return "".join(template_parts)
    return _node_text(node, source_bytes).strip().strip('"')


def _node_text(node: Any, source_bytes: bytes) -> str:
    """Return the exact source text for one node."""

    return source_bytes[node.start_byte : node.end_byte].decode("utf-8", "ignore")


__all__ = ["parse_hcl_document"]
