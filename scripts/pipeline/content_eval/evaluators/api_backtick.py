"""API backtick evaluator — detects API class names in prose that lack backtick markup.

Class names from the knowledge model that appear in prose without backtick
wrapping are ambiguous and hard to verify.  This evaluator reports:

* WARN  — the class is used *both* with and without backticks on the same page
          (inconsistent markup).
* INFO  — the class is used ≥ 2 times in prose *without* any backtick usage
          (consistently un-marked).

Short pages, very short class names, and common English words are skipped.
Each class name is reported at most once per page.
"""

from __future__ import annotations

import re
from typing import Any

from ..models import Finding, Page
from . import BaseEvaluator

# Match PascalCase identifiers (optionally with a dot-separated lowercase method)
_PASCAL_RE = re.compile(
    r"\b([A-Z][A-Za-z0-9]{2,}(?:\.[a-z][A-Za-z0-9]+)?)\b"
)

# Backtick-wrapped identifier (class or method)
_BACKTICK_RE = re.compile(r"`([A-Z][A-Za-z0-9]{2,}(?:\.[a-zA-Z0-9]+)?)`")

# Common English words that happen to be PascalCase-ish — skip these
_SKIP_WORDS: frozenset[str] = frozenset({
    "The", "This", "That", "Also", "True", "False", "None",
    "For", "And", "But", "Not", "New", "Get", "Set", "All",
    "Has", "Can", "May", "Are", "Was", "Were", "Had", "Did",
    "Its", "Our", "Your", "Their", "Both", "Each", "Some",
    "Any", "Yet", "Now", "Just", "Via", "Per",
})


class ApiBacktickEvaluator(BaseEvaluator):
    """Detects API class names in prose that are not wrapped in backticks.

    Uses the knowledge model's class list as a reference.  Reports WARN for
    inconsistent usage (some backticked, some not) and INFO for consistently
    un-backticked usage.
    """

    name = "api_backtick"

    def evaluate(self, page: Page, knowledge: Any) -> list[Finding]:
        # Requires knowledge
        if not (hasattr(knowledge, "available") and knowledge.available):
            return []
        if not knowledge.classes:
            return []

        # Skip very short pages
        if len(page.prose_lines) < 5:
            return []

        known_classes: set[str] = set(knowledge.classes.keys())

        # ---------------------------------------------------------------
        # Pass 1: collect bare (non-backtick) occurrences and
        #         backtick occurrences per class across all prose lines
        # ---------------------------------------------------------------
        bare_count: dict[str, int] = {}          # class → count without backtick
        bare_first_line: dict[str, int] = {}     # class → first line_no seen bare
        backtick_classes: set[str] = set()       # classes seen WITH backtick

        # Build a set of line numbers that are inside code blocks (skip those)
        code_block_lines: set[int] = set()
        for block in page.code_blocks:
            for ln in range(block.start_line, block.end_line + 1):
                code_block_lines.add(ln)

        for line_no, line_text in page.prose_lines:
            if line_no in code_block_lines:
                continue

            # Collect backtick-wrapped class names on this line
            for m in _BACKTICK_RE.finditer(line_text):
                cls = m.group(1).split(".")[0]  # just the class part
                if cls in known_classes:
                    backtick_classes.add(cls)

            # Build a set of ranges that are inside backticks on this line
            backtick_spans: list[tuple[int, int]] = [
                (bm.start(), bm.end()) for bm in _BACKTICK_RE.finditer(line_text)
            ]

            # Collect bare (non-backtick) PascalCase matches
            for m in _PASCAL_RE.finditer(line_text):
                token = m.group(1)
                cls = token.split(".")[0]  # class part only

                if cls not in known_classes:
                    continue
                if cls in _SKIP_WORDS or len(cls) < 4:
                    continue

                # Check that this match position is not inside a backtick span
                start = m.start()
                in_backtick = any(bs <= start < be for bs, be in backtick_spans)
                if in_backtick:
                    continue

                bare_count[cls] = bare_count.get(cls, 0) + 1
                if cls not in bare_first_line:
                    bare_first_line[cls] = line_no

        # ---------------------------------------------------------------
        # Pass 2: emit findings for each flagged class
        # ---------------------------------------------------------------
        findings: list[Finding] = []

        for cls, count in bare_count.items():
            line_no = bare_first_line.get(cls, 1)
            if cls in backtick_classes:
                # Inconsistent: some with backtick, some without
                findings.append(Finding(
                    level="WARN",
                    category="AB",
                    filepath=str(page.filepath),
                    line_no=line_no,
                    message=(
                        f"`{cls}` is used both with and without backtick markup "
                        f"({count} bare occurrence(s))"
                    ),
                    suggestion=(
                        f"Wrap all occurrences of `{cls}` in backticks for consistency"
                    ),
                    evaluator=self.name,
                ))
            elif count >= 2:
                # Consistently un-backticked, appears 2+ times
                findings.append(Finding(
                    level="INFO",
                    category="AB",
                    filepath=str(page.filepath),
                    line_no=line_no,
                    message=(
                        f"{cls} used {count} time(s) in prose without backtick markup"
                    ),
                    suggestion=(
                        f"Consider wrapping `{cls}` in backticks so readers know "
                        f"it is an API identifier"
                    ),
                    evaluator=self.name,
                ))

        return findings
