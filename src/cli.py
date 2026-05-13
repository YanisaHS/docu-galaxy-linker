"""
CLI entry point for docu-galaxy-linker.

Commands:
  extract   – scan a documentation project and emit graph JSON
  visualize – serve an interactive Cytoscape.js graph
  analyze   – print statistics about a saved graph JSON
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from .orchestrator import ExtractorOrchestrator


@click.group()
@click.version_option(package_name='docu-galaxy-linker')
def cli() -> None:
    """docu-galaxy-linker — extract and visualize documentation link graphs."""


# ---------------------------------------------------------------------------
# extract
# ---------------------------------------------------------------------------

@cli.command()
@click.argument('project_path', type=click.Path(exists=True, file_okay=False, resolve_path=True))
@click.option('--output', '-o', default='graph.json', show_default=True,
              help='Output graph JSON file.')
@click.option('--cytoscape', '-c', default=None,
              help='Also write a Cytoscape.js elements JSON file.')
@click.option('--project-name', default=None,
              help='Tag all nodes with this project name (used in multi-project merges).')
@click.option('--source-base', default=None,
              help='Base URL for source files (overrides .docu-galaxy.toml).')
@click.option('--render-base', default=None,
              help='Base URL for the rendered docs site (overrides config).')
@click.option('--config', 'config_path', default=None,
              type=click.Path(dir_okay=False),
              help='Path to a docu-galaxy.toml. Auto-discovered if omitted.')
@click.option('--no-ownership', is_flag=True, default=False,
              help='Skip CODEOWNERS annotation even if a CODEOWNERS file is present.')
@click.option('--verbose', '-v', is_flag=True, help='Show per-file progress.')
def extract(project_path: str, output: str, cytoscape: str | None,
            project_name: str | None, source_base: str | None,
            render_base: str | None, config_path: str | None,
            no_ownership: bool, verbose: bool) -> None:
    """Extract all links from PROJECT_PATH and save a graph JSON.

    PROJECT_PATH is the root directory of a documentation project
    (e.g. a cloned Canonical docs repository). Configuration is loaded from
    the nearest `.docu-galaxy.toml`; CLI flags override config values.
    """
    from .config import load_config, load_redirects, load_sphinx_conf, merged, \
        _normalise_redirect_key as _norm
    from .ownership import load_codeowners

    pp = Path(project_path)
    cfg = load_config(Path(config_path).parent if config_path else pp)
    cfg = merged(cfg, source_base=source_base, render_base=render_base)

    def _resolve(p: str) -> Path:
        path = Path(p)
        return path if path.is_absolute() else (pp / p)

    redirects: dict[str, str] = {}
    if cfg.redirects_file:
        redirects.update(load_redirects(_resolve(cfg.redirects_file)))

    exclude = list(cfg.ignore)
    if cfg.sphinx_conf:
        sx = load_sphinx_conf(_resolve(cfg.sphinx_conf))
        if isinstance(sx.get('redirects'), dict):
            redirects.update({_norm(k): _norm(v) for k, v in sx['redirects'].items()})
        if isinstance(sx.get('exclude_patterns'), list):
            exclude.extend(str(p) for p in sx['exclude_patterns'])

    co = None if no_ownership else load_codeowners(pp, cfg.codeowners)

    click.echo(f'Extracting links from: {project_path}')
    if cfg.config_path:
        click.echo(f'  Using config:  {cfg.config_path}')
    if redirects:
        click.echo(f'  Redirects:     {len(redirects)} mappings')
    if exclude:
        click.echo(f'  Exclude:       {len(exclude)} patterns')
    if co:
        click.echo(f'  Ownership:     CODEOWNERS loaded')

    orchestrator = ExtractorOrchestrator(
        project_path,
        project_name=project_name,
        source_base=cfg.source_base,
        render_base=cfg.render_base,
        redirects=redirects or None,
        exclude_patterns=exclude or None,
        known_external_prefixes=cfg.known_external_prefixes or None,
        diataxis_prefixes=cfg.diataxis_prefixes or None,
        codeowners=co,
    )
    orchestrator.extract(verbose=verbose)
    orchestrator.save(output, cytoscape_path=cytoscape, verbose=verbose)

    analysis = orchestrator.builder.analyze()
    _print_summary(analysis)

    if orchestrator.errors:
        click.echo(f'\nWarnings: {len(orchestrator.errors)} file(s) failed to parse.')
        if verbose:
            for fp, msg in orchestrator.errors:
                click.echo(f'  {fp}: {msg}')

    click.echo(f'\nGraph written to: {output}')
    if cytoscape:
        click.echo(f'Cytoscape data written to: {cytoscape}')


# ---------------------------------------------------------------------------
# visualize
# ---------------------------------------------------------------------------

@cli.command()
@click.argument('graph_json', type=click.Path(exists=True, dir_okay=False, resolve_path=True))
@click.option('--port', '-p', default=5000, show_default=True, help='HTTP port.')
@click.option('--host', default='127.0.0.1', show_default=True, help='Bind host.')
def visualize(graph_json: str, port: int, host: str) -> None:
    """Start an interactive visualization server for GRAPH_JSON."""
    from .web.app import create_app  # lazy import to keep startup fast

    app = create_app(graph_json)
    click.echo(f'Visualization server: http://{host}:{port}')
    click.echo('Press Ctrl+C to stop.')
    app.run(host=host, port=port, debug=False)


# ---------------------------------------------------------------------------
# analyze
# ---------------------------------------------------------------------------

@cli.command()
@click.argument('graph_json', type=click.Path(exists=True, dir_okay=False))
def analyze(graph_json: str) -> None:
    """Print statistics about a saved GRAPH_JSON file."""
    with open(graph_json, encoding='utf-8') as f:
        data = json.load(f)

    nodes = data.get('nodes', [])
    edges = data.get('edges', [])

    node_types: dict[str, int] = {}
    for n in nodes:
        t = n.get('node_type', 'unknown')
        node_types[t] = node_types.get(t, 0) + 1

    edge_types: dict[str, int] = {}
    for e in edges:
        t = e.get('edge_type', 'unknown')
        edge_types[t] = edge_types.get(t, 0) + 1

    click.echo(f'Graph: {graph_json}')
    click.echo(f'\nNodes  ({len(nodes)} total):')
    for t, count in sorted(node_types.items()):
        click.echo(f'  {t:20s} {count:>6}')
    click.echo(f'\nEdges  ({len(edges)} total):')
    for t, count in sorted(edge_types.items()):
        click.echo(f'  {t:20s} {count:>6}')


# ---------------------------------------------------------------------------
# fetch-projects  (helper for projects.txt)
# ---------------------------------------------------------------------------

@cli.command('fetch-projects')
@click.argument('projects_file', type=click.Path(exists=True, dir_okay=False),
                default='projects.txt')
@click.option('--dest', '-d', default='repos', show_default=True,
              help='Directory to clone repositories into.')
@click.option('--output-dir', '-o', default='graphs', show_default=True,
              help='Directory to write graph JSON files into.')
@click.option('--verbose', '-v', is_flag=True)
def fetch_projects(projects_file: str, dest: str, output_dir: str, verbose: bool) -> None:
    """Clone each GitHub repo in PROJECTS_FILE and extract its link graph.

    Requires git to be available on PATH.
    """
    import subprocess

    dest_dir = Path(dest)
    out_dir = Path(output_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    urls = [
        line.strip()
        for line in Path(projects_file).read_text().splitlines()
        if line.strip() and not line.startswith('#')
    ]

    click.echo(f'Processing {len(urls)} project(s) from {projects_file}')

    for url in urls:
        repo_name = url.rstrip('/').rsplit('/', 1)[-1]
        repo_dir = dest_dir / repo_name
        graph_file = out_dir / f'{repo_name}.json'
        cy_file = out_dir / f'{repo_name}-cytoscape.json'

        if not repo_dir.exists():
            click.echo(f'\nCloning {url} → {repo_dir}')
            result = subprocess.run(
                ['git', 'clone', '--depth', '1', url, str(repo_dir)],
                capture_output=not verbose,
            )
            if result.returncode != 0:
                click.echo(f'  ERROR: git clone failed for {url}', err=True)
                continue
        else:
            click.echo(f'\nUsing existing clone: {repo_dir}')

        # Find docs directory
        docs_dir = _find_docs_dir(repo_dir)
        click.echo(f'  Extracting from: {docs_dir}')

        # Derive a sensible default source_base from the GitHub clone URL,
        # rooted at the docs directory relative to the repo.
        source_base = None
        if url.startswith('https://github.com/'):
            base = url.rstrip('/')
            if base.endswith('.git'):
                base = base[:-4]
            try:
                docs_rel = docs_dir.resolve().relative_to(repo_dir.resolve()).as_posix()
            except ValueError:
                docs_rel = ''
            suffix = ('/' + docs_rel.rstrip('/') + '/') if docs_rel else '/'
            source_base = f'{base}/blob/main{suffix}'

        orchestrator = ExtractorOrchestrator(
            str(docs_dir),
            project_name=repo_name,
            source_base=source_base,
        )
        orchestrator.extract(verbose=verbose)
        orchestrator.save(str(graph_file), cytoscape_path=str(cy_file), verbose=verbose)

        analysis = orchestrator.builder.analyze()
        _print_summary(analysis, indent='  ')
        click.echo(f'  Graph → {graph_file}')


def _find_docs_dir(repo_root: Path) -> Path:
    """Return the documentation root inside a repo."""
    for candidate in ('docs', 'doc', '.'):
        d = repo_root / candidate
        if d.is_dir() and list(d.glob('**/*.md')) + list(d.glob('**/*.rst')):
            return d
    return repo_root


def _print_summary(analysis: dict, indent: str = '') -> None:
    ntc = analysis.get('node_type_counts', {})
    click.echo(
        f'{indent}Nodes: {analysis["total_nodes"]} '
        f'({ntc.get("document", 0)} docs, '
        f'{ntc.get("external", 0)} external, '
        f'{ntc.get("label", 0)} labels)'
    )
    click.echo(f'{indent}Edges: {analysis["total_edges"]}')
    click.echo(f'{indent}Isolated nodes: {analysis["isolated_count"]}')
    click.echo(f'{indent}Weakly-connected components: {analysis["weakly_connected_components"]}')


# ---------------------------------------------------------------------------
# merge
# ---------------------------------------------------------------------------

@cli.command()
@click.argument('graph_files', nargs=-1, required=True,
                type=click.Path(exists=True, dir_okay=False))
@click.option('--output', '-o', required=True,
              help='Output merged graph JSON file.')
@click.option('--cytoscape', '-c', default=None,
              help='Also write a Cytoscape.js elements JSON file.')
def merge(graph_files: tuple[str, ...], output: str, cytoscape: str | None) -> None:
    """Merge multiple per-project GRAPH_FILES into a single combined graph.

    Non-external node IDs are namespaced by project (derived from the filename
    if no 'project' field is already set on the node) to avoid ID collisions.
    External URLs are shared across projects.
    """
    all_nodes: dict[str, dict] = {}  # final id -> node dict
    all_edges: list[dict] = []

    for gf in graph_files:
        project = Path(gf).stem  # e.g. "landscape-documentation"
        with open(gf, encoding='utf-8') as f:
            data = json.load(f)

        nodes: list[dict] = data.get('nodes', [])
        edges: list[dict] = data.get('edges', [])

        id_remap: dict[str, str] = {}
        for node in nodes:
            orig_id: str = node['id']
            node_type: str = node.get('node_type', '')
            node_project: str = node.get('project') or project

            if node_type == 'external':
                # External URLs are shared — keep original ID, no project tag
                new_id = orig_id
                if new_id not in all_nodes:
                    all_nodes[new_id] = dict(node)
            else:
                # Namespace by project to avoid collisions
                new_id = f'{project}/{orig_id}'
                new_node = dict(node)
                new_node['id'] = new_id
                new_node['project'] = node_project
                if new_node.get('path'):
                    new_node['path'] = f'{project}/{new_node["path"]}'
                all_nodes[new_id] = new_node

            id_remap[orig_id] = new_id

        for edge in edges:
            src = id_remap.get(edge['source'], edge['source'])
            tgt = id_remap.get(edge['target'], edge['target'])
            if src == tgt:
                continue
            new_edge = dict(edge)
            new_edge['source'] = src
            new_edge['target'] = tgt
            all_edges.append(new_edge)

    from .graph.models import Edge, Node
    from .export import export_graph_json, export_cytoscape_json

    node_objs = [Node.from_dict(n) for n in all_nodes.values()]
    edge_objs = [Edge.from_dict(e) for e in all_edges]

    Path(output).parent.mkdir(parents=True, exist_ok=True)
    with open(output, 'w', encoding='utf-8') as f:
        json.dump(export_graph_json(node_objs, edge_objs), f, indent=2)
    click.echo(f'Merged graph ({len(node_objs)} nodes, {len(edge_objs)} edges) → {output}')

    if cytoscape:
        Path(cytoscape).parent.mkdir(parents=True, exist_ok=True)
        with open(cytoscape, 'w', encoding='utf-8') as f:
            json.dump(export_cytoscape_json(node_objs, edge_objs), f, indent=2)
        click.echo(f'Cytoscape data → {cytoscape}')


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

@cli.command()
@click.argument('graph_json', type=click.Path(exists=True, dir_okay=False, resolve_path=True))
@click.option('--output', '-o', default='-',
              help="Output path (default '-' = stdout).")
@click.option('--format', '-f', 'fmt', default='markdown', show_default=True,
              type=click.Choice(['markdown', 'json', 'text', 'csv']),
              help='Output format.')
@click.option('--limit', default=25, show_default=True, type=int,
              help='Max rows to show per section.')
def report(graph_json: str, output: str, fmt: str, limit: int) -> None:
    """Print a structured report of a graph: hubs, orphans, broken refs, etc.

    The report is the main workflow tool — feed it into a PR comment, file
    findings as issues, or pipe through grep/jq.
    """
    from .report import write_report
    text = write_report(graph_json, None if output == '-' else output,
                        fmt=fmt, limit=limit)
    if output == '-':
        click.echo(text, nl=False)
    else:
        click.echo(f'Report → {output}')


# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------

@cli.command()
@click.argument('base_graph', type=click.Path(exists=True, dir_okay=False, resolve_path=True))
@click.argument('head_graph', type=click.Path(exists=True, dir_okay=False, resolve_path=True))
@click.option('--output', '-o', default='-', help="Output path (default '-' = stdout).")
@click.option('--format', '-f', 'fmt', default='markdown', show_default=True,
              type=click.Choice(['markdown', 'json', 'text']),
              help='Output format.')
@click.option('--fail-on-regression/--no-fail-on-regression', default=True,
              show_default=True,
              help='Exit with code 1 if BASE → HEAD adds orphans, dead ends, '
                   'or broken refs. Suitable for CI gating.')
def diff(base_graph: str, head_graph: str, output: str, fmt: str,
         fail_on_regression: bool) -> None:
    """Compare BASE_GRAPH against HEAD_GRAPH and report regressions.

    Typical CI flow: extract on the PR base ref, extract on the head, then run
    `docu-galaxy-linker diff base.json head.json -o diff.md` and post the
    markdown as a PR comment.
    """
    from .diff import write_diff
    text, regressions = write_diff(
        base_graph, head_graph,
        None if output == '-' else output,
        fmt=fmt,
    )
    if output == '-':
        click.echo(text, nl=False)
    else:
        click.echo(f'Diff → {output}  (regressions: {regressions})')
    if fail_on_regression and regressions > 0:
        sys.exit(1)


# ---------------------------------------------------------------------------
# check-external
# ---------------------------------------------------------------------------

@cli.command('check-external')
@click.argument('graph_json', type=click.Path(exists=True, dir_okay=False, resolve_path=True))
@click.option('--cache', default=None,
              help='Cache file (default: <graph>.external-cache.json next to the graph).')
@click.option('--timeout', default=5.0, show_default=True, type=float,
              help='Per-request timeout in seconds.')
@click.option('--parallelism', default=8, show_default=True, type=int,
              help='Number of concurrent requests.')
@click.option('--ttl-days', default=7, show_default=True, type=int,
              help='Reuse cached results younger than this.')
@click.option('--output', '-o', default='-', help="Output path (default '-' = stdout).")
@click.option('--format', '-f', 'fmt', default='markdown', show_default=True,
              type=click.Choice(['markdown', 'json', 'text']),
              help='Output format.')
def check_external(graph_json: str, cache: str | None, timeout: float,
                   parallelism: int, ttl_days: int, output: str, fmt: str) -> None:
    """Check the health of every external URL in GRAPH_JSON.

    Issues HEAD (fallback GET) requests with bounded concurrency, caches
    results, and prints a categorised report (ok / redirect / broken /
    timeout / error).
    """
    from .link_check import check_graph, render_markdown, render_text, render_json
    if cache is None:
        cache = str(Path(graph_json).with_suffix('.external-cache.json'))

    def _progress(done: int, total: int, url: str, cls: str) -> None:
        marker = {'ok': '✓', 'redirect': '↪', 'broken': '✗',
                  'timeout': '⏱', 'error': '!', 'skipped': '·'}.get(cls, '?')
        click.echo(f'  [{done:>4}/{total}] {marker} {cls:<8} {url[:80]}', err=True)

    click.echo(f'Checking external URLs (timeout={timeout}s, parallelism={parallelism})…',
               err=True)
    results = check_graph(graph_json, cache_path=cache, timeout=timeout,
                          parallelism=parallelism, cache_ttl_days=ttl_days,
                          progress=_progress)

    renderers = {'markdown': render_markdown, 'json': render_json, 'text': render_text}
    text = renderers[fmt](results)
    if output == '-':
        click.echo(text, nl=False)
    else:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(text, encoding='utf-8')
        click.echo(f'Report → {output}', err=True)


# ---------------------------------------------------------------------------
# bundle
# ---------------------------------------------------------------------------

@cli.command()
@click.argument('graph_json', type=click.Path(exists=True, dir_okay=False, resolve_path=True))
@click.option('--output', '-o', required=True,
              help='Output HTML file (self-contained, opens via file://).')
@click.option('--title', default=None, help='Page title (defaults to graph filename).')
def bundle(graph_json: str, output: str, title: str | None) -> None:
    """Emit a single self-contained HTML viewer for GRAPH_JSON.

    The result inlines Cytoscape.js, the fcose layout, the visualization
    script, and the graph data — no server or network access needed.
    """
    from .bundle import bundle_html
    bundle_html(graph_json, output, title=title)
    click.echo(f'Standalone viewer → {output}')


if __name__ == '__main__':
    cli()
