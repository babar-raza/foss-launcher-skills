"""sections.py — Split markdown body into heading-delimited sections.

Extracted from attach_evidence.py (Phase 5). Used to provide per-section
evidence breakdown in the `sections:` array of the evidence frontmatter block.
"""
from __future__ import annotations

import re
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
