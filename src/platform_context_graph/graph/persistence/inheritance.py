"""Inheritance-style relationship helpers for ``GraphBuilder``."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable


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
    rows = _collect_inheritance_rows(
        caller_file_path=caller_file_path,
        local_class_names=local_class_names,
        local_imports=local_imports,
        file_data=file_data,
        imports_map=imports_map,
    )

    if not rows:
        return

    _flush_inheritance_rows(session, rows)


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
    inheritance_rows, interface_rows = _collect_csharp_inheritance_rows(
        caller_file_path=caller_file_path,
        local_interfaces=local_interfaces,
        file_data=file_data,
        imports_map=imports_map,
    )
    _flush_csharp_inheritance_rows(session, inheritance_rows, interface_rows)


def create_all_inheritance_links(
    builder: Any, all_file_data: Iterable[dict[str, Any]], imports_map: dict[str, Any]
) -> None:
    """Create inheritance-style links after all files are indexed.

    Args:
        builder: ``GraphBuilder`` facade instance.
        all_file_data: Parsed file payloads for the full indexing run.
        imports_map: Import resolution map collected during pre-scan.
    """
    non_csharp_rows: list[dict[str, str]] = []
    csharp_inheritance_rows: list[dict[str, str]] = []
    csharp_interface_rows: list[dict[str, str]] = []

    for file_data in all_file_data:
        caller_file_path = str(Path(file_data["path"]).resolve())
        if file_data.get("lang") == "c_sharp":
            inheritance_rows, interface_rows = _collect_csharp_inheritance_rows(
                caller_file_path=caller_file_path,
                local_interfaces={
                    item["name"] for item in file_data.get("interfaces", [])
                },
                file_data=file_data,
                imports_map=imports_map,
            )
            csharp_inheritance_rows.extend(inheritance_rows)
            csharp_interface_rows.extend(interface_rows)
            continue

        local_class_names = {c["name"] for c in file_data.get("classes", [])}
        local_imports = {
            imp.get("alias") or imp["name"].split(".")[-1]: imp["name"]
            for imp in file_data.get("imports", [])
        }
        non_csharp_rows.extend(
            _collect_inheritance_rows(
                caller_file_path=caller_file_path,
                local_class_names=local_class_names,
                local_imports=local_imports,
                file_data=file_data,
                imports_map=imports_map,
            )
        )

    with builder.driver.session() as session:
        _flush_inheritance_rows(session, non_csharp_rows)
        _flush_csharp_inheritance_rows(
            session,
            csharp_inheritance_rows,
            csharp_interface_rows,
        )


def _collect_inheritance_rows(
    *,
    caller_file_path: str,
    local_class_names: set[str],
    local_imports: dict[str, str],
    file_data: dict[str, Any],
    imports_map: dict[str, Any],
) -> list[dict[str, str]]:
    """Collect non-C# inheritance rows without writing them immediately."""

    rows: list[dict[str, str]] = []
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
            rows.append(
                {
                    "child_name": class_item["name"],
                    "file_path": caller_file_path,
                    "parent_name": target_class_name,
                    "resolved_parent_file_path": resolved_path,
                }
            )
    return rows


def _collect_csharp_inheritance_rows(
    *,
    caller_file_path: str,
    local_interfaces: set[str],
    file_data: dict[str, Any],
    imports_map: dict[str, Any],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Collect C# inheritance and interface rows without writing them immediately."""

    inheritance_rows: list[dict[str, str]] = []
    interface_rows: list[dict[str, str]] = []
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
                    interface_rows.append(
                        {
                            "child_name": type_item["name"],
                            "file_path": caller_file_path,
                            "interface_name": base_name,
                        }
                    )
                    continue

                inheritance_rows.append(
                    {
                        "child_name": type_item["name"],
                        "file_path": caller_file_path,
                        "parent_name": base_name,
                    }
                )
    return inheritance_rows, interface_rows


def _flush_inheritance_rows(session: Any, rows: list[dict[str, str]]) -> None:
    """Write batched non-C# inheritance rows in one query."""

    if not rows:
        return
    session.run(
        """
        UNWIND $rows AS row
        MATCH (child:Class {name: row.child_name, path: row.file_path})
        MATCH (parent:Class {name: row.parent_name, path: row.resolved_parent_file_path})
        MERGE (child)-[:INHERITS]->(parent)
        """,
        rows=rows,
    )


def _flush_csharp_inheritance_rows(
    session: Any,
    inheritance_rows: list[dict[str, str]],
    interface_rows: list[dict[str, str]],
) -> None:
    """Write batched C# inheritance and interface rows in one or two queries."""

    if inheritance_rows:
        session.run(
            """
            UNWIND $rows AS row
            MATCH (child {name: row.child_name, path: row.file_path})
            WHERE child:Class OR child:Record OR child:Interface
            MATCH (parent {name: row.parent_name})
            WHERE parent:Class OR parent:Record OR parent:Interface
            MERGE (child)-[:INHERITS]->(parent)
            """,
            rows=inheritance_rows,
        )
    if interface_rows:
        session.run(
            """
            UNWIND $rows AS row
            MATCH (child {name: row.child_name, path: row.file_path})
            WHERE child:Class OR child:Struct OR child:Record
            MATCH (iface:Interface {name: row.interface_name})
            MERGE (child)-[:IMPLEMENTS]->(iface)
            """,
            rows=interface_rows,
        )


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
    "create_all_inheritance_links",
    "create_csharp_inheritance_and_interfaces",
    "create_inheritance_links",
]
