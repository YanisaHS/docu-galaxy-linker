"""
Markdown / MyST parser.

Extracts all link-like constructs from .md files, including:
- Standard inline links and images
- Reference-style links
- Autolinks
- MyST roles: {doc}, {ref}, {term}
- MyST label definitions
- MyST toctree directive entries
- HTML href attributes (inline HTML)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import patterns


@dataclass
class ParsedLink:
    source_file: str
    link_text: str
    target: str
    link_type: str
    line_number: Optional[int] = None


def _get_code_fence_ranges(text: str) -> list[tuple[int, int]]:
    """Return (start, end) character ranges that are inside code fences."""
    ranges: list[tuple[int, int]] = []
    fence_start: Optional[int] = None
    fence_char: Optional[str] = None

    for m in patterns.MD_CODE_FENCE.finditer(text):
        ch = m.group(1)[0]
        if fence_start is None:
            fence_start = m.start()
            fence_char = ch
        elif ch == fence_char:
            ranges.append((fence_start, m.end()))
            fence_start = None
            fence_char = None
    return ranges


def _in_code_fence(pos: int, fence_ranges: list[tuple[int, int]]) -> bool:
    return any(start < pos < end for start, end in fence_ranges)


def _pos_to_line(text: str, pos: int) -> int:
    return text[:pos].count('\n') + 1


_HEADING_RE = re.compile(r'^(#{1,6})\s+(.+?)\s*#*\s*$', re.MULTILINE)
_FRONT_MATTER_TITLE_RE = re.compile(r'^title:\s*(.+?)\s*$', re.MULTILINE)


def _strip_front_matter(text: str) -> tuple[str, str]:
    """Return (front_matter, body). Front matter is empty if absent."""
    if not text.startswith('---'):
        return '', text
    end = text.find('\n---', 3)
    if end == -1:
        return '', text
    return text[:end], text[end + 4:]


def parse_markdown_headings(filepath: str) -> list[str]:
    """Return all heading texts from a Markdown / MyST file (in document order)."""
    text = Path(filepath).read_text(encoding='utf-8', errors='replace')
    _, text = _strip_front_matter(text)
    fence_ranges = _get_code_fence_ranges(text)
    headings: list[str] = []
    for m in _HEADING_RE.finditer(text):
        if _in_code_fence(m.start(), fence_ranges):
            continue
        headings.append(m.group(2).strip())
    return headings


def parse_markdown_title(filepath: str) -> Optional[str]:
    """Return the document's title — preferred sources, in order:

    1. `title:` field in YAML front matter (Sphinx/Jekyll convention)
    2. First `# H1` heading in the body
    3. First heading of any level (fallback for docs that start with `##`)

    Returns `None` if none of those exist.
    """
    text = Path(filepath).read_text(encoding='utf-8', errors='replace')
    front, body = _strip_front_matter(text)
    if front:
        fm = _FRONT_MATTER_TITLE_RE.search(front)
        if fm:
            return fm.group(1).strip().strip('"').strip("'") or None
    fence_ranges = _get_code_fence_ranges(body)
    first_h1: Optional[str] = None
    first_any: Optional[str] = None
    for m in _HEADING_RE.finditer(body):
        if _in_code_fence(m.start(), fence_ranges):
            continue
        level = len(m.group(1))
        text_part = m.group(2).strip()
        if first_any is None:
            first_any = text_part
        if level == 1 and first_h1 is None:
            first_h1 = text_part
            break
    return first_h1 or first_any


def parse_markdown_file(filepath: str) -> list[ParsedLink]:
    path = Path(filepath)
    text = path.read_text(encoding='utf-8', errors='replace')

    # Strip YAML front matter
    if text.startswith('---'):
        end = text.find('\n---', 3)
        if end != -1:
            text = text[end + 4:]

    fence_ranges = _get_code_fence_ranges(text)
    links: list[ParsedLink] = []

    def add(link_text: str, target: str, link_type: str, pos: int) -> None:
        if _in_code_fence(pos, fence_ranges):
            return
        # Strip trailing title from url: url "title"  or  url 'title'
        target = re.sub(r'\s+["\'].+["\']$', '', target.strip()).strip()
        if not target:
            return
        links.append(ParsedLink(
            source_file=filepath,
            link_text=link_text,
            target=target,
            link_type=link_type,
            line_number=_pos_to_line(text, pos),
        ))

    # ---- Inline images (must run before inline links to avoid double-match) ----
    for m in patterns.MD_IMAGE.finditer(text):
        add(m.group(1), m.group(2), 'md_image', m.start())

    # ---- Inline links (skip if preceded by !) ----
    for m in patterns.MD_INLINE_LINK.finditer(text):
        if m.start() > 0 and text[m.start() - 1] == '!':
            continue  # already captured as image
        add(m.group(1), m.group(2), 'md_inline', m.start())

    # ---- Autolinks ----
    for m in patterns.MD_AUTOLINK.finditer(text):
        add(m.group(1), m.group(1), 'md_autolink', m.start())

    # ---- HTML href ----
    for m in patterns.MD_HTML_HREF.finditer(text):
        add('', m.group(1), 'md_html_href', m.start())

    # ---- Reference-style links ----
    for m in patterns.MD_REF_LINK.finditer(text):
        ref_key = m.group(2) or m.group(1)
        add(m.group(1), f'[ref:{ref_key}]', 'md_ref_link', m.start())

    # ---- Reference definitions ----
    for m in patterns.MD_REF_DEF.finditer(text):
        links.append(ParsedLink(
            source_file=filepath,
            link_text=m.group(1),
            target=m.group(2),
            link_type='md_ref_def',
            line_number=_pos_to_line(text, m.start()),
        ))

    # ---- MyST {doc} role ----
    for m in patterns.MYST_DOC_ROLE.finditer(text):
        if _in_code_fence(m.start(), fence_ranges):
            continue
        target = patterns.extract_role_target(m.group(1))
        add(m.group(1), target, 'myst_doc', m.start())

    # ---- MyST {ref} role ----
    for m in patterns.MYST_REF_ROLE.finditer(text):
        if _in_code_fence(m.start(), fence_ranges):
            continue
        target = patterns.extract_role_target(m.group(1))
        add(m.group(1), target, 'myst_ref', m.start())

    # ---- MyST {term} role ----
    for m in patterns.MYST_TERM_ROLE.finditer(text):
        if _in_code_fence(m.start(), fence_ranges):
            continue
        target = patterns.extract_role_target(m.group(1))
        add(m.group(1), target, 'myst_term', m.start())

    # ---- MyST label definitions ----
    for m in patterns.MYST_LABEL_DEF.finditer(text):
        links.append(ParsedLink(
            source_file=filepath,
            link_text=m.group(1),
            target=m.group(1),
            link_type='myst_label_def',
            line_number=_pos_to_line(text, m.start()),
        ))

    # ---- MyST toctree directive ----
    links.extend(_parse_myst_toctree(text, filepath))

    return links


def _parse_myst_toctree(text: str, filepath: str) -> list[ParsedLink]:
    """Extract entries from MyST ```{toctree} ... ``` blocks."""
    links: list[ParsedLink] = []
    # Match fenced toctree: ```{toctree}\n...\n```
    toctree_block = re.compile(
        r'```\{toctree\}[^\n]*\n(.*?)```',
        re.DOTALL,
    )
    for block in toctree_block.finditer(text):
        body = block.group(1)
        line_offset = text[:block.start()].count('\n') + 2  # +2 for opening line
        for i, line in enumerate(body.splitlines()):
            stripped = line.strip()
            # Skip options (:maxdepth:, :caption:, etc.) and blank lines
            if not stripped or stripped.startswith(':') or stripped.startswith('#'):
                continue
            # Handle "Title <path>" format
            angle = re.match(r'.+<([^>]+)>', stripped)
            entry = angle.group(1).strip() if angle else stripped
            links.append(ParsedLink(
                source_file=filepath,
                link_text=stripped,
                target=entry,
                link_type='myst_toctree',
                line_number=line_offset + i,
            ))
    return links
