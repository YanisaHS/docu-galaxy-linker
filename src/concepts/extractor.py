"""
Concept extractor for Landscape documentation.

Parses Markdown files and extracts:
- Document title (H1 heading)
- Section category (from directory structure)
- Sub-headings (H2 / H3 headings)
- Key technical terms (for TF-IDF similarity)
- Word count
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Stopwords — common English words + doc-noise + Landscape-ubiquitous terms
# ---------------------------------------------------------------------------
_STOPWORDS: frozenset[str] = frozenset({
    'a', 'about', 'above', 'after', 'again', 'against', 'all', 'also',
    'although', 'am', 'an', 'and', 'any', 'are', 'as', 'at',
    'be', 'because', 'been', 'before', 'being', 'between', 'both',
    'but', 'by', 'can', 'click', 'could',
    'did', 'do', 'does', 'don', 'during',
    'each', 'either', 'else', 'enable', 'even', 'every',
    'few', 'follow', 'following', 'for', 'from',
    'get', 'gets', 'go', 'goes',
    'had', 'has', 'have', 'he', 'help', 'her', 'here', 'him', 'his', 'how',
    'if', 'in', 'include', 'including', 'into', 'is', 'it', 'its',
    'just',
    'like', 'list',
    'make', 'may', 'more', 'most', 'must', 'my',
    'need', 'new', 'no', 'nor', 'not', 'note',
    'of', 'on', 'only', 'or', 'other', 'our', 'out', 'over',
    'page', 'per',
    'run', 'runs',
    'same', 'see', 'set', 'shall', 'she', 'should', 'so', 'some',
    'step', 'such',
    'than', 'that', 'the', 'their', 'them', 'then', 'there', 'these',
    'they', 'this', 'those', 'through', 'to', 'too',
    'under', 'until', 'up', 'use', 'used', 'using', 'us',
    'value', 'via',
    'was', 'we', 'were', 'what', 'when', 'where', 'which', 'while',
    'who', 'will', 'with', 'would',
    'you', 'your',
    # Documentation noise
    'index', 'section', 'guide', 'guides', 'documentation', 'doc', 'docs',
    'example', 'examples', 'default', 'option', 'options', 'click',
    'below', 'above', 'following', 'refer', 'related', 'more',
    'information', 'details', 'learn', 'read', 'find', 'create', 'view',
    'also', 'note', 'important', 'warning', 'tip', 'optional',
    # Landscape-ubiquitous (near-zero IDF, not discriminating)
    'landscape', 'client', 'server', 'ubuntu', 'system', 'systems',
    'machine', 'machines', 'instance', 'instances', 'managed',
    'account', 'accounts', 'user', 'users',
})


# ---------------------------------------------------------------------------
# Diátaxis classification  (https://diataxis.fr/)
# ---------------------------------------------------------------------------
_DIATAXIS_RULES: list[tuple[str, str, str]] = [
    ('tutorial',      'Tutorial',     'tutorial'),
    ('how-to-guides', 'How-to guide', 'how-to'),
    ('explanation',   'Explanation',  'explanation'),
    ('reference',     'Reference',    'reference'),
]
# Anything outside those four folders (e.g. what-is-landscape.md) is
# conceptually an explanation.
_DIATAXIS_DEFAULT = ('Explanation', 'explanation')


# ---------------------------------------------------------------------------
# Regex helpers
# ---------------------------------------------------------------------------
_RE_HEADING = re.compile(r'^(#{1,6})\s+(.+)', re.MULTILINE)
_RE_CODE_BLOCK = re.compile(r'```.*?```', re.DOTALL)
_RE_INLINE_CODE = re.compile(r'`[^`]+`')
_RE_YAML_FRONT = re.compile(r'^---.*?---\s*', re.DOTALL)
_RE_MYST_LABEL = re.compile(r'^\([^)]+\)=\s*', re.MULTILINE)
_RE_LINK = re.compile(r'\[[^\]]*\]\([^)]*\)')
_RE_HTML_TAG = re.compile(r'<[^>]+>')
_RE_PUNCTUATION = re.compile(r"[^a-zA-Z0-9\s'-]")
_RE_WORD_SPLIT = re.compile(r"[\s\-_/]+")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass
class DocPage:
    """A single documentation page with extracted concept metadata."""
    id: str               # relative path from docs root
    path: str             # absolute file path
    title: str            # H1 heading (or title-cased filename)
    section: str          # human-readable section name
    section_key: str      # section key (used as node_type for colouring)
    headings: list[str] = field(default_factory=list)   # H2/H3 headings
    terms: dict[str, int] = field(default_factory=dict)  # term -> count in doc
    word_count: int = 0
    shingles: frozenset = field(default_factory=frozenset)  # word trigrams for duplicate detection
    section_terms: list[dict[str, int]] = field(default_factory=list)  # per-H2-section term counts
    section_titles: list[str] = field(default_factory=list)  # H2 headings that define each section


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _classify_section(rel_path: str) -> tuple[str, str]:
    """Return (diataxis_label, diataxis_key) for a relative file path."""
    p = rel_path.replace('\\', '/')
    for prefix, label, key in _DIATAXIS_RULES:
        if p == prefix or p.startswith(prefix + '/') or p.startswith(prefix + '.'):
            return label, key
    return _DIATAXIS_DEFAULT


def _split_sections(raw_text: str) -> tuple[list[dict[str, int]], list[str]]:
    """
    Split page at H2 (##) boundaries and return
    (section_terms, section_titles) where both lists are parallel.
    Sections with fewer than 30 words are ignored.
    """
    text = _RE_YAML_FRONT.sub('', raw_text)
    # Find all H2 headings and their positions
    h2_re = re.compile(r'(?m)^## (.+)$')
    boundaries = [(m.start(), m.group(1).strip()) for m in h2_re.finditer(text)]

    # Build (title, body) pairs
    segments: list[tuple[str, str]] = []
    for idx, (pos, heading) in enumerate(boundaries):
        # Body = text from end of this heading line to start of the next
        body_start = text.index('\n', pos) + 1 if '\n' in text[pos:] else pos
        body_end = boundaries[idx + 1][0] if idx + 1 < len(boundaries) else len(text)
        body = text[body_start:body_end]
        if len(body.split()) >= 30:
            segments.append((heading, body))

    terms  = [_extract_terms(body) for _, body in segments]
    titles = [heading for heading, _ in segments]
    return terms, titles


def _extract_shingles(raw_text: str, n: int = 3) -> frozenset:
    """Extract word n-gram shingles from cleaned text for duplicate detection."""
    text = _RE_YAML_FRONT.sub(' ', raw_text)
    text = _RE_CODE_BLOCK.sub(' ', text)
    text = _RE_INLINE_CODE.sub(' ', text)
    text = _RE_LINK.sub(' ', text)
    text = _RE_HTML_TAG.sub(' ', text)
    text = _RE_PUNCTUATION.sub(' ', text)
    text = text.lower()
    words = [w for w in _RE_WORD_SPLIT.split(text) if len(w) >= 2]
    if len(words) < n:
        return frozenset()
    return frozenset(tuple(words[i:i + n]) for i in range(len(words) - n + 1))


def _extract_terms(raw_text: str) -> dict[str, int]:
    """Extract meaningful technical terms from raw markdown text."""
    text = _RE_YAML_FRONT.sub(' ', raw_text)
    text = _RE_CODE_BLOCK.sub(' ', text)
    text = _RE_INLINE_CODE.sub(' ', text)
    text = _RE_LINK.sub(' ', text)
    text = _RE_HTML_TAG.sub(' ', text)
    text = _RE_PUNCTUATION.sub(' ', text)
    text = text.lower()

    counts: dict[str, int] = {}
    for word in _RE_WORD_SPLIT.split(text):
        word = word.strip("'-")
        if len(word) >= 4 and word not in _STOPWORDS and word.isalpha():
            counts[word] = counts.get(word, 0) + 1
    return counts


def _extract_title_and_headings(raw_text: str, fallback: str) -> tuple[str, list[str]]:
    """Return (title, [h2/h3 headings]) from raw markdown text."""
    title = fallback
    headings: list[str] = []

    # Work on a version with YAML front matter stripped
    text = _RE_YAML_FRONT.sub('', raw_text)

    for m in _RE_HEADING.finditer(text):
        level = len(m.group(1))
        raw_h = m.group(2).strip()
        # Strip MyST label anchors: (label)=
        raw_h = _RE_MYST_LABEL.sub('', raw_h).strip()
        # Strip inline code and MyST roles
        raw_h = _RE_INLINE_CODE.sub('', raw_h)
        raw_h = re.sub(r'\{[^}]+\}', '', raw_h)
        raw_h = raw_h.strip('# ').strip()
        if not raw_h:
            continue
        if level == 1 and title == fallback:
            title = raw_h
        elif level in (2, 3):
            headings.append(raw_h)

    return title, headings


_RE_DIATAXIS_PREFIX = re.compile(
    r'^(?:How to |How-to: ?|Tutorial: ?|Explanation: ?|Reference: ?)',
    re.IGNORECASE,
)


def _strip_diataxis_prefix(title: str) -> str:
    """Remove redundant Diátaxis-type prefixes from a page title."""
    return _RE_DIATAXIS_PREFIX.sub('', title).strip()


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------
def extract_doc_pages(docs_dir: str) -> list[DocPage]:
    """
    Scan *docs_dir* recursively for .md files and return a list of DocPage
    objects.  Index pages and reuse/ snippets are skipped.
    """
    root = Path(docs_dir).resolve()
    pages: list[DocPage] = []

    for md_file in sorted(root.rglob('*.md')):
        rel = str(md_file.relative_to(root)).replace('\\', '/')

        # Skip reuse snippets and hidden dirs
        if rel.startswith('reuse/') or any(part.startswith('_') for part in md_file.parts):
            continue
        # Skip index files — they're structural, not conceptual
        if md_file.name == 'index.md':
            continue

        try:
            text = md_file.read_text(encoding='utf-8', errors='replace')
        except OSError:
            continue

        fallback_title = md_file.stem.replace('-', ' ').title()
        title, headings = _extract_title_and_headings(text, fallback_title)
        title = _strip_diataxis_prefix(title)
        terms = _extract_terms(text)
        shingles = _extract_shingles(text)
        section_terms, section_titles = _split_sections(text)
        word_count = len(text.split())
        section, section_key = _classify_section(rel)

        pages.append(DocPage(
            id=rel,
            path=str(md_file),
            title=title,
            section=section,
            section_key=section_key,
            headings=headings,
            terms=terms,
            word_count=word_count,
            shingles=shingles,
            section_terms=section_terms,
            section_titles=section_titles,
        ))

    return pages
