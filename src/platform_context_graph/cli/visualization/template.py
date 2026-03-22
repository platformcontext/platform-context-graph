"""HTML template builder for CLI graph visualizations."""

from __future__ import annotations

from typing import Any

from .core import escape_html, _json_for_inline_script

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>__TITLE__ | PlatformContextGraph</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
  <style>
    :root { --bg:#0f172a; --panel:rgba(15,23,42,.82); --panel-strong:rgba(30,41,59,.86); --text:#f8fafc; --muted:#94a3b8; --accent:#818cf8; --border:rgba(255,255,255,.12); }
    * { box-sizing:border-box; }
    body { margin:0; font-family:'Outfit',sans-serif; color:var(--text); background:radial-gradient(circle at top left, rgba(99,102,241,.18), transparent 35%),radial-gradient(circle at bottom right, rgba(56,189,248,.12), transparent 35%),var(--bg); overflow:hidden; }
    #mynetwork { width:100vw; height:100vh; }
    .panel { position:fixed; background:var(--panel); backdrop-filter:blur(14px); border:1px solid var(--border); border-radius:18px; box-shadow:0 18px 40px rgba(0,0,0,.28); }
    .header { top:18px; left:18px; right:18px; padding:14px 18px; display:flex; justify-content:space-between; align-items:center; gap:16px; z-index:10; }
    .brand { display:flex; align-items:center; gap:12px; }
    .brand-mark { width:32px; height:32px; border-radius:10px; display:grid; place-items:center; background:linear-gradient(135deg,#6366f1,#38bdf8); font-weight:700; box-shadow:0 0 18px rgba(99,102,241,.45); }
    .brand-copy { display:flex; flex-direction:column; gap:2px; }
    .brand-title { font-weight:700; letter-spacing:-.02em; }
    .brand-subtitle { font-size:.9rem; color:var(--muted); }
    .stats { display:flex; gap:18px; align-items:center; }
    .stat { display:flex; flex-direction:column; align-items:flex-end; }
    .stat-label { font-size:.7rem; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); }
    .stat-value { font-size:1rem; font-weight:600; color:var(--accent); }
    .search-panel { top:96px; left:18px; width:240px; padding:14px; z-index:10; }
    .search-title, .legend-title { font-size:.74rem; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); font-weight:700; }
    .search-input { width:100%; margin-top:10px; border-radius:10px; border:1px solid var(--border); background:rgba(0,0,0,.18); color:var(--text); padding:10px 12px; font-family:inherit; outline:none; }
    .search-input:focus { border-color:#6366f1; box-shadow:0 0 0 2px rgba(99,102,241,.22); }
    .search-description { margin-top:10px; font-size:.84rem; color:var(--muted); line-height:1.45; }
    .legend { left:18px; bottom:18px; width:240px; padding:16px 14px; z-index:10; max-height:42vh; overflow:auto; }
    .legend-item { display:flex; align-items:center; gap:10px; padding:7px 0; color:#dbe4f2; cursor:pointer; }
    .legend-item:hover { color:#fff; }
    .legend-swatch { width:11px; height:11px; border-radius:999px; flex:none; }
    .info-panel { top:96px; right:18px; width:340px; max-height:calc(100vh - 120px); padding:20px; z-index:10; overflow:auto; transform:translateX(calc(100% + 24px)); transition:transform .25s ease; }
    .info-panel.active { transform:translateX(0); }
    .info-header { display:flex; justify-content:space-between; align-items:center; gap:12px; }
    .badge { font-size:.72rem; letter-spacing:.06em; text-transform:uppercase; font-weight:700; padding:6px 10px; border-radius:999px; border:1px solid var(--border); }
    .close-btn { cursor:pointer; color:var(--muted); font-size:1.1rem; }
    .close-btn:hover { color:#fff; }
    .node-name { margin:14px 0 0; font-size:1.3rem; font-weight:700; word-break:break-word; }
    .field { margin-top:16px; }
    .field-label { font-size:.72rem; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); margin-bottom:6px; }
    .field-value { font-family:'JetBrains Mono',monospace; font-size:.84rem; padding:10px 12px; border-radius:10px; background:rgba(0,0,0,.18); border:1px solid rgba(255,255,255,.05); word-break:break-word; white-space:pre-wrap; }
    .controls { position:fixed; right:18px; bottom:18px; z-index:10; padding:10px 14px; font-size:.78rem; color:var(--muted); }
    ::-webkit-scrollbar { width:7px; } ::-webkit-scrollbar-thumb { background:rgba(148,163,184,.35); border-radius:999px; }
  </style>
</head>
<body>
  <div class="panel header">
    <div class="brand">
      <div class="brand-mark">C</div>
      <div class="brand-copy">
        <div class="brand-title">PlatformContextGraph</div>
        <div class="brand-subtitle">__TITLE__</div>
      </div>
    </div>
    <div class="stats">
      <div class="stat"><span class="stat-label">Nodes</span><span class="stat-value">__NODE_COUNT__</span></div>
      <div class="stat"><span class="stat-label">Edges</span><span class="stat-value">__EDGE_COUNT__</span></div>
    </div>
  </div>
  <div class="panel search-panel">
    <div class="search-title">Quick Search</div>
    <input id="node-search" class="search-input" type="text" placeholder="Find symbol...">
    <div class="search-description">__DESCRIPTION__</div>
  </div>
  <div id="info-panel" class="panel info-panel">
    <div class="info-header">
      <div id="node-badge" class="badge">TYPE</div>
      <div id="close-panel" class="close-btn">✕</div>
    </div>
    <div id="node-name" class="node-name">Symbol Name</div>
    <div class="field"><div class="field-label">File Path</div><div id="node-path" class="field-value">Unknown</div></div>
    <div class="field"><div class="field-label">Context</div><div id="node-context" class="field-value">None</div></div>
    <div class="field"><div class="field-label">Details</div><div id="node-details" class="field-value">No additional details.</div></div>
  </div>
  <div id="mynetwork"></div>
  <div class="panel legend"><div class="legend-title">Entity Types</div><div id="legend-items"></div></div>
  <div class="panel controls">Scroll to zoom • Click to inspect • Drag to explore</div>
  <script>
    const nodesData = __NODES__;
    const edgesData = __EDGES__;
    const options = __OPTIONS__;
    const nodes = new vis.DataSet(nodesData);
    const edges = new vis.DataSet(edgesData);
    const container = document.getElementById("mynetwork");
    const network = new vis.Network(container, { nodes, edges }, options);
    const infoPanel = document.getElementById("info-panel");
    const searchInput = document.getElementById("node-search");
    function closePanel() { infoPanel.classList.remove("active"); resetNodes(); }
    function resetNodes() { nodes.forEach((node) => nodes.update({ id: node.id, opacity: 1 })); }
    function parseTooltip(text) {
      const lines = (text || "").split("\\n");
      let path = "Unknown";
      let context = "None";
      for (const line of lines) {
        if (line.startsWith("File:")) path = line.replace("File:", "").trim();
        if (line.startsWith("Line:")) context = "Line " + line.replace("Line:", "").trim();
      }
      return { path, context, details: text || "No additional details." };
    }
    function accentColor(node) {
      if (node && typeof node.color === "object") return node.color.border || node.color.background || "#94a3b8";
      return "#94a3b8";
    }
    document.getElementById("close-panel").addEventListener("click", closePanel);
    network.on("click", (params) => {
      if (!params.nodes.length) { closePanel(); return; }
      const node = nodes.get(params.nodes[0]);
      const parsed = parseTooltip(node.title || "");
      const color = accentColor(node);
      document.getElementById("node-name").textContent = node.label || "Unknown";
      const badge = document.getElementById("node-badge");
      badge.textContent = node.group || "Unknown";
      badge.style.color = color;
      badge.style.backgroundColor = color + "22";
      badge.style.borderColor = color;
      document.getElementById("node-path").textContent = parsed.path;
      document.getElementById("node-context").textContent = parsed.context;
      document.getElementById("node-details").textContent = parsed.details;
      infoPanel.classList.add("active");
      const connected = new Set(network.getConnectedNodes(node.id));
      nodes.forEach((item) => nodes.update({ id: item.id, opacity: item.id === node.id || connected.has(item.id) ? 1 : 0.14 }));
    });
    const groups = [...new Set(nodesData.map((node) => node.group).filter(Boolean))];
    const legendContainer = document.getElementById("legend-items");
    groups.forEach((group) => {
      const node = nodesData.find((candidate) => candidate.group === group);
      const color = accentColor(node);
      const item = document.createElement("div");
      item.className = "legend-item";
      item.innerHTML = `<span class="legend-swatch" style="background:${color}"></span><span>${group}</span>`;
      item.addEventListener("click", () => {
        nodes.forEach((candidate) => nodes.update({ id: candidate.id, opacity: candidate.group === group ? 1 : 0.14 }));
      });
      legendContainer.appendChild(item);
    });
    searchInput.addEventListener("input", (event) => {
      const term = event.target.value.trim().toLowerCase();
      if (!term) { resetNodes(); return; }
      nodes.forEach((node) => {
        const label = (node.label || "").toLowerCase();
        nodes.update({ id: node.id, opacity: label.includes(term) ? 1 : 0.08 });
      });
    });
  </script>
</body>
</html>
"""


def _layout_options(layout_type: str) -> dict[str, Any]:
    """Build vis-network layout options for a given visualization mode.

    Args:
        layout_type: Layout type requested by the caller.

    Returns:
        A vis-network options dictionary.
    """
    base = {
        "nodes": {
            "shape": "dot",
            "size": 24,
            "font": {"color": "#e2e8f0", "size": 14, "face": "Outfit"},
            "borderWidth": 2,
            "shadow": {
                "enabled": True,
                "color": "rgba(0,0,0,0.5)",
                "size": 10,
                "x": 0,
                "y": 4,
            },
        },
        "edges": {
            "width": 1.5,
            "color": {
                "color": "rgba(148, 163, 184, 0.3)",
                "highlight": "#6366f1",
                "hover": "#818cf8",
            },
            "font": {
                "size": 11,
                "face": "Outfit",
                "color": "#94a3b8",
                "strokeWidth": 0,
            },
            "smooth": {
                "type": "cubicBezier",
                "forceDirection": "none",
                "roundness": 0.5,
            },
            "arrows": {"to": {"enabled": True, "scaleFactor": 0.5}},
        },
        "interaction": {
            "hover": True,
            "tooltipDelay": 300,
            "hideEdgesOnDrag": True,
            "navigationButtons": False,
            "keyboard": True,
        },
    }
    if layout_type == "hierarchical":
        base.update(
            {
                "layout": {
                    "hierarchical": {
                        "enabled": True,
                        "direction": "UD",
                        "sortMethod": "directed",
                        "levelSeparation": 100,
                        "nodeSpacing": 150,
                        "treeSpacing": 200,
                        "blockShifting": True,
                        "edgeMinimization": True,
                        "parentCentralization": True,
                    }
                },
                "physics": {"enabled": False},
            }
        )
        return base
    if layout_type == "hierarchical_lr":
        base.update(
            {
                "layout": {
                    "hierarchical": {
                        "enabled": True,
                        "direction": "LR",
                        "sortMethod": "directed",
                        "levelSeparation": 200,
                        "nodeSpacing": 100,
                        "treeSpacing": 200,
                    }
                },
                "physics": {"enabled": False},
            }
        )
        return base

    base.update(
        {
            "layout": {"improvedLayout": True},
            "physics": {
                "enabled": True,
                "forceAtlas2Based": {
                    "gravitationalConstant": -50,
                    "centralGravity": 0.01,
                    "springLength": 150,
                    "springConstant": 0.08,
                    "damping": 0.4,
                },
                "maxVelocity": 50,
                "solver": "forceAtlas2Based",
                "timestep": 0.35,
                "stabilization": {
                    "enabled": True,
                    "iterations": 200,
                    "updateInterval": 25,
                },
            },
        }
    )
    return base


def generate_html_template(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    title: str,
    layout_type: str = "force",
    description: str = "",
) -> str:
    """Generate the standalone HTML document for a graph visualization.

    Args:
        nodes: vis-network node payloads.
        edges: vis-network edge payloads.
        title: Visualization title.
        layout_type: vis-network layout mode.
        description: Optional descriptive text displayed beside the search box.

    Returns:
        A complete HTML document string.
    """
    safe_nodes = []
    for node in nodes:
        node_copy = dict(node)
        if "title" in node_copy:
            node_copy["title"] = escape_html(node_copy.get("title", ""))
        safe_nodes.append(node_copy)

    rendered = _HTML_TEMPLATE
    replacements = {
        "__TITLE__": escape_html(title),
        "__DESCRIPTION__": escape_html(description),
        "__NODE_COUNT__": str(len(nodes)),
        "__EDGE_COUNT__": str(len(edges)),
        "__NODES__": _json_for_inline_script(safe_nodes),
        "__EDGES__": _json_for_inline_script([dict(edge) for edge in edges]),
        "__OPTIONS__": _json_for_inline_script(_layout_options(layout_type)),
    }
    for key, value in replacements.items():
        rendered = rendered.replace(key, value)
    return rendered
