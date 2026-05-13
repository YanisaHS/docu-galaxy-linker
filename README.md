# docu-galaxy-linker

Map every link in a Canonical documentation project, find orphan / dead-end /
broken pages, and visualise the structure interactively. Designed to be a
**workflow tool** — surface findings as Markdown for PR comments, CSV for
spreadsheets, JSON for pipelines, and an interactive web view for exploration.

Built and tested against [`canonical/landscape-documentation`](
https://github.com/canonical/landscape-documentation), but works against any
Markdown / MyST / reStructuredText docs project.

---

## What it produces

From a docs repo it produces:

1. **A link graph** (`graphs/<project>.json`) — every doc, label, external URL
   and asset, plus every link between them.
2. **A structured report** — orphans, dead ends, top hubs, most-cited pages,
   broken references, Diataxis cross-edges, external-domain inventory.
   Markdown / JSON / CSV / plain text.
3. **A diff** — compare two graphs and report regressions with a CI-friendly
   exit code.
4. **An interactive visualisation** — Cytoscape.js, dark-themed, with intensity
   sizing, Diataxis colouring, impact-analysis panel, copy-as-Markdown, URL
   state, keyboard shortcuts.

---

## Installation

```bash
# From the repo root
python3 -m venv .venv
.venv/bin/pip install -e .
```

Requires Python 3.11+.

---

## Common workflows

### 1. Extract the link graph

```bash
docu-galaxy-linker extract \
    repos/landscape-documentation/docs \
    -o graphs/landscape.json \
    --project-name landscape-documentation \
    --source-base https://github.com/canonical/landscape-documentation/blob/main/docs/ \
    --render-base https://documentation.ubuntu.com/landscape/latest/
```

`--source-base` lets the report and the viz link each document straight to its
source file on GitHub. `--render-base` does the same for the published docs
site.

The shorthand for all-of-projects.txt-at-once:

```bash
docu-galaxy-linker fetch-projects projects.txt --dest repos --output-dir graphs
```

### 2. Generate a report

```bash
# Human readable
docu-galaxy-linker report graphs/landscape.json -o graphs/report.md

# Machine readable
docu-galaxy-linker report graphs/landscape.json -f json > findings.json
docu-galaxy-linker report graphs/landscape.json -f csv  > findings.csv

# Quick check
docu-galaxy-linker report graphs/landscape.json -f text
```

The Markdown report includes:
- **Top hubs** (most outgoing links) — fragile pages, careful when renaming.
- **Most-cited** — the canonical references your readers actually land on.
- **Orphans** — documents with no incoming internal link (navigation bug).
- **Dead ends** — documents that don't link onwards (bad for discoverability).
- **Broken doc references** — links pointing at paths that don't exist.
- **Broken label references** — `{ref}` / `:ref:` targets that were never
  defined.
- **Diataxis cross-edges** — e.g. `tutorial -> reference`, signalling drift.
- **Top external domains** — third-party sites your docs depend on.

Each entry links straight to the source file when `--source-base` was set.

### 3. Diff two graphs (CI gate)

```bash
docu-galaxy-linker diff \
    graphs/landscape-base.json graphs/landscape-head.json \
    -o diff.md
echo "exit: $?"
```

Exit code is **1** if the head graph introduces new orphans / dead ends /
broken refs (use `--no-fail-on-regression` to disable). The Markdown diff is
suitable to paste into a PR comment.

A minimal GitHub Actions step:

```yaml
- name: Compute base and head link graphs
  run: |
    docu-galaxy-linker extract main-docs/  -o base.json
    docu-galaxy-linker extract head-docs/  -o head.json
- name: Diff (fail PR on regression)
  run: |
    docu-galaxy-linker diff base.json head.json -o diff.md
- name: Post diff to PR
  uses: marocchino/sticky-pull-request-comment@v2
  with:
    path: diff.md
```

### 4. Explore interactively

**Local server** (re-extract first if data changed):

```bash
docu-galaxy-linker visualize graphs/landscape.json --port 5173
# open http://127.0.0.1:5173
```

**Standalone shareable HTML** (no server needed):

```bash
docu-galaxy-linker bundle graphs/landscape.json -o graphs/landscape-map.html
# double-click landscape-map.html or drop it in Slack
```

---

## Visualisation features

| Feature                            | What it gives you                                                |
|------------------------------------|-------------------------------------------------------------------|
| Intensity sizing                   | Hubs are visibly larger; orphans recede                          |
| Diataxis colouring                 | Tutorial / How-to / Reference / Explanation are immediately visible |
| Quick-view presets (`1`–`6`)       | All / Docs / Hubs / Orphans / Dead ends / Broken                 |
| Internal / External tabs           | Doc-to-doc structure vs external-link dependency map             |
| Impact analysis (info panel)       | "Linked from" vs "Links to" split for the selected node         |
| **Copy impact as Markdown** (`c`)  | Pastes a PR-ready checklist of every page that links here       |
| **Open source / render URL** (`o`) | One-click jump to the file on GitHub or the published page      |
| Search (`/`)                       | Dim-and-highlight by label / id                                  |
| Minimap                            | Overview while zoomed in                                         |
| URL state                          | `#sel=foo&preset=hubs&view=internal` — shareable views          |
| Keyboard shortcuts                 | `?` for the full list                                            |
| Broken-refs preset                 | Surfaces missing files / undefined labels                        |

---

## How an engineer uses it day-to-day

**"What breaks if I rename `reference/config/service-conf.md`?"**

```bash
# Open the viz, search "service-conf", click the node, press `c`.
# Paste the resulting Markdown checklist into your PR description.
```

**"My PR moved 12 files — did I break anything?"**

```bash
# In CI:
docu-galaxy-linker extract <main_docs>  -o base.json
docu-galaxy-linker extract <head_docs>  -o head.json
docu-galaxy-linker diff base.json head.json -o diff.md
# A non-zero exit fails the PR.
```

**"Where are the orphan pages in Landscape?"**

```bash
docu-galaxy-linker report graphs/landscape.json -f csv | grep ^orphan,
# or: open the viz, press `4`.
```

**"Is our tutorial really a tutorial?"**

The Markdown report's *Diataxis cross-edges* table shows how many links go
between sections. If your tutorial has 20 outgoing edges and 15 of them are
`tutorial -> reference`, it's probably acting as a reference doc.

**"Which third-party sites do we lean on?"**

```bash
docu-galaxy-linker report graphs/landscape.json -f markdown | sed -n '/Top external/,/^$/p'
```

---

## Architecture

```
src/
├── cli.py                          # Click entry points
├── orchestrator.py                 # discover files → parse → build graph
├── parsers/
│   ├── patterns.py                 # regex library
│   ├── markdown_parser.py          # MD + MyST
│   └── rst_parser.py               # reStructuredText
├── graph/
│   ├── models.py                   # Node, Edge
│   └── builder.py                  # graph assembly, Diataxis & broken-ref detection
├── report.py                       # findings → markdown / json / csv / text
├── diff.py                         # base ↔ head comparison
├── bundle.py                       # standalone HTML producer
├── export.py                       # graph → cytoscape.js elements
└── web/                            # Flask server + Cytoscape.js viz
    ├── app.py
    ├── templates/graph-view.html
    └── static/
        ├── js/                     # cytoscape + fcose + navigator + visualization.js
        └── css/                    # navigator css
```

The vendor JS (Cytoscape, fcose layout, navigator minimap) is checked in under
`src/web/static/js/` so the tool works **fully offline** and the standalone
bundle has no external requests.

---

## Extending

### Add a new project

```bash
echo https://github.com/canonical/<repo> >> projects.txt
docu-galaxy-linker fetch-projects projects.txt
```

The fetcher auto-derives a `--source-base` from the GitHub URL.

### Tune the Diataxis classifier

`src/graph/builder.py:_DIATAXIS_PREFIXES` maps path prefixes (e.g.
`how-to-guides`) to sections. Add any synonyms your project uses there. The
function `classify_diataxis(path)` is unit-tested in
`tests/test_diataxis_and_broken_refs.py`.

### Add a new finding type

1. Compute it in `src/report.py:build_report` and add it as a list field on
   `GraphReport`.
2. Render it in `render_markdown` / `render_csv` / `render_json`.
3. Track regressions in `src/diff.py` if it makes sense to gate CI on it.

---

## Running the tests

```bash
.venv/bin/pytest -q
```

There are unit tests for parsers, the graph builder (Diataxis, broken refs,
source URLs), report, diff, and the bundler. Integration tests against
`landscape-documentation` run automatically if you've cloned it under
`repos/`.

---

## Why the standalone HTML is safe to share

`src/bundle.py` does not modify `visualization.js`. Instead the viz contains a
tiny data-source adapter:

```js
async function loadData() {
  if (window.__DGL_DATA__) return window.__DGL_DATA__;          // standalone
  const [g, s] = await Promise.all([fetch('/api/graph'),
                                    fetch('/api/stats')]);       // server
  return { elements: await g.json(),
           stats:    s.ok ? await s.json() : null };
}
```

The bundler inlines the vendor scripts and injects
`<script>window.__DGL_DATA__ = {...}</script>` before the viz. Any change to
`visualization.js` flows through both the served and standalone versions
automatically.
