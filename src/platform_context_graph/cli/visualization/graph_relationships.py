"""Relationship-centric graph visualization builders."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from .core import console, get_node_color, save_and_open_visualization
from .template import generate_html_template


def _render_visualization(
    nodes: list[dict],
    edges: list[dict],
    title: str,
    layout_type: str,
    description: str,
    prefix: str,
) -> str | None:
    """Render and persist a visualization artifact.

    Args:
        nodes: vis-network node payloads.
        edges: vis-network edge payloads.
        title: Visualization title.
        layout_type: vis-network layout mode.
        description: Optional descriptive text displayed in the UI.
        prefix: Filename prefix for the generated HTML file.

    Returns:
        The saved visualization path, or ``None`` when saving fails.
    """
    html = generate_html_template(
        nodes,
        edges,
        title,
        layout_type=layout_type,
        description=description,
    )
    return save_and_open_visualization(html, prefix)


def visualize_call_graph(
    results: list[dict],
    function_name: str,
    direction: Literal["outgoing", "incoming"] = "outgoing",
) -> str | None:
    """Visualize incoming or outgoing function calls.

    Args:
        results: Call graph rows returned by the code query layer.
        function_name: Central function being visualized.
        direction: Whether the results represent outgoing calls or callers.

    Returns:
        The saved visualization path, or ``None`` when there is nothing to show.
    """
    if not results:
        console.print("[yellow]No results to visualize.[/yellow]")
        return None

    nodes = []
    edges = []
    seen_nodes = set()
    central_id = f"central_{function_name}"
    central_group = "Source" if direction == "outgoing" else "Target"
    nodes.append(
        {
            "id": central_id,
            "label": function_name,
            "group": central_group,
            "title": f"{'Caller' if direction == 'outgoing' else 'Called'}: {function_name}",
            "color": get_node_color(central_group),
            "size": 30,
            "font": {"size": 16, "color": "#ffffff"},
        }
    )
    seen_nodes.add(central_id)

    for idx, result in enumerate(results):
        if direction == "outgoing":
            func_name = result.get("called_function", f"unknown_{idx}")
            path = result.get("called_file_path", "")
            line_num = result.get("called_line_number", "")
            is_dep = result.get("called_is_dependency", False)
        else:
            func_name = result.get("caller_function", f"unknown_{idx}")
            path = result.get("caller_file_path", "")
            line_num = result.get("caller_line_number", "")
            is_dep = result.get("caller_is_dependency", False)

        node_id = f"node_{func_name}_{idx}"
        node_type = (
            "Package" if is_dep else ("Callee" if direction == "outgoing" else "Caller")
        )
        if node_id not in seen_nodes:
            nodes.append(
                {
                    "id": node_id,
                    "label": func_name,
                    "group": node_type,
                    "title": f"{func_name}\nFile: {path}\nLine: {line_num}",
                    "color": get_node_color(node_type),
                }
            )
            seen_nodes.add(node_id)

        if direction == "outgoing":
            edges.append(
                {"from": central_id, "to": node_id, "label": "calls", "arrows": "to"}
            )
        else:
            edges.append(
                {"from": node_id, "to": central_id, "label": "calls", "arrows": "to"}
            )

    title = f"{'Outgoing Calls' if direction == 'outgoing' else 'Incoming Callers'}: {function_name}"
    description = (
        f"Showing {len(results)} "
        f"{'called functions' if direction == 'outgoing' else 'caller functions'}"
    )
    prefix = "pcg_calls" if direction == "outgoing" else "pcg_callers"
    return _render_visualization(nodes, edges, title, "force", description, prefix)


def visualize_call_chain(
    results: list[dict],
    from_func: str,
    to_func: str,
) -> str | None:
    """Visualize call chains between two functions.

    Args:
        results: Chain results containing ``function_chain`` entries.
        from_func: Starting function name.
        to_func: Target function name.

    Returns:
        The saved visualization path, or ``None`` when there is nothing to show.
    """
    if not results:
        console.print("[yellow]No call chain found to visualize.[/yellow]")
        return None

    nodes = []
    edges = []
    seen_nodes = set()

    for chain_idx, chain in enumerate(results):
        functions = chain.get("function_chain", [])
        for idx, func in enumerate(functions):
            func_name = func.get("name", f"unknown_{idx}")
            path = func.get("path", "")
            line_num = func.get("line_number", "")
            node_id = f"chain{chain_idx}_{func_name}_{idx}"
            if idx == 0:
                node_type = "Source"
            elif idx == len(functions) - 1:
                node_type = "Target"
            else:
                node_type = "Function"

            if node_id not in seen_nodes:
                nodes.append(
                    {
                        "id": node_id,
                        "label": func_name,
                        "group": node_type,
                        "title": f"{func_name}\nFile: {path}\nLine: {line_num}",
                        "color": get_node_color(node_type),
                        "level": idx,
                    }
                )
                seen_nodes.add(node_id)

            if idx < len(functions) - 1:
                next_func = functions[idx + 1]
                next_name = next_func.get("name", f"unknown_{idx + 1}")
                next_id = f"chain{chain_idx}_{next_name}_{idx + 1}"
                edges.append(
                    {"from": node_id, "to": next_id, "label": "→", "arrows": "to"}
                )

    return _render_visualization(
        nodes,
        edges,
        f"Call Chain: {from_func} → {to_func}",
        "hierarchical",
        f"Found {len(results)} path(s)",
        "pcg_chain",
    )


def visualize_dependencies(results: dict, module_name: str) -> str | None:
    """Visualize module importers and imports.

    Args:
        results: Dictionary containing ``importers`` and ``imports`` lists.
        module_name: Central module name.

    Returns:
        The saved visualization path, or ``None`` when there is nothing to show.
    """
    importers = results.get("importers", [])
    imports = results.get("imports", [])
    if not importers and not imports:
        console.print("[yellow]No dependency information to visualize.[/yellow]")
        return None

    nodes = []
    edges = []
    seen_nodes = set()
    central_id = f"central_{module_name}"
    nodes.append(
        {
            "id": central_id,
            "label": module_name,
            "group": "Module",
            "title": f"Module: {module_name}",
            "color": get_node_color("Module"),
            "size": 30,
        }
    )
    seen_nodes.add(central_id)

    for idx, imp in enumerate(importers):
        path = imp.get("importer_file_path", f"file_{idx}")
        file_name = Path(path).name if path else f"file_{idx}"
        node_id = f"importer_{idx}"
        if node_id not in seen_nodes:
            nodes.append(
                {
                    "id": node_id,
                    "label": file_name,
                    "group": "Importer",
                    "title": f"File: {path}\nLine: {imp.get('import_line_number', '')}",
                    "color": get_node_color("File"),
                }
            )
            seen_nodes.add(node_id)
        edges.append(
            {"from": node_id, "to": central_id, "label": "imports", "arrows": "to"}
        )

    for idx, imp in enumerate(imports):
        imported_module = imp.get("imported_module", f"module_{idx}")
        alias = imp.get("import_alias", "")
        node_id = f"imported_{idx}"
        if node_id not in seen_nodes:
            nodes.append(
                {
                    "id": node_id,
                    "label": imported_module + (f" as {alias}" if alias else ""),
                    "group": "Imported",
                    "title": f"Module: {imported_module}",
                    "color": get_node_color("Package"),
                }
            )
            seen_nodes.add(node_id)
        edges.append(
            {"from": central_id, "to": node_id, "label": "imports", "arrows": "to"}
        )

    return _render_visualization(
        nodes,
        edges,
        f"Dependencies: {module_name}",
        "force",
        f"{len(importers)} importer(s), {len(imports)} import(s)",
        "pcg_deps",
    )


def visualize_inheritance_tree(results: dict, class_name: str) -> str | None:
    """Visualize class inheritance relationships.

    Args:
        results: Dictionary with ``parent_classes``, ``child_classes``, and ``methods``.
        class_name: Central class name.

    Returns:
        The saved visualization path, or ``None`` when there is nothing to show.
    """
    parents = results.get("parent_classes", [])
    children = results.get("child_classes", [])
    methods = results.get("methods", [])
    if not parents and not children:
        console.print("[yellow]No inheritance hierarchy to visualize.[/yellow]")
        return None

    nodes = []
    edges = []
    seen_nodes = set()
    central_id = f"central_{class_name}"
    method_list = ", ".join(method.get("method_name", "") for method in methods[:5])
    if len(methods) > 5:
        method_list += f"... (+{len(methods) - 5} more)"

    nodes.append(
        {
            "id": central_id,
            "label": class_name,
            "group": "Class",
            "title": f"Class: {class_name}\nMethods: {method_list or 'None'}",
            "color": get_node_color("Class"),
            "size": 30,
            "level": 1,
        }
    )
    seen_nodes.add(central_id)

    for idx, parent in enumerate(parents):
        node_id = f"parent_{idx}"
        if node_id not in seen_nodes:
            nodes.append(
                {
                    "id": node_id,
                    "label": parent.get("parent_class", f"Parent_{idx}"),
                    "group": "Parent",
                    "title": f"Parent: {parent.get('parent_class', f'Parent_{idx}')}\nFile: {parent.get('parent_file_path', '')}",
                    "color": get_node_color("Parent"),
                    "level": 0,
                }
            )
            seen_nodes.add(node_id)
        edges.append(
            {"from": central_id, "to": node_id, "label": "extends", "arrows": "to"}
        )

    for idx, child in enumerate(children):
        node_id = f"child_{idx}"
        if node_id not in seen_nodes:
            nodes.append(
                {
                    "id": node_id,
                    "label": child.get("child_class", f"Child_{idx}"),
                    "group": "Child",
                    "title": f"Child: {child.get('child_class', f'Child_{idx}')}\nFile: {child.get('child_file_path', '')}",
                    "color": get_node_color("Child"),
                    "level": 2,
                }
            )
            seen_nodes.add(node_id)
        edges.append(
            {"from": node_id, "to": central_id, "label": "extends", "arrows": "to"}
        )

    return _render_visualization(
        nodes,
        edges,
        f"Class Hierarchy: {class_name}",
        "hierarchical",
        f"{len(parents)} parent(s), {len(children)} child(ren), {len(methods)} method(s)",
        "pcg_tree",
    )
