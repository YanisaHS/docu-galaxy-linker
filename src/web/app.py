"""
Flask web application for interactive graph visualization.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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


def create_concept_app(graph_data: dict[str, Any]) -> Flask:
    """Create a Flask app for the concept / topic map visualisation."""
    app = Flask(
        __name__,
        template_folder='templates',
        static_folder='static',
    )

    @app.route('/')
    def index():  # type: ignore[return]
        return render_template('concept-map.html', title='Landscape Concept Map')

    @app.route('/api/graph')
    def concept_graph():  # type: ignore[return]
        nodes = graph_data.get('nodes', [])
        edges = graph_data.get('edges', [])

        elements = []
        for n in nodes:
            elements.append({
                'data': {
                    'id': n['id'],
                    'label': n.get('label', n['id']),
                    'type': n.get('node_type', 'other'),
                    'section': n.get('metadata', {}).get('section', ''),
                    'word_count': n.get('metadata', {}).get('word_count', 0),
                    'headings': n.get('metadata', {}).get('headings', []),
                    'path': n.get('path', ''),
                    'project': n.get('project', ''),
                },
                'classes': n.get('node_type', 'other'),
            })
        for e in edges:
            elements.append({
                'data': {
                    'id': f"{e.get('edge_type', 'edge')}:{e['source']}→{e['target']}",
                    'source': e['source'],
                    'target': e['target'],
                    'type': e.get('edge_type', 'unknown'),
                    'label': e.get('label', ''),
                    'similarity': e.get('metadata', {}).get('similarity', None),
                    'shared_terms': e.get('metadata', {}).get('shared_terms', []),
                    'heading_overlap': e.get('metadata', {}).get('heading_overlap', 0),
                    'overlap_coefficient': e.get('metadata', {}).get('overlap_coefficient', None),
                    'potential_duplicate': e.get('metadata', {}).get('potential_duplicate', False),
                    'jaccard': e.get('metadata', {}).get('jaccard', None),
                },
                'classes': e.get('edge_type', 'unknown'),
            })
        return jsonify(elements)

    @app.route('/api/stats')
    def stats():  # type: ignore[return]
        nodes = graph_data.get('nodes', [])
        edges = graph_data.get('edges', [])

        section_counts: dict[str, int] = {}
        for n in nodes:
            s = n.get('metadata', {}).get('section', 'Other')
            section_counts[s] = section_counts.get(s, 0) + 1

        edge_types: dict[str, int] = {}
        for e in edges:
            t = e.get('edge_type', 'unknown')
            edge_types[t] = edge_types.get(t, 0) + 1

        return jsonify({
            'total_nodes': len(nodes),
            'total_edges': len(edges),
            'section_counts': section_counts,
            'edge_types': edge_types,
        })

    return app

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
