"""Compatibility facade for graph-builder relationship helpers."""

from ..graph.persistence.calls import (
    create_all_function_calls,
    create_function_calls,
    name_from_symbol,
    safe_run_create,
)
from ..graph.persistence.inheritance import (
    create_all_inheritance_links,
    create_csharp_inheritance_and_interfaces,
    create_inheritance_links,
)
from ..relationships.infra_links import create_all_infra_links

__all__ = [
    "create_all_function_calls",
    "create_all_infra_links",
    "create_all_inheritance_links",
    "create_csharp_inheritance_and_interfaces",
    "create_function_calls",
    "create_inheritance_links",
    "name_from_symbol",
    "safe_run_create",
]
