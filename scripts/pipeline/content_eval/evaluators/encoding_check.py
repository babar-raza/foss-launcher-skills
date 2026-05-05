"""encoding_check -- Detect UTF-8 mojibake and control characters in content."""

from __future__ import annotations

import re
from typing import Any

from ..models import Finding, Page
from . import BaseEvaluator

_MOJIBAKE_PATTERNS: list[tuple[str, str]] = [
    ("\u00e2\u20ac\u201c", "Mojibake: em dash corrupted -- replace with '--' or U+2014"),
    ("\u00e2\u20ac\u2122", "Mojibake: right single quote corrupted -- replace with apostrophe or U+2019"),
    ("\u00e2\u20ac\u0153", "Mojibake: left double quote corrupted -- replace with '\"' or U+201C"),
    ("\u00e2\u20ac\u009d", "Mojibake: right double quote corrupted -- replace with '\"' or U+201D"),
    ("\u00e2\u20ac\u00a6", "Mojibake: ellipsis corrupted -- replace with '...' or U+2026"),
    ("\u00e2\u20ac\u02dc", "Mojibake: left single quote corrupted -- replace with apostrophe or U+2018"),
    ("\u00e2\u20ac\u201d", "Mojibake: en dash corrupted -- replace with '-' or U+2013"),
    ("\u00e2\u20ac\u00a2", "Mojibake: bullet corrupted -- replace with '*' or U+2022"),
    ("\u00c2\u00a0", "Mojibake: non-breaking space corrupted -- replace with space"),
    ("\u00c2\u00b0", "Mojibake: degree sign corrupted -- replace with 'deg' or U+00B0"),
    ("\u00c3\u00a9", "Mojibake: e-acute corrupted -- replace with 'e' or U+00E9"),
    ("\u00c3\u00a8", "Mojibake: e-grave corrupted -- replace with 'e' or U+00E8"),
]

_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_REPLACEMENT_CHAR = "\ufffd"


class EncodingCheckEvaluator(BaseEvaluator):
    """Detects UTF-8 encoding corruption (mojibake) and stray control characters."""

    name = "encoding_check"

    def evaluate(self, page: Page, knowledge: Any) -> list[Finding]:
        findings: list[Finding] = []

        for line_no, line_text in page.prose_lines:
            for pattern, description in _MOJIBAKE_PATTERNS:
                if pattern in line_text:
                    findings.append(Finding(
                        level="FAIL",
                        category="EN",
                        filepath=str(page.filepath),
                        line_no=line_no,
                        message=description,
                        suggestion="Re-encode or replace the corrupted character.",
                        evaluator=self.name,
                    ))
                    break

            if _REPLACEMENT_CHAR in line_text:
                findings.append(Finding(
                    level="FAIL",
                    category="EN",
                    filepath=str(page.filepath),
                    line_no=line_no,
                    message="Unicode replacement character (U+FFFD) found -- encoding failure",
                    suggestion="Re-save the source file with correct UTF-8 encoding.",
                    evaluator=self.name,
                ))

            m = _CONTROL_CHAR_RE.search(line_text)
            if m:
                findings.append(Finding(
                    level="WARN",
                    category="EN",
                    filepath=str(page.filepath),
                    line_no=line_no,
                    message=f"Stray control character (U+{ord(m.group()):04X}) found in content",
                    suggestion="Remove or replace the control character.",
                    evaluator=self.name,
                ))

        return findings
