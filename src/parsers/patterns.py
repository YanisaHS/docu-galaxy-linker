"""
Regex pattern library for all documentation link types.
Covers Markdown, MyST, and reStructuredText.
"""
import re

# ---------------------------------------------------------------------------
# Markdown / MyST patterns
# ---------------------------------------------------------------------------

# Standard inline link: [text](url) or [text](url "title")
MD_INLINE_LINK = re.compile(r'\[([^\]]*)\]\(([^)]+)\)')

# Image: ![alt](url) or ![alt](url "title")
MD_IMAGE = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')

# Reference-style link: [text][ref] or [text][]
MD_REF_LINK = re.compile(r'(?<!!)\[([^\]]+)\]\[([^\]]*)\]')

# Reference definition: [ref]: url  or  [ref]: url "title"
MD_REF_DEF = re.compile(r'^\[([^\]]+)\]:\s*(\S+)', re.MULTILINE)

# Autolink: <https://...>
MD_AUTOLINK = re.compile(r'<(https?://[^>\s]+)>')

# HTML anchor href (simple): href="url" or href='url'
MD_HTML_HREF = re.compile(r'href=["\']([^"\']+)["\']')

# ---------------------------------------------------------------------------
# MyST roles
# ---------------------------------------------------------------------------

# {doc}`path` or {doc}`title <path>`
MYST_DOC_ROLE = re.compile(r'\{doc\}`([^`]+)`')

# {ref}`label` or {ref}`title <label>`
MYST_REF_ROLE = re.compile(r'\{ref\}`([^`]+)`')

# {term}`term` or {term}`text <term>`
MYST_TERM_ROLE = re.compile(r'\{term\}`([^`]+)`')

# MyST label definition: (label)=
MYST_LABEL_DEF = re.compile(r'^\(([^)]+)\)=\s*$', re.MULTILINE)

# MyST toctree directive entries (inside ```{toctree} blocks)
MYST_TOCTREE_ENTRY = re.compile(r'^(?!:)([^\s#][^\n]*)$', re.MULTILINE)

# ---------------------------------------------------------------------------
# reStructuredText patterns
# ---------------------------------------------------------------------------

# External hyperlink: `text <url>`_
RST_HYPERLINK = re.compile(r'`([^`<]+?)\s*<([^>]+)>`_{1,2}')

# Standalone hyperlink reference: url_
RST_STANDALONE_REF = re.compile(r'\b(\w[\w.-]*(?:/[\w./-]*)?)_\b')

# Named hyperlink target: .. _label: url-or-path
RST_TARGET = re.compile(r'^\.\.\s+_([^:]+):\s*(\S.*?)$', re.MULTILINE)

# Anonymous hyperlink target: .. __: url
RST_ANON_TARGET = re.compile(r'^\.\.\s+__:\s*(\S+)', re.MULTILINE)

# :ref:`label` or :ref:`title <label>`
RST_REF_ROLE = re.compile(r':ref:`([^`]+)`')

# :doc:`path` or :doc:`title <path>`
RST_DOC_ROLE = re.compile(r':doc:`([^`]+)`')

# :any:`target`
RST_ANY_ROLE = re.compile(r':any:`([^`]+)`')

# .. toctree:: directive header
RST_TOCTREE = re.compile(r'^\.\.\s+toctree::', re.MULTILINE)

# .. include:: path
RST_INCLUDE = re.compile(r'^\.\.\s+include::\s*(\S+)', re.MULTILINE)

# .. literalinclude:: path
RST_LITERALINCLUDE = re.compile(r'^\.\.\s+literalinclude::\s*(\S+)', re.MULTILINE)

# .. figure:: path  /  .. image:: path
RST_IMAGE = re.compile(r'^\.\.\s+(?:figure|image)::\s*(\S+)', re.MULTILINE)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Extract target from role with optional title: "title <target>" -> "target"
ROLE_ANGLE_BRACKET = re.compile(r'<([^>]+)>$')

# Code fence start/end (Markdown)
MD_CODE_FENCE = re.compile(r'^(`{3,}|~{3,})', re.MULTILINE)


def extract_role_target(role_content: str) -> str:
    """Return the target from a role value like 'title <target>' or just 'target'."""
    m = ROLE_ANGLE_BRACKET.search(role_content.strip())
    return m.group(1).strip() if m else role_content.strip()
