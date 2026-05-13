"""
Extraction orchestrator.

Discovers documentation files in a project, parses them, builds the graph,
and saves outputs.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .export import export_cytoscape_json, export_graph_json
from .graph.builder import GraphBuilder
from .parsers.markdown_parser import parse_markdown_file
from .parsers.rst_parser import parse_rst_file


class ExtractorOrchestrator:
    def __init__(self, project_path: str, project_name: Optional[str] = None) -> None:
        self.project_path = Path(project_path).resolve()
        self.builder = GraphBuilder(str(self.project_path), project_name=project_name)
        self._errors: list[tuple[str, str]] = []  # (filepath, error_message)

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover_files(self) -> list[Path]:
        files: list[Path] = []
        for pattern in ('**/*.md', '**/*.rst'):
            files.extend(self.project_path.glob(pattern))
        return sorted(files)

    # ------------------------------------------------------------------
    # Extraction
    # ------------------------------------------------------------------

    def extract(self, verbose: bool = False) -> 'ExtractorOrchestrator':
        files = self.discover_files()
        if verbose:
            print(f'Found {len(files)} documentation files in {self.project_path}')

        for filepath in files:
            rel = filepath.relative_to(self.project_path)
            if verbose:
                print(f'  Parsing: {rel}')

            try:
                if filepath.suffix == '.md':
                    links = parse_markdown_file(str(filepath))
                elif filepath.suffix == '.rst':
                    links = parse_rst_file(str(filepath))
                else:
                    continue
                self.builder.add_parsed_links(links, str(filepath))
            except Exception as exc:  # noqa: BLE001
                msg = f'{type(exc).__name__}: {exc}'
                self._errors.append((str(rel), msg))
                if verbose:
                    print(f'  WARNING: {rel}: {msg}')

        return self

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
