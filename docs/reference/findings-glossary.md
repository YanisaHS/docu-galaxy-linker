# Findings glossary

This page provides the canonical definitions of every finding category and
metric reported by DocuGalaxy. The same definitions are surfaced inline in
the interactive viewer.

## Categories

Findings are grouped into three severity classes:

- **Issue**: a link is unresolved and is likely to render as an error or a
  literal-text link for end users.
- **Warning**: a structural concern that may be intentional, but typically
  warrants investigation.
- **Metric**: a numerical health indicator. Track trends rather than
  absolute values.

| Term | Class |
|---|---|
| [Broken doc references](#broken-doc-references) | Issue |
| [Broken anchors](#broken-anchors) | Issue |
| [Broken labels](#broken-labels) | Issue |
| [Orphans](#orphans) | Warning |
| [Dead ends](#dead-ends) | Warning |
| [Diataxis crosses](#diataxis-crosses) | Informational |
| [Diataxis purity](#diataxis-purity) | Metric |
| [Reachability @ 3](#reachability--3) | Metric |

## Broken doc references

A link in one page targets a file path that does not resolve to a document
in the project. When a reader follows the link, they receive a 404
response. In Sphinx-rendered output, the build emits a warning and the
link is rendered as literal text. The usual cause is a rename or move
where the linker was not updated.

**Example**: a page that links to `[install guide](how-to/install.md)`
when the file is now `how-to/installation.md`.

**Detection**: every internal link target is resolved against the project
file tree, honouring the redirects in `.docu-galaxy.toml` and the
`known_external_prefixes` allowlist. Targets that do not resolve are
flagged.

**Resolution**: update the link in the source page, or add an entry to
`redirects.txt`. The interactive viewer's **Broken refs** preset (key `6`)
highlights every broken target and the pages that reference it.

## Broken anchors

A link to a heading on another page, written as `page.md#section-name`,
where the heading no longer exists on the target page. The reader scrolls
to the top of the target page rather than to the expected section.

**Example**: a link to `[](architecture.md#authentication)` when the
target page no longer has an "Authentication" heading.

**Detection**: for each parseable file, headings are extracted and
slugified using the same convention as Sphinx, MyST, and Jekyll
(lowercase the text, then replace non-alphanumeric characters with
hyphens). Anchor links to slugs that are not present on the target page
are flagged. Anchors that target files DocuGalaxy cannot parse are not
penalised.

**Resolution**: update the anchor in each referring link, or restore the
missing heading on the target page.

## Broken labels

A `{ref}` or `:ref:` cross-reference that uses a label name that was never
defined anywhere with `(label-name)=` or `.. _label-name:`. Sphinx fails to
resolve the reference at build time, and the rendered output contains the
literal source text.

**Detection**: during extraction, every label definition
(`(name)=` or `.. _name:`) is collected, as is every `{ref}` and `:ref:`
target. Any reference whose target was never defined is flagged.

**Resolution**: define the label on the intended target page, or correct
the typo in the reference.

## Orphans

A document with zero incoming internal links. No other page in the project
links to the document. The only ways for a reader to reach it are by
direct URL or through search.

Common causes:

- A page that has been forgotten and is no longer linked from anywhere.
- A page that should appear in the navigation or toctree but does not.
- A stale file left behind during a restructure.

Not every orphan is a problem. A release-notes index that is reached only
via a top-level menu is technically an orphan in the link graph and is
expected to be so. The tool flags candidates; the decision to act on each
one is editorial.

**Detection**: the in-degree of each document node is computed across the
resolved internal-link edges. Documents with an in-degree of zero, and
which are not themselves broken targets, are flagged.

## Dead ends

A document with zero outgoing internal links. Once a reader reaches the
page, there is no in-page navigation to a related page or a parent
overview. Dead ends are a common driver of bounces on documentation sites.

Common causes:

- Stub pages that were never fleshed out.
- Short reference cards that should link to a related how-to or
  explanation.
- Pages where the author has not added a "Related" or "Next steps"
  section.

**Detection**: the out-degree of each document node is computed.
Documents with an out-degree of zero, and which are not themselves broken
targets, are flagged.

**Resolution**: add a short "Related" or "Next steps" footer linking to
one or two adjacent pages.

## Diataxis crosses

An internal link where the source document and the target document belong
to different Diataxis sections (`tutorial`, `how-to`, `reference`,
`explanation`).

Some crossing is expected and healthy. A tutorial that links to a
reference page for syntax is appropriate. A high count of crosses,
especially in the `tutorial → reference` direction, suggests that the
tutorial may have drifted toward being a reference document.

**Detection**: every internal `doc_link`, `link`, and `include` edge
between two documents is classified using the Diataxis section of each
endpoint. Edges that change section, and that do not involve `meta` pages
(index, contributing, and similar), are reported.

The direction of the cross is more diagnostic than the raw count.

## Diataxis purity

Of all internal links between documents in named Diataxis sections,
excluding meta pages, the percentage that stay within their own section.

```text
purity = within-section internal edges / total internal edges between named sections
```

Higher values indicate that documents within each section are more
self-contained. A sudden drop after a restructure is worth investigating.

A purity of 100% is not a goal; it would imply that how-to guides never
link to reference content, which is unrealistic. Projects with purity
below approximately 70%, and with a heavy skew in one direction, are
likely candidates for editorial review.

## Reachability @ 3

The percentage of documents reachable from the entry page (`index.md` by
default) in three or fewer link hops, using internal edges only.

The metric approximates the proportion of documentation that a reader can
discover from the front page without resorting to search.

A low value does not necessarily mean that pages are missing. The
documents may be present in the project but only reachable through search
or external links. What the metric indicates is that the internal
navigation graph is sparse.

**Detection**: a breadth-first search from the entry document, limited to
depth three, is performed over internal edges. The number of documents
reached is divided by the total number of documents.

## See also

- [How to interpret the findings report](../how-to/interpret-findings.md):
  the recommended response to each finding category.
- [Diataxis and this tool](../explanation/diataxis-and-this-tool.md): the
  model behind the purity and reachability metrics.
