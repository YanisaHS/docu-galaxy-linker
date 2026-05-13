# docu-galaxy-linker

> NOTE: This is a test project

Map every link in a Canonical documentation project, find orphan / dead-end / broken pages, and visualise the structure interactively.

Built and tested against [`canonical/landscape-documentation`](https://github.com/canonical/landscape-documentation), but works against any Markdown / MyST / reStructuredText docs project.

---

## Running locally

Requires Python 3.11+.

```bash
# 1. Create a virtual environment and install
python3 -m venv .venv
.venv/bin/pip install -e .

# 2. Clone a docs project
git clone https://github.com/canonical/landscape-documentation repos/landscape-documentation

# 3. Extract the link graph
.venv/bin/docu-galaxy-linker extract repos/landscape-documentation \
    -o graphs/landscape-documentation.json

# 4. Open the interactive visualisation
.venv/bin/docu-galaxy-linker visualize graphs/landscape-documentation.json
# → open http://127.0.0.1:5000
```

To skip the `.venv/bin/` prefix, activate the venv first: `source .venv/bin/activate`.

---

## Other commands

```bash
# Generate a report (markdown, json, csv, or text)
docu-galaxy-linker report graphs/landscape-documentation.json -o report.md

# Diff two graphs (exits 1 if regressions are introduced — useful for CI)
docu-galaxy-linker diff base.json head.json -o diff.md

# Produce a standalone shareable HTML file (no server needed)
docu-galaxy-linker bundle graphs/landscape-documentation.json -o landscape-map.html
```

---

## Running the tests

```bash
.venv/bin/pytest -q
```
