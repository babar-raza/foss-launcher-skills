"""package_install_literal.py — Mission MT015-2026-07-30-PACKAGE-REGISTRY, TC-MT015-05.

Regression gate: analogous to maven_coordinates.py, but for the 4 registries
that don't have their own dedicated shortcode's audit gate (pypi, nuget, npm,
go_modules) -- Maven/Cargo already have maven_coordinates.py; that module is
untouched by this mission (different literal-text shape: XML dependency
blocks vs. a single CLI line, not a clean parameterization target).

Two checks, both FAIL-level (hard gate, not advisory):

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
_INSTALL_CMD_RE = re.compile(
    r"\b(pip install|dotnet add package|npm install|go get)\s+(\S+)",
    re.IGNORECASE,
)

_SHORTCODE_MARKER = "package-install"


def _load_registry_cached(registry: dict | None) -> dict:
    return registry if registry is not None else load_registry()


def verify_package_install_literals(
    filepath: Path, family: str | None, platform: str | None, *, registry: dict | None = None,
) -> list:
    """Check a content file for raw literal install-command text belonging to
    a tracked (non-Maven, non-Cargo) family/platform.

    Returns a list of Finding objects (FAIL level). Returns [] if family/platform
    can't be inferred, has no data/package_registry.json entry, or the entry's
    registry_type isn't one of the 4 this module covers.
    """
    if not family or not platform:
        return []

    data = _load_registry_cached(registry)
    entry = data.get(family, {}).get(platform)
    if not entry or entry.get("registry_type") not in _TRACKED_REGISTRY_TYPES:
        return []

    try:
        text = filepath.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    published = bool(entry.get("verification", {}).get("published"))
    findings = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if _SHORTCODE_MARKER in line:
            continue  # the shortcode call itself is not a literal-text violation
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
            continue
        match = _INSTALL_CMD_RE.search(line)
        if not match:
            continue
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
                f'({{{{< package-install "{family}" "{platform}" >}}}}, which renders the correct '
                '"not yet published" notice) or the canonical fallback text, never a specific '
                "command a generation step guessed at. See root cause 1 in the governing plan "
                "(this exact defect class already shipped once: 3D-NET-REFRESH-002).",
            ))

    return findings
