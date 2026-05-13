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
        elements.append({
            'data': {
                'id': node.id,
                'label': node.label,
                'type': node.node_type,
                'path': node.path,
                'url': node.url,
                'project': node.project,
            },
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
