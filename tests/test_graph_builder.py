"""
Unit tests for the graph builder.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.graph.builder import GraphBuilder
from src.parsers.markdown_parser import ParsedLink


FIXTURES = Path(__file__).parent / 'fixtures' / 'docs'


def _make_link(source: str, target: str, link_type: str, text: str = '') -> ParsedLink:
    return ParsedLink(source_file=source, link_text=text, target=target,
                      link_type=link_type, line_number=1)


class TestGraphBuilder:
    def _builder(self) -> GraphBuilder:
        return GraphBuilder(str(FIXTURES))

    def test_document_node_added(self):
        b = self._builder()
        source = str(FIXTURES / 'index.md')
        b.add_parsed_links([], source)
        assert any(n.node_type == 'document' for n in b.get_nodes())

    def test_external_link_creates_external_node(self):
        b = self._builder()
        source = str(FIXTURES / 'index.md')
        links = [_make_link(source, 'https://ubuntu.com', 'md_inline', 'Ubuntu')]
        b.add_parsed_links(links, source)
        nodes_by_id = {n.id: n for n in b.get_nodes()}
        assert 'https://ubuntu.com' in nodes_by_id
        assert nodes_by_id['https://ubuntu.com'].node_type == 'external'

    def test_external_edge_type(self):
        b = self._builder()
        source = str(FIXTURES / 'index.md')
        links = [_make_link(source, 'https://ubuntu.com', 'md_inline')]
        b.add_parsed_links(links, source)
        edges = b.get_edges()
        assert any(e.edge_type == 'external_link' for e in edges)

    def test_myst_ref_creates_label_node(self):
        b = self._builder()
        source = str(FIXTURES / 'index.md')
        links = [_make_link(source, 'getting-started', 'myst_ref')]
        b.add_parsed_links(links, source)
        nodes_by_id = {n.id: n for n in b.get_nodes()}
        assert 'label:getting-started' in nodes_by_id
        assert nodes_by_id['label:getting-started'].node_type == 'label'

    def test_definitions_do_not_create_edges(self):
        b = self._builder()
        source = str(FIXTURES / 'index.md')
        links = [
            _make_link(source, 'https://ubuntu.com', 'md_ref_def', 'ubuntu'),
            _make_link(source, 'my-label', 'myst_label_def', 'my-label'),
        ]
        b.add_parsed_links(links, source)
        assert b.get_edges() == []

    def test_anchor_link_creates_anchor_node(self):
        b = self._builder()
        source = str(FIXTURES / 'tutorial.md')
        links = [_make_link(source, '#step-1', 'md_inline', 'Step 1')]
        b.add_parsed_links(links, source)
        nodes_by_id = {n.id: n for n in b.get_nodes()}
        anchor_nodes = [n for n in nodes_by_id.values() if n.node_type == 'anchor']
        assert len(anchor_nodes) >= 1

    def test_no_self_loops(self):
        b = self._builder()
        source = str(FIXTURES / 'index.md')
        # A link pointing to the same file should not produce a self-loop
        links = [_make_link(source, 'index.md', 'md_inline')]
        b.add_parsed_links(links, source)
        edges = b.get_edges()
        assert not any(e.source == e.target for e in edges)

    def test_analyze_returns_totals(self):
        b = self._builder()
        source = str(FIXTURES / 'index.md')
        links = [_make_link(source, 'https://example.com', 'md_inline')]
        b.add_parsed_links(links, source)
        analysis = b.analyze()
        assert analysis['total_nodes'] >= 2
        assert analysis['total_edges'] >= 1

    def test_graph_from_fixtures(self):
        """Smoke-test: parse all fixture files without errors."""
        from src.parsers.markdown_parser import parse_markdown_file
        from src.parsers.rst_parser import parse_rst_file

        b = self._builder()
        for md in FIXTURES.glob('*.md'):
            links = parse_markdown_file(str(md))
            b.add_parsed_links(links, str(md))
        for rst in FIXTURES.glob('*.rst'):
            links = parse_rst_file(str(rst))
            b.add_parsed_links(links, str(rst))

        assert b.graph.number_of_nodes() > 0
        assert b.graph.number_of_edges() > 0
