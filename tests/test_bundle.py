"""
Tests for the standalone HTML bundler.

The bundler is asserted to:
  - Produce a single self-contained HTML file.
  - Inline all vendor scripts (no /static/js/ references remain in the head).
  - Inject the graph data as window.__DGL_DATA__ before visualization.js.
  - Leave visualization.js unchanged (no fragile string substitution).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.bundle import bundle_html


@pytest.fixture
def tiny_graph(tmp_path: Path) -> str:
    data = {
        'nodes': [
            {'id': 'a.md', 'node_type': 'document', 'label': 'a.md',
             'path': 'a.md', 'url': None, 'project': 'demo',
             'metadata': {'diataxis': 'meta', 'resolved': True}},
        ],
        'edges': [],
    }
    p = tmp_path / 'g.json'
    p.write_text(json.dumps(data))
    return str(p)


def test_bundle_produces_html(tiny_graph: str, tmp_path: Path):
    out = tmp_path / 'bundle.html'
    bundle_html(tiny_graph, str(out), title='Demo')
    assert out.exists()
    text = out.read_text(encoding='utf-8')
    assert '<!DOCTYPE html>' in text
    assert 'Demo' in text
    # Data injection
    assert 'window.__DGL_DATA__' in text
    # Inlined libs
    assert 'cytoscape.min.js' in text
    assert 'cytoscape-fcose.js' in text
    # No remaining external script tags pointing to /static/js
    head_section = text.split('<body')[0]
    assert '<script src="/static/js/' not in head_section


def test_bundle_keeps_viz_source_intact(tiny_graph: str, tmp_path: Path):
    """The bundler must not patch visualization.js — it relies on the
    data-source adapter inside the JS to pick up window.__DGL_DATA__."""
    out = tmp_path / 'b.html'
    bundle_html(tiny_graph, str(out))
    text = out.read_text(encoding='utf-8')
    # The exact function name from the adapter pattern.
    assert 'async function loadData' in text
    # Visualization.js still references /api/graph (as a fallback path) —
    # which means it wasn't string-replaced.
    assert "fetch('/api/graph')" in text
