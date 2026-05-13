"""
Concept graph builder.

Takes DocPage objects (from the extractor) and builds a graph where:
  - Nodes  = documentation pages (labelled with their H1 title)
  - Edges  = explicit cross-references  +  conceptual similarity (TF-IDF)

Output is a plain dict that can be serialised to JSON and consumed by
the web visualisation.
"""
from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

from .extractor import DocPage


# ---------------------------------------------------------------------------
# TF-IDF helpers
# ---------------------------------------------------------------------------

def _compute_tfidf(pages: list[DocPage]) -> dict[str, dict[str, float]]:
    """
    Return {page_id: {term: tfidf_score}}.
    Uses sublinear TF scaling: log(1 + tf) * log(N / (df + 1)).
    Only terms that appear in ≥2 and ≤70 % of docs are kept.
    """
    n = len(pages)
    df: dict[str, int] = {}
    for page in pages:
        for term in page.terms:
            df[term] = df.get(term, 0) + 1

    min_df = 2
    max_df = int(n * 0.70)
    valid_terms = {t for t, f in df.items() if min_df <= f <= max_df}

    result: dict[str, dict[str, float]] = {}
    for page in pages:
        vec: dict[str, float] = {}
        for term, tf in page.terms.items():
            if term in valid_terms:
                idf = math.log(n / (df[term] + 1)) + 1.0
                vec[term] = (1.0 + math.log(tf)) * idf
        result[page.id] = vec
    return result


def _cosine_sim(va: dict[str, float], vb: dict[str, float]) -> float:
    common = set(va) & set(vb)
    if not common:
        return 0.0
    dot = sum(va[t] * vb[t] for t in common)
    norm_a = math.sqrt(sum(v * v for v in va.values()))
    norm_b = math.sqrt(sum(v * v for v in vb.values()))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _top_shared_terms(
    va: dict[str, float],
    vb: dict[str, float],
    n: int = 6,
) -> list[str]:
    common = set(va) & set(vb)
    return sorted(common, key=lambda t: va[t] * vb[t], reverse=True)[:n]


# ---------------------------------------------------------------------------
# Cross-reference helpers
# ---------------------------------------------------------------------------

def _build_label_map(docs_root: str) -> dict[str, str]:
    """
    Scan all .md files and return a dict mapping every MyST label
    ``(label-name)=`` to the docs-root-relative path of the file that
    defines it.
    """
    root = Path(docs_root).resolve()
    label_re = re.compile(r'^\(([^)]+)\)=', re.MULTILINE)
    mapping: dict[str, str] = {}
    for md_file in sorted(root.rglob('*.md')):
        try:
            text = md_file.read_text(encoding='utf-8', errors='replace')
        except OSError:
            continue
        rel = str(md_file.relative_to(root)).replace('\\', '/')
        for m in label_re.finditer(text):
            label = m.group(1).strip()
            if label not in mapping:   # first definition wins
                mapping[label] = rel
    return mapping


def _normalise_link_target(target: str, source_dir: str, docs_root: str) -> str | None:
    """
    Try to resolve a markdown link target to a docs-root-relative path.
    Returns None if it can't be resolved to a local .md file.
    """
    # Skip external, anchors-only, mailto etc.
    if target.startswith(('http://', 'https://', 'mailto:', '//', '#')):
        return None

    # Strip anchor fragment
    target = target.split('#')[0].strip()
    if not target:
        return None

    root = Path(docs_root).resolve()
    src_dir = Path(source_dir)

    # Try relative from source dir first, then absolute from docs root
    candidates = [
        src_dir / target,
        root / target.lstrip('/'),
    ]

    for candidate in candidates:
        candidate = candidate.resolve()
        # Add .md if no suffix
        if not candidate.suffix:
            candidate = candidate.with_suffix('.md')
        if candidate.exists():
            try:
                return str(candidate.relative_to(root)).replace('\\', '/')
            except ValueError:
                pass
    return None


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_concept_graph(
    pages: list[DocPage],
    docs_root: str,
    similarity_threshold: float = 0.12,
    max_sim_edges_per_node: int = 8,
) -> dict[str, Any]:
    """
    Build a concept graph from a list of DocPage objects.

    Returns a dict with keys 'nodes' and 'edges' that can be serialised
    to JSON and loaded by the web visualisation.

    Args:
        pages:                  DocPage objects (all non-index pages).
        docs_root:              Absolute path to the docs root directory.
        similarity_threshold:   Minimum cosine similarity to create a
                                shared-concept edge (0–1).
        max_sim_edges_per_node: Cap on similarity edges per node to keep
                                the graph readable.
    """
    node_ids: set[str] = {p.id for p in pages}
    tfidf = _compute_tfidf(pages)

    # ------------------------------------------------------------------
    # Nodes
    # ------------------------------------------------------------------
    nodes: list[dict[str, Any]] = []
    for page in pages:
        nodes.append({
            'id': page.id,
            'node_type': page.section_key,
            'label': page.title,
            'path': page.id,
            'url': None,
            'project': 'landscape',
            'metadata': {
                'section': page.section,
                'word_count': page.word_count,
                'headings': page.headings[:12],
            },
        })

    # ------------------------------------------------------------------
    # Cross-reference edges  (parse links from each markdown file)
    # ------------------------------------------------------------------
    _re_md_link = re.compile(r'\[([^\]]*)\]\(([^)]+)\)')
    _re_myst_ref = re.compile(r'\{ref\}`(?:[^<`]+<)?([^>`]+)>?`')
    _re_myst_doc = re.compile(r'\{doc\}`([^`]+)`')

    # Build label → file map for {ref} resolution
    label_map = _build_label_map(docs_root)

    cross_ref_edges: list[dict[str, Any]] = []
    seen_xref: set[tuple[str, str]] = set()

    for page in pages:
        try:
            text = Path(page.path).read_text(encoding='utf-8', errors='replace')
        except OSError:
            continue

        src_dir = str(Path(page.path).parent)
        found_targets: list[str] = []

        # Plain markdown links → resolve as file paths
        for m in _re_md_link.finditer(text):
            resolved = _normalise_link_target(m.group(2).split('#')[0], src_dir, docs_root)
            if resolved:
                found_targets.append(resolved)

        # {doc}`...` → resolve as file paths
        for m in _re_myst_doc.finditer(text):
            resolved = _normalise_link_target(m.group(1).strip(), src_dir, docs_root)
            if resolved:
                found_targets.append(resolved)

        # {ref}`label` or {ref}`text <label>` → resolve via label map
        for m in _re_myst_ref.finditer(text):
            label = m.group(1).strip()
            resolved = label_map.get(label)
            if resolved:
                found_targets.append(resolved)

        for resolved in found_targets:
            if resolved in node_ids and resolved != page.id:
                key = (page.id, resolved)
                if key not in seen_xref:
                    seen_xref.add(key)
                    cross_ref_edges.append({
                        'source': page.id,
                        'target': resolved,
                        'edge_type': 'cross_ref',
                        'label': 'cross-reference',
                        'metadata': {},
                    })

    # ------------------------------------------------------------------
    # Conceptual similarity edges  (TF-IDF cosine similarity)
    # ------------------------------------------------------------------

    # Build inverted index: term -> [page_ids]
    inverted: dict[str, list[str]] = {}
    for pid, vec in tfidf.items():
        for term in vec:
            inverted.setdefault(term, []).append(pid)

    # Candidate pairs that share at least 3 terms
    candidate_pairs: dict[tuple[str, str], int] = {}
    for pids in inverted.values():
        for i in range(len(pids)):
            for j in range(i + 1, len(pids)):
                pair = (pids[i], pids[j]) if pids[i] < pids[j] else (pids[j], pids[i])
                candidate_pairs[pair] = candidate_pairs.get(pair, 0) + 1

    sim_candidates: list[tuple[float, str, str, list[str]]] = []
    for (pid_a, pid_b), shared_count in candidate_pairs.items():
        if shared_count < 3:
            continue
        va = tfidf.get(pid_a, {})
        vb = tfidf.get(pid_b, {})
        sim = _cosine_sim(va, vb)
        if sim >= similarity_threshold:
            top_terms = _top_shared_terms(va, vb)
            sim_candidates.append((sim, pid_a, pid_b, top_terms))

    sim_candidates.sort(reverse=True)

    node_sim_count: dict[str, int] = {}
    sim_edges: list[dict[str, Any]] = []
    for sim, pid_a, pid_b, top_terms in sim_candidates:
        ca = node_sim_count.get(pid_a, 0)
        cb = node_sim_count.get(pid_b, 0)
        if ca < max_sim_edges_per_node and cb < max_sim_edges_per_node:
            node_sim_count[pid_a] = ca + 1
            node_sim_count[pid_b] = cb + 1
            sim_edges.append({
                'source': pid_a,
                'target': pid_b,
                'edge_type': 'shared_concept',
                'label': ', '.join(top_terms),
                'metadata': {
                    'similarity': round(sim, 3),
                    'shared_terms': top_terms,
                },
            })

    return {
        'nodes': nodes,
        'edges': cross_ref_edges + sim_edges,
    }
