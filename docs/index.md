# DocuGalaxy documentation

DocuGalaxy is a documentation link analyser. It walks a docs project, builds a
graph of every internal and external reference, identifies common structural
problems (broken references, orphan pages, dead ends, low reachability), and
serves an interactive map that you can use to investigate findings or share
with collaborators.

DocuGalaxy is intended for engineering teams that maintain documentation
alongside code. It supports two main audiences: engineers who want fast
feedback on link health as part of pull request review, and documentation
specialists who want a higher-level view of structure and discoverability.

This documentation set is itself organised using the Diataxis framework. You
can run `docu-galaxy-linker` against it as a worked example.

## Tutorial

Start here if you are new to DocuGalaxy.

- [Your first link graph](tutorial.md)

## How-to guides

Task-oriented guides for common operations.

- [How to interpret the findings report](how-to/interpret-findings.md)

## Reference

Look-up material for every command, flag, and finding type.

- [Findings glossary](reference/findings-glossary.md)
- [CLI reference](reference/cli.md)

## Explanation

Background information on the model behind the tool.

- [Diataxis and this tool](explanation/diataxis-and-this-tool.md)

## Project links

- The repository [README](../README.md) covers installation, CI integration,
  and the internal architecture.
- The interactive visualisation is launched with
  `docu-galaxy-linker visualize <graph>.json`.
- A self-contained HTML viewer can be produced with
  `docu-galaxy-linker bundle <graph>.json -o map.html`.
