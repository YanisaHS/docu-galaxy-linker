"""
External link health checker.

Given a graph JSON, collects every external URL, issues bounded-concurrency
HEAD (or fallback GET) requests, and reports the result. Caches outcomes in a
sidecar JSON file so repeated runs only re-check stale entries.

Uses only the stdlib (`urllib`, `threading`) so there's no extra dependency.
"""
from __future__ import annotations

import json
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


USER_AGENT = 'docu-galaxy-linker/0.1 (link-health check)'


@dataclass
class LinkCheckResult:
    url: str
    status: Optional[int] = None      # HTTP status or None on network error
    final_url: Optional[str] = None   # if redirected
    classification: str = 'unknown'   # ok, redirect, broken, timeout, error
    error: Optional[str] = None
    checked_at: str = ''              # ISO timestamp


def check_url(url: str, timeout: float) -> LinkCheckResult:
    """Issue HEAD (fallback GET) to `url`. Returns a result object."""
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        return LinkCheckResult(url=url, classification='skipped',
                               error=f'unsupported scheme: {parsed.scheme}',
                               checked_at=_now())
    req = Request(url, method='HEAD', headers={'User-Agent': USER_AGENT})
    try:
        with urlopen(req, timeout=timeout) as resp:
            return _classify(url, resp.status, resp.geturl())
    except HTTPError as e:
        if e.code in (405, 501):  # method not allowed → try GET
            try:
                req = Request(url, method='GET', headers={'User-Agent': USER_AGENT})
                with urlopen(req, timeout=timeout) as resp:
                    return _classify(url, resp.status, resp.geturl())
            except HTTPError as e2:
                return _classify(url, e2.code, url)
            except (URLError, socket.timeout, TimeoutError) as e2:
                return _network_error(url, e2)
        return _classify(url, e.code, url)
    except (socket.timeout, TimeoutError):
        return LinkCheckResult(url=url, classification='timeout',
                               error='timeout', checked_at=_now())
    except (URLError, OSError) as e:
        return _network_error(url, e)


def _classify(url: str, status: int, final_url: str) -> LinkCheckResult:
    if 200 <= status < 300:
        cls = 'ok'
    elif 300 <= status < 400:
        cls = 'redirect'
    else:
        cls = 'broken'
    return LinkCheckResult(url=url, status=status, final_url=final_url,
                           classification=cls, checked_at=_now())


def _network_error(url: str, exc: Exception) -> LinkCheckResult:
    return LinkCheckResult(url=url, classification='error',
                           error=f'{type(exc).__name__}: {exc}',
                           checked_at=_now())


def _now() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


# ---------------------------------------------------------------------------
# Batch runner with caching
# ---------------------------------------------------------------------------

def check_graph(graph_path: str, *, cache_path: Optional[str] = None,
                timeout: float = 5.0, parallelism: int = 8,
                cache_ttl_days: int = 7,
                progress: Optional[callable] = None) -> dict[str, LinkCheckResult]:
    """Check every external URL in the graph and return a results map.

    `cache_path` controls where prior results are read from / written to;
    entries newer than `cache_ttl_days` are reused.
    """
    with open(graph_path, encoding='utf-8') as f:
        data = json.load(f)

    urls = sorted({
        n.get('url') or n['id']
        for n in data.get('nodes', [])
        if n.get('node_type') == 'external'
        and (n.get('url') or n['id']).startswith(('http://', 'https://'))
    })

    cache: dict[str, dict[str, Any]] = {}
    if cache_path and Path(cache_path).is_file():
        try:
            cache = json.loads(Path(cache_path).read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            cache = {}

    cutoff = datetime.now(timezone.utc) - timedelta(days=cache_ttl_days)
    fresh: dict[str, LinkCheckResult] = {}
    stale: list[str] = []
    for url in urls:
        entry = cache.get(url)
        if entry:
            try:
                when = datetime.strptime(entry['checked_at'], '%Y-%m-%dT%H:%M:%SZ')
                when = when.replace(tzinfo=timezone.utc)
            except (KeyError, ValueError):
                when = None
            if when and when >= cutoff:
                fresh[url] = LinkCheckResult(**entry)
                continue
        stale.append(url)

    results: dict[str, LinkCheckResult] = dict(fresh)
    if stale:
        lock = threading.Lock()
        done = 0
        with ThreadPoolExecutor(max_workers=max(1, parallelism)) as ex:
            futures = {ex.submit(check_url, u, timeout): u for u in stale}
            for fut in as_completed(futures):
                u = futures[fut]
                try:
                    res = fut.result()
                except Exception as exc:  # noqa: BLE001
                    res = LinkCheckResult(url=u, classification='error',
                                          error=f'{type(exc).__name__}: {exc}',
                                          checked_at=_now())
                results[u] = res
                with lock:
                    done += 1
                    if progress:
                        progress(done, len(stale), u, res.classification)

    if cache_path:
        # Persist the merged cache (preserves entries for URLs not in this graph)
        merged = dict(cache)
        for u, r in results.items():
            merged[u] = asdict(r)
        Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
        Path(cache_path).write_text(
            json.dumps(merged, indent=2, ensure_ascii=False), encoding='utf-8',
        )

    return results


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def summary(results: dict[str, LinkCheckResult]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in results.values():
        out[r.classification] = out.get(r.classification, 0) + 1
    return out


def render_markdown(results: dict[str, LinkCheckResult], *, limit: int = 50) -> str:
    s = summary(results)
    out: list[str] = []
    out.append('# External link health\n')
    parts = ', '.join(f'**{k}**: {v}' for k, v in sorted(s.items()))
    out.append(f'Total: {len(results)} · {parts}')

    def _section(title: str, classification: str) -> None:
        rows = [r for r in results.values() if r.classification == classification]
        if not rows:
            return
        out.append('')
        out.append(f'## {title} ({len(rows)})')
        out.append('')
        out.append('| URL | Status | Detail |')
        out.append('|---|---|---|')
        for r in rows[:limit]:
            detail = r.error or (r.final_url if r.final_url and r.final_url != r.url else '')
            out.append(f'| `{r.url}` | {r.status or "—"} | {detail or "—"} |')
        if len(rows) > limit:
            out.append(f'\n_… and {len(rows) - limit} more._')

    _section('Broken', 'broken')
    _section('Timed out', 'timeout')
    _section('Errored', 'error')
    _section('Redirected', 'redirect')
    return '\n'.join(out) + '\n'


def render_text(results: dict[str, LinkCheckResult]) -> str:
    s = summary(results)
    return ' · '.join(f'{k}: {v}' for k, v in sorted(s.items())) + '\n'


def render_json(results: dict[str, LinkCheckResult]) -> str:
    return json.dumps({u: asdict(r) for u, r in results.items()},
                      indent=2, ensure_ascii=False)
