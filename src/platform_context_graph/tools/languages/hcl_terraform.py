"""HCL/Terraform parser using regex-based block extraction.

Parses .tf and .hcl files to extract resource, variable, output,
module, data, and terragrunt configuration blocks. Does not use
tree-sitter; instead uses a brace-matching parser that handles
nested blocks correctly.
"""

import re
from pathlib import Path
from typing import Any

from ...utils.debug_log import warning_logger

# --- Block type patterns ---

# Matches: resource "type" "name" {
_RESOURCE_RE = re.compile(
    r'^resource\s+"([^"]+)"\s+"([^"]+)"\s*\{',
    re.MULTILINE,
)

# Matches: variable "name" {
_VARIABLE_RE = re.compile(r'^variable\s+"([^"]+)"\s*\{', re.MULTILINE)

# Matches: output "name" {
_OUTPUT_RE = re.compile(r'^output\s+"([^"]+)"\s*\{', re.MULTILINE)

# Matches: module "name" {
_MODULE_RE = re.compile(r'^module\s+"([^"]+)"\s*\{', re.MULTILINE)

# Matches: data "type" "name" {
_DATA_RE = re.compile(r'^data\s+"([^"]+)"\s+"([^"]+)"\s*\{', re.MULTILINE)

# Matches: terraform {
_TERRAFORM_BLOCK_RE = re.compile(r"^terraform\s*\{", re.MULTILINE)

# Matches: include "name" { (terragrunt)
_INCLUDE_RE = re.compile(r'^include\s+"([^"]+)"\s*\{', re.MULTILINE)

# Simple attribute extractors inside blocks
_STRING_ATTR_RE = re.compile(r'^\s*(\w+)\s*=\s*"([^"]*)"', re.MULTILINE)
_UNQUOTED_ATTR_RE = re.compile(r"^\s*(\w+)\s*=\s*(\S+)", re.MULTILINE)


def _find_matching_brace(content: str, start: int) -> int:
    """Find the position of the closing brace matching the opening at start.

    Args:
        content: Full file content.
        start: Position of the opening '{'.

    Returns:
        Position of the matching '}', or -1 if not found.
    """
    depth = 0
    in_string = False
    escape_next = False
    i = start

    while i < len(content):
        ch = content[i]

        if escape_next:
            escape_next = False
            i += 1
            continue

        if ch == "\\":
            escape_next = True
            i += 1
            continue

        if ch == '"' and not in_string:
            in_string = True
            i += 1
            continue
        if ch == '"' and in_string:
            in_string = False
            i += 1
            continue

        if in_string:
            i += 1
            continue

        # Skip single-line comments
        if ch == "#" or (ch == "/" and i + 1 < len(content) and content[i + 1] == "/"):
            newline = content.find("\n", i)
            if newline == -1:
                break
            i = newline + 1
            continue

        # Skip block comments
        if ch == "/" and i + 1 < len(content) and content[i + 1] == "*":
            end = content.find("*/", i + 2)
            if end == -1:
                break
            i = end + 2
            continue

        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i

        i += 1

    return -1


def _line_number_at(content: str, pos: int) -> int:
    """Return 1-based line number for character position."""
    return content[:pos].count("\n") + 1


def _extract_block_body(content: str, match: re.Match) -> tuple[str, int]:
    """Extract the body text of a block and its line number.

    Args:
        content: Full file content.
        match: Regex match whose end is at the opening '{'.

    Returns:
        Tuple of (block_body_text, line_number).
    """
    brace_pos = content.find("{", match.start())
    if brace_pos == -1:
        return "", _line_number_at(content, match.start())

    end = _find_matching_brace(content, brace_pos)
    if end == -1:
        body = content[brace_pos + 1 :]
    else:
        body = content[brace_pos + 1 : end]

    return body, _line_number_at(content, match.start())


def _extract_string_attr(body: str, key: str) -> str:
    """Extract a quoted string attribute from a block body."""
    for m in _STRING_ATTR_RE.finditer(body):
        if m.group(1) == key:
            return m.group(2)
    return ""


def _extract_attr(body: str, key: str) -> str:
    """Extract any attribute value (quoted or unquoted)."""
    val = _extract_string_attr(body, key)
    if val:
        return val
    for m in _UNQUOTED_ATTR_RE.finditer(body):
        if m.group(1) == key:
            return m.group(2)
    return ""


class HCLTerraformParser:
    """Parser for HCL/Terraform files.

    Uses regex-based block detection with brace matching.
    Sufficient for extracting top-level resource/variable/output/
    module/data blocks needed for graph building.

    Args:
        language_name: Language identifier (always 'hcl').
    """

    def __init__(self, language_name: str) -> None:
        """Initialize the regex-based Terraform parser."""
        self.language_name = language_name

    def parse(
        self,
        path: str,
        is_dependency: bool = False,
        index_source: bool = True,
    ) -> dict[str, Any]:
        """Parse an HCL/Terraform file.

        Args:
            path: Absolute path to the .tf or .hcl file.
            is_dependency: Whether this file is a dependency.
            index_source: Whether to store raw source.

        Returns:
            Dict with terraform_resources, terraform_variables,
            terraform_outputs, terraform_modules,
            terraform_data_sources, terragrunt_configs, plus
            standard keys.
        """
        result: dict[str, Any] = {
            "path": path,
            "lang": "hcl",
            "is_dependency": is_dependency,
            "functions": [],
            "classes": [],
            "imports": [],
            "function_calls": [],
            "variables": [],
            # Terraform categories
            "terraform_resources": [],
            "terraform_variables": [],
            "terraform_outputs": [],
            "terraform_modules": [],
            "terraform_data_sources": [],
            "terragrunt_configs": [],
        }

        file_path = Path(path)

        try:
            content = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            warning_logger(f"Cannot read {path}: {e}")
            return result

        if not content.strip():
            return result

        # Detect terragrunt files
        is_terragrunt = file_path.name in (
            "terragrunt.hcl",
            "terragrunt.hcl.json",
        )

        if is_terragrunt:
            self._parse_terragrunt(content, path, result)
            return result

        # Parse standard terraform blocks
        self._parse_resources(content, path, result)
        self._parse_variables(content, path, result)
        self._parse_outputs(content, path, result)
        self._parse_modules(content, path, result)
        self._parse_data_sources(content, path, result)

        return result

    def _parse_resources(self, content: str, path: str, result: dict) -> None:
        """Parse Terraform resource blocks into the result payload."""
        for match in _RESOURCE_RE.finditer(content):
            resource_type = match.group(1)
            resource_name = match.group(2)
            body, line_number = _extract_block_body(content, match)

            result["terraform_resources"].append(
                {
                    "name": f"{resource_type}.{resource_name}",
                    "line_number": line_number,
                    "resource_type": resource_type,
                    "resource_name": resource_name,
                    "path": path,
                    "lang": "hcl",
                }
            )

    def _parse_variables(self, content: str, path: str, result: dict) -> None:
        """Parse Terraform variable blocks into the result payload."""
        for match in _VARIABLE_RE.finditer(content):
            var_name = match.group(1)
            body, line_number = _extract_block_body(content, match)

            var_type = _extract_attr(body, "type")
            default = _extract_string_attr(body, "default")
            description = _extract_string_attr(body, "description")

            result["terraform_variables"].append(
                {
                    "name": var_name,
                    "line_number": line_number,
                    "var_type": var_type,
                    "default": default,
                    "description": description,
                    "path": path,
                    "lang": "hcl",
                }
            )

    def _parse_outputs(self, content: str, path: str, result: dict) -> None:
        """Parse Terraform output blocks into the result payload."""
        for match in _OUTPUT_RE.finditer(content):
            output_name = match.group(1)
            body, line_number = _extract_block_body(content, match)

            description = _extract_string_attr(body, "description")
            value = _extract_attr(body, "value")

            result["terraform_outputs"].append(
                {
                    "name": output_name,
                    "line_number": line_number,
                    "description": description,
                    "value": value,
                    "path": path,
                    "lang": "hcl",
                }
            )

    def _parse_modules(self, content: str, path: str, result: dict) -> None:
        """Parse Terraform module blocks into the result payload."""
        for match in _MODULE_RE.finditer(content):
            module_name = match.group(1)
            body, line_number = _extract_block_body(content, match)

            source = _extract_string_attr(body, "source")
            version = _extract_string_attr(body, "version")

            result["terraform_modules"].append(
                {
                    "name": module_name,
                    "line_number": line_number,
                    "source": source,
                    "version": version,
                    "path": path,
                    "lang": "hcl",
                }
            )

    def _parse_data_sources(self, content: str, path: str, result: dict) -> None:
        """Parse Terraform data source blocks into the result payload."""
        for match in _DATA_RE.finditer(content):
            data_type = match.group(1)
            data_name = match.group(2)
            _, line_number = _extract_block_body(content, match)

            result["terraform_data_sources"].append(
                {
                    "name": f"{data_type}.{data_name}",
                    "line_number": line_number,
                    "data_type": data_type,
                    "data_name": data_name,
                    "path": path,
                    "lang": "hcl",
                }
            )

    def _parse_terragrunt(self, content: str, path: str, result: dict) -> None:
        """Parse a Terragrunt configuration file."""
        terraform_source = ""
        for match in _TERRAFORM_BLOCK_RE.finditer(content):
            body, _ = _extract_block_body(content, match)
            terraform_source = _extract_string_attr(body, "source")
            break

        includes = []
        for match in _INCLUDE_RE.finditer(content):
            includes.append(match.group(1))

        result["terragrunt_configs"].append(
            {
                "name": "terragrunt",
                "line_number": 1,
                "terraform_source": terraform_source,
                "includes": ",".join(includes),
                "path": path,
                "lang": "hcl",
            }
        )
