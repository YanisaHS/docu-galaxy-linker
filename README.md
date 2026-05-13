# Docu Galaxy Linker

<img width="1512" height="957" alt="image" src="https://github.com/user-attachments/assets/5a1f6356-5790-4da1-949c-01353bd775e4" />


A tool for extracting, analysing, and visualising the link structure and conceptual topology of Canonical documentation projects.

Two complementary views are available:

- **Link graph** — every internal link, external URL, MyST label, anchor, and image reference extracted from `.md` and `.rst` files, rendered as an interactive Cytoscape.js graph.
- **Concept map** — a topic-level view where nodes are documentation pages coloured by [Diátaxis](https://diataxis.fr/) category, and edges represent either explicit cross-references. The concept map also surfaces **split candidates** (pages whose sections cover divergent topics) and **duplicate content** (pages with high phrase-level text overlap).

---

## Requirements

- Python 3.11+
- `git` (for `fetch-projects`)

---

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

---

## Quick start

### Single project — concept map

```bash
docu-galaxy-linker concept-map repos/landscape-documentation/docs
```

Opens an interactive concept map at `http://127.0.0.1:5001`.

### Single project — link graph

```bash
# Extract
docu-galaxy-linker extract repos/landscape-documentation/docs \
    -o graphs/landscape.json \
    -c graphs/landscape-cytoscape.json

# Visualise
docu-galaxy-linker visualize graphs/landscape.json
```

Opens the link graph at `http://127.0.0.1:5000`.

### Multiple projects

```bash
# Clone all repos listed in projects.txt and extract their graphs
docu-galaxy-linker fetch-projects projects.txt --dest repos --output-dir graphs

# Merge into a single combined graph
docu-galaxy-linker merge graphs/landscape-documentation.json \
    graphs/ubuntu-server-documentation.json \
    graphs/ubuntu-security-documentation.json \
    -o graphs/all-projects.json \
    -c graphs/all-projects-cytoscape.json

# Visualise the merged graph
docu-galaxy-linker visualize graphs/all-projects.json
```

`projects.txt` is a plain-text file with one GitHub repository URL per line (lines starting with `#` are ignored).

---

## CLI reference

### `concept-map DOCS_DIR`

Build and serve an interactive concept / topic map.

| Option | Default | Description |
|---|---|---|
| `--output`, `-o` | — | Save the concept graph JSON to a file |
| `--port`, `-p` | `5001` | HTTP port |
| `--host` | `127.0.0.1` | Bind host |
| `--similarity` | `0.12` | Cosine-similarity threshold for topic-overlap edges (0–1) |
| `--no-serve` | — | Build the graph and exit without starting a server |

### `extract PROJECT_PATH`

Parse all `.md` and `.rst` files and save a link graph.

| Option | Default | Description |
|---|---|---|
| `--output`, `-o` | `graph.json` | Output graph JSON |
| `--cytoscape`, `-c` | — | Also write a Cytoscape.js elements JSON |
| `--project-name` | — | Tag all nodes with this name (useful before merging) |
| `--verbose`, `-v` | — | Show per-file progress |

### `visualize GRAPH_JSON`

Serve the interactive link-graph visualisation.

| Option | Default | Description |
|---|---|---|
| `--port`, `-p` | `5000` | HTTP port |
| `--host` | `127.0.0.1` | Bind host |

### `fetch-projects PROJECTS_FILE`

Clone GitHub repos listed in a text file and extract each one.

| Option | Default | Description |
|---|---|---|
| `--dest`, `-d` | `repos/` | Directory to clone into |
| `--output-dir`, `-o` | `graphs/` | Directory for output JSON files |
| `--verbose`, `-v` | — | Show per-file progress |

### `merge GRAPH_FILES…`

Merge multiple per-project graphs into one. Node IDs are namespaced by project to avoid collisions; external URLs are shared.

| Option | Default | Description |
|---|---|---|
| `--output`, `-o` | *(required)* | Output merged graph JSON |
| `--cytoscape`, `-c` | — | Also write a Cytoscape.js elements JSON |

### `analyze GRAPH_JSON`

Print node and edge type statistics for a saved graph.

---

## Concept map features

### Diátaxis colouring

Pages are coloured by their [Diátaxis](https://diataxis.fr/) category, inferred from the directory structure:

| Colour | Category |
|---|---|
| 🟡 Gold | Tutorial |
| 🟢 Green | How-to guide |
| 🔵 Blue | Explanation |
| 🟣 Purple | Reference |

### Edge types

| Style | Type | Meaning |
|---|---|---|
| Solid blue arrow | Cross-reference | An explicit link written by the author |
| Dashed green | Topic overlap | Pages share significant technical vocabulary (TF-IDF cosine similarity) |
| Dashed orange | Duplicate | Pages share substantial verbatim phrasing (word trigram Jaccard ≥ 0.30) |

### Split candidates

Pages flagged with a dashed amber border have **≥ 4 substantive sections** with **≥ 1 000 words** and a high average pairwise section-vocabulary dissimilarity (≥ 0.90). This indicates the sections cover distinct topics that may each benefit from a dedicated page. Release-notes pages are excluded from this check.

Clicking a split-candidate node shows a suggested split plan: the divergent sections are listed as proposed new pages, along with guidance on titles, introductions, and cross-references.

### Duplicate detection

Clicking a node that is involved in a duplicate relationship shows:
- Which pages are near-identical (⚠, hard duplicate via Jaccard) or substantially overlapping (~, flagged via overlap coefficient)
- The percentage of text overlap for each pair
- A contextual recommendation: merge + redirect for near-identical pages, or scope differentiation / shared snippet extraction for partial overlaps

---

## Project structure

```
src/
  cli.py               CLI entry point (click)
  orchestrator.py      File discovery and extraction pipeline
  export.py            Cytoscape.js export
  concepts/
    extractor.py       DocPage extraction (titles, headings, terms, shingles)
    builder.py         Concept graph builder (TF-IDF, duplicates, split detection)
  graph/
    builder.py         Link graph builder (NetworkX)
    models.py          Node / Edge data models
  parsers/
    markdown_parser.py MyST / Markdown link parser
    rst_parser.py      reStructuredText link parser
    patterns.py        Regex pattern library
  web/
    app.py             Flask application (link graph + concept map)
    templates/         Jinja2 HTML templates
    static/js/         Cytoscape.js + visualisation logic
graphs/                Generated graph JSON files
repos/                 Cloned documentation repositories
```

---

## Running the tests

```bash
pip install pytest
pytest
```
