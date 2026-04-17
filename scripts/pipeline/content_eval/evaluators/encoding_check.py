"""encoding_check -- Detect UTF-8 mojibake and control characters in content."""

from __future__ import annotations

import re
from typing import Any

from ..models import Finding, Page
from . import BaseEvaluator

# Common UTF-8 mojibake sequences that appear when content is double-encoded
# or read as Latin-1 then converted. These are the most frequent patterns.
# The sequences below are the literal Latin-1 byte-reinterpretations of UTF-8.
# E.g. em-dash U+2014 encodes as E2 80 94 in UTF-8; misread as Latin-1 gives:
#   U+00E2 (a-circumflex), U+20AC (euro sign), U+201C (left double quote)
_MOJIBAKE_PATTERNS: list[tuple[str, str]] = [
    # em-dash (U+2014) -- E2 80 94 misread as Latin-1
    ("\u00e2\u20ac\u201c", "Mojibake: em dash corrupted -- replace with '--' or U+2014"),
    # right single quote (U+2019) -- E2 80 99 misread
    ("\u00e2\u20ac\u2122", "Mojibake: right single quote corrupted -- replace with apostrophe or U+2019"),
    # left double quote (U+201C) -- E2 80 9C misread
    ("\u00e2\u20ac\u0153", "Mojibake: left double quote corrupted -- replace with '\"' or U+201C"),
    # right double quote (U+201D) -- E2 80 9D misread
    ("\u00e2\u20ac\u009d", "Mojibake: right double quote corrupted -- replace with '\"' or U+201D"),
    # ellipsis (U+2026) -- E2 80 A6 misread
    ("\u00e2\u20ac\u00a6", "Mojibake: ellipsis corrupted -- replace with '...' or U+2026"),
    # left single quote (U+2018) -- E2 80 98 misread
    ("\u00e2\u20ac\u02dc", "Mojibake: left single quote corrupted -- replace with apostrophe or U+2018"),
    # en-dash (U+2013) -- E2 80 93 misread
    ("\u00e2\u20ac\u201d", "Mojibake: en dash corrupted -- replace with '-' or U+2013"),
    # bullet (U+2022) -- E2 80 A2 misread
    ("\u00e2\u20ac\u00a2", "Mojibake: bullet corrupted -- replace with '*' or U+2022"),
    # Non-breaking space (U+00A0) misread as C2 A0 -> Â + NBSP
    ("\u00c2\u00a0", "Mojibake: non-breaking space corrupted -- replace with space"),
    # Degree sign (U+00B0) misread as C2 B0 -> Â°
    ("\u00c2\u00b0", "Mojibake: degree sign corrupted -- replace with 'deg' or U+00B0"),
    # e-acute (U+00E9) misread as C3 A9 -> Ã©
    ("\u00c3\u00a9", "Mojibake: e-acute corrupted -- replace with 'e' or U+00E9"),
    # e-grave (U+00E8) misread as C3 A8 -> Ã¨
    ("\u00c3\u00a8", "Mojibake: e-grave corrupted -- replace with 'e' or U+00E8"),
]

# Control characters that should not appear in content
# (excluding \t, \n, \r which are normal whitespace)
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Literal replacement character (U+FFFD) -- indicates encoding failure
_REPLACEMENT_CHAR = "\ufffd"


class EncodingCheckEvaluator(BaseEvaluator):
    """Detects UTF-8 encoding corruption (mojibake) and stray control characters.

    Mojibake occurs when UTF-8 content is treated as Latin-1 during processing
    and the byte sequences are reinterpreted. This evaluator scans all prose
    lines for known corruption patterns. FAIL is emitted because mojibake
    directly harms readability -- readers see garbage characters instead of
    em-dashes, smart quotes, and other typographic characters.
    """

    name = "encoding_check"

    def evaluate(self, page: Page, knowledge: Any) -> list[Finding]:
        findings: list[Finding] = []

        for line_no, line_text in page.prose_lines:
            # Check for known mojibake patterns
            for pattern, description in _MOJIBAKE_PATTERNS:
                if pattern in line_text:
                    findings.append(Finding(
                        level="FAIL",
                        category="EC",
                        filepath=str(page.filepath),
                        line_no=line_no,
                        message=description,
                        suggestion=(
                            "Re-encode or replace the corrupted character. "
                            "Use a plain ASCII equivalent or the correct Unicode character."
                        ),
                        evaluator=self.name,
                    ))
                    break  # one finding per line is enough

            # Check for Unicode replacement character
            if _REPLACEMENT_CHAR in line_text:
                findings.append(Finding(
                    level="FAIL",
                    category="EC",
                    filepath=str(page.filepath),
                    line_no=line_no,
                    message="Unicode replacement character (U+FFFD) found -- encoding failure",
                    suggestion="Re-save the source file with correct UTF-8 encoding.",
                    evaluator=self.name,
                ))

            # Check for stray control characters
            m = _CONTROL_CHAR_RE.search(line_text)
            if m:
                findings.append(Finding(
                    level="WARN",
                    category="EC",
                    filepath=str(page.filepath),
                    line_no=line_no,
                    message=f"Stray control character (U+{ord(m.group()):04X}) found in content",
                    suggestion="Remove or replace the control character.",
                    evaluator=self.name,
                ))

        return findings
