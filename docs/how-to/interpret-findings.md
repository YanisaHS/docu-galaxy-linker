# How to interpret the findings report

DocuGalaxy reports a number of finding categories for each project. This
guide describes each category, indicates how to prioritise it, and suggests
the typical response. See the [findings glossary](../reference/findings-glossary.md)
for full definitions of each term.

## Broken doc references

Broken document references are nearly always actionable. A link in one page
targets a file path that does not resolve to a document in the project.
Readers see a 404 or a literal-text link in the rendered output.

To investigate broken references:

1. In the interactive viewer, press `6` to apply the **Broken refs** preset.
   Each broken target appears with a red dashed outline, with arrows
   pointing in from the pages that reference it.
2. Click a broken target. The information panel shows the list of pages
   that reference it.
3. Press `c` to copy the list as a Markdown checklist, which can be pasted
   directly into a pull request description.

The appropriate fix depends on why the reference is broken:

- **Renamed target**: if the target was renamed rather than removed, add a
  redirect in `redirects.txt` instead of updating every referring page.
- **External target misclassified as internal**: if the target lives in a
  sister documentation project (for example, `pro/something.md`), add the
  prefix to `known_external_prefixes` in `.docu-galaxy.toml`. The tool will
  then treat the link as external rather than broken.
- **Genuinely missing target**: update each referrer to point at the
  correct page, or restore the missing file.

## Broken anchors

A broken anchor is a link to a heading within a page where that heading no
longer exists. Readers arrive at the top of the target page rather than at
the section they expected.

To investigate broken anchors:

1. Apply the **Broken refs** preset and look for nodes whose identifiers
   contain a `#` fragment.
2. Click a node to see the list of referrers in the information panel.
3. Either rename the anchor in each referring link or restore the missing
   heading on the target page.

## Broken labels

Broken labels are Sphinx-specific. They occur when a `{ref}` or `:ref:`
target is used but never defined with `(label-name)=` or `.. _label-name:`.
Sphinx fails to resolve the reference, and the rendered output contains the
literal source text.

```rst
.. _my-label:           # definition
{ref}`my-label`         # resolves
{ref}`my-labl`          # broken: no matching definition
```

To fix a broken label, correct the typo in the reference or add the missing
definition on the target page.

## Orphans

An orphan is a document with no incoming internal links from any other page
in the project. The only way for a reader to reach it is by direct URL or
search.

Not every orphan is a problem. A release-notes index that is reached only
via a top-level menu is technically an orphan in the link graph and is
expected to be so. The tool flags candidates for review; the decision to
act on each one is editorial.

To review orphans:

1. Apply the **Orphans** preset (`4`).
2. For each candidate, consider whether it should be reachable from a
   parent page, whether it should appear in the sidebar or toctree, or
   whether it is stale and should be removed.

The `report` command emits an orphan count that can be tracked over time as
a trend metric.

## Dead ends

A dead end is a document with no outgoing internal links. Readers arrive at
the page with no onward navigation, and the reading session ends there.
Dead ends are a common cause of high bounce rates on documentation sites
and are easily overlooked because they do not produce build warnings.

To review dead ends:

1. Apply the **Dead ends** preset (`5`).
2. Identify pages that should belong to a learning path. Reference cards
   are common offenders.
3. Add a short **Related** or **Next steps** section at the bottom of the
   page. Two links is usually enough.

A common pattern for reference pages:

```markdown
## Related

- [How to configure X](../how-to/configure-x.md): the most common usage.
- [Why X exists](../explanation/x-design.md): the rationale.
```

## Diataxis purity

Diataxis purity is the percentage of internal links between documents in
named Diataxis sections that stay within the same section. A drop in
purity after a restructure is worth investigating.

The `report` command produces a Diataxis cross-edges table that shows the
edge counts for each direction (for example, `tutorial → reference`). When
purity drops:

1. Identify the dominant direction in the cross-edges table. A heavy
   `tutorial → reference` count, for example, suggests that the tutorial
   has drifted toward reference content.
2. In the viewer, locate the tutorial and inspect its outgoing edges in the
   **Links to** tab.
3. Where possible, inline the necessary content into the tutorial rather
   than sending the reader to a reference mid-flow.

## Reachability @ 3

Reachability @ 3 is the percentage of documents reachable from the entry
page within three link hops. It approximates how much of the documentation
is discoverable from the landing page without using search.

When reachability is low:

1. Apply the **Top hubs** preset (`3`). The largest nodes are the most
   heavily linked pages. Check whether `index.md` is among them; if it is
   not, the front page is not performing its navigation function.
2. Inspect `index.md` in the **Links to** tab. Confirm that it covers the
   four Diataxis sections at minimum.
3. Add a "Where next" or table-of-contents block to the front page.

## External link health

The `check-external` command issues HTTP requests for every external URL
in the graph and produces a Markdown report grouped by status. Run it
periodically:

```bash
docu-galaxy-linker check-external graphs/<project>.json
```

Redirects are not strictly broken, but a `301 → new URL` is worth updating
at the source so that future readers do not pay the redirect cost.

## See also

- [Findings glossary](../reference/findings-glossary.md): definitions and
  examples for each finding category.
- [CLI reference](../reference/cli.md): every command and option.
