"""frontmatter_blocks.py — TC-18 (MT072-2026-09-23-EXAMPLE-VERIFICATION-
PRODUCTIONIZATION): extract fenced code blocks embedded inside YAML
frontmatter string values.

CONTRACT: scripts/pipeline/lib/example_verification/frontmatter_blocks.py
  purpose: products.aspose.org's pages have no separate markdown body at
           all -- the entire file IS one YAML frontmatter block (`---`
           at line 1, `---` again at the last line), rendered by Hugo
           "plugin"/"family" layout templates directly from frontmatter
           fields. Real ` ```lang ` fenced code examples live inside
           multi-line YAML block-scalar string values (`content: |`),
           indented 4+ spaces at the raw-file level -- code_fences.py's
           CommonMark-conformant tokenizer correctly refuses to see
           indented text as a fenced block (that's CommonMark §4.4, an
           indented code block, not a fenced one), so these examples were
           entirely invisible to example_verification_sweep.py before
           this module (disclosed as `excluded_frontmatter_embedded`,
           never silently miscounted as zero -- see that module's own
           docstring history).
  inputs:  raw file text (str) -- the WHOLE file, since there is no body
  outputs: list[CodeBlock] (from code_fences.py, the same canonical
           tokenizer every other consumer uses -- not parser #41)
  owner_domain: content-quality
  requires_test: true

Mechanism: parse the file as plain YAML (once `---` delimiters are
stripped), then walk every string value in the resulting structure
(dicts/lists/scalars) looking for one containing a ` ``` ` fence marker.
Once PyYAML has parsed a block scalar, its internal newlines and content
are a normal, un-indented Python string -- the SAME code_fences.py
tokenizer that already handles every other site's markdown body parses
these fence markers correctly, no new parser needed.

Known, disclosed limitation: line numbers on the returned CodeBlock
objects are relative to the START of the STRING VALUE they came from,
not the raw file. Getting true file-line accuracy would require a
YAML round-trip library that preserves source positions (e.g.
ruamel.yaml with mark tracking) -- out of scope for what this taskcard
needs (classification, not line-precise diagnostics). Every block is
still correctly attributed to its FILE (the sweep's own per-file
grouping), just not to an exact line within it.
"""
from __future__ import annotations

from typing import Any

import yaml

from .code_fences import CodeBlock, enumerate_code_blocks


def _strip_frontmatter_delimiters(text: str) -> str:
    """products.aspose.org pages are ONE frontmatter block for the whole
    file (`---` at line 1 and again at the last line) -- strip both so
    the remainder parses as plain YAML."""
    if not text.startswith("---"):
        return text
    body = text[3:]
    if body.endswith("\n---\n") or body.endswith("\n---"):
        last = body.rfind("\n---")
        body = body[:last]
    return body


def _walk_strings(node: Any) -> "list[str]":
    """Recursively collect every string value in a parsed YAML
    structure (dict/list/scalar), in a stable, deterministic order."""
    out: "list[str]" = []
    if isinstance(node, str):
        out.append(node)
    elif isinstance(node, dict):
        for value in node.values():
            out.extend(_walk_strings(value))
    elif isinstance(node, list):
        for item in node:
            out.extend(_walk_strings(item))
    return out


def extract_frontmatter_embedded_blocks(text: str) -> "list[CodeBlock]":
    """Parse `text` (a whole products.aspose.org page) as YAML and return
    every fenced code block found inside any string value. Returns an
    empty list (never raises) on unparseable YAML -- a malformed page is
    a content_eval/frontmatter-validation concern, not this module's."""
    yaml_text = _strip_frontmatter_delimiters(text)
    try:
        data = yaml.safe_load(yaml_text)
    except yaml.YAMLError:
        return []

    blocks: "list[CodeBlock]" = []
    for value in _walk_strings(data):
        if "```" not in value:
            continue
        blocks.extend(enumerate_code_blocks(value))
    return blocks
