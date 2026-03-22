"""Inheritance and infrastructure relationship helpers for ``GraphBuilder``."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def create_all_infra_links(
    builder: Any, all_file_data: list[dict[str, Any]], *, info_logger_fn: Any
) -> None:
    """Link infrastructure nodes after indexing completes.

    Args:
        builder: ``GraphBuilder`` facade instance.
        all_file_data: Parsed file payloads for the full indexing run.
        info_logger_fn: Info logger callable.
    """
    infra_keys = (
        "k8s_resources",
        "argocd_applications",
        "argocd_applicationsets",
        "crossplane_xrds",
        "crossplane_compositions",
        "crossplane_claims",
        "kustomize_overlays",
        "helm_charts",
        "helm_values",
        "terraform_resources",
        "terraform_modules",
        "terragrunt_configs",
        "cloudformation_resources",
    )
    has_infra = any(
        item
        for file_data in all_file_data
        for key in infra_keys
        for item in file_data.get(key, [])
    )
    if not has_infra:
        return

    info_logger_fn("Creating infrastructure relationships...")
    from .cross_repo_linker import CrossRepoLinker

    linker = CrossRepoLinker(builder.db_manager)
    stats = linker.link_all()
    total = sum(stats.values())
    if total > 0:
        info_logger_fn(
            f"Infrastructure linking: {total} relationships created ({stats})"
        )
    else:
        info_logger_fn("Infrastructure linking: no relationships found")


def create_inheritance_links(
    session: Any, file_data: dict[str, Any], imports_map: dict[str, Any]
) -> None:
    """Create ``INHERITS`` links for one non-C# file.

    Args:
        session: Active database session.
        file_data: Parsed file payload.
        imports_map: Import resolution map collected during pre-scan.
    """
    caller_file_path = str(Path(file_data["path"]).resolve())
    local_class_names = {c["name"] for c in file_data.get("classes", [])}
    local_imports = {
        imp.get("alias") or imp["name"].split(".")[-1]: imp["name"]
        for imp in file_data.get("imports", [])
    }

    for class_item in file_data.get("classes", []):
        if not class_item.get("bases"):
            continue

        for base_class_str in class_item["bases"]:
            if base_class_str == "object":
                continue

            target_class_name = base_class_str.split(".")[-1]
            resolved_path = _resolve_inheritance_path(
                caller_file_path,
                target_class_name,
                base_class_str,
                local_class_names,
                local_imports,
                imports_map,
            )

            if not resolved_path:
                continue

            session.run(
                """
                MATCH (child:Class {name: $child_name, path: $file_path})
                MATCH (parent:Class {name: $parent_name, path: $resolved_parent_file_path})
                MERGE (child)-[:INHERITS]->(parent)
                """,
                child_name=class_item["name"],
                file_path=caller_file_path,
                parent_name=target_class_name,
                resolved_parent_file_path=resolved_path,
            )


def create_csharp_inheritance_and_interfaces(
    session: Any, file_data: dict[str, Any], imports_map: dict[str, Any]
) -> None:
    """Create inheritance and interface links for one C# file.

    Args:
        session: Active database session.
        file_data: Parsed file payload.
        imports_map: Import resolution map collected during pre-scan.
    """
    if file_data.get("lang") != "c_sharp":
        return

    caller_file_path = str(Path(file_data["path"]).resolve())
    local_interfaces = {item["name"] for item in file_data.get("interfaces", [])}

    for type_list_name, type_label in [
        ("classes", "Class"),
        ("structs", "Struct"),
        ("records", "Record"),
        ("interfaces", "Interface"),
    ]:
        for type_item in file_data.get(type_list_name, []):
            if not type_item.get("bases"):
                continue

            for base_index, base_str in enumerate(type_item["bases"]):
                base_name = base_str.split("<")[0].strip()
                is_interface = base_name in local_interfaces

                if base_name in imports_map and imports_map[base_name]:
                    _ = imports_map[base_name][0]

                if is_interface or (base_index > 0 and type_label == "Class"):
                    session.run(
                        """
                        MATCH (child {name: $child_name, path: $file_path})
                        WHERE child:Class OR child:Struct OR child:Record
                        MATCH (iface:Interface {name: $interface_name})
                        MERGE (child)-[:IMPLEMENTS]->(iface)
                        """,
                        child_name=type_item["name"],
                        file_path=caller_file_path,
                        interface_name=base_name,
                    )
                    continue

                session.run(
                    """
                    MATCH (child {name: $child_name, path: $file_path})
                    WHERE child:Class OR child:Record OR child:Interface
                    MATCH (parent {name: $parent_name})
                    WHERE parent:Class OR parent:Record OR parent:Interface
                    MERGE (child)-[:INHERITS]->(parent)
                    """,
                    child_name=type_item["name"],
                    file_path=caller_file_path,
                    parent_name=base_name,
                )


def create_all_inheritance_links(
    builder: Any, all_file_data: list[dict[str, Any]], imports_map: dict[str, Any]
) -> None:
    """Create inheritance-style links after all files are indexed.

    Args:
        builder: ``GraphBuilder`` facade instance.
        all_file_data: Parsed file payloads for the full indexing run.
        imports_map: Import resolution map collected during pre-scan.
    """
    with builder.driver.session() as session:
        for file_data in all_file_data:
            if file_data.get("lang") == "c_sharp":
                builder._create_csharp_inheritance_and_interfaces(
                    session, file_data, imports_map
                )
            else:
                builder._create_inheritance_links(session, file_data, imports_map)


def _resolve_inheritance_path(
    caller_file_path: str,
    target_class_name: str,
    base_class_str: str,
    local_class_names: set[str],
    local_imports: dict[str, str],
    imports_map: dict[str, Any],
) -> str | None:
    """Resolve the file path for a base class reference."""
    if "." in base_class_str:
        lookup_name = base_class_str.split(".")[0]
        if lookup_name not in local_imports:
            return None
        full_import_name = local_imports[lookup_name]
        return _match_imported_base_path(
            target_class_name, full_import_name, imports_map
        )

    lookup_name = base_class_str
    if lookup_name in local_class_names:
        return caller_file_path
    if lookup_name in local_imports:
        full_import_name = local_imports[lookup_name]
        return _match_imported_base_path(
            target_class_name, full_import_name, imports_map
        )
    if lookup_name in imports_map and len(imports_map[lookup_name]) == 1:
        return imports_map[lookup_name][0]
    return None


def _match_imported_base_path(
    target_class_name: str, full_import_name: str, imports_map: dict[str, Any]
) -> str | None:
    """Match a dotted import name to an indexed file path."""
    for path in imports_map.get(target_class_name, []):
        if full_import_name.replace(".", "/") in path:
            return path
    return None


__all__ = [
    "create_all_infra_links",
    "create_all_inheritance_links",
    "create_csharp_inheritance_and_interfaces",
    "create_inheritance_links",
]
