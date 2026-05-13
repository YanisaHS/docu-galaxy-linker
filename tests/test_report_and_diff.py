"""
Tests for the `report` and `diff` modules.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.diff import compute_diff, render_markdown as render_diff_md
from src.report import build_report, render_markdown, render_json, render_csv


@pytest.fixture
def tiny_graph(tmp_path: Path) -> str:
    """A tiny synthetic graph with one of each finding category."""
    data = {
        'nodes': [
            {'id': 'tutorial/start.md', 'node_type': 'document',
             'label': 'start.md', 'path': 'tutorial/start.md', 'url': None,
             'project': 'demo',
             'metadata': {'diataxis': 'tutorial', 'resolved': True,
                          'source_url': 'https://example.com/blob/main/tutorial/start.md'}},
            {'id': 'reference/api.md', 'node_type': 'document',
             'label': 'api.md', 'path': 'reference/api.md', 'url': None,
             'project': 'demo',
             'metadata': {'diataxis': 'reference', 'resolved': True}},
            {'id': 'how-to/missing.md', 'node_type': 'document',
             'label': 'missing.md', 'path': 'how-to/missing.md', 'url': None,
             'project': 'demo',
             'metadata': {'diataxis': 'how-to', 'resolved': False}},
            {'id': 'explanation/lonely.md', 'node_type': 'document',
             'label': 'lonely.md', 'path': 'explanation/lonely.md', 'url': None,
             'project': 'demo',
             'metadata': {'diataxis': 'explanation', 'resolved': True}},
            {'id': 'https://example.com', 'node_type': 'external',
             'label': 'https://example.com', 'path': None,
             'url': 'https://example.com', 'project': None, 'metadata': {}},
            {'id': 'label:undef', 'node_type': 'label', 'label': 'undef',
             'path': None, 'url': None, 'project': 'demo',
             'metadata': {'resolved': False}},
        ],
        'edges': [
            # start.md -> api.md (tutorial → reference: cross-edge)
            {'source': 'tutorial/start.md', 'target': 'reference/api.md',
             'edge_type': 'doc_link', 'label': '', 'metadata': {}},
            # start.md -> missing.md (broken doc ref)
            {'source': 'tutorial/start.md', 'target': 'how-to/missing.md',
             'edge_type': 'doc_link', 'label': '', 'metadata': {}},
            # start.md -> external
            {'source': 'tutorial/start.md', 'target': 'https://example.com',
             'edge_type': 'external_link', 'label': '', 'metadata': {}},
            # api.md -> label:undef (broken label ref)
            {'source': 'reference/api.md', 'target': 'label:undef',
             'edge_type': 'ref_link', 'label': '', 'metadata': {}},
        ],
    }
    p = tmp_path / 'g.json'
    p.write_text(json.dumps(data))
    return str(p)


class TestReport:
    def test_build(self, tiny_graph: str):
        r = build_report(tiny_graph)
        assert r.project == 'demo'
        assert r.total_nodes == 6
        assert r.total_edges == 4
        assert r.diataxis_counts == {
            'tutorial': 1, 'reference': 1, 'how-to': 1, 'explanation': 1,
        }
        # Orphans: api.md (only inbound is from a doc) - actually it has inbound.
        # Lonely is orphan, missing.md is broken so excluded.
        assert any(o['id'] == 'explanation/lonely.md' for o in r.orphans)
        # missing.md is *not* listed as orphan — it's a broken target, separate
        # category.
        assert not any(o['id'] == 'how-to/missing.md' for o in r.orphans)
        # Dead ends: api.md only links to label:undef so it has outbound;
        # lonely.md has no outbound.
        assert any(d['id'] == 'explanation/lonely.md' for d in r.dead_ends)
        # Broken doc refs
        assert len(r.broken_doc_refs) == 1
        assert r.broken_doc_refs[0]['id'] == 'how-to/missing.md'
        assert r.broken_doc_refs[0]['referrers'] == ['tutorial/start.md']
        # Broken label refs
        assert len(r.broken_label_refs) == 1
        assert r.broken_label_refs[0]['id'] == 'label:undef'
        # Diataxis cross-edges
        pairs = [e['pair'] for e in r.diataxis_cross_edges]
        assert 'tutorial -> reference' in pairs
        # Top hubs: start.md has 3 outgoing
        assert r.top_hubs[0]['id'] == 'tutorial/start.md'
        assert r.top_hubs[0]['out_degree'] == 3
        # External domains
        assert r.external_domains[0]['host'] == 'example.com'

    def test_markdown_render(self, tiny_graph: str):
        text = render_markdown(build_report(tiny_graph))
        assert '# Documentation link report' in text
        assert 'tutorial -> reference' in text
        assert 'how-to/missing.md' in text
        # Source URL link is rendered
        assert '(https://example.com/blob/main/tutorial/start.md)' in text

    def test_json_render(self, tiny_graph: str):
        text = render_json(build_report(tiny_graph))
        d = json.loads(text)
        assert d['project'] == 'demo'
        assert 'orphans' in d
        assert 'broken_doc_refs' in d

    def test_csv_render(self, tiny_graph: str):
        text = render_csv(build_report(tiny_graph))
        lines = text.strip().splitlines()
        header = lines[0].split(',')
        assert 'category' in header[0]
        # At least one orphan and one broken doc ref row
        assert any(l.startswith('orphan,') for l in lines[1:])
        assert any(l.startswith('broken_doc_ref,') for l in lines[1:])


class TestDiff:
    def test_no_change(self, tiny_graph: str):
        d = compute_diff(tiny_graph, tiny_graph)
        assert d.regression_count() == 0
        assert not d.docs_added and not d.docs_removed

    def test_new_orphan_is_regression(self, tmp_path: Path, tiny_graph: str):
        # Build a HEAD where we remove the edge that points at api.md → it
        # becomes an orphan (its only inbound was start.md).
        with open(tiny_graph) as f:
            base = json.load(f)
        head = {
            'nodes': base['nodes'],
            'edges': [e for e in base['edges']
                      if not (e['source'] == 'tutorial/start.md'
                              and e['target'] == 'reference/api.md')],
        }
        head_path = tmp_path / 'head.json'
        head_path.write_text(json.dumps(head))

        d = compute_diff(tiny_graph, str(head_path))
        assert 'reference/api.md' in d.orphans_added
        assert d.regression_count() >= 1

    def test_renders_markdown(self, tiny_graph: str):
        d = compute_diff(tiny_graph, tiny_graph)
        text = render_diff_md(d)
        assert 'No regressions' in text

    def test_fixed_orphan_is_not_regression(self, tmp_path: Path, tiny_graph: str):
        # BASE has the orphan; HEAD adds an edge into it.
        with open(tiny_graph) as f:
            base = json.load(f)
        head = json.loads(json.dumps(base))  # deep copy
        head['edges'].append({
            'source': 'tutorial/start.md',
            'target': 'explanation/lonely.md',
            'edge_type': 'doc_link', 'label': '', 'metadata': {},
        })
        head_path = tmp_path / 'head.json'
        head_path.write_text(json.dumps(head))
        d = compute_diff(tiny_graph, str(head_path))
        assert 'explanation/lonely.md' in d.orphans_removed
        assert d.regression_count() == 0
