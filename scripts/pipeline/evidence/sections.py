"""sections.py — Split markdown body into heading-delimited sections.

Extracted from attach_evidence.py (Phase 5). Used to provide per-section
evidence breakdown in the `sections:` array of the evidence frontmatter block.

DISCLOSED GAP, hardened not fixed (TC-22, MT072-2026-09-23-EXAMPLE-VERIFICATION-
PRODUCTIONIZATION, root cause of ST-213): the fence toggle below is a naive
"any ``` line flips in_code" state machine with no fence-pairing validation. A
single misplaced/orphaned fence marker anywhere in the document (an odd total
count of ``` lines up to that point) flips parity for everything downstream --
every subsequent real heading is then silently absorbed into the current
section's `body_lines` instead of starting a new section, with no error, no
warning, nothing (confirmed live: this exact mechanism dropped 5 of 8 real
sections on content/docs.aspose.org/en/3d/java/developer-guide/scene-graph.md
until the underlying fence-placement bug was fixed in the content itself).
This module does not attempt to auto-recover the split when parity is
suspect -- guessing which side of a flipped toggle is "real" risks a worse,
subtler bug than doing nothing. It does now DISCLOSE the situation (a stderr
warning naming the file, line, and swallowed heading) so a future occurrence
is a visible, debuggable signal instead of a second silent data-loss defect.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)")
_CODE_FENCE_RE = re.compile(r"^```(\w*)")


def _parse_sections(filepath) -> list:
    """Split the markdown body into sections delimited by H2/H3 headings.

    Returns a list of dicts:
        [{"heading": str, "level": int, "line": int,
          "body_lines": [(line_no, text), ...],
          "code_ranges": [(start, end), ...]}, ...]

    Content before the first heading is assigned heading="Introduction", line=1.
    """
    text = filepath.read_text(encoding="utf-8")
    lines = text.splitlines()

    # Skip frontmatter
    body_start = 0
    fm_match = re.match(r"^---\s*\n.*?\n---\s*\n", text, re.DOTALL)
    if fm_match:
        body_start = text[:fm_match.end()].count("\n")

    sections = []
    current = {
        "heading": "Introduction",
        "level": 1,
        "line": 1,
        "body_lines": [],
        "code_ranges": [],
    }

    in_code = False
    code_start = 0

    for idx in range(body_start, len(lines)):
        line_no = idx + 1  # 1-based
        line = lines[idx]
        stripped = line.strip()

        # Code fence toggle
        if stripped.startswith("```"):
            if not in_code:
                in_code = True
                code_start = line_no
            else:
                current["code_ranges"].append((code_start, line_no))
                in_code = False
            current["body_lines"].append((line_no, line))
            continue

        if in_code:
            hm_in_code = _HEADING_RE.match(line)
            if hm_in_code and len(hm_in_code.group(1)) <= 3:
                print(
                    f"WARNING [evidence/sections.py]: {filepath}:{line_no}: "
                    f"heading '{hm_in_code.group(2).strip()}' seen while in_code=True "
                    f"(suspect unbalanced/misplaced code fence earlier in the file, "
                    f"currently attributed to section '{current['heading']}' starting "
                    f"line {current['line']}) -- this heading will NOT start a new "
                    f"section; verify the fence pairing around it",
                    file=sys.stderr,
                )
            current["body_lines"].append((line_no, line))
            continue

        # Heading detection (H2/H3 are section boundaries)
        hm = _HEADING_RE.match(line)
        if hm:
            level = len(hm.group(1))
            if level <= 3:
                # Flush current section
                sections.append(current)
                current = {
                    "heading": hm.group(2).strip(),
                    "level": level,
                    "line": line_no,
                    "body_lines": [],
                    "code_ranges": [],
                }
                continue

        current["body_lines"].append((line_no, line))

    # Flush last section
    sections.append(current)

    return sections
