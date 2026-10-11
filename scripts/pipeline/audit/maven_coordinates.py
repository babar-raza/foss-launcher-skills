"""maven_coordinates.py — Mission MT008 (plans/master-plan.md) D-07 / TC-MT008-07.

Regression gate: fails any content page that contains a raw, literal Java-FOSS
Maven coordinate (com.aspose or org.aspose) as text. After the Mission MT008
migration, this fact is rendered exclusively by the `maven-coord`/`maven-gav`
Hugo shortcodes from `data/foss_packages.json` (layouts/shortcodes/) -- no
content page should ever contain the literal string again, correct or not,
since a literal string can go stale the moment the real coordinate changes
(exactly the defect class this mission exists to close; see Finding F-01/F-08).

This is deliberately defense-in-depth, not the primary defense -- the primary
defense is that the shortcode is the only thing that ever computes this fact.
This gate exists to catch the residual case where an LLM-authored sentence
mentions the coordinate outside the scaffolded section (Risk R-04).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# sibling-import guard: see links.py for why this is the correct pattern here.
_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from token_ops import Finding  # noqa: E402

# groupId:artifactId coordinate form, e.g. "org.aspose:aspose-cells-foss" or
# "com.aspose:aspose-cells-foss". Matches either groupId regardless of
# correctness -- see module docstring for why even the currently-correct
# groupId is banned as raw text.
_GAV_PATTERN = re.compile(r"\b(?:com|org)\.aspose(?:\.[\w.]+)?:aspose-[\w-]+-foss\b")

# <groupId>com.aspose</groupId> / <groupId>org.aspose</groupId> (and dotted
# variants like org.aspose.slides.foss) as a literal XML tag.
_GROUPID_TAG_PATTERN = re.compile(r"<groupId>\s*(?:com|org)\.aspose[\w.]*\s*</groupId>")


def verify_maven_coordinates(filepath) -> list:
    """Check a content file for raw literal Java-FOSS Maven coordinate text.

    Returns a list of Finding objects (FAIL level -- this is a hard gate, not
    an advisory).

    Deliberately does NOT strip frontmatter before scanning (unlike links.py's
    convention, which is correct for docs/kb/blog markdown bodies). products.aspose.org
    "plugin" layout pages embed their entire visible content INSIDE YAML
    frontmatter (`content: |` block scalars) -- there is no markdown body to
    speak of. Stripping frontmatter there would silently scan nothing and miss
    the exact defect class on the exact site the original bug report was
    about. Confirmed via a real end-to-end run against
    content/products.aspose.org/en/3d/java/_index.md during this taskcard: the
    frontmatter-stripped version produced zero findings against a file with a
    known, real `<groupId>com.aspose</groupId>` on line 62. The chosen regex
    patterns are specific enough (see module-level pattern comments) that
    scanning frontmatter too does not risk false positives on unrelated
    fields like `evidence.model_sha`.
    """
    try:
        text = filepath.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    findings = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        gav_match = _GAV_PATTERN.search(line)
        if gav_match:
            findings.append(Finding(
                "FAIL", filepath, line_no,
                f"Raw literal Maven coordinate text found: {gav_match.group(0)!r}",
                "Use the maven-gav shortcode instead (no surrounding backticks): "
                '{{< maven-gav "{family}" "java" >}}. See Mission MT008 in plans/master-plan.md.',
            ))
            continue  # avoid double-flagging the same line for both patterns
        tag_match = _GROUPID_TAG_PATTERN.search(line)
        if tag_match:
            findings.append(Finding(
                "FAIL", filepath, line_no,
                f"Raw literal <groupId> tag found: {tag_match.group(0)!r}",
                "Use the maven-coord shortcode instead: "
                '{{< maven-coord "{family}" "java" >}}. See Mission MT008 in plans/master-plan.md.',
            ))

    return findings
