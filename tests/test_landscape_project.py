"""
Integration test: run the full extraction pipeline against each project
listed in projects.txt, using locally cloned copies if present.

Run with:
    pytest tests/test_landscape_project.py -v

If the repos have not been cloned yet, run first:
    docu-galaxy-linker fetch-projects projects.txt --dest repos
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.orchestrator import ExtractorOrchestrator

REPO_DIR = Path(__file__).parent.parent / 'repos'
PROJECTS_FILE = Path(__file__).parent.parent / 'projects.txt'


def _available_projects() -> list[tuple[str, Path]]:
    """Return (name, path) for any cloned repos that exist locally."""
    if not PROJECTS_FILE.exists():
        return []
    projects = []
    for line in PROJECTS_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        name = line.rstrip('/').rsplit('/', 1)[-1]
        repo_path = REPO_DIR / name
        if repo_path.exists():
            projects.append((name, repo_path))
    return projects


AVAILABLE = _available_projects()


@pytest.mark.skipif(not AVAILABLE, reason='No cloned repos found under repos/. '
                    'Run: docu-galaxy-linker fetch-projects projects.txt')
@pytest.mark.parametrize('name,repo_path', AVAILABLE)
def test_extraction_runs_without_errors(name: str, repo_path: Path, tmp_path: Path):
    """Full extraction should complete and produce a non-empty graph."""
    # Find docs directory
    docs_dir = _find_docs_dir(repo_path)
    orchestrator = ExtractorOrchestrator(str(docs_dir))
    orchestrator.extract(verbose=False)

    nodes = orchestrator.builder.get_nodes()
    edges = orchestrator.builder.get_edges()
    analysis = orchestrator.builder.analyze()

    assert len(nodes) > 0, f'{name}: no nodes extracted'
    assert len(edges) > 0, f'{name}: no edges extracted'
    assert analysis['document_nodes'] if 'document_nodes' in analysis else analysis['node_type_counts'].get('document', 0) > 0

    # Save and verify output
    out = tmp_path / f'{name}.json'
    orchestrator.save(str(out))
    assert out.exists()
    assert out.stat().st_size > 0

    print(f'\n{name}:')
    print(f'  Nodes: {analysis["total_nodes"]}')
    print(f'  Edges: {analysis["total_edges"]}')
    print(f'  Parse errors: {len(orchestrator.errors)}')


@pytest.mark.skipif(not AVAILABLE, reason='No cloned repos found under repos/.')
@pytest.mark.parametrize('name,repo_path', AVAILABLE)
def test_no_critical_parse_errors(name: str, repo_path: Path):
    """Parse errors should be below 5% of total files."""
    docs_dir = _find_docs_dir(repo_path)
    orchestrator = ExtractorOrchestrator(str(docs_dir))
    orchestrator.extract()

    total_files = len(orchestrator.discover_files())
    error_count = len(orchestrator.errors)

    if total_files > 0:
        error_rate = error_count / total_files
        assert error_rate < 0.05, (
            f'{name}: {error_rate:.1%} parse error rate '
            f'({error_count}/{total_files} files failed)'
        )


def _find_docs_dir(repo_root: Path) -> Path:
    for candidate in ('docs', 'doc', '.'):
        d = repo_root / candidate
        if d.is_dir() and (list(d.glob('**/*.md')) + list(d.glob('**/*.rst'))):
            return d
    return repo_root
