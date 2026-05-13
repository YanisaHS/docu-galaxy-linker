"""
Compare two graph JSONs (e.g. the same project on the PR base branch vs the
head branch) and report regressions.

Designed for CI: returns a structured diff and an exit code so a workflow can
fail the build when new orphans / dead ends / broken refs are introduced.
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class GraphDiff:
    base_path: str
    head_path: str

    docs_added:   list[str] = field(default_factory=list)
    docs_removed: list[str] = field(default_factory=list)

    orphans_added:   list[str] = field(default_factory=list)
    orphans_removed: list[str] = field(default_factory=list)

    dead_ends_added:   list[str] = field(default_factory=list)
    dead_ends_removed: list[str] = field(default_factory=list)

    broken_doc_refs_added:   list[str] = field(default_factory=list)
    broken_doc_refs_removed: list[str] = field(default_factory=list)

    broken_label_refs_added:   list[str] = field(default_factory=list)
    broken_label_refs_removed: list[str] = field(default_factory=list)

    diataxis_delta: dict[str, int] = field(default_factory=dict)
    edge_delta:     int = 0
    node_delta:     int = 0

    def regression_count(self) -> int:
        """Number of *worsening* findings — used for CI exit codes."""
        return (
            len(self.orphans_added)
            + len(self.dead_ends_added)
            + len(self.broken_doc_refs_added)
            + len(self.broken_label_refs_added)
        )

    def has_regressions(self) -> bool:
        return self.regression_count() > 0

    def to_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d['regression_count'] = self.regression_count()
        return d


# ---------------------------------------------------------------------------
# Computation
# ---------------------------------------------------------------------------

def _load(path: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    return data.get('nodes', []), data.get('edges', [])


def _degrees(edges: list[dict[str, Any]]) -> tuple[dict[str, int], dict[str, int]]:
    in_deg: dict[str, int] = defaultdict(int)
    out_deg: dict[str, int] = defaultdict(int)
    for e in edges:
        out_deg[e['source']] += 1
        in_deg[e['target']] += 1
    return dict(in_deg), dict(out_deg)


def _resolved_docs(nodes: list[dict[str, Any]]) -> set[str]:
    return {
        n['id'] for n in nodes
        if n.get('node_type') == 'document'
        and (n.get('metadata') or {}).get('resolved', True)
    }


def _broken(nodes: list[dict[str, Any]], node_type: str) -> set[str]:
    return {
        n['id'] for n in nodes
        if n.get('node_type') == node_type
        and (n.get('metadata') or {}).get('resolved') is False
    }


def compute_diff(base_path: str, head_path: str) -> GraphDiff:
    base_nodes, base_edges = _load(base_path)
    head_nodes, head_edges = _load(head_path)

    base_in, base_out = _degrees(base_edges)
    head_in, head_out = _degrees(head_edges)

    base_docs = _resolved_docs(base_nodes)
    head_docs = _resolved_docs(head_nodes)

    docs_added   = sorted(head_docs - base_docs)
    docs_removed = sorted(base_docs - head_docs)

    def _orphans(docs: set[str], in_deg: dict[str, int]) -> set[str]:
        return {d for d in docs if in_deg.get(d, 0) == 0}

    def _dead_ends(docs: set[str], out_deg: dict[str, int]) -> set[str]:
        return {d for d in docs if out_deg.get(d, 0) == 0}

    base_orphans = _orphans(base_docs, base_in)
    head_orphans = _orphans(head_docs, head_in)

    base_dead = _dead_ends(base_docs, base_out)
    head_dead = _dead_ends(head_docs, head_out)

    base_broken_docs   = _broken(base_nodes, 'document')
    head_broken_docs   = _broken(head_nodes, 'document')

    base_broken_labels = _broken(base_nodes, 'label')
    head_broken_labels = _broken(head_nodes, 'label')

    # Diataxis composition delta
    def _diataxis_counts(nodes: list[dict[str, Any]]) -> dict[str, int]:
        c: dict[str, int] = defaultdict(int)
        for n in nodes:
            if n.get('node_type') != 'document':
                continue
            sec = (n.get('metadata') or {}).get('diataxis', 'meta')
            c[sec] += 1
        return c

    base_dia = _diataxis_counts(base_nodes)
    head_dia = _diataxis_counts(head_nodes)
    delta = {}
    for sec in sorted(set(base_dia) | set(head_dia)):
        d = head_dia.get(sec, 0) - base_dia.get(sec, 0)
        if d:
            delta[sec] = d

    return GraphDiff(
        base_path=base_path,
        head_path=head_path,
        docs_added=docs_added,
        docs_removed=docs_removed,
        orphans_added=sorted(head_orphans - base_orphans),
        orphans_removed=sorted(base_orphans - head_orphans),
        dead_ends_added=sorted(head_dead - base_dead),
        dead_ends_removed=sorted(base_dead - head_dead),
        broken_doc_refs_added=sorted(head_broken_docs - base_broken_docs),
        broken_doc_refs_removed=sorted(base_broken_docs - head_broken_docs),
        broken_label_refs_added=sorted(head_broken_labels - base_broken_labels),
        broken_label_refs_removed=sorted(base_broken_labels - head_broken_labels),
        diataxis_delta=delta,
        edge_delta=len(head_edges) - len(base_edges),
        node_delta=len(head_nodes) - len(base_nodes),
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_markdown(d: GraphDiff) -> str:
    out: list[str] = []
    out.append('# Documentation link diff\n')
    base_name = Path(d.base_path).name
    head_name = Path(d.head_path).name
    out.append(f'Comparing `{base_name}` → `{head_name}`\n')
    out.append(f'**Δ nodes:** {d.node_delta:+d}  ·  **Δ edges:** {d.edge_delta:+d}')

    if d.diataxis_delta:
        parts = ', '.join(f'{k}: {v:+d}' for k, v in d.diataxis_delta.items())
        out.append(f'\n**Diataxis composition Δ:** {parts}\n')

    regressions = d.regression_count()
    if regressions:
        out.append(f'\n> ⚠️ **{regressions} regression(s) detected.**')
    else:
        out.append('\n> ✅ No regressions detected.')

    def _block(title: str, added: list[str], removed: list[str],
               *, added_is_bad: bool = True, limit: int = 15) -> None:
        if not added and not removed:
            return
        out.append(f'\n## {title}\n')
        if added:
            tag = '➕ Added' if not added_is_bad else '🔴 New (regression)'
            out.append(f'**{tag} ({len(added)}):**')
            for x in added[:limit]:
                out.append(f'- `{x}`')
            if len(added) > limit:
                out.append(f'- _… and {len(added) - limit} more_')
        if removed:
            tag = '➖ Removed' if not added_is_bad else '🟢 Fixed'
            out.append(f'\n**{tag} ({len(removed)}):**')
            for x in removed[:limit]:
                out.append(f'- `{x}`')
            if len(removed) > limit:
                out.append(f'- _… and {len(removed) - limit} more_')

    _block('Documents', d.docs_added, d.docs_removed, added_is_bad=False)
    _block('Orphans', d.orphans_added, d.orphans_removed)
    _block('Dead ends', d.dead_ends_added, d.dead_ends_removed)
    _block('Broken doc references', d.broken_doc_refs_added, d.broken_doc_refs_removed)
    _block('Broken label references', d.broken_label_refs_added, d.broken_label_refs_removed)

    return '\n'.join(out) + '\n'


def render_json(d: GraphDiff) -> str:
    return json.dumps(d.to_dict(), indent=2, ensure_ascii=False)


def render_text(d: GraphDiff) -> str:
    out: list[str] = []
    out.append(f'Δ nodes: {d.node_delta:+d}  edges: {d.edge_delta:+d}')
    out.append(f'  orphans +{len(d.orphans_added)} / -{len(d.orphans_removed)}')
    out.append(f'  dead-ends +{len(d.dead_ends_added)} / -{len(d.dead_ends_removed)}')
    out.append(f'  broken docs +{len(d.broken_doc_refs_added)} / -{len(d.broken_doc_refs_removed)}')
    out.append(f'  broken labels +{len(d.broken_label_refs_added)} / -{len(d.broken_label_refs_removed)}')
    out.append(f'  regressions: {d.regression_count()}')
    return '\n'.join(out) + '\n'


RENDERERS = {
    'markdown': render_markdown,
    'json':     render_json,
    'text':     render_text,
}


def write_diff(base_path: str, head_path: str,
               output_path: Optional[str], fmt: str = 'markdown') -> tuple[str, int]:
    """Compute the diff, write it, and return (rendered text, regression count)."""
    fmt = fmt.lower()
    if fmt not in RENDERERS:
        raise ValueError(f'Unknown format: {fmt}. Choose from {list(RENDERERS)}')
    d = compute_diff(base_path, head_path)
    text = RENDERERS[fmt](d)
    if output_path and output_path != '-':
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(text, encoding='utf-8')
    return text, d.regression_count()
