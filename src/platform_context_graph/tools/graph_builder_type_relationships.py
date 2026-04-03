"""Compatibility facade for relocated inheritance and infra-link helpers."""

from platform_context_graph.graph.persistence.inheritance import *  # noqa: F403
from platform_context_graph.relationships.infra_links import (  # noqa: F401
    create_all_infra_links,
)

__all__ = [
    "create_all_infra_links",
    "create_all_inheritance_links",
    "create_csharp_inheritance_and_interfaces",
    "create_inheritance_links",
]
