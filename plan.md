# Documentation Link Extractor & Visualizer — Implementation Plan

## Executive Summary
Build a standalone tool to extract all links from any Canonical documentation project (Markdown and reStructuredText), output a graph data structure, and generate an interactive visualization using Cytoscape.js. Landscape documentation is used as a reference example.

---

## Phases & Steps

### Phase 0: Research & Analysis
- Inventory all link types in Landscape docs (Markdown, MyST, reStructuredText, Sphinx directives, external URLs, redirects)
- Document regex patterns and test cases for each link type
- Research parsing strategies (regex, AST, Sphinx APIs)
- Define graph schema (nodes, edges, metadata)

### Phase 1: Core Extraction Engine
- Set up Python project structure (modular, testable)
- Implement regex pattern library for all link types
- Build Markdown (MyST) parser
- Build reStructuredText parser
- Validate extraction on Landscape docs

### Phase 2: Graph Construction
- Define node/edge data models (document, label, external URL, etc.)
- Implement graph builder (add nodes/edges, resolve references, path resolution)
- Integrate with NetworkX for analysis

### Phase 3: Extraction Orchestrator
- Discover all .md/.rst files in a project
- Parse each file, collect links/labels
- Build graph, resolve internal references
- Analyze graph (unreachable docs, broken links, centrality)
- Save graph to JSON

### Phase 4: Export & Visualization
- Export graph to Cytoscape.js format
- Build HTML/JS template for interactive visualization (Cytoscape.js)
- Implement Flask web server to serve visualization

### Phase 5: CLI & Integration
- Build CLI (click) for extraction, export, and visualization
- Integrate with build/CI pipelines

### Phase 6: Testing & Validation
- Unit tests for parsers and graph logic
- Integration tests on Landscape docs
- Verification checklist (completeness, accuracy, performance)

### Phase 7: Documentation & Deployment
- Write README with usage, examples, and API reference
- Document installation, CLI, and web server usage
- Provide verification checklist for maintainers

---

## Key Files & References
- Reference: docs/index.md, docs/tutorial.md, docs/what-is-landscape.md, docs/conf.py, docs/redirects.txt
- Output: graph.json (nodes/edges), cytoscape.json (for visualization)
- Web: web/templates/graph-view.html, web/static/js/visualization.js
- CLI: src/cli.py
- Test: tests/test_landscape_project.py

---

## Verification
- Extraction completeness (all link types, all files)
- Graph accuracy (structure matches docs)
- Visualization renders all nodes/edges interactively
- CLI and web server work as documented
- All tests pass on Landscape docs

---

## Success Criteria
- 100% link extraction from Landscape docs
- Interactive visualization with Cytoscape.js
- CLI and web server are user-friendly and documented
- Robust to malformed links and edge cases
- Extensible to other Canonical documentation projects
