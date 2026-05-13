# Diataxis and this tool

This document describes the Diataxis framework, explains how DocuGalaxy
applies it, and defines the assumptions behind the Diataxis purity and
reachability metrics.

## What Diataxis is

[Diataxis](https://diataxis.fr/) is an organising model for technical
documentation. It classifies each page into one of four kinds, defined by
the user need that the page serves.

| Kind | User need | Voice |
|---|---|---|
| Tutorial | Learning by doing | "We will..." |
| How-to | Achieving a goal | "Here is how to..." |
| Reference | Looking something up | Terse, lookup-friendly |
| Explanation | Understanding | Conversational, focused on why |

Canonical has adopted Diataxis across the majority of its documentation
projects. The Landscape documentation, for example, uses the standard
folder layout:

```text
docs/
├── tutorial.md           # single tutorial
├── how-to-guides/        # how-to section
├── reference/            # reference section
└── explanation/          # explanation section
```

DocuGalaxy classifies each document by its top-level folder, with the
exception of single-file root pages such as `tutorial.md`, which are
classified by their stem. The mapping between folder name and Diataxis
section is configurable in `.docu-galaxy.toml` for projects that use
non-standard folder names.

## Why Diataxis matters for a link graph

Diataxis is more than a folder convention. It implies expectations about
where links should go.

- A **tutorial** is a guided journey. Its outgoing links should keep the
  reader on the path. Heavy linking out to reference pages tends to break
  the guided flow.
- A **how-to** assumes the reader knows what they want. It can link
  freely to reference pages for syntax, and to explanations for
  background, provided that the link target does not block progress.
- A **reference** page is for lookup. Outgoing links to other reference
  pages are appropriate. Deep links into tutorials suggest that the
  reference is performing the wrong role.
- An **explanation** can link freely. It is a synthesising page by
  definition.

DocuGalaxy reports the count of internal links that cross Diataxis
section boundaries. The classification is not judgemental; some crossing
is healthy. The direction of the cross is generally more diagnostic than
the raw count.

## Diataxis purity

Diataxis purity is defined as:

```text
purity =  cross-document internal edges that stay in section
         ────────────────────────────────────────────────────
          all cross-document internal edges between named sections
```

Meta pages, such as `index.md`, `contributing.md`, and release notes, are
excluded from both the numerator and the denominator. They exist to
bridge sections by design.

Purity is a useful metric, not a target. A project that reports 100%
purity is suspect, since it implies that how-to guides never link to
reference content. A project below approximately 70% purity, with a
heavy skew in one direction, is generally worth investigating.

## Reachability @ 3

Reachability @ 3 is defined as:

```text
reach@3 =  documents reachable from <entry> in ≤ 3 link hops
          ─────────────────────────────────────────────────
                       total documents
```

The entry point is `index.md` by default and is configurable. The
calculation uses internal edges only, traversed by breadth-first search.

The choice of three hops is empirical. Readers rarely traverse more than
three hops from a landing page before falling back to search.
Reachability @ 3 therefore approximates how much of the documentation
surface is discoverable from the front page through the internal
navigation graph alone.

A low reachability value does not mean that pages are missing. The
documents may be present and reachable, but only through search, external
links, or paths longer than three hops. The metric reports on the
internal navigation graph, not on the existence of pages.

## How DocuGalaxy presents the metrics

- The interactive viewer displays purity and reachability in the metrics
  bar, with a colour-coded background derived from configurable
  thresholds.
- The `report` command emits both metrics in every output format.
- The `diff` command tracks the delta between two graphs. A five-point
  drop in purity introduced by a pull request, for example, is reported
  as a regression.

## Known limitations

The following limitations are worth being aware of when interpreting
DocuGalaxy output:

- **Section classification is heuristic.** A page placed in `reference/`
  but written as an explanation is still classified as a reference. The
  tool relies on path prefixes rather than content analysis.
- **Anchor matching is best-effort.** Headings are slugified using a
  common convention that matches Sphinx, MyST, and Jekyll defaults.
  Custom slug functions, such as Sphinx's `myst_heading_slug_func`, are
  not honoured. Projects that use such functions may see false positives
  in the broken-anchors report.
- **Intersphinx is not followed.** A `{doc}` or `{ref}` target that
  resolves into another Sphinx project will appear as a broken reference
  unless its prefix is added to `known_external_prefixes` in the
  configuration file.
- **External link health is a separate check.** Building the graph does
  not issue requests for external URLs. Run
  `docu-galaxy-linker check-external` to assess external link health.

## See also

- [Findings glossary](../reference/findings-glossary.md): full definitions
  of every finding category.
- [How to interpret the findings report](../how-to/interpret-findings.md):
  the recommended response to each finding category.
