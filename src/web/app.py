"""
Flask web application for interactive graph visualization.
"""
from __future__ import annotations

import json
from pathlib import Path

from flask import Flask, jsonify, render_template

from ..export import export_cytoscape_json
from ..graph.models import Edge, Node


def create_app(graph_json_path: str) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(
        __name__,
        template_folder='templates',
        static_folder='static',
    )

    graph_path = Path(graph_json_path).resolve()

    @app.route('/')
    def index():  # type: ignore[return]
        return render_template('graph-view.html', title=graph_path.stem)

    @app.route('/api/graph')
    def graph_data():  # type: ignore[return]
        with open(graph_path, encoding='utf-8') as f:
            data = json.load(f)

        nodes = [Node.from_dict(n) for n in data.get('nodes', [])]
        edges = [Edge.from_dict(e) for e in data.get('edges', [])]
        elements = export_cytoscape_json(nodes, edges)
        return jsonify(elements)

    @app.route('/api/stats')
    def stats():  # type: ignore[return]
        with open(graph_path, encoding='utf-8') as f:
            data = json.load(f)

        nodes = data.get('nodes', [])
        edges = data.get('edges', [])

        node_types: dict[str, int] = {}
        for n in nodes:
            t = n.get('node_type', 'unknown')
            node_types[t] = node_types.get(t, 0) + 1

        edge_types: dict[str, int] = {}
        for e in edges:
            t = e.get('edge_type', 'unknown')
            edge_types[t] = edge_types.get(t, 0) + 1

        return jsonify({
            'total_nodes': len(nodes),
            'total_edges': len(edges),
            'node_types': node_types,
            'edge_types': edge_types,
        })

    return app
