"""
Generate human- and machine-readable reports from a graph JSON.

Reports surface the things a documentation engineer needs to act on:
  - top hubs (most outgoing links)
  - most-cited pages (most incoming links)
  - orphan pages (no incoming internal link — usually a navigation bug)
  - dead-end pages (no outgoing link — bad for discoverability)
  - broken references (unresolved doc paths or undefined labels)
  - Diataxis cross-edges (e.g. tutorial → reference, signalling drift)
  - external-link inventory (top external domains)

Output formats: markdown (default), json, text, csv.
"""
from __future__ import annotations

import csv
import io
import json
import os
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Optional
from urllib.parse import urlparse


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class GraphReport:
    project: str
    total_nodes: int
    total_edges: int
    node_type_counts: dict[str, int]
    edge_type_counts: dict[str, int]
    diataxis_counts: dict[str, int]

    top_hubs: list[dict[str, Any]]              # most outgoing
    most_cited: list[dict[str, Any]]            # most incoming
    orphans: list[dict[str, Any]]               # docs with in-degree 0
    dead_ends: list[dict[str, Any]]             # docs with out-degree 0
    broken_doc_refs: list[dict[str, Any]]       # unresolved doc paths
    broken_label_refs: list[dict[str, Any]]     # undefined label targets
    broken_anchors: list[dict[str, Any]]        # anchors pointing at missing headings
    diataxis_cross_edges: list[dict[str, Any]]  # cross-section edges
    external_domains: list[dict[str, Any]]      # ranked external hosts

    # Quality metrics
    diataxis_purity: float          # fraction of internal edges within section
    reachability_at_3: float        # fraction of docs reachable from entry in <=3 hops
    reachability_entry: Optional[str]

    # Owner grouping (path → owners)
    orphans_by_owner:   dict[str, list[str]]
    dead_ends_by_owner: dict[str, list[str]]

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


# ---------------------------------------------------------------------------
# Computation
# ---------------------------------------------------------------------------

def _degrees(edges: list[dict[str, Any]]) -> tuple[dict[str, int], dict[str, int]]:
    in_deg: dict[str, int] = defaultdict(int)
    out_deg: dict[str, int] = defaultdict(int)
    for e in edges:
        out_deg[e['source']] += 1
        in_deg[e['target']] += 1
    return dict(in_deg), dict(out_deg)


def _node_record(node: dict[str, Any], in_deg: int, out_deg: int) -> dict[str, Any]:
    meta = node.get('metadata') or {}
    return {
        'id':        node['id'],
        'path':      node.get('path'),
        'diataxis':  meta.get('diataxis'),
        'in_degree': in_deg,
        'out_degree': out_deg,
        'source_url': meta.get('source_url'),
        'render_url': meta.get('render_url'),
    }


def build_report(graph_json_path: str, *, limit: int = 25,
                 reachability_entry: Optional[str] = None) -> GraphReport:
    with open(graph_json_path, encoding='utf-8') as f:
        data = json.load(f)
    nodes: list[dict[str, Any]] = data.get('nodes', [])
    edges: list[dict[str, Any]] = data.get('edges', [])

    in_deg, out_deg = _degrees(edges)
    nodes_by_id = {n['id']: n for n in nodes}

    docs = [n for n in nodes if n.get('node_type') == 'document']
    externals = [n for n in nodes if n.get('node_type') == 'external']

    # Top hubs (most outgoing among docs)
    top_hubs = sorted(
        ({'node': n, 'out': out_deg.get(n['id'], 0), 'in': in_deg.get(n['id'], 0)}
         for n in docs),
        key=lambda r: r['out'], reverse=True,
    )[:limit]
    top_hubs_out = [_node_record(r['node'], r['in'], r['out']) for r in top_hubs if r['out'] > 0]

    # Most cited (most incoming; can be docs or labels)
    cited_candidates = [n for n in nodes if n.get('node_type') in ('document', 'label')]
    most_cited = sorted(
        ({'node': n, 'in': in_deg.get(n['id'], 0), 'out': out_deg.get(n['id'], 0)}
         for n in cited_candidates),
        key=lambda r: r['in'], reverse=True,
    )[:limit]
    most_cited_out = [_node_record(r['node'], r['in'], r['out']) for r in most_cited if r['in'] > 0]

    # Orphans / dead-ends (documents only)
    orphans = [
        _node_record(n, 0, out_deg.get(n['id'], 0))
        for n in docs
        if in_deg.get(n['id'], 0) == 0
        and (n.get('metadata') or {}).get('resolved', True)
    ]
    dead_ends = [
        _node_record(n, in_deg.get(n['id'], 0), 0)
        for n in docs
        if out_deg.get(n['id'], 0) == 0
        and (n.get('metadata') or {}).get('resolved', True)
    ]

    # Broken doc refs (virtual doc nodes whose path was never found on disk)
    broken_doc_refs = []
    for n in docs:
        meta = n.get('metadata') or {}
        if meta.get('resolved') is False:
            # Find who pointed at it (incoming edges)
            referrers = sorted({e['source'] for e in edges if e['target'] == n['id']})
            broken_doc_refs.append({
                **_node_record(n, in_deg.get(n['id'], 0), out_deg.get(n['id'], 0)),
                'referrers': referrers,
            })

    # Broken label refs
    labels = [n for n in nodes if n.get('node_type') == 'label']
    broken_label_refs = []
    for n in labels:
        meta = n.get('metadata') or {}
        if meta.get('resolved') is False:
            referrers = sorted({e['source'] for e in edges if e['target'] == n['id']})
            broken_label_refs.append({
                'id':         n['id'],
                'label':      n.get('label'),
                'in_degree':  in_deg.get(n['id'], 0),
                'referrers':  referrers,
            })

    # Diataxis cross-edges (doc → doc, different sections, excluding 'meta')
    diataxis_cross_edges = []
    for e in edges:
        if e['edge_type'] not in ('doc_link', 'link', 'include'):
            continue
        s = nodes_by_id.get(e['source'])
        t = nodes_by_id.get(e['target'])
        if not s or not t:
            continue
        if s.get('node_type') != 'document' or t.get('node_type') != 'document':
            continue
        sec_s = (s.get('metadata') or {}).get('diataxis')
        sec_t = (t.get('metadata') or {}).get('diataxis')
        if not sec_s or not sec_t or sec_s == sec_t:
            continue
        if 'meta' in (sec_s, sec_t):
            continue
        diataxis_cross_edges.append({
            'from': e['source'],
            'to':   e['target'],
            'from_section': sec_s,
            'to_section':   sec_t,
            'pair':         f'{sec_s} -> {sec_t}',
        })

    # External-link inventory: rank by host
    host_counts: dict[str, int] = defaultdict(int)
    host_examples: dict[str, set[str]] = defaultdict(set)
    for e in edges:
        if e.get('edge_type') != 'external_link':
            continue
        t = nodes_by_id.get(e['target'])
        if not t:
            continue
        url = t.get('url') or t.get('id')
        try:
            host = urlparse(url).netloc or url
        except Exception:  # noqa: BLE001
            host = url
        host_counts[host] += 1
        if len(host_examples[host]) < 3:
            host_examples[host].add(url)
    external_domains = [
        {'host': h, 'count': c, 'examples': sorted(host_examples[h])}
        for h, c in sorted(host_counts.items(), key=lambda kv: -kv[1])[:limit]
    ]

    # Diataxis counts
    diataxis_counts: dict[str, int] = defaultdict(int)
    for d in docs:
        sec = (d.get('metadata') or {}).get('diataxis', 'meta')
        diataxis_counts[sec] += 1

    # Broken anchors (anchor nodes whose target heading is missing)
    broken_anchors = []
    for n in nodes:
        if n.get('node_type') != 'anchor':
            continue
        meta = n.get('metadata') or {}
        if meta.get('resolved') is False:
            referrers = sorted({e['source'] for e in edges if e['target'] == n['id']})
            doc_id, _, anchor = n['id'].partition('#')
            broken_anchors.append({
                'id':        n['id'],
                'doc':       doc_id,
                'anchor':    anchor,
                'referrers': referrers,
            })

    # Diataxis purity — internal edges that stay within section
    internal_total = 0
    internal_within = 0
    for e in edges:
        if e['edge_type'] not in ('doc_link', 'link', 'include'):
            continue
        s = nodes_by_id.get(e['source'])
        t = nodes_by_id.get(e['target'])
        if not s or not t:
            continue
        if s.get('node_type') != 'document' or t.get('node_type') != 'document':
            continue
        sec_s = (s.get('metadata') or {}).get('diataxis')
        sec_t = (t.get('metadata') or {}).get('diataxis')
        if not sec_s or not sec_t:
            continue
        if 'meta' in (sec_s, sec_t):
            continue
        internal_total += 1
        if sec_s == sec_t:
            internal_within += 1
    diataxis_purity = (internal_within / internal_total) if internal_total else 1.0

    # Reachability — BFS from the entry doc, count distinct docs at distance <= 3
    if reachability_entry is None:
        # Pick the most plausible entry: 'index.md' at the root, or the top hub.
        candidates = ['index.md', 'index.rst', 'README.md', 'tutorial.md']
        entry = next((c for c in candidates if any(d['id'] == c for d in docs)), None)
        if entry is None and docs:
            entry = top_hubs_out[0]['id'] if top_hubs_out else docs[0]['id']
    else:
        entry = reachability_entry
    reachable_at_3 = _reachable(entry, edges, max_dist=3) if entry else set()
    total_docs = max(1, len(docs))
    reachability_at_3 = len(reachable_at_3 & {d['id'] for d in docs}) / total_docs

    # Owner grouping for orphans / dead-ends
    def _owners(rec: dict[str, Any]) -> list[str]:
        nid = rec.get('id')
        if not nid: return []
        meta = (nodes_by_id.get(nid, {}).get('metadata') or {})
        return list(meta.get('owners') or [])

    orphans_by_owner: dict[str, list[str]] = defaultdict(list)
    for o in orphans:
        ow = _owners(o) or ['(no owner)']
        for w in ow:
            orphans_by_owner[w].append(o['id'])
    dead_ends_by_owner: dict[str, list[str]] = defaultdict(list)
    for d in dead_ends:
        ow = _owners(d) or ['(no owner)']
        for w in ow:
            dead_ends_by_owner[w].append(d['id'])

    project = (docs[0].get('project') if docs else None) or Path(graph_json_path).stem

    return GraphReport(
        project=project,
        total_nodes=len(nodes),
        total_edges=len(edges),
        node_type_counts=_count_field(nodes, 'node_type'),
        edge_type_counts=_count_field(edges, 'edge_type'),
        diataxis_counts=dict(diataxis_counts),
        top_hubs=top_hubs_out,
        most_cited=most_cited_out,
        orphans=sorted(orphans, key=lambda r: r['id']),
        dead_ends=sorted(dead_ends, key=lambda r: r['id']),
        broken_doc_refs=sorted(broken_doc_refs, key=lambda r: r['id']),
        broken_label_refs=sorted(broken_label_refs, key=lambda r: r['id']),
        broken_anchors=sorted(broken_anchors, key=lambda r: r['id']),
        diataxis_cross_edges=diataxis_cross_edges,
        external_domains=external_domains,
        diataxis_purity=round(diataxis_purity, 3),
        reachability_at_3=round(reachability_at_3, 3),
        reachability_entry=entry,
        orphans_by_owner=dict(orphans_by_owner),
        dead_ends_by_owner=dict(dead_ends_by_owner),
    )


def _reachable(start: str, edges: list[dict[str, Any]], max_dist: int) -> set[str]:
    """BFS the set of nodes reachable from `start` within `max_dist` hops."""
    adj: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        adj[e['source']].append(e['target'])
    seen = {start}
    frontier = [start]
    for _ in range(max_dist):
        nxt: list[str] = []
        for u in frontier:
            for v in adj.get(u, []):
                if v not in seen:
                    seen.add(v)
                    nxt.append(v)
        if not nxt:
            break
        frontier = nxt
    return seen


def _count_field(items: Iterable[dict[str, Any]], key: str) -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    for it in items:
        out[it.get(key, 'unknown')] += 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _doc_link(rec: dict[str, Any]) -> str:
    label = rec.get('path') or rec.get('id')
    url = rec.get('source_url')
    return f'[`{label}`]({url})' if url else f'`{label}`'


def _table(out: list[str], title: str, items: list[dict[str, Any]],
           header_cols: list[str], row_fn, limit: int) -> None:
    out.append('')
    out.append(f'## {title} ({len(items)})')
    out.append('')
    if not items:
        out.append('_None._')
        return
    out.append('| ' + ' | '.join(header_cols) + ' |')
    out.append('|' + '|'.join('---' for _ in header_cols) + '|')
    for it in items[:limit]:
        out.append(row_fn(it))
    if len(items) > limit:
        out.append('')
        out.append(f'_… and {len(items) - limit} more._')


def _checklist(out: list[str], title: str, items: list[dict[str, Any]],
               limit: int) -> None:
    out.append('')
    out.append(f'## {title} ({len(items)})')
    out.append('')
    if not items:
        out.append('_None._')
        return
    for rec in items[:limit]:
        sec = rec.get('diataxis') or '—'
        out.append(f'- [ ] {_doc_link(rec)}  _({sec})_')
    if len(items) > limit:
        out.append(f'- _… and {len(items) - limit} more._')


def render_markdown(r: GraphReport, *, limit: int = 15) -> str:
    out: list[str] = []
    out.append(f'# Documentation link report — `{r.project}`')
    out.append('')
    out.append(f'**{r.total_nodes}** nodes · **{r.total_edges}** edges · '
               f'**{r.node_type_counts.get("document", 0)}** docs · '
               f'**{r.node_type_counts.get("external", 0)}** external')
    if r.diataxis_counts:
        parts = ', '.join(f'{k}: {v}' for k, v in sorted(r.diataxis_counts.items()))
        out.append('')
        out.append(f'**Diataxis composition:** {parts}')

    # Quality metrics
    out.append('')
    out.append('| Metric | Value |')
    out.append('|---|---|')
    out.append(f'| Diataxis purity | {r.diataxis_purity:.0%} |')
    entry = f' from `{r.reachability_entry}`' if r.reachability_entry else ''
    out.append(f'| Reachability @ 3 hops{entry} | {r.reachability_at_3:.0%} |')
    out.append(f'| Orphans | {len(r.orphans)} |')
    out.append(f'| Dead ends | {len(r.dead_ends)} |')
    out.append(f'| Broken doc refs | {len(r.broken_doc_refs)} |')
    out.append(f'| Broken label refs | {len(r.broken_label_refs)} |')
    out.append(f'| Broken anchors | {len(r.broken_anchors)} |')

    _table(out, 'Top hubs (most outgoing links)', r.top_hubs,
           ['Page', 'Section', 'Out', 'In'],
           lambda rec: f'| {_doc_link(rec)} | {rec.get("diataxis") or "—"} | '
                       f'{rec["out_degree"]} | {rec["in_degree"]} |',
           limit)

    _table(out, 'Most cited', r.most_cited,
           ['Target', 'Section', 'In'],
           lambda rec: f'| `{rec.get("path") or rec["id"]}` | '
                       f'{rec.get("diataxis") or "—"} | {rec["in_degree"]} |',
           limit)

    _checklist(out, 'Orphan documents (no incoming internal link)',
               r.orphans, limit)
    _checklist(out, 'Dead-end documents (no outgoing link)',
               r.dead_ends, limit)

    _table(out, 'Broken doc references', r.broken_doc_refs,
           ['Missing target', 'Referenced by'],
           lambda rec: f'| `{rec.get("path") or rec["id"]}` | '
                       f'{", ".join(f"`{x}`" for x in rec.get("referrers", [])[:5]) or "—"} |',
           limit)

    _table(out, 'Broken label references (referenced but never defined)',
           r.broken_label_refs,
           ['Label', 'Referenced by'],
           lambda rec: f'| `{rec.get("label") or rec["id"]}` | '
                       f'{", ".join(f"`{x}`" for x in rec.get("referrers", [])[:5]) or "—"} |',
           limit)

    _table(out, 'Broken anchor references',
           r.broken_anchors,
           ['Target', 'Referenced by'],
           lambda rec: f'| `{rec["doc"]}#{rec["anchor"]}` | '
                       f'{", ".join(f"`{x}`" for x in rec.get("referrers", [])[:5]) or "—"} |',
           limit)

    # Owner grouping
    if r.orphans_by_owner and any(o != '(no owner)' for o in r.orphans_by_owner):
        out.append('')
        out.append('## Orphans by owner')
        out.append('')
        out.append('| Owner | Count |')
        out.append('|---|---|')
        for owner, ids in sorted(r.orphans_by_owner.items(),
                                  key=lambda kv: -len(kv[1])):
            out.append(f'| `{owner}` | {len(ids)} |')

    if r.diataxis_cross_edges:
        pair_counts: dict[str, int] = defaultdict(int)
        for e in r.diataxis_cross_edges:
            pair_counts[e['pair']] += 1
        out.append('')
        out.append(f'## Diataxis cross-edges ({len(r.diataxis_cross_edges)})')
        out.append('')
        out.append('Cross-section links can signal scope drift (e.g. a '
                   'tutorial leaning heavily on references).')
        out.append('')
        out.append('| Direction | Count |')
        out.append('|---|---|')
        for pair, c in sorted(pair_counts.items(), key=lambda kv: -kv[1]):
            out.append(f'| `{pair}` | {c} |')

    if r.external_domains:
        out.append('')
        out.append(f'## Top external domains ({len(r.external_domains)})')
        out.append('')
        out.append('| Host | Count | Examples |')
        out.append('|---|---|---|')
        for d in r.external_domains[:limit]:
            ex = ' · '.join(d['examples'][:2])
            out.append(f'| `{d["host"]}` | {d["count"]} | {ex} |')

    return '\n'.join(out) + '\n'


def render_json(r: GraphReport) -> str:
    return json.dumps(r.to_dict(), indent=2, ensure_ascii=False)


def render_text(r: GraphReport) -> str:
    out: list[str] = []
    out.append(f'{r.project}: {r.total_nodes} nodes, {r.total_edges} edges')
    if r.diataxis_counts:
        out.append('  Diataxis: ' + ', '.join(f'{k}={v}' for k, v in sorted(r.diataxis_counts.items())))
    out.append(f'  Diataxis purity:   {r.diataxis_purity:.0%}')
    if r.reachability_entry:
        out.append(f'  Reachability @3:   {r.reachability_at_3:.0%}  (from {r.reachability_entry})')
    out.append(f'  Orphans:           {len(r.orphans)}')
    out.append(f'  Dead ends:         {len(r.dead_ends)}')
    out.append(f'  Broken doc refs:   {len(r.broken_doc_refs)}')
    out.append(f'  Broken label refs: {len(r.broken_label_refs)}')
    out.append(f'  Broken anchors:    {len(r.broken_anchors)}')
    out.append(f'  Diataxis crosses:  {len(r.diataxis_cross_edges)}')
    return '\n'.join(out) + '\n'


def render_csv(r: GraphReport) -> str:
    """Single CSV of all flagged findings with a `category` column."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['category', 'id', 'path', 'diataxis', 'in_degree', 'out_degree',
                'source_url', 'extra'])
    for rec in r.orphans:
        w.writerow(['orphan', rec['id'], rec.get('path'), rec.get('diataxis'),
                    rec.get('in_degree'), rec.get('out_degree'),
                    rec.get('source_url'), ''])
    for rec in r.dead_ends:
        w.writerow(['dead_end', rec['id'], rec.get('path'), rec.get('diataxis'),
                    rec.get('in_degree'), rec.get('out_degree'),
                    rec.get('source_url'), ''])
    for rec in r.broken_doc_refs:
        w.writerow(['broken_doc_ref', rec['id'], rec.get('path'), rec.get('diataxis'),
                    rec.get('in_degree'), rec.get('out_degree'),
                    rec.get('source_url'),
                    ';'.join(rec.get('referrers', []))])
    for rec in r.broken_label_refs:
        w.writerow(['broken_label_ref', rec['id'], '', '',
                    rec.get('in_degree'), 0, '',
                    ';'.join(rec.get('referrers', []))])
    for rec in r.top_hubs:
        w.writerow(['hub', rec['id'], rec.get('path'), rec.get('diataxis'),
                    rec.get('in_degree'), rec.get('out_degree'),
                    rec.get('source_url'), ''])
    return buf.getvalue()


RENDERERS = {
    'markdown': render_markdown,
    'json':     render_json,
    'text':     render_text,
    'csv':      render_csv,
}


def write_report(graph_json_path: str, output_path: Optional[str],
                 fmt: str = 'markdown', limit: int = 25) -> str:
    fmt = fmt.lower()
    if fmt not in RENDERERS:
        raise ValueError(f'Unknown format: {fmt}. Choose from {list(RENDERERS)}')
    report = build_report(graph_json_path, limit=limit)
    text = RENDERERS[fmt](report)
    if output_path and output_path != '-':
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(text, encoding='utf-8')
    return text
