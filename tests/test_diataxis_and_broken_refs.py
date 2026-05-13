"""
Tests for Diataxis classification, broken-reference detection, and source-URL
attachment in the graph builder.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.graph.builder import GraphBuilder, classify_diataxis
from src.orchestrator import ExtractorOrchestrator
from src.parsers.markdown_parser import ParsedLink


def _link(source: str, target: str, link_type: str = 'md_inline') -> ParsedLink:
    return ParsedLink(source_file=source, link_text='', target=target,
                      link_type=link_type, line_number=1)


class TestClassifyDiataxis:
    @pytest.mark.parametrize('path,expected', [
        ('tutorial/index.md',                       'tutorial'),
        ('tutorials/getting-started.md',            'tutorial'),
        ('how-to/install.md',                       'how-to'),
        ('how-to-guides/deploy.md',                 'how-to'),
        ('reference/config.md',                     'reference'),
        ('explanation/architecture.md',             'explanation'),
        ('explanations/security.md',                'explanation'),
        ('index.md',                                'meta'),
        ('contributing.md',                         'meta'),
        ('tutorial.md',                             'tutorial'),
        ('reference.md',                            'reference'),
        ('how-to-guides/external-auth/oidc.md',     'how-to'),
    ])
    def test_classification(self, path: str, expected: str):
        assert classify_diataxis(path) == expected

    def test_handles_leading_slash(self):
        assert classify_diataxis('/how-to-guides/foo.md') == 'how-to'

    def test_unknown_is_meta(self):
        assert classify_diataxis('docs/random/foo.md') == 'meta'


class TestBrokenRefs:
    @pytest.fixture
    def project(self, tmp_path: Path) -> Path:
        # Build a tiny project: index.md links to one real file and one missing one.
        (tmp_path / 'reference').mkdir()
        (tmp_path / 'reference' / 'real.md').write_text('# real\n')
        (tmp_path / 'index.md').write_text(
            '[real](reference/real.md)\n'
            '[missing](does/not/exist.md)\n'
        )
        return tmp_path

    def test_unresolved_doc_marked_broken(self, project: Path):
        o = ExtractorOrchestrator(str(project))
        o.extract()
        nodes = {n.id: n for n in o.builder.get_nodes()}
        # The missing target should appear as a broken doc node.
        broken_docs = [n for n in nodes.values()
                       if n.node_type == 'document' and n.metadata.get('resolved') is False]
        assert any('does/not/exist.md' in n.id for n in broken_docs)

    def test_resolved_doc_not_marked_broken(self, project: Path):
        o = ExtractorOrchestrator(str(project))
        o.extract()
        nodes = {n.id: n for n in o.builder.get_nodes()}
        real = nodes.get('reference/real.md')
        assert real is not None
        assert real.metadata.get('resolved') is True

    def test_diataxis_attached(self, project: Path):
        o = ExtractorOrchestrator(str(project))
        o.extract()
        nodes = {n.id: n for n in o.builder.get_nodes()}
        assert nodes['reference/real.md'].metadata['diataxis'] == 'reference'
        assert nodes['index.md'].metadata['diataxis'] == 'meta'

    def test_undefined_label_marked_broken(self, tmp_path: Path):
        (tmp_path / 'a.md').write_text('{ref}`undefined-label`\n')
        o = ExtractorOrchestrator(str(tmp_path))
        o.extract()
        nodes = {n.id: n for n in o.builder.get_nodes()}
        lbl = nodes.get('label:undefined-label')
        assert lbl is not None
        assert lbl.metadata.get('resolved') is False

    def test_defined_label_not_marked_broken(self, tmp_path: Path):
        (tmp_path / 'a.md').write_text('(my-label)=\n\n{ref}`my-label`\n')
        o = ExtractorOrchestrator(str(tmp_path))
        o.extract()
        nodes = {n.id: n for n in o.builder.get_nodes()}
        lbl = nodes.get('label:my-label')
        assert lbl is not None
        assert lbl.metadata.get('resolved') is True


class TestSourceURL:
    def test_source_url_attached(self, tmp_path: Path):
        (tmp_path / 'reference').mkdir()
        (tmp_path / 'reference' / 'x.md').write_text('# x\n')
        o = ExtractorOrchestrator(
            str(tmp_path),
            source_base='https://github.com/foo/bar/blob/main/docs/',
        )
        o.extract()
        nodes = {n.id: n for n in o.builder.get_nodes()}
        url = nodes['reference/x.md'].metadata.get('source_url')
        assert url == 'https://github.com/foo/bar/blob/main/docs/reference/x.md'

    def test_render_url_only_for_resolved(self, tmp_path: Path):
        (tmp_path / 'a.md').write_text('[missing](no.md)\n')
        o = ExtractorOrchestrator(
            str(tmp_path),
            source_base='https://github.com/foo/bar/blob/main/',
            render_base='https://docs.example.com/',
        )
        o.extract()
        nodes = {n.id: n for n in o.builder.get_nodes()}
        # Resolved node gets render_url
        assert nodes['a.md'].metadata.get('render_url') == 'https://docs.example.com/a/'
        # Broken nodes don't
        broken = [n for n in nodes.values() if n.id == 'no.md']
        assert broken
        assert 'render_url' not in broken[0].metadata
