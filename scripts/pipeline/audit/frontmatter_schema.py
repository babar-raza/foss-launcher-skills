"""frontmatter_schema.py — ASPOSE-URL-FRONTMATTER-COLLISION-REMEDIATION, TC-URL-005 (REQ-URL-003).

Regression gate: FAILs any content page that carries an explicit top-level
`url:` frontmatter key.

Root cause this closes: Hugo derives a page's permalink automatically from
its file path plus the site's per-language `contentDir` configuration, and
that derivation already produces the correct, correctly locale-prefixed URL
for every language (`defaultContentLanguageInSubdir = false` puts English at
the bare path; every other language is auto-prefixed with its language
code). An explicit `url:` in frontmatter overrides that derivation entirely.
Because content generation (both the "agent-executed" S-56/S-57 skill path
and the separate ACT `shadow_content_generator.py` pipeline) had, at
different points and for different reasons, been writing an explicit `url:`
whose value merely duplicated what Hugo would already compute, and because
`hugo-translator` copies frontmatter fields verbatim into every locale file,
every language's copy of an affected page ended up declaring the *same*
`url:` value — causing Hugo to collapse all of them onto one output path. A
local Hugo v0.154.5 build/rebuild against real content confirmed this
directly: Hugo's own `--printPathWarnings` flag reports
`Duplicate target paths` for exactly the affected file, and removing the
`url:` key (with no other change) fixed routing for every language with
zero regression to the page that already rendered correctly (English).

This is deliberately a hard FAIL, not a WARN or a soft grade ceiling: every
case inspected during the investigating session was either a redundant
no-op duplicate of the auto-derived permalink or active production
breakage — never a case where the override served a purpose Hugo's default
derivation could not already satisfy. See:
`docs/reference/hugo-rendering.md` §9 (the documented frontmatter contracts
for every site already omit `url:` — this check enforces that documented
contract, it does not introduce a new one).

Deliberately does NOT special-case nested/indented `url:` keys — a
directory-wide search across all checked content this session
(`grep -rnE "^\\s+url:"`) found zero nested occurrences of `url:` as a
frontmatter field anywhere; top-level-only detection was confirmed
sufficient, not a known gap.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# sibling-import guard: see links.py / maven_coordinates.py for why this is
# the correct pattern here — Python adds the sub-package dir to sys.path,
# not the pipeline root, so sibling top-level modules must be reachable via
# an explicit parent-dir insert.
_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from token_ops import Finding  # noqa: E402

# Top-level frontmatter key only (no leading whitespace) — see module
# docstring for why nested/indented occurrences are out of scope.
_EXPLICIT_URL_KEY_PATTERN = re.compile(r"^url:\s*(.*)$")

# Frontmatter is delimited by a `---` line at the very start of the file and
# a second `---` line closing it. Only scan inside that block — a markdown
# body could legitimately contain a line starting with "url:" as prose or
# inside a code fence, which must never be flagged.
_FRONTMATTER_DELIMITER = "---"


def _frontmatter_lines(text: str) -> list[tuple[int, str]]:
    """Return (line_no, line_text) pairs for lines strictly inside the
    leading YAML frontmatter block. Returns [] if the file has no
    frontmatter block (first line is not exactly '---')."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != _FRONTMATTER_DELIMITER:
        return []
    result = []
    for i, line in enumerate(lines[1:], start=2):
        if line.strip() == _FRONTMATTER_DELIMITER:
            break
        result.append((i, line))
    return result


def verify_no_explicit_url(filepath) -> list:
    """Check a content file for an explicit top-level url: frontmatter key.

    Returns a list of Finding objects (FAIL level — this is a hard gate).
    """
    try:
        text = filepath.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    findings = []
    for line_no, line in _frontmatter_lines(text):
        match = _EXPLICIT_URL_KEY_PATTERN.match(line)
        if match:
            findings.append(Finding(
                "FAIL", filepath, line_no,
                f"Explicit url: frontmatter key found: {line.strip()!r}",
                "Remove the url: key — Hugo derives the correct, "
                "correctly locale-prefixed permalink automatically from the "
                "file path. An explicit override collapses every language's "
                "copy of this page onto the same output URL. See "
                "docs/reference/hugo-rendering.md §9.",
            ))
    return findings
