"""Result-centric graph visualization builders."""

from __future__ import annotations

from .core import _safe_json_dumps, console, get_node_color
from .graph_relationships import _render_visualization


def visualize_overrides(results: list[dict], function_name: str) -> str | None:
    """Visualize override implementations for a method.

    Args:
        results: Override result rows containing class and method metadata.
        function_name: Method name being visualized.

    Returns:
        The saved visualization path, or ``None`` when there is nothing to show.
    """
    if not results:
        console.print("[yellow]No overrides to visualize.[/yellow]")
        return None

    nodes = []
    edges = []
    seen_nodes = set()
    central_id = f"method_{function_name}"
    nodes.append(
        {
            "id": central_id,
            "label": f"Method: {function_name}",
            "group": "Method",
            "title": f"Method: {function_name}\n{len(results)} implementation(s)",
            "color": get_node_color("Function"),
            "size": 30,
        }
    )
    seen_nodes.add(central_id)

    for idx, result in enumerate(results):
        node_id = f"class_{idx}"
        if node_id not in seen_nodes:
            nodes.append(
                {
                    "id": node_id,
                    "label": result.get("class_name", f"Class_{idx}"),
                    "group": "Class",
                    "title": (
                        f"Class: {result.get('class_name', f'Class_{idx}')}\n"
                        f"File: {result.get('class_file_path', '')}\n"
                        f"Line: {result.get('function_line_number', '')}"
                    ),
                    "color": get_node_color("Override"),
                }
            )
            seen_nodes.add(node_id)
        edges.append(
            {"from": node_id, "to": central_id, "label": "implements", "arrows": "to"}
        )

    return _render_visualization(
        nodes,
        edges,
        f"Overrides: {function_name}",
        "force",
        f"{len(results)} implementation(s) found",
        "pcg_overrides",
    )


def visualize_search_results(
    results: list[dict],
    search_term: str,
    search_type: str = "search",
) -> str | None:
    """Visualize generic search results around a central search term.

    Args:
        results: Search result rows.
        search_term: Term used to perform the search.
        search_type: Search mode used to generate the results.

    Returns:
        The saved visualization path, or ``None`` when there is nothing to show.
    """
    if not results:
        console.print("[yellow]No search results to visualize.[/yellow]")
        return None

    nodes = [
        {
            "id": "search_center",
            "label": f"Search: {search_term}",
            "group": "Search",
            "title": f"Search term: {search_term}\n{len(results)} result(s)",
            "color": {"background": "#ff4081", "border": "#c51162"},
            "size": 35,
        }
    ]
    edges = []
    seen_nodes = {"search_center"}

    for idx, result in enumerate(results):
        node_id = f"result_{idx}"
        node_type = result.get("type", "Unknown")
        if node_id not in seen_nodes:
            nodes.append(
                {
                    "id": node_id,
                    "label": result.get("name", f"result_{idx}"),
                    "group": node_type,
                    "title": (
                        f"{node_type}: {result.get('name', f'result_{idx}')}\n"
                        f"File: {result.get('path', '')}\n"
                        f"Line: {result.get('line_number', '')}"
                    ),
                    "color": get_node_color(
                        "Package" if result.get("is_dependency", False) else node_type
                    ),
                }
            )
            seen_nodes.add(node_id)
        edges.append(
            {
                "from": "search_center",
                "to": node_id,
                "label": "matches",
                "arrows": "to",
                "dashes": True,
            }
        )

    return _render_visualization(
        nodes,
        edges,
        f"Search Results: {search_term}",
        "force",
        f"Found {len(results)} match(es) for '{search_term}'",
        f"pcg_find_{search_type}",
    )


def visualize_cypher_results(records: list[dict], query: str) -> str | None:
    """Visualize raw Cypher records as graph nodes.

    Args:
        records: Records returned by a Cypher query.
        query: Original query string.

    Returns:
        The saved visualization path, or ``None`` when there is nothing to show.
    """
    if not records:
        console.print("[yellow]No query results to visualize.[/yellow]")
        return None

    nodes = []
    edges = []
    seen_nodes = set()

    for record in records:
        for _, value in record.items():
            if isinstance(value, dict):
                node_id = value.get("id", value.get("name", f"node_{len(seen_nodes)}"))
                if str(node_id) not in seen_nodes:
                    labels = value.get("labels", ["Node"])
                    label = (
                        labels[0]
                        if isinstance(labels, list) and labels
                        else str(labels)
                    )
                    name = value.get("name", str(node_id))
                    nodes.append(
                        {
                            "id": str(node_id),
                            "label": str(name) if name else str(node_id),
                            "group": label,
                            "title": _safe_json_dumps(value),
                            "color": get_node_color(label),
                        }
                    )
                    seen_nodes.add(str(node_id))
            elif isinstance(value, list):
                for item in value:
                    if not isinstance(item, dict):
                        continue
                    node_id = item.get(
                        "id", item.get("name", f"node_{len(seen_nodes)}")
                    )
                    if str(node_id) in seen_nodes:
                        continue
                    labels = item.get("labels", ["Node"])
                    label = labels[0] if isinstance(labels, list) and labels else "Node"
                    name = item.get("name", str(node_id))
                    nodes.append(
                        {
                            "id": str(node_id),
                            "label": str(name) if name else str(node_id),
                            "group": label,
                            "title": _safe_json_dumps(item),
                            "color": get_node_color(label),
                        }
                    )
                    seen_nodes.add(str(node_id))

    short_query = query[:50] + "..." if len(query) > 50 else query
    return _render_visualization(
        nodes,
        edges,
        "Cypher Query Results",
        "force",
        f"Query: {short_query}",
        "pcg_query",
    )
