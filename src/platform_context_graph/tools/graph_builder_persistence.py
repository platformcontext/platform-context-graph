"""Persistence helpers for repository and file graph updates."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..core.records import record_to_dict
from ..content.ingest import (
    CONTENT_ENTITY_LABELS,
    prepare_content_entries,
    repository_metadata_from_row,
)
from ..content.state import get_postgres_content_provider
from .graph_builder_entities import build_entity_merge_statement


def add_repository_to_graph(
    builder: Any,
    repo_path: Path,
    is_dependency: bool,
    *,
    git_remote_for_path_fn: Any,
    repository_metadata_fn: Any,
) -> None:
    """Merge a repository node using the canonical remote-first identity.

    Args:
        builder: ``GraphBuilder`` facade instance.
        repo_path: Repository root to persist.
        is_dependency: Whether the repository is indexed as a dependency.
        git_remote_for_path_fn: Callable resolving the repository remote URL.
        repository_metadata_fn: Callable building canonical repository metadata.
    """
    repo_path_str = str(repo_path.resolve())
    remote_url = git_remote_for_path_fn(repo_path)
    metadata = repository_metadata_fn(
        name=repo_path.name,
        local_path=repo_path_str,
        remote_url=remote_url,
    )

    with builder.driver.session() as session:
        existing = session.run(
            """
            MATCH (r:Repository {path: $repo_path})
            RETURN r.id as id
            LIMIT 1
            """,
            repo_path=repo_path_str,
        ).single()
        if existing is None:
            existing = session.run(
                """
                MATCH (r:Repository {id: $repo_id})
                RETURN r.id as id
                LIMIT 1
                """,
                repo_id=metadata["id"],
            ).single()

        if existing is None:
            session.run(
                """
                CREATE (r:Repository {id: $repo_id})
                SET r.name = $name,
                    r.path = $repo_path,
                    r.local_path = $local_path,
                    r.remote_url = $remote_url,
                    r.repo_slug = $repo_slug,
                    r.has_remote = $has_remote,
                    r.is_dependency = $is_dependency
                """,
                repo_id=metadata["id"],
                repo_path=repo_path_str,
                local_path=metadata["local_path"],
                name=metadata["name"],
                remote_url=metadata["remote_url"],
                repo_slug=metadata["repo_slug"],
                has_remote=metadata["has_remote"],
                is_dependency=is_dependency,
            )
            return

        session.run(
            """
            MATCH (r:Repository)
            WHERE r.path = $repo_path OR r.id = $repo_id
            SET r.id = $repo_id,
                r.name = $name,
                r.path = $repo_path,
                r.local_path = $local_path,
                r.remote_url = $remote_url,
                r.repo_slug = $repo_slug,
                r.has_remote = $has_remote,
                r.is_dependency = $is_dependency
            """,
            repo_id=metadata["id"],
            repo_path=repo_path_str,
            local_path=metadata["local_path"],
            name=metadata["name"],
            remote_url=metadata["remote_url"],
            repo_slug=metadata["repo_slug"],
            has_remote=metadata["has_remote"],
            is_dependency=is_dependency,
        )


def add_file_to_graph(
    builder: Any,
    file_data: dict[str, Any],
    repo_name: str,
    imports_map: dict[str, Any],
    *,
    debug_log_fn: Any,
    info_logger_fn: Any,
    warning_logger_fn: Any,
) -> None:
    """Persist a parsed file, its contained nodes, and immediate edges.

    Args:
        builder: ``GraphBuilder`` facade instance.
        file_data: Parsed file payload emitted by the language parser.
        repo_name: Preserved compatibility argument from the public method signature.
        imports_map: Preserved compatibility argument for public method parity.
        debug_log_fn: Debug logger callable.
        info_logger_fn: Info logger callable.
        warning_logger_fn: Warning logger callable.
    """
    _ = (repo_name, imports_map)
    calls_count = len(file_data.get("function_calls", []))
    debug_log_fn(
        f"Executing add_file_to_graph for {file_data.get('path', 'unknown')} - Calls found: {calls_count}"
    )

    file_path_str = str(Path(file_data["path"]).resolve())
    file_path_obj = Path(file_path_str)
    file_name = Path(file_path_str).name
    is_dependency = file_data.get("is_dependency", False)

    with builder.driver.session() as session:
        try:
            repo_result = session.run(
                """
                MATCH (r:Repository {path: $repo_path})
                RETURN r.id as id,
                       r.name as name,
                       r.path as path,
                       coalesce(r.local_path, r.path) as local_path,
                       r.remote_url as remote_url,
                       r.repo_slug as repo_slug,
                       coalesce(r.has_remote, false) as has_remote
                """,
                repo_path=str(Path(file_data["repo_path"]).resolve()),
            ).single()
        except ValueError:
            repo_result = None

        repo_row = record_to_dict(repo_result) if repo_result is not None else None
        repo_path_obj = Path(file_data["repo_path"]).resolve()
        repository = repository_metadata_from_row(row=repo_row, repo_path=repo_path_obj)
        try:
            relative_path = file_path_obj.relative_to(repo_path_obj).as_posix()
        except ValueError:
            relative_path = file_name

        session.run(
            """
            MERGE (f:File {path: $file_path})
            SET f.name = $name, f.relative_path = $relative_path, f.is_dependency = $is_dependency
        """,
            file_path=file_path_str,
            name=file_name,
            relative_path=relative_path,
            is_dependency=is_dependency,
        )

        content_provider = get_postgres_content_provider()
        if content_provider is not None and content_provider.enabled:
            try:
                file_entry, entity_entries = prepare_content_entries(
                    file_data=file_data,
                    repository=repository,
                )
                if file_entry is not None:
                    content_provider.upsert_file(file_entry)
                if entity_entries:
                    content_provider.upsert_entities(entity_entries)
            except Exception as exc:
                warning_logger_fn(
                    f"Content store dual-write failed for {file_name}: {exc}"
                )

        relative_path_to_file = file_path_obj.relative_to(repo_path_obj)
        parent_path = str(repo_path_obj)
        parent_label = "Repository"

        for part in relative_path_to_file.parts[:-1]:
            current_path = Path(parent_path) / part
            current_path_str = str(current_path)

            session.run(
                f"""
                MATCH (p:{parent_label} {{path: $parent_path}})
                MERGE (d:Directory {{path: $current_path}})
                SET d.name = $part
                MERGE (p)-[:CONTAINS]->(d)
            """,
                parent_path=parent_path,
                current_path=current_path_str,
                part=part,
            )

            parent_path = current_path_str
            parent_label = "Directory"

        session.run(
            f"""
            MATCH (p:{parent_label} {{path: $parent_path}})
            MATCH (f:File {{path: $file_path}})
            MERGE (p)-[:CONTAINS]->(f)
        """,
            parent_path=parent_path,
            file_path=file_path_str,
        )

        item_mappings = [
            (file_data.get("functions", []), "Function"),
            (file_data.get("classes", []), "Class"),
            (file_data.get("traits", []), "Trait"),
            (file_data.get("variables", []), "Variable"),
            (file_data.get("interfaces", []), "Interface"),
            (file_data.get("macros", []), "Macro"),
            (file_data.get("structs", []), "Struct"),
            (file_data.get("enums", []), "Enum"),
            (file_data.get("unions", []), "Union"),
            (file_data.get("records", []), "Record"),
            (file_data.get("properties", []), "Property"),
            (file_data.get("k8s_resources", []), "K8sResource"),
            (file_data.get("argocd_applications", []), "ArgoCDApplication"),
            (file_data.get("argocd_applicationsets", []), "ArgoCDApplicationSet"),
            (file_data.get("crossplane_xrds", []), "CrossplaneXRD"),
            (file_data.get("crossplane_compositions", []), "CrossplaneComposition"),
            (file_data.get("crossplane_claims", []), "CrossplaneClaim"),
            (file_data.get("kustomize_overlays", []), "KustomizeOverlay"),
            (file_data.get("helm_charts", []), "HelmChart"),
            (file_data.get("helm_values", []), "HelmValues"),
            (file_data.get("terraform_resources", []), "TerraformResource"),
            (file_data.get("terraform_variables", []), "TerraformVariable"),
            (file_data.get("terraform_outputs", []), "TerraformOutput"),
            (file_data.get("terraform_modules", []), "TerraformModule"),
            (file_data.get("terraform_data_sources", []), "TerraformDataSource"),
            (file_data.get("terragrunt_configs", []), "TerragruntConfig"),
        ]
        for item_data, label in item_mappings:
            for item in item_data:
                if label == "Function" and "cyclomatic_complexity" not in item:
                    item["cyclomatic_complexity"] = 1

                query, params = build_entity_merge_statement(
                    label=label,
                    item=item,
                    file_path=file_path_str,
                    use_uid_identity=label in CONTENT_ENTITY_LABELS
                    and bool(item.get("uid")),
                )
                session.run(query, params)

                if label == "Function":
                    for arg_name in item.get("args", []):
                        session.run(
                            """
                            MATCH (fn:Function {name: $func_name, path: $file_path, line_number: $line_number})
                            MERGE (p:Parameter {name: $arg_name, path: $file_path, function_line_number: $line_number})
                            MERGE (fn)-[:HAS_PARAMETER]->(p)
                        """,
                            func_name=item["name"],
                            file_path=file_path_str,
                            line_number=item["line_number"],
                            arg_name=arg_name,
                        )

        for module_item in file_data.get("modules", []):
            session.run(
                """
                MERGE (mod:Module {name: $name})
                ON CREATE SET mod.lang = $lang
                ON MATCH  SET mod.lang = coalesce(mod.lang, $lang)
            """,
                name=module_item["name"],
                lang=file_data.get("lang"),
            )

        for item in file_data.get("functions", []):
            if item.get("context_type") == "function_definition":
                session.run(
                    """
                    MATCH (outer:Function {name: $context, path: $file_path})
                    MATCH (inner:Function {name: $name, path: $file_path, line_number: $line_number})
                    MERGE (outer)-[:CONTAINS]->(inner)
                """,
                    context=item["context"],
                    file_path=file_path_str,
                    name=item["name"],
                    line_number=item["line_number"],
                )

        for imp in file_data.get("imports", []):
            info_logger_fn(f"Processing import: {imp}")
            lang = file_data.get("lang")
            if lang == "javascript":
                module_name = imp.get("source")
                if not module_name:
                    continue

                rel_params = {
                    "file_path": file_path_str,
                    "module_name": module_name,
                    "imported_name": imp.get("name", "*"),
                }
                set_parts = ["r.imported_name = $imported_name"]
                if imp.get("alias"):
                    rel_params["alias"] = imp["alias"]
                    set_parts.append("r.alias = $alias")
                if imp.get("line_number"):
                    rel_params["imp_line"] = imp["line_number"]
                    set_parts.append("r.line_number = $imp_line")
                set_clause = f"SET {', '.join(set_parts)}"

                session.run(
                    f"""
                    MATCH (f:File {{path: $file_path}})
                    MERGE (m:Module {{name: $module_name}})
                    MERGE (f)-[r:IMPORTS]->(m)
                    {set_clause}
                """,
                    **rel_params,
                )
            else:
                set_clauses = []
                if "full_import_name" in imp:
                    set_clauses.append("m.full_import_name = $full_import_name")

                set_clause_str = (
                    ("SET " + ", ".join(set_clauses)) if set_clauses else ""
                )

                rel_props: dict[str, Any] = {}
                if imp.get("line_number"):
                    rel_props["line_number"] = imp.get("line_number")
                if imp.get("alias"):
                    rel_props["alias"] = imp.get("alias")

                params: dict[str, Any] = {
                    "file_path": file_path_str,
                    "module_name": imp.get("name"),
                }
                for key, value in imp.items():
                    if key not in ("path", "name"):
                        params[key] = value

                rel_set_parts = [f"r.{key} = ${key}_rel" for key in rel_props]
                rel_set_clause = (
                    f"SET {', '.join(rel_set_parts)}" if rel_set_parts else ""
                )
                for key, value in rel_props.items():
                    params[f"{key}_rel"] = value

                session.run(
                    f"""
                    MATCH (f:File {{path: $file_path}})
                    MERGE (m:Module {{name: $module_name}})
                    {set_clause_str}
                    MERGE (f)-[r:IMPORTS]->(m)
                    {rel_set_clause}
                """,
                    **params,
                )

        for func in file_data.get("functions", []):
            if func.get("class_context"):
                session.run(
                    """
                    MATCH (c:Class {name: $class_name, path: $file_path})
                    MATCH (fn:Function {name: $func_name, path: $file_path, line_number: $func_line})
                    MERGE (c)-[:CONTAINS]->(fn)
                """,
                    class_name=func["class_context"],
                    file_path=file_path_str,
                    func_name=func["name"],
                    func_line=func["line_number"],
                )

        for inclusion in file_data.get("module_inclusions", []):
            session.run(
                """
                MATCH (c:Class {name: $class_name, path: $file_path})
                MERGE (m:Module {name: $module_name})
                MERGE (c)-[:INCLUDES]->(m)
            """,
                class_name=inclusion["class"],
                file_path=file_path_str,
                module_name=inclusion["module"],
            )

__all__ = [
    "add_file_to_graph",
    "add_repository_to_graph",
]
