"""
reStructuredText parser.

Extracts all link-like constructs from .rst files, including:
- External hyperlinks: `text <url>`_
- Named hyperlink targets: .. _label: url
- :ref: and :doc: roles
- toctree directive entries
- include / literalinclude directives
- image / figure directives
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


def _pos_to_line(text: str, pos: int) -> int:
    return text[:pos].count('\n') + 1


_RST_UNDERLINE = re.compile(
    r'^([^\n]+)\n([=\-~\^\*\+_#"\'`]{3,})\s*$',
    re.MULTILINE,
)


def parse_rst_headings(filepath: str) -> list[str]:
    """Return all section-title texts from an .rst file (in document order).

    Matches the classic underline style:
        Title
        =====
    """
    text = Path(filepath).read_text(encoding='utf-8', errors='replace')
    out: list[str] = []
    for m in _RST_UNDERLINE.finditer(text):
        title = m.group(1).strip()
        underline = m.group(2)
        # Underline must be at least as long as the title.
        if len(underline) >= max(3, len(title) - 2):
            out.append(title)
    return out


def parse_rst_title(filepath: str) -> Optional[str]:
    """Return the first section title in an .rst file (the document title)."""
    headings = parse_rst_headings(filepath)
    return headings[0] if headings else None


def parse_rst_file(filepath: str) -> list[ParsedLink]:
    path = Path(filepath)
    text = path.read_text(encoding='utf-8', errors='replace')
    links: list[ParsedLink] = []

    def add(link_text: str, target: str, link_type: str, pos: int) -> None:
        target = target.strip()
        if not target:
            return
        links.append(ParsedLink(
            source_file=filepath,
            link_text=link_text,
            target=target,
            link_type=link_type,
            line_number=_pos_to_line(text, pos),
        ))

    # ---- External hyperlinks: `text <url>`_ ----
    for m in patterns.RST_HYPERLINK.finditer(text):
        add(m.group(1).strip(), m.group(2).strip(), 'rst_hyperlink', m.start())

    # ---- Named hyperlink targets: .. _label: url ----
    for m in patterns.RST_TARGET.finditer(text):
        label = m.group(1).strip()
        target = m.group(2).strip()
        links.append(ParsedLink(
            source_file=filepath,
            link_text=label,
            target=target,
            link_type='rst_target',
            line_number=_pos_to_line(text, m.start()),
        ))

    # ---- :ref: role ----
    for m in patterns.RST_REF_ROLE.finditer(text):
        target = patterns.extract_role_target(m.group(1))
        add(m.group(1), target, 'rst_ref', m.start())

    # ---- :doc: role ----
    for m in patterns.RST_DOC_ROLE.finditer(text):
        target = patterns.extract_role_target(m.group(1))
        add(m.group(1), target, 'rst_doc', m.start())

    # ---- :any: role ----
    for m in patterns.RST_ANY_ROLE.finditer(text):
        target = patterns.extract_role_target(m.group(1))
        add(m.group(1), target, 'rst_any', m.start())

    # ---- .. include:: ----
    for m in patterns.RST_INCLUDE.finditer(text):
        add(m.group(1), m.group(1), 'rst_include', m.start())

    # ---- .. literalinclude:: ----
    for m in patterns.RST_LITERALINCLUDE.finditer(text):
        add(m.group(1), m.group(1), 'rst_literalinclude', m.start())

    # ---- .. image:: / .. figure:: ----
    for m in patterns.RST_IMAGE.finditer(text):
        add(m.group(1), m.group(1), 'rst_image', m.start())

    # ---- .. toctree:: ----
    links.extend(_parse_rst_toctree(text, filepath))

    return links


def _parse_rst_toctree(text: str, filepath: str) -> list[ParsedLink]:
    """Parse toctree directives and extract document entries."""
    links: list[ParsedLink] = []
    # Match: .. toctree:: [options]\n\n   <indented entries>
    toctree_pattern = re.compile(
        r'^\.\.\s+toctree::[^\n]*\n((?:[ \t]*[^\n]*\n)*)',
        re.MULTILINE,
    )
    for block in toctree_pattern.finditer(text):
        body = block.group(1)
        line_offset = _pos_to_line(text, block.start()) + 1
        for i, line in enumerate(body.splitlines()):
            stripped = line.strip()
            # Skip directive options, blank lines, and comments
            if not stripped or stripped.startswith(':') or stripped.startswith('#'):
                continue
            # Handle "Title <path>" format
            angle = re.match(r'.+<([^>]+)>', stripped)
            entry = angle.group(1).strip() if angle else stripped
            links.append(ParsedLink(
                source_file=filepath,
                link_text=stripped,
                target=entry,
                link_type='rst_toctree',
                line_number=line_offset + i,
            ))
    return links
