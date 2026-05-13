# CLI reference

This page documents every `docu-galaxy-linker` command and its options.
The same information is available in the terminal by running any command
with the `--help` flag.

## Command summary

```text
$ docu-galaxy-linker --help

Commands:
  analyze         Print statistics about a saved GRAPH_JSON file.
  bundle          Emit a single self-contained HTML viewer for GRAPH_JSON.
  check-external  Check the health of every external URL in GRAPH_JSON.
  diff            Compare BASE_GRAPH against HEAD_GRAPH and report
                  regressions.
  extract         Extract all links from PROJECT_PATH and save a graph JSON.
  fetch-projects  Clone each GitHub repo in PROJECTS_FILE and extract its
                  link graph.
  merge           Merge multiple per-project GRAPH_FILES into a single
                  combined graph.
  report          Print a structured report of a graph.
  visualize       Start an interactive visualization server for GRAPH_JSON.
```

## `extract`

Walks a documentation project, parses every Markdown, MyST, and
reStructuredText file, builds the link graph, and writes the result to a
JSON file.

```bash
docu-galaxy-linker extract <project_path> [options]
```

| Flag | Description |
|---|---|
| `-o, --output PATH` | Output graph JSON. Default: `graph.json`. |
| `-c, --cytoscape PATH` | Also write a Cytoscape.js elements file. |
| `--project-name NAME` | Tag all nodes with this project name. Used by `merge`. |
| `--source-base URL` | Base URL for source files, for example a GitHub `blob` URL. Attaches `source_url` to each document node. |
| `--render-base URL` | Base URL for the rendered documentation site. Attaches `render_url` to each document node. |
| `--config PATH` | Path to `.docu-galaxy.toml`. Auto-discovered if omitted. |
| `--no-ownership` | Skip CODEOWNERS annotation even if a `CODEOWNERS` file is present. |
| `-v, --verbose` | Emit per-file progress to standard error. |

The equivalent configuration-file fields are documented in the
[configuration file](#configuration-file) section.

## `report`

Produces a structured report from a graph JSON file.

```bash
docu-galaxy-linker report <graph_json> [options]
```

| Flag | Description |
|---|---|
| `-o, --output PATH` | Output path. Default: `-` (standard output). |
| `-f, --format FORMAT` | Output format. One of `markdown` (default), `json`, `text`, `csv`. |
| `--limit N` | Maximum rows shown per section. Default: 25. |

See the [findings glossary](findings-glossary.md) for a description of each
report section.

## `diff`

Compares two graphs and reports regressions. The expected use case is
comparing the base and head of a pull request. The command exits with
status `1` when the head introduces new orphans, dead ends, broken
references, or broken anchors, which makes it suitable for use as a
continuous integration check.

```bash
docu-galaxy-linker diff <base_graph> <head_graph> [options]
```

| Flag | Description |
|---|---|
| `-o, --output PATH` | Output path. Default: `-` (standard output). |
| `-f, --format FORMAT` | Output format. One of `markdown` (default), `json`, `text`. |
| `--fail-on-regression` | Exit `1` on regressions. This is the default. |
| `--no-fail-on-regression` | Always exit `0`. Use when only the report is required. |

## `visualize`

Starts a local HTTP server that serves the interactive Cytoscape.js view of
a graph.

```bash
docu-galaxy-linker visualize <graph_json> [options]
```

| Flag | Description |
|---|---|
| `-p, --port N` | HTTP port. Default: `5000`. |
| `--host HOST` | Bind host. Default: `127.0.0.1`. |

## `bundle`

Produces a self-contained HTML viewer in a single file. The bundle inlines
Cytoscape.js, the `fcose` layout, the navigator overlay, the visualisation
JavaScript, and the graph data. No server or network access is required to
view the result.

```bash
docu-galaxy-linker bundle <graph_json> -o map.html [--title "..."]
```

| Flag | Description |
|---|---|
| `-o, --output PATH` | Output HTML path. Required. |
| `--title TEXT` | Title shown in the page header. Defaults to the graph file name. |

## `check-external`

Issues HEAD requests (falling back to GET) for every external URL in the
graph, with bounded concurrency, and reports the result. Outcomes are
cached in a sidecar JSON file for the duration of the configured TTL so
that re-runs are fast.

```bash
docu-galaxy-linker check-external <graph_json> [options]
```

| Flag | Description |
|---|---|
| `--cache PATH` | Cache file. Default: `<graph>.external-cache.json`. |
| `--timeout SECS` | Per-request timeout in seconds. Default: `5.0`. |
| `--parallelism N` | Concurrent requests. Default: `8`. |
| `--ttl-days N` | Reuse cached results younger than this many days. Default: `7`. |
| `-o, --output PATH` | Output path. Default: `-` (standard output). |
| `-f, --format FORMAT` | Output format. One of `markdown` (default), `json`, `text`. |

## `fetch-projects`

Convenience wrapper that performs `git clone` followed by `extract` for
every URL in a `projects.txt`-style file.

```bash
docu-galaxy-linker fetch-projects <projects_file> [options]
```

| Flag | Description |
|---|---|
| `-d, --dest DIR` | Directory to clone repositories into. Default: `repos`. |
| `-o, --output-dir DIR` | Directory in which to write graph JSON files. Default: `graphs`. |
| `-v, --verbose` | Emit per-file progress to standard error. |

For GitHub URLs, the fetcher automatically derives a `--source-base` so
that each document node receives a working source link.

## `merge`

Merges multiple per-project graph files into a single combined graph.
External nodes are de-duplicated by URL, and document identifiers are
namespaced by project name to prevent collisions.

```bash
docu-galaxy-linker merge a.json b.json c.json -o merged.json [-c merged-cy.json]
```

## `analyze`

Prints a minimal set of summary counts for a graph. For most purposes,
`report` produces more useful output.

```bash
docu-galaxy-linker analyze <graph_json>
```

## Configuration file

The `extract` command auto-discovers a `.docu-galaxy.toml` (or
`docu-galaxy.toml`) file by walking up the directory tree from the project
path. Command-line flags take precedence over configuration file values.

```toml
docs_dir       = "docs"
source_base    = "https://github.com/canonical/landscape-documentation/blob/main/docs/"
render_base    = "https://documentation.ubuntu.com/landscape/latest/"
redirects_file = "redirects.txt"
sphinx_conf    = "conf.py"
codeowners     = ".github/CODEOWNERS"
ignore         = ["**/.venv/**", "reuse/**"]
known_external_prefixes = ["ubuntu/", "pro/"]

[diataxis_prefixes]
tutorial    = ["tutorial", "tutorials", "getting-started"]
how-to      = ["how-to", "how-to-guides", "guides"]
reference   = ["reference", "references"]
explanation = ["explanation", "explanations"]
```

Field descriptions:

- `docs_dir`: subdirectory of the project that contains the documentation.
- `source_base`: base URL for source files. When set, each document node
  receives a `source_url` derived from this prefix.
- `render_base`: base URL for the rendered documentation site. Used to
  populate `render_url` on each document node.
- `redirects_file`: path to a Sphinx-style redirects file, relative to
  `docs_dir`.
- `sphinx_conf`: path to a `conf.py` file. Parsed via AST; never executed.
- `codeowners`: path to a CODEOWNERS file used to annotate ownership of
  each document.
- `ignore`: glob patterns excluded from extraction.
- `known_external_prefixes`: link prefixes that should be classified as
  external rather than broken.
- `diataxis_prefixes`: mapping from Diataxis section name to the path
  prefixes that identify documents in that section.
