"""
Bundle a graph JSON into a single self-contained HTML file.

Inlines Cytoscape.js + fcose extension and the visualization JS so the result
opens in a browser via file:// with no server and no network access required.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .export import export_cytoscape_json
from .graph.models import Edge, Node

_WEB_ROOT = Path(__file__).parent / 'web'
_STATIC_JS = _WEB_ROOT / 'static' / 'js'
_TEMPLATE  = _WEB_ROOT / 'templates' / 'graph-view.html'

# JS files inlined in order — fcose's deps must load before fcose itself.
_INLINE_SCRIPTS = [
    'cytoscape.min.js',
    'layout-base.js',
    'cose-base.js',
    'cytoscape-fcose.js',
]


def _read_static(name: str) -> str:
    return (_STATIC_JS / name).read_text(encoding='utf-8')


def _compute_stats(nodes: list[dict[str, Any]],
                   edges: list[dict[str, Any]]) -> dict[str, Any]:
    node_types: dict[str, int] = {}
    for n in nodes:
        t = n.get('node_type', 'unknown')
        node_types[t] = node_types.get(t, 0) + 1

    edge_types: dict[str, int] = {}
    for e in edges:
        t = e.get('edge_type', 'unknown')
        edge_types[t] = edge_types.get(t, 0) + 1

    return {
        'total_nodes': len(nodes),
        'total_edges': len(edges),
        'node_types':  node_types,
        'edge_types':  edge_types,
    }


def bundle_html(graph_json_path: str, output_path: str,
                title: str | None = None) -> None:
    """Produce a self-contained HTML for the graph at graph_json_path."""
    with open(graph_json_path, encoding='utf-8') as f:
        data = json.load(f)

    nodes_raw = data.get('nodes', [])
    edges_raw = data.get('edges', [])
    nodes = [Node.from_dict(n) for n in nodes_raw]
    edges = [Edge.from_dict(e) for e in edges_raw]
    elements = export_cytoscape_json(nodes, edges)
    stats    = _compute_stats(nodes_raw, edges_raw)

    title = title or Path(graph_json_path).stem

    html = _TEMPLATE.read_text(encoding='utf-8')
    viz_js = _read_static('visualization.js')

    # Replace title placeholder
    html = html.replace('{{ title }}', title)

    # Replace external <script src="..."> tags with inlined contents
    head_scripts = []
    for name in _INLINE_SCRIPTS:
        content = _read_static(name)
        head_scripts.append(f'<script>/* {name} */\n{content}\n</script>')

    # Strip the original <script src="/static/js/..."> block (the head ones).
    # Our template has them on consecutive lines after a comment.
    import re
    replacement = '\n'.join(head_scripts) + '\n'
    html = re.sub(
        r'<!-- Cytoscape\.js \+ fcose layout \(served locally\) -->\s*'
        r'(<script src="/static/js/[^"]+"></script>\s*)+',
        lambda _m: replacement,
        html,
        count=1,
    )

    # Inject the graph data + stats, and adapt visualization.js to read from
    # those globals instead of calling /api/*.
    payload = {'elements': elements, 'stats': stats}
    data_block = (
        '<script id="__graph_data__" type="application/json">'
        + json.dumps(payload, ensure_ascii=False)
        + '</script>'
    )

    # Replace the fetch() block with an inline data reader.
    viz_js_patched = viz_js.replace(
        "const [elemRes, statsRes] = await Promise.all([\n"
        "        fetch('/api/graph'),\n"
        "        fetch('/api/stats'),\n"
        "      ]);\n"
        "      if (!elemRes.ok) throw new Error(`/api/graph returned ${elemRes.status}`);\n"
        "      elements = await elemRes.json();\n"
        "      statsData = statsRes.ok ? await statsRes.json() : null;",
        "const payload = JSON.parse(\n"
        "        document.getElementById('__graph_data__').textContent\n"
        "      );\n"
        "      elements = payload.elements;\n"
        "      statsData = payload.stats;"
    )

    # Replace the external visualization.js script tag with the patched contents
    inline_viz = (
        data_block
        + '\n<script>/* visualization.js (inlined) */\n'
        + viz_js_patched
        + '\n</script>'
    )
    html = html.replace(
        '<script src="/static/js/visualization.js"></script>',
        inline_viz,
    )

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(html, encoding='utf-8')
