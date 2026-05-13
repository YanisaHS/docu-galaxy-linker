"""
Extraction orchestrator.

Discovers documentation files in a project, parses them, builds the graph,
and saves outputs.
"""
from __future__ import annotations

import fnmatch
import json
from pathlib import Path
from typing import Optional

from .export import export_cytoscape_json, export_graph_json
from .graph.builder import GraphBuilder
from .parsers.markdown_parser import (
    parse_markdown_file, parse_markdown_headings, parse_markdown_title,
)
from .parsers.rst_parser import (
    parse_rst_file, parse_rst_headings, parse_rst_title,
)


class ExtractorOrchestrator:
    def __init__(self, project_path: str, project_name: Optional[str] = None,
                 source_base: Optional[str] = None,
                 render_base: Optional[str] = None,
                 redirects: Optional[dict[str, str]] = None,
                 exclude_patterns: Optional[list[str]] = None,
                 known_external_prefixes: Optional[list[str]] = None,
                 diataxis_prefixes: Optional[dict[str, list[str]]] = None,
                 codeowners: Optional['CodeOwners'] = None) -> None:
        self.project_path = Path(project_path).resolve()
        self.builder = GraphBuilder(
            str(self.project_path),
            project_name=project_name,
            source_base=source_base,
            render_base=render_base,
            redirects=redirects,
            known_external_prefixes=known_external_prefixes,
            diataxis_prefixes=diataxis_prefixes,
        )
        self.exclude_patterns: list[str] = list(exclude_patterns or [])
        self.codeowners = codeowners
        self._errors: list[tuple[str, str]] = []  # (filepath, error_message)

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def _is_excluded(self, rel_path: str) -> bool:
        for pat in self.exclude_patterns:
            if fnmatch.fnmatch(rel_path, pat):
                return True
        return False

    def discover_files(self) -> list[Path]:
        files: list[Path] = []
        for pattern in ('**/*.md', '**/*.rst'):
            for f in self.project_path.glob(pattern):
                rel = f.relative_to(self.project_path).as_posix()
                if self._is_excluded(rel):
                    continue
                files.append(f)
        return sorted(files)

    # ------------------------------------------------------------------
    # Extraction
    # ------------------------------------------------------------------

    def extract(self, verbose: bool = False) -> 'ExtractorOrchestrator':
        files = self.discover_files()
        if verbose:
            print(f'Found {len(files)} documentation files in {self.project_path}')

        # Pass 1: parse links from every file.
        for filepath in files:
            rel = filepath.relative_to(self.project_path)
            if verbose:
                print(f'  Parsing: {rel}')
            try:
                if filepath.suffix == '.md':
                    links    = parse_markdown_file(str(filepath))
                    headings = parse_markdown_headings(str(filepath))
                    title    = parse_markdown_title(str(filepath))
                elif filepath.suffix == '.rst':
                    links    = parse_rst_file(str(filepath))
                    headings = parse_rst_headings(str(filepath))
                    title    = parse_rst_title(str(filepath))
                else:
                    continue
                self.builder.add_parsed_links(links, str(filepath))
                self.builder.register_headings(str(filepath), headings)
                if title:
                    self.builder.set_document_title(str(filepath), title)
            except Exception as exc:  # noqa: BLE001
                msg = f'{type(exc).__name__}: {exc}'
                self._errors.append((str(rel), msg))
                if verbose:
                    print(f'  WARNING: {rel}: {msg}')

        # Post-pass: classify undefined labels and broken anchors.
        self.builder.finalize()

        # Optional ownership annotation.
        if self.codeowners is not None:
            self._annotate_ownership()

        return self

    def _annotate_ownership(self) -> None:
        if self.codeowners is None:
            return
        for node in self.builder.get_nodes():
            if node.node_type != 'document' or not node.path:
                continue
            owners = self.codeowners.owners_for(node.path)
            if owners:
                node.metadata['owners'] = owners
                self.builder.graph.nodes[node.id]['metadata'] = node.metadata

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(
        self,
        output_path: str,
        cytoscape_path: Optional[str] = None,
        verbose: bool = False,
    ) -> None:
        nodes = self.builder.get_nodes()
        edges = self.builder.get_edges()

        graph_data = export_graph_json(nodes, edges)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(graph_data, f, indent=2)
        if verbose:
            print(f'Graph saved → {output_path}')

        if cytoscape_path:
            cy_data = export_cytoscape_json(nodes, edges)
            Path(cytoscape_path).parent.mkdir(parents=True, exist_ok=True)
            with open(cytoscape_path, 'w', encoding='utf-8') as f:
                json.dump(cy_data, f, indent=2)
            if verbose:
                print(f'Cytoscape data saved → {cytoscape_path}')

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    @property
    def errors(self) -> list[tuple[str, str]]:
        return list(self._errors)


# Backward-compat: forward declaration for type hints.
from .ownership import CodeOwners  # noqa: E402,F401
