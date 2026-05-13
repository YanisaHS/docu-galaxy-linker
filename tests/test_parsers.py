"""
Unit tests for the Markdown and RST parsers.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from src.parsers.markdown_parser import parse_markdown_file
from src.parsers.rst_parser import parse_rst_file


FIXTURES = Path(__file__).parent / 'fixtures' / 'docs'


# ---------------------------------------------------------------------------
# Markdown parser tests
# ---------------------------------------------------------------------------

class TestMarkdownParser:
    def _links(self, filename: str):
        return parse_markdown_file(str(FIXTURES / filename))

    def _links_by_type(self, filename: str) -> dict[str, list]:
        result: dict[str, list] = {}
        for lnk in self._links(filename):
            result.setdefault(lnk.link_type, []).append(lnk)
        return result

    def test_inline_link_detected(self):
        by_type = self._links_by_type('index.md')
        inline = by_type.get('md_inline', [])
        targets = [l.target for l in inline]
        assert 'https://canonical.com' in targets

    def test_external_autolink(self):
        by_type = self._links_by_type('index.md')
        auto = by_type.get('md_autolink', [])
        assert any('ubuntu.com' in l.target for l in auto)

    def test_image_link_detected(self):
        by_type = self._links_by_type('index.md')
        images = by_type.get('md_image', [])
        assert len(images) >= 1

    def test_myst_doc_role(self):
        by_type = self._links_by_type('index.md')
        doc_links = by_type.get('myst_doc', [])
        assert any('tutorial' in l.target for l in doc_links)

    def test_myst_ref_role(self):
        by_type = self._links_by_type('index.md')
        refs = by_type.get('myst_ref', [])
        assert any('getting-started' in l.target for l in refs)

    def test_myst_toctree_entries(self):
        by_type = self._links_by_type('index.md')
        toc = by_type.get('myst_toctree', [])
        targets = [l.target for l in toc]
        assert 'tutorial' in targets
        assert 'how-to/install' in targets
        assert 'reference/api' in targets

    def test_myst_label_def(self):
        by_type = self._links_by_type('index.md')
        defs = by_type.get('myst_label_def', [])
        assert any(l.target == 'index-label' for l in defs)

    def test_ref_style_link(self):
        by_type = self._links_by_type('tutorial.md')
        ref_links = by_type.get('md_ref_link', [])
        assert len(ref_links) >= 1

    def test_ref_def_captured(self):
        by_type = self._links_by_type('tutorial.md')
        defs = by_type.get('md_ref_def', [])
        assert any('reference/api' in l.target for l in defs)

    def test_anchor_link(self):
        by_type = self._links_by_type('tutorial.md')
        inline = by_type.get('md_inline', [])
        assert any(l.target.startswith('#') or 'step' in l.target for l in inline)

    def test_no_links_in_code_fence(self, tmp_path):
        md = tmp_path / 'code.md'
        md.write_text(textwrap.dedent('''
            Normal [link](https://example.com).

            ```python
            # This [fake](link) should not be extracted
            x = "[hidden](hidden)"
            ```
        '''))
        links = parse_markdown_file(str(md))
        targets = [l.target for l in links]
        assert 'https://example.com' in targets
        assert 'hidden' not in targets

    def test_front_matter_skipped(self, tmp_path):
        md = tmp_path / 'fm.md'
        md.write_text(textwrap.dedent('''
            ---
            title: My Page
            relatedlinks: https://should-not-appear.example.com
            ---

            [Real link](https://real.example.com)
        ''').lstrip())
        links = parse_markdown_file(str(md))
        targets = [l.target for l in links]
        assert 'https://real.example.com' in targets
        assert 'https://should-not-appear.example.com' not in targets

    def test_line_numbers_populated(self):
        links = self._links('index.md')
        assert all(l.line_number is not None for l in links if l.link_type != 'md_ref_def')


# ---------------------------------------------------------------------------
# RST parser tests
# ---------------------------------------------------------------------------

class TestRstParser:
    def _links(self, filename: str):
        return parse_rst_file(str(FIXTURES / filename))

    def _links_by_type(self, filename: str) -> dict[str, list]:
        result: dict[str, list] = {}
        for lnk in self._links(filename):
            result.setdefault(lnk.link_type, []).append(lnk)
        return result

    def test_external_hyperlink(self):
        by_type = self._links_by_type('index.rst')
        hyper = by_type.get('rst_hyperlink', [])
        assert any('ubuntu.com' in l.target for l in hyper)

    def test_ref_role(self):
        by_type = self._links_by_type('index.rst')
        refs = by_type.get('rst_ref', [])
        assert any('getting-started-rst' in l.target for l in refs)

    def test_doc_role(self):
        by_type = self._links_by_type('index.rst')
        docs = by_type.get('rst_doc', [])
        assert any('tutorial' in l.target for l in docs)

    def test_toctree_entries(self):
        by_type = self._links_by_type('index.rst')
        toc = by_type.get('rst_toctree', [])
        targets = [l.target for l in toc]
        assert 'tutorial' in targets
        assert 'how-to/install' in targets

    def test_include_directive(self):
        by_type = self._links_by_type('index.rst')
        includes = by_type.get('rst_include', [])
        assert len(includes) >= 1

    def test_image_directive(self):
        by_type = self._links_by_type('index.rst')
        images = by_type.get('rst_image', [])
        assert len(images) >= 1

    def test_named_target(self):
        by_type = self._links_by_type('index.rst')
        targets = by_type.get('rst_target', [])
        assert any('ubuntu' in l.link_text for l in targets)
