"""
Serialization helpers: export graph to plain JSON and Cytoscape.js format.
"""
from __future__ import annotations

from typing import Any

from .graph.models import Edge, Node


def export_graph_json(nodes: list[Node], edges: list[Edge]) -> dict[str, Any]:
    """Return a plain JSON-serialisable dict with nodes and edges."""
    return {
        'nodes': [n.to_dict() for n in nodes],
        'edges': [e.to_dict() for e in edges],
    }


def export_cytoscape_json(nodes: list[Node], edges: list[Edge]) -> list[dict[str, Any]]:
    """Return a list of Cytoscape.js elements (nodes + edges)."""
    elements: list[dict[str, Any]] = []

    for node in nodes:
        meta = node.metadata or {}
        data: dict[str, Any] = {
            'id': node.id,
            'label': node.label,
            'type': node.node_type,
            'path': node.path,
            'url': node.url,
            'project': node.project,
        }
        # Flatten select metadata fields into the element so Cytoscape
        # selectors / the viz can use them directly.
        if meta.get('diataxis'):    data['diataxis']    = meta['diataxis']
        if meta.get('source_url'):  data['source_url']  = meta['source_url']
        if meta.get('render_url'):  data['render_url']  = meta['render_url']
        if meta.get('resolved') is False:
            data['broken'] = 'true'

        elements.append({
            'data': data,
            'classes': ' '.join(filter(None, [node.node_type, node.project])),
        })

    for i, edge in enumerate(edges):
        elements.append({
            'data': {
                'id': f'e{i}',
                'source': edge.source,
                'target': edge.target,
                'type': edge.edge_type,
                'label': edge.label,
            },
            'classes': edge.edge_type,
        })

    return elements
