"""package_install_literal.py — Mission MT015-2026-07-30-PACKAGE-REGISTRY, TC-MT015-05.
Fail-on-missing-entry behavior added Mission MT018-2026-08-01-PACKAGE-IDENTITY-COVERAGE, TC-MT018-07.

Regression gate: analogous to maven_coordinates.py, but for the 4 registries
that don't have their own dedicated shortcode's audit gate (pypi, nuget, npm,
go_modules) -- Maven/Cargo already have maven_coordinates.py; that module is
untouched by this mission (different literal-text shape: XML dependency
blocks vs. a single CLI line, not a clean parameterization target).

Three checks, all FAIL-level (hard gate, not advisory):

1. Any content page for a family/platform tracked in data/package_registry.json
   under one of these 4 registry types must never contain a raw literal
   install command (pip install X / dotnet add package X / npm install X /
   go get X) as text -- that fact must be rendered exclusively by the
   package-install shortcode (TC-MT015-05), never freehand, for the same
   staleness-risk reason maven_coordinates.py exists (Mission MT008 F-01/F-08).

2. A family/platform whose entry is NOT verification.published must never
   show a *specific* install command in prose at all -- this is the
   mechanical enforcement of root cause 1 from the governing plan (a
   generation event must never guess a live command for an unconfirmed
   package). Confirmed real: this exact defect class already shipped once
   (3D-NET-REFRESH-002, a wrong NuGet command across 19 files).

3. (TC-MT018-07) A page showing an install-command-shaped pattern for a
   family/platform with NO data/package_registry.json entry at all is
   ITSELF a FAIL, not a silent pass. This closes the exact blind spot a
   full-repo audit (2026-08-01) traced as the root cause behind 14 launched
   products shipping fabricated or never-published install commands
   undetected: this gate previously had zero power to catch anything for a
   family/platform it had never been pointed at. Only safe to enable once
   every real, launched product has a registry entry (TC-MT018-06's
   backfill) -- enabling it earlier would FAIL already-correct content for
   every then-uncovered product, a false positive this mission's own
   sequencing was designed to avoid.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
_LIB_DIR = str(_HERE / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from token_ops import Finding  # noqa: E402
from package_registry_data import load_registry  # noqa: E402

_TRACKED_REGISTRY_TYPES = {"pypi", "nuget", "npm", "go_modules"}

# A literal CLI-style install command for one of the 4 tracked registries.
# Deliberately does not anchor to a specific package name -- structural match
# (does this line look like an install command at all), mirroring
# maven_coordinates.py's "any literal coordinate is banned, correct or not"
# philosophy: a hand-authored command is a staleness risk regardless of
# whether it happens to be right today.
#
# ST-054 TC-02 (2026-09-10): added Install-Package (PowerShell Package Manager
# Console syntax) and <PackageReference Include="..."> (raw .csproj XML) --
# both real, live .NET-family patterns this regex previously missed entirely,
# undercounting true .NET scope in every sweep run before this fix (confirmed:
# content/docs.aspose.org/en/cells/net/getting-started/installation.md has
# both forms, live, alongside the correct package-install shortcode call).
#
# ST-054 TC-17 (2026-09-10): the package-identifier group was `(\S+)`, which
# is unbounded at markdown-syntax boundaries -- when no whitespace follows the
# closing backtick of an inline code span (routine in locale-translated
# prose, e.g. Arabic/CJK punctuation directly abutting markup with no space),
# it swallowed the backtick plus adjacent trailing text into the "matched
# identifier". Confirmed live: content/docs.aspose.org/ar/note/python/_index.md:38
# reported as `pip install aspose-note`.PDF' instead of the real span
# `` `pip install aspose-note` ``. Bounded to stop at whitespace or a
# backtick -- NOT a double quote, since a legitimate quoted argument
# (`pip install "aspose-note[pdf]"`) starts with one; excluding quotes here
# was tried first and broke matching on exactly that real, live pattern
# (same file, line 38's second occurrence) -- caught by this fix's own new
# regression tests before landing, not assumed correct.
_INSTALL_CMD_RE = re.compile(
    r"\b(pip install|dotnet add package|npm install|go get|Install-Package)\s+([^\s`]+)"
    r"|<PackageReference\s+Include=\"[^\"]+\"",
    re.IGNORECASE,
)

_SHORTCODE_MARKER = "package-install"


def _load_registry_cached(registry: dict | None) -> dict:
    return registry if registry is not None else load_registry()


def _is_noise_line(line: str) -> bool:
    if _SHORTCODE_MARKER in line:
        return True  # the shortcode call itself is not a literal-text violation
    if re.match(r"^#{1,6}\s", line) or re.match(r"^\s*-?\s*heading:\s", line, re.IGNORECASE):
        # Confirmed real case (content/kb.aspose.org/en/words/net/troubleshooting.md):
        # "### `dotnet add package Aspose.Words` cannot find the package" is a
        # troubleshooting heading explaining the command DOESN'T work, not an
        # install instruction -- flagging it would be a false positive against
        # already-shipped, correct content. The same text is mirrored in
        # frontmatter as a `heading:` field (a TOC/FAQ-list entry), which the
        # first end-to-end test run against the real file caught -- the
        # Markdown-heading-only guard alone was not sufficient. Headings (in
        # either form) describing a command are a different genre from
        # prose/code-block asserting it as instructions.
        return True
    return False


def verify_package_install_literals(
    filepath: Path, family: str | None, platform: str | None, *, registry: dict | None = None,
) -> list:
    """Check a content file for raw literal install-command text belonging to
    a family/platform.

    Returns a list of Finding objects (FAIL level). Returns [] if family/platform
    can't be inferred, or the entry's registry_type is maven/cargo (out of
    scope -- those have their own dedicated maven_coordinates.py gate).
    A family/platform with NO registry entry at all is NOT silently skipped
    (TC-MT018-07) -- any install-command-shaped line is a FAIL, since there
    is no grounding source to trust it against.
    """
    if not family or not platform:
        return []

    data = _load_registry_cached(registry)
    entry = data.get(family, {}).get(platform)
    if entry and entry.get("registry_type") not in _TRACKED_REGISTRY_TYPES:
        return []  # maven/cargo -- out of scope, has its own dedicated gate

    try:
        text = filepath.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    findings = []

    if entry is None:
        for line_no, line in enumerate(text.splitlines(), start=1):
            if _is_noise_line(line):
                continue
            # ST-054 TC-17: iterate ALL matches on the line, not just the
            # first -- a line with two independent install-command mentions
            # (e.g. a base package plus an optional-extras variant) previously
            # produced only one Finding, silently undercounting.
            for match in _INSTALL_CMD_RE.finditer(line):
                findings.append(Finding(
                    "FAIL", filepath, line_no,
                    f"Install command found for an UNREGISTERED family/platform: {match.group(0)!r}",
                    f"{family}/{platform} has no entry in data/package_registry.json at all -- "
                    "there is no live-verified identity to ground this command against, which is "
                    "exactly the gap that let 14 launched products ship fabricated or "
                    "never-published install commands undetected (Mission "
                    "MT018-2026-08-01-PACKAGE-IDENTITY-COVERAGE). Add a registry entry first "
                    "(registry_backfill.py), then use the appropriate shortcode.",
                ))
        return findings

    published = bool(entry.get("verification", {}).get("published"))
    for line_no, line in enumerate(text.splitlines(), start=1):
        if _is_noise_line(line):
            continue
        # ST-054 TC-17: same finditer fix as the unregistered-entry branch
        # above -- a line with two install-command mentions previously
        # surfaced only the first, silently hiding the second until the
        # first was fixed and the second was promoted into view on some
        # future sweep. Confirmed live on real content, not hypothetical --
        # see the regex's own docstring note above this function.
        for match in _INSTALL_CMD_RE.finditer(line):
            if published:
                findings.append(Finding(
                    "FAIL", filepath, line_no,
                    f"Raw literal install command found: {match.group(0)!r}",
                    f'Use the package-install shortcode instead: '
                    f'{{{{< package-install "{family}" "{platform}" >}}}}. '
                    "See Mission MT015-2026-07-30-PACKAGE-REGISTRY.",
                ))
            else:
                findings.append(Finding(
                    "FAIL", filepath, line_no,
                    f"Specific install command found for an UNPUBLISHED package: {match.group(0)!r}",
                    f'{family}/{platform} is not yet confirmed published (data/package_registry.json '
                    f'verification.published=false) -- use the package-install shortcode '
                    f'({{{{< package-install "{family}" "{platform}" >}}}}, which renders a real, '
                    "actionable GitHub-source install command for this case, ST-054 TC-13) rather "
                    "than a specific command a generation step guessed at. See root cause 1 in the "
                    "governing plan (this exact defect class already shipped once: 3D-NET-REFRESH-002).",
                ))

    return findings
