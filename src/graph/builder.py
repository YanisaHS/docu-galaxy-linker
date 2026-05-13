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


class GraphBuilder:
    def __init__(self, project_root: str, project_name: Optional[str] = None) -> None:
        self.project_root = Path(project_root).resolve()
        self.project_name = project_name
        self.graph: nx.DiGraph = nx.DiGraph()
        self._nodes: dict[str, Node] = {}
        self._edges: list[Edge] = []

        # Map from reference label -> list of source nodes that define it
        self._label_defs: dict[str, str] = {}
        # Map from md ref-key -> target URL (from ref definitions)
        self._md_ref_defs: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Node management
    # ------------------------------------------------------------------

    def _add_node(self, node: Node) -> None:
        if node.id not in self._nodes:
            self._nodes[node.id] = node
            self.graph.add_node(node.id, **node.to_dict())

    def _ensure_document_node(self, filepath: str) -> str:
        """Add a document node for an existing file path and return its id."""
        try:
            rel = str(Path(filepath).resolve().relative_to(self.project_root))
        except ValueError:
            rel = filepath
        node_id = rel
        self._add_node(Node(
            id=node_id,
            node_type='document',
            label=Path(filepath).name,
            path=rel,
            project=self.project_name,
        ))
        return node_id

    def _ensure_virtual_document_node(self, rel_path: str) -> str:
        """Add a (possibly unresolved) document node and return its id."""
        self._add_node(Node(
            id=rel_path,
            node_type='document',
            label=Path(rel_path).name,
            path=rel_path,
            project=self.project_name,
        ))
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
                    target_id = self._ensure_anchor_node(source_id, raw_target.lstrip('#'))
                    self._add_edge(source_id, target_id, 'anchor_link', link.link_text)
                else:
                    # May contain an anchor suffix
                    doc_part, _, anchor = raw_target.partition('#')
                    target_id = self._resolve_and_add_doc(doc_part, source_file)
                    self._add_edge(source_id, target_id, 'link', link.link_text)
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
                    return self._ensure_virtual_document_node(rel)
                except ValueError:
                    pass

        # Fallback: use the path as a virtual node
        if not Path(clean).suffix:
            clean = clean + '.md'
        return self._ensure_virtual_document_node(clean)

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

        return {
            'total_nodes': g.number_of_nodes(),
            'total_edges': g.number_of_edges(),
            'node_type_counts': node_type_counts,
            'edge_type_counts': edge_type_counts,
            'isolated_nodes': isolated,
            'isolated_count': len(isolated),
            'weakly_connected_components': nx.number_weakly_connected_components(g),
        }

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def get_nodes(self) -> list[Node]:
        return list(self._nodes.values())

    def get_edges(self) -> list[Edge]:
        return self._edges
