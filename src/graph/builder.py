"""
Graph builder.

Consumes ParsedLink objects from the parsers and constructs a directed graph
with Node and Edge objects. Uses NetworkX for analysis.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

import networkx as nx

from .models import Edge, Node


# Link types classified as "internal document" references
_DOC_LINK_TYPES = frozenset({
    'myst_doc', 'rst_doc', 'myst_toctree', 'rst_toctree',
    'rst_include', 'rst_literalinclude',
})

# Link types classified as cross-reference labels
_REF_LINK_TYPES = frozenset({'myst_ref', 'rst_ref', 'rst_any'})

# Link types that are definitions (not actual links to follow)
_DEFINITION_TYPES = frozenset({'md_ref_def', 'rst_target', 'myst_label_def'})

# External URL schemes
_EXTERNAL_SCHEMES = ('http://', 'https://', 'ftp://', 'mailto:', '//')


_DIATAXIS_PREFIXES = {
    'tutorial':    ('tutorial', 'tutorials'),
    'how-to':      ('how-to', 'how-to-guides', 'howto', 'guides'),
    'reference':   ('reference', 'references'),
    'explanation': ('explanation', 'explanations'),
}


def classify_diataxis(path: str,
                      prefixes: Optional[dict[str, list[str]]] = None) -> str:
    """Classify a document path into a Diataxis section.

    Returns one of: tutorial, how-to, reference, explanation, meta.
    Single-file root pages (`tutorial.md`, `index.md`, etc.) are classified
    by their stem when possible. `prefixes` overrides the default mapping
    (e.g. project-specific aliases).
    """
    table: dict[str, tuple[str, ...]] = {
        k: tuple(v) for k, v in _DIATAXIS_PREFIXES.items()
    }
    if prefixes:
        for k, v in prefixes.items():
            table[k] = tuple(v)
    p = (path or '').lower().lstrip('./').lstrip('/')
    head = p.split('/', 1)[0]
    for section, group in table.items():
        if head in group:
            return section
    stem = Path(head).stem
    for section, group in table.items():
        if stem in group:
            return section
    return 'meta'


class GraphBuilder:
    def __init__(self, project_root: str, project_name: Optional[str] = None,
                 source_base: Optional[str] = None,
                 render_base: Optional[str] = None,
                 redirects: Optional[dict[str, str]] = None,
                 known_external_prefixes: Optional[list[str]] = None,
                 diataxis_prefixes: Optional[dict[str, list[str]]] = None) -> None:
        self.project_root = Path(project_root).resolve()
        self.project_name = project_name
        # Base URLs for "open source" / "open rendered" links from doc nodes.
        self.source_base = source_base.rstrip('/') + '/' if source_base else None
        self.render_base = render_base.rstrip('/') + '/' if render_base else None
        # Redirect map (old_path → new_path), without extensions. Applied
        # before resolving doc refs so a redirected link doesn't appear broken.
        self.redirects = redirects or {}
        # Prefixes that should be treated as external rather than broken
        # (e.g. "ubuntu/" if you cross-link into another Sphinx project).
        self.known_external_prefixes = tuple(known_external_prefixes or ())
        # Per-project Diataxis prefix overrides.
        self.diataxis_prefixes = diataxis_prefixes or {}

        self.graph: nx.DiGraph = nx.DiGraph()
        self._nodes: dict[str, Node] = {}
        self._edges: list[Edge] = []

        # Map from reference label -> list of source nodes that define it
        self._label_defs: dict[str, str] = {}
        # Map from md ref-key -> target URL (from ref definitions)
        self._md_ref_defs: dict[str, str] = {}
        # Heading IDs per document (for anchor validation).
        self._heading_ids: dict[str, set[str]] = {}
        # Anchor links to validate after all docs have been parsed.
        self._pending_anchors: list[tuple[str, str, str]] = []  # (source, doc, anchor)
        # Track which docs were created from a *real* file on disk vs only as
        # a link target whose path could not be resolved → broken doc ref.
        self._resolved_docs: set[str] = set()
        # Labels that were referenced; populated to detect undefined labels.
        self._referenced_labels: set[str] = set()

    # ------------------------------------------------------------------
    # Node management
    # ------------------------------------------------------------------

    def _add_node(self, node: Node) -> None:
        if node.id not in self._nodes:
            self._nodes[node.id] = node
            self.graph.add_node(node.id, **node.to_dict())

    def _doc_metadata(self, rel_path: str, *, resolved: bool) -> dict:
        # Normalise any leading './' or '/' so URL concatenation is clean.
        norm = rel_path.lstrip('./').lstrip('/')
        meta = {
            'diataxis': classify_diataxis(norm, self.diataxis_prefixes),
            'resolved': resolved,
        }
        if self.source_base:
            meta['source_url'] = self.source_base + norm
        if self.render_base and resolved:
            base = norm
            for ext in ('.md', '.rst'):
                if base.endswith(ext):
                    base = base[: -len(ext)]
                    break
            if base.endswith('/index') or base == 'index':
                base = base[: -len('index')].rstrip('/')
            meta['render_url'] = (self.render_base + base).rstrip('/') + '/'
        return meta

    def _ensure_document_node(self, filepath: str) -> str:
        """Add a document node for an existing file path and return its id."""
        try:
            rel = str(Path(filepath).resolve().relative_to(self.project_root))
        except ValueError:
            rel = filepath
        node_id = rel
        existing = self._nodes.get(node_id)
        meta = self._doc_metadata(rel, resolved=True)
        if existing is None:
            self._add_node(Node(
                id=node_id,
                node_type='document',
                label=Path(filepath).name,
                path=rel,
                project=self.project_name,
                metadata=meta,
            ))
        else:
            # Upgrade an existing virtual node to "resolved"
            existing.metadata.update(meta)
            self.graph.nodes[node_id].update(existing.to_dict())
        self._resolved_docs.add(node_id)
        return node_id

    def _ensure_virtual_document_node(self, rel_path: str, *, resolved: bool = True) -> str:
        """Add a (possibly unresolved) document node and return its id.

        `resolved=False` marks the node as a broken-link target — the
        referenced path could not be found on disk.
        """
        meta = self._doc_metadata(rel_path, resolved=resolved)
        existing = self._nodes.get(rel_path)
        if existing is None:
            self._add_node(Node(
                id=rel_path,
                node_type='document',
                label=Path(rel_path).name,
                path=rel_path,
                project=self.project_name,
                metadata=meta,
            ))
        else:
            # Don't downgrade a resolved node to broken
            if resolved and not existing.metadata.get('resolved', False):
                existing.metadata.update(meta)
                self.graph.nodes[rel_path].update(existing.to_dict())
        if resolved:
            self._resolved_docs.add(rel_path)
        return rel_path

    def _ensure_external_node(self, url: str) -> str:
        self._add_node(Node(
            id=url,
            node_type='external',
            label=url,
            url=url,
        ))
        return url

    def _ensure_label_node(self, label: str) -> str:
        node_id = f'label:{label}'
        self._add_node(Node(
            id=node_id,
            node_type='label',
            label=label,
            project=self.project_name,
        ))
        self._referenced_labels.add(label)
        return node_id

    def _ensure_anchor_node(self, doc_id: str, anchor: str) -> str:
        node_id = f'{doc_id}#{anchor}'
        self._add_node(Node(
            id=node_id,
            node_type='anchor',
            label=anchor,
            path=doc_id,
            project=self.project_name,
        ))
        return node_id

    def _ensure_asset_node(self, rel_path: str) -> str:
        self._add_node(Node(
            id=rel_path,
            node_type='asset',
            label=Path(rel_path).name,
            path=rel_path,
            project=self.project_name,
        ))
        return rel_path

    # ------------------------------------------------------------------
    # Edge management
    # ------------------------------------------------------------------

    def _add_edge(self, source: str, target: str, edge_type: str, label: str = '') -> None:
        if source == target:
            return
        edge = Edge(source=source, target=target, edge_type=edge_type, label=label)
        self._edges.append(edge)
        # NetworkX allows multiple edges only in MultiDiGraph; use DiGraph and
        # track duplicates only in self._edges for export.
        if not self.graph.has_edge(source, target):
            self.graph.add_edge(source, target, edge_type=edge_type, label=label)

    # ------------------------------------------------------------------
    # Main API
    # ------------------------------------------------------------------

    def register_headings(self, source_file: str, headings: list[str]) -> None:
        """Record slugified heading IDs for a file (used for anchor validation)."""
        doc_id = self._ensure_document_node(source_file)
        bucket = self._heading_ids.setdefault(doc_id, set())
        for h in headings:
            slug = _slugify_heading(h)
            if slug:
                bucket.add(slug)

    def add_parsed_links(self, links: list, source_file: str) -> None:
        """Ingest a list of ParsedLink objects from one source file."""
        source_id = self._ensure_document_node(source_file)

        # First pass: collect reference definitions for this file
        for link in links:
            if link.link_type == 'md_ref_def':
                key = link.link_text.lower()
                self._md_ref_defs[key] = link.target
            elif link.link_type == 'myst_label_def':
                self._label_defs[link.target] = source_id
            elif link.link_type == 'rst_target':
                self._label_defs[link.link_text.strip('_')] = source_id

        # Second pass: build edges
        for link in links:
            lt = link.link_type
            raw_target = link.target.strip()

            if lt in _DEFINITION_TYPES:
                continue

            # ------ external URL ------
            if self._is_external(raw_target):
                target_id = self._ensure_external_node(raw_target)
                self._add_edge(source_id, target_id, 'external_link', link.link_text)
                continue

            # ------ resolve [ref:key] placeholders from md_ref_link ------
            if lt == 'md_ref_link':
                ref_key = raw_target[5:-1].lower() if raw_target.startswith('[ref:') else raw_target.lower()
                resolved = self._md_ref_defs.get(ref_key, raw_target)
                if self._is_external(resolved):
                    target_id = self._ensure_external_node(resolved)
                    self._add_edge(source_id, target_id, 'external_link', link.link_text)
                else:
                    target_id = self._resolve_and_add_doc(resolved, source_file)
                    self._add_edge(source_id, target_id, 'link', link.link_text)
                continue

            # ------ MyST / RST doc / toctree ------
            if lt in _DOC_LINK_TYPES:
                target_id = self._resolve_and_add_doc(raw_target, source_file)
                edge_type = 'include' if lt in ('rst_include', 'rst_literalinclude') else 'doc_link'
                self._add_edge(source_id, target_id, edge_type, link.link_text)
                continue

            # ------ cross-reference labels ------
            if lt in _REF_LINK_TYPES:
                target_id = self._ensure_label_node(raw_target)
                self._add_edge(source_id, target_id, 'ref_link', link.link_text)
                continue

            # ------ MyST term ------
            if lt == 'myst_term':
                target_id = self._ensure_label_node(f'term:{raw_target}')
                self._add_edge(source_id, target_id, 'term_link', link.link_text)
                continue

            # ------ inline markdown link / html href ------
            if lt in ('md_inline', 'md_html_href', 'md_autolink'):
                if raw_target.startswith('#'):
                    # Same-document anchor
                    anchor = raw_target.lstrip('#')
                    target_id = self._ensure_anchor_node(source_id, anchor)
                    self._add_edge(source_id, target_id, 'anchor_link', link.link_text)
                    self._pending_anchors.append((source_id, source_id, anchor))
                else:
                    # May contain an anchor suffix
                    doc_part, _, anchor = raw_target.partition('#')
                    target_id = self._resolve_and_add_doc(doc_part, source_file)
                    self._add_edge(source_id, target_id, 'link', link.link_text)
                    if anchor:
                        self._pending_anchors.append((source_id, target_id, anchor))
                continue

            # ------ images ------
            if lt in ('md_image', 'rst_image'):
                if self._is_external(raw_target):
                    target_id = self._ensure_external_node(raw_target)
                else:
                    target_id = self._resolve_and_add_asset(raw_target, source_file)
                self._add_edge(source_id, target_id, 'image', link.link_text)
                continue

            # ------ RST external hyperlink ------
            if lt == 'rst_hyperlink':
                if self._is_external(raw_target):
                    target_id = self._ensure_external_node(raw_target)
                    self._add_edge(source_id, target_id, 'external_link', link.link_text)
                else:
                    target_id = self._resolve_and_add_doc(raw_target, source_file)
                    self._add_edge(source_id, target_id, 'link', link.link_text)
                continue

    # ------------------------------------------------------------------
    # Path resolution helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_external(target: str) -> bool:
        return target.startswith(_EXTERNAL_SCHEMES)

    def _resolve_and_add_doc(self, target: str, source_file: str) -> str:
        """Resolve a doc-relative or project-relative path and return node id."""
        clean = target.split('#')[0].split('?')[0].strip()
        if not clean:
            return self._ensure_document_node(source_file)

        # Apply redirects (matching either with or without extension).
        if self.redirects:
            from ..config import _normalise_redirect_key
            key = _normalise_redirect_key(clean)
            if key in self.redirects:
                redirected = self.redirects[key]
                # Try to find the redirected target as a real file
                clean = redirected
                # Re-add a default extension if needed
                if not Path(clean).suffix:
                    clean_with_ext = clean + '.md'
                else:
                    clean_with_ext = clean
                pr = self.project_root / clean_with_ext
                if pr.exists():
                    try:
                        rel = str(pr.resolve().relative_to(self.project_root))
                        return self._ensure_virtual_document_node(rel, resolved=True)
                    except ValueError:
                        pass

        # Known external prefixes: treat as external rather than broken.
        # Strip any leading './' or '/' before comparing.
        plain = clean.lstrip('./').lstrip('/')
        if any(plain.startswith(pref) for pref in self.known_external_prefixes):
            return self._ensure_external_node(plain)

        source_dir = Path(source_file).resolve().parent

        # Try the path as-is and with common doc extensions
        candidates: list[Path] = [source_dir / clean]
        if not Path(clean).suffix:
            for ext in ('.md', '.rst'):
                candidates.append(source_dir / (clean + ext))
                candidates.append(self.project_root / (clean + ext))
        candidates.append(self.project_root / clean)

        for candidate in candidates:
            if candidate.exists():
                try:
                    rel = str(candidate.resolve().relative_to(self.project_root))
                    return self._ensure_virtual_document_node(rel, resolved=True)
                except ValueError:
                    pass

        # Fallback: target is a broken / unresolved doc reference.
        if not Path(clean).suffix:
            clean = clean + '.md'
        return self._ensure_virtual_document_node(clean, resolved=False)

    # ------------------------------------------------------------------
    # Post-processing
    # ------------------------------------------------------------------

    def finalize(self) -> None:
        """Post-process: mark undefined labels and broken anchors as unresolved."""
        # Labels referenced but never defined
        for node_id, node in self._nodes.items():
            if node.node_type != 'label':
                continue
            label = node.label
            if label.startswith('term:'):
                continue
            defined = label in self._label_defs
            node.metadata['resolved'] = defined
            self.graph.nodes[node_id]['metadata'] = node.metadata

        # Anchor validation
        for source_id, target_doc_id, anchor in self._pending_anchors:
            slug = _slugify_heading(anchor)
            if not slug:
                continue
            headings = self._heading_ids.get(target_doc_id, set())
            anchor_node_id = f'{target_doc_id}#{anchor}'
            node = self._nodes.get(anchor_node_id)
            if node is None:
                continue
            # If we know the target doc's headings and the anchor isn't there,
            # mark it broken. If we don't know the headings (e.g. virtual /
            # external doc), don't penalise.
            target_doc = self._nodes.get(target_doc_id)
            if target_doc and target_doc.node_type == 'document' \
               and target_doc.metadata.get('resolved', True) and headings:
                node.metadata['resolved'] = slug in headings
                self.graph.nodes[anchor_node_id]['metadata'] = node.metadata

    def _resolve_and_add_asset(self, target: str, source_file: str) -> str:
        source_dir = Path(source_file).resolve().parent
        candidate = source_dir / target
        try:
            rel = str(candidate.resolve().relative_to(self.project_root))
        except ValueError:
            rel = target
        return self._ensure_asset_node(rel)

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    def analyze(self) -> dict[str, Any]:
        g = self.graph
        node_type_counts: dict[str, int] = {}
        for _, data in g.nodes(data=True):
            t = data.get('node_type', 'unknown')
            node_type_counts[t] = node_type_counts.get(t, 0) + 1

        edge_type_counts: dict[str, int] = {}
        for e in self._edges:
            edge_type_counts[e.edge_type] = edge_type_counts.get(e.edge_type, 0) + 1

        isolated = list(nx.isolates(g))

        # Broken references
        broken_docs = [
            nid for nid, n in self._nodes.items()
            if n.node_type == 'document' and not n.metadata.get('resolved', True)
        ]
        broken_labels = [
            nid for nid, n in self._nodes.items()
            if n.node_type == 'label' and not n.metadata.get('resolved', True)
        ]

        # Diataxis composition (documents only)
        diataxis_counts: dict[str, int] = {}
        for n in self._nodes.values():
            if n.node_type != 'document':
                continue
            sec = n.metadata.get('diataxis', 'meta')
            diataxis_counts[sec] = diataxis_counts.get(sec, 0) + 1

        return {
            'total_nodes': g.number_of_nodes(),
            'total_edges': g.number_of_edges(),
            'node_type_counts': node_type_counts,
            'edge_type_counts': edge_type_counts,
            'isolated_nodes': isolated,
            'isolated_count': len(isolated),
            'weakly_connected_components': nx.number_weakly_connected_components(g),
            'broken_doc_refs': broken_docs,
            'broken_label_refs': broken_labels,
            'diataxis_counts': diataxis_counts,
        }

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def get_nodes(self) -> list[Node]:
        return list(self._nodes.values())

    def get_edges(self) -> list[Edge]:
        return self._edges


# ---------------------------------------------------------------------------
# Heading slugification (matches Sphinx / MyST conventions closely enough)
# ---------------------------------------------------------------------------

_SLUG_KEEP = re.compile(r'[^a-z0-9\- ]+')


def _slugify_heading(text: str) -> str:
    """Slugify a heading the way Sphinx/MyST/Jekyll usually do.

    Lowercase, replace non-alphanumeric with hyphens, collapse runs of
    hyphens. This is good enough to match links written by humans against
    document headings in the same project.
    """
    s = (text or '').strip().lower()
    s = _SLUG_KEEP.sub(' ', s)
    s = '-'.join(s.split())
    return s.strip('-')
