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


# ---------------------------------------------------------------------------
# ASPOSE-URL-FRONTMATTER-COLLISION-REMEDIATION Part 2, TC-ALIAS-003 (REQ-ALIAS-003)
#
# Root cause this closes: `aliases:` is a legitimate Hugo feature — it is
# added deliberately (confirmed via git history on a real slug-rename sprint,
# commit 3af9e1ee8b, "rename concatenated-slug docs pages + aliases") to
# preserve an old URL after a page is renamed, so existing inbound
# links/bookmarks/search-engine listings keep working. The defect is not the
# field's existence — it is that `hugo-translator` had no explicit rule for
# `aliases` in any site profile, so every unlisted frontmatter key survives
# untouched into every translated locale file by default (confirmed by
# directly tracing `text_unit_extractor.py`'s `_get_translatable_frontmatter_
# fields()`/`_get_protected_frontmatter_fields()`, which build their sets
# purely from explicit config rules once any rules exist, and
# `markdown_reconstructor.py::reconstruct_frontmatter()`, which starts its
# output as `deepcopy(original)` and only mutates fields with a matching
# rule). A translated copy of a renamed page never existed at the pre-rename
# URL in the first place (confirmed: no non-English file was ever created at
# an old, pre-renamed slug for the sampled pages), so the alias value that
# lands on non-English copies is not a real historical fact about that
# locale — it is pure translator-passthrough contamination of the English
# value, and every locale copy declaring the identical, English-unprefixed
# alias path is exactly the same `Duplicate target paths` collision `url:`
# caused.
#
# This check is therefore asymmetric by design, unlike `verify_no_explicit_
# url` (which bans the field everywhere): `aliases:` on the English/default-
# language copy of a page is legitimate and must PASS; the identical field
# on any non-English copy is never legitimate and must FAIL.
# ---------------------------------------------------------------------------

_EXPLICIT_ALIASES_KEY_PATTERN = re.compile(r"^aliases:\s*(.*)$")

# Directory-per-language sites (docs/kb/products/reference): the language is
# the path segment immediately after the site's content root, e.g.
# content/docs.aspose.org/de/cells/java/... -> "de".
_SITE_LANG_DIR_PATTERN = re.compile(
    r"content[\\/](?:docs|kb|products|reference)\.aspose\.org[\\/]([a-z]{2})[\\/]"
)

# blog.aspose.org (and www.aspose.org) use a flat filename-suffix convention
# instead of a per-language directory: index.md is English, index.de.md is
# German, etc. — see docs/reference/hugo-rendering.md §13.
_BLOG_LOCALE_SUFFIX_PATTERN = re.compile(r"\.([a-z]{2})\.md$")


def _infer_language(filepath) -> str:
    """Infer the locale code for a content file. Defaults to "en" for the
    English/default-language copy or when no locale marker is found (fail
    open toward *not* flagging — this check's job is to catch known-bad
    non-English aliases:, not to guess at an unfamiliar path shape)."""
    path_str = str(filepath).replace("\\", "/")
    match = _SITE_LANG_DIR_PATTERN.search(path_str)
    if match:
        return match.group(1)
    match = _BLOG_LOCALE_SUFFIX_PATTERN.search(Path(filepath).name)
    if match:
        return match.group(1)
    return "en"


def verify_no_non_english_aliases(filepath) -> list:
    """Check a content file for an explicit top-level aliases: frontmatter
    key on a non-English locale copy.

    Returns a list of Finding objects (FAIL level — this is a hard gate).
    The English/default-language copy of a page is exempt: `aliases:` is a
    legitimate redirect-preservation mechanism there.
    """
    if _infer_language(filepath) == "en":
        return []

    try:
        text = filepath.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    findings = []
    for line_no, line in _frontmatter_lines(text):
        match = _EXPLICIT_ALIASES_KEY_PATTERN.match(line)
        if match:
            findings.append(Finding(
                "FAIL", filepath, line_no,
                f"aliases: frontmatter key found on a non-English page: {line.strip()!r}",
                "Remove the aliases: key from this locale copy — it was "
                "inherited verbatim from the English source via translator "
                "passthrough and does not reflect a real historical URL for "
                "this locale (translated pages are generated fresh under "
                "the current slug, never existed at a pre-rename path). "
                "Every locale copy sharing the identical, English-unprefixed "
                "alias collapses onto the same output URL. The English "
                "copy's aliases: field is legitimate and must not be "
                "touched. See docs/reference/hugo-rendering.md §9.",
            ))
    return findings
