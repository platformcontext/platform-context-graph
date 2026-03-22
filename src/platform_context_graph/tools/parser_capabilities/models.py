"""Shared types and constants for parser capability contracts."""

from __future__ import annotations

from typing import Final, Literal, TypedDict

CapabilityStatus = Literal["supported", "partial", "unsupported"]
SpecFamily = Literal["language", "iac"]


class GraphSurface(TypedDict, total=False):
    """Structured description of a graph surface exposed by one capability."""

    kind: str
    target: str


class CapabilitySpec(TypedDict, total=False):
    """One checklist item inside a parser capability spec."""

    id: str
    name: str
    status: CapabilityStatus
    extracted_bucket: str
    required_fields: list[str]
    graph_surface: GraphSurface
    unit_test: str
    integration_test: str
    rationale: str


class LanguageCapabilitySpec(TypedDict, total=False):
    """Top-level parser capability spec loaded from one YAML file."""

    language: str
    title: str
    family: SpecFamily
    parser: str
    parser_entrypoint: str
    doc_path: str
    fixture_repo: str
    unit_test_file: str
    integration_test_suite: str
    capabilities: list[CapabilitySpec]
    known_limitations: list[str]
    spec_path: str


AUTO_GENERATED_BANNER: Final = "This file is auto-generated. Do not edit manually."
SUPPORTED_STATUSES: Final[set[CapabilityStatus]] = {
    "supported",
    "partial",
    "unsupported",
}
CODE_MATRIX_CAPABILITY_ALIASES: Final[dict[str, set[str]]] = {
    "classes": {
        "actors",
        "classes",
        "companion_objects",
        "extensions",
        "mixins",
        "modules",
        "modules_defmodule",
        "objects_object",
        "packages",
        "records",
    },
    "enums": {"enums", "enumerations"},
    "interfaces": {"interfaces"},
    "macros": {"macros", "macros_define"},
    "structs": {"data_types_struct_like", "structs"},
    "traits": {"protocols", "protocols_typeclasses", "traits", "type_classes"},
}
CODE_MATRIX_BUCKET_FALLBACK_IDS: Final[set[str]] = {
    "function_calls",
    "functions",
    "imports",
    "variables",
}
