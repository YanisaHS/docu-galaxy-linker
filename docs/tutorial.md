# Tutorial: your first link graph

This tutorial guides you through the process of cloning a documentation
project, extracting its link graph with DocuGalaxy, generating a report,
opening the interactive visualisation, and producing a self-contained HTML
viewer for sharing.

The example used in this tutorial is the Landscape documentation project. If
you already have another documentation project available locally, the steps
are the same and you can substitute its path.

Completing this tutorial should take approximately ten minutes.

## Prerequisites

Before starting this tutorial, you'll need:

- Python 3.11 or later
- `git` available on `PATH`
- A local checkout of this repository

Install the tool in a virtual environment:

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

For the remainder of this tutorial, the `docu-galaxy-linker` command is
assumed to be on your `PATH`.

## Fetch a documentation project

The repository ships with a `projects.txt` file that lists one or more
documentation repositories. By default it contains the Landscape
documentation. The `fetch-projects` command clones each listed repository and
extracts a link graph for it.

```bash
docu-galaxy-linker fetch-projects projects.txt --dest repos --output-dir graphs
```

This command clones `landscape-documentation` into `repos/` and writes its
link graph to `graphs/landscape-documentation.json`. The output should look
similar to the following:

```text
Cloning https://github.com/canonical/landscape-documentation
  → repos/landscape-documentation
  Extracting from: repos/landscape-documentation/docs
  Nodes: 645 (238 docs, 219 external, 155 labels)
  Edges: 760
```

## Generate a report

To produce a one-shot summary of the graph from the terminal, run the
`report` command in text format:

```bash
docu-galaxy-linker report graphs/landscape-documentation.json -f text
```

The output reports the key findings and metrics:

```text
landscape-documentation: 645 nodes, 886 edges
  Diataxis purity:   93%
  Reachability @3:   49%  (from index.md)
  Orphans:           82
  Dead ends:         68
  Broken doc refs:   31
  Broken anchors:    1
```

For definitions of these terms, see the [findings glossary](reference/findings-glossary.md).

## Open the interactive map

To explore the graph visually, start the visualisation server:

```bash
docu-galaxy-linker visualize graphs/landscape-documentation.json --port 5173
```

Open `http://127.0.0.1:5173` in a browser. The interface has three main
areas:

- A **metrics bar** along the top, showing the same values as the text
  report. Each metric can be clicked to filter the graph to the
  corresponding nodes.
- A **sidebar** on the left, containing a list of findings with brief
  descriptions and a list of preset views.
- The **graph view**, where each node represents a page, label, or
  external URL. Node size scales with degree, and node colour encodes the
  Diataxis section.

## Investigate a broken reference

To inspect broken document references, press `6` to switch to the
**Broken refs** preset. The graph filters to the broken targets and the
pages that link to them.

Click any node with a red dashed border. The information panel opens on the
right and displays the following:

- The node's Diataxis section, type, and in and out degrees
- The full path of the source file
- A link to the source file on GitHub, when a source base URL is configured
- Two tabs: **Linked from** lists every page that links to this target;
  **Links to** lists every target this page links out to

To copy the list of referring pages as a Markdown checklist that can be
pasted into a pull request description, press `c`.

## Bundle the viewer for sharing

To produce a self-contained HTML file that contains the graph data, the
visualisation code, and all dependencies, run the `bundle` command:

```bash
docu-galaxy-linker bundle graphs/landscape-documentation.json -o map.html
```

The resulting `map.html` can be opened directly in a browser, attached to a
pull request, or shared in a chat client. No server is required.

## Summary

In this tutorial, you fetched a documentation project, extracted its link
graph, generated a text report, explored the graph in the interactive map,
and produced a self-contained HTML viewer for sharing. You now have a
working understanding of the main DocuGalaxy commands and the structure of
the findings the tool produces.

From here, you have several options:

- **Act on the findings**: see [how to interpret the findings report](how-to/interpret-findings.md)
  for guidance on what to do about each finding category.
- **Look up command options**: the [CLI reference](reference/cli.md) lists
  every command and option in detail.
- **Understand the metrics**: see [Diataxis and this tool](explanation/diataxis-and-this-tool.md)
  for background on Diataxis purity and reachability.
