"""
Bundle a graph JSON into a single self-contained HTML file.

Inlines Cytoscape.js + fcose + navigator extensions and the visualization JS so
the result opens in a browser via file:// with no server / no network needed.

The visualization JS itself contains a small data-source adapter that prefers
`window.__DGL_DATA__` if present and falls back to the Flask `/api/*`
endpoints otherwise. So the bundler only has to:

  1. Inline the vendor scripts.
  2. Inline `<script>window.__DGL_DATA__ = {...}</script>` before the viz.
  3. Inline the visualization JS unchanged.

This means tweaks to visualization.js cannot silently break the standalone.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .export import export_cytoscape_json
from .graph.models import Edge, Node

_WEB_ROOT = Path(__file__).parent / 'web'
_STATIC_JS = _WEB_ROOT / 'static' / 'js'
_STATIC_CSS = _WEB_ROOT / 'static' / 'css'
_TEMPLATE  = _WEB_ROOT / 'templates' / 'graph-view.html'

# Order matters: fcose's deps load before fcose itself; navigator after core.
_INLINE_SCRIPTS = [
    'cytoscape.min.js',
    'layout-base.js',
    'cose-base.js',
    'cytoscape-fcose.js',
    'cytoscape-navigator.js',
]


def _read_static(name: str, subdir: str = 'js') -> str:
    path = (_STATIC_CSS if subdir == 'css' else _STATIC_JS) / name
    return path.read_text(encoding='utf-8')


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
    html = _TEMPLATE.read_text(encoding='utf-8').replace('{{ title }}', title)

    # Replace the head <script src=...> block with inlined contents.
    head_scripts = []
    for name in _INLINE_SCRIPTS:
        try:
            content = _read_static(name)
        except FileNotFoundError:
            continue
        head_scripts.append(f'<script>/* {name} */\n{content}\n</script>')

    # Inline navigator CSS too so the standalone has no external requests.
    try:
        nav_css = _read_static('cytoscape.js-navigator.css', 'css')
        head_block = f'<style>/* navigator css */\n{nav_css}\n</style>\n'
    except FileNotFoundError:
        head_block = ''
    head_block += '\n'.join(head_scripts) + '\n'

    # Replace everything from the Cytoscape comment through the last script
    # tag in the head's vendor block.
    html = re.sub(
        r'<!--\s*Cytoscape\.js[^>]*-->\s*'
        r'(?:<link[^>]+/>\s*)?'
        r'(?:<script src="/static/js/[^"]+"></script>\s*)+',
        lambda _m: head_block,
        html,
        count=1,
    )

    # Inject data immediately before the visualization.js <script> tag so the
    # adapter picks it up.
    payload = {'elements': elements, 'stats': stats}
    inline_data = (
        '<script>window.__DGL_DATA__ = '
        + json.dumps(payload, ensure_ascii=False)
        + ';</script>\n'
    )
    viz_js = _read_static('visualization.js')
    inline_viz = (
        inline_data
        + '<script>/* visualization.js (inlined) */\n'
        + viz_js
        + '\n</script>'
    )
    html = html.replace(
        '<script src="/static/js/visualization.js"></script>',
        inline_viz,
    )

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(html, encoding='utf-8')
