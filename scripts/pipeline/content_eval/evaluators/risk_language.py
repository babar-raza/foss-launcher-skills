"""Risk language evaluator — detects speculative and superlative claims."""

from __future__ import annotations

import re
from typing import Any

from ..config import RISK_LANGUAGE_PATTERNS
from ..models import Finding, Page
from . import BaseEvaluator


class RiskLanguageEvaluator(BaseEvaluator):
    """Detects unsupported superlatives, speculative phrases, and marketing language.

    Scans prose lines for patterns like 'seamless', 'fastest', '100% compatible',
    'no limitations', etc. that make claims not backed by evidence.
    """

    name = "risk_language"

    def evaluate(self, page: Page, knowledge: Any) -> list[Finding]:
        findings: list[Finding] = []

        for line_no, line_text in page.prose_lines:
            for pattern, desc, severity in RISK_LANGUAGE_PATTERNS:
                if re.search(pattern, line_text, re.IGNORECASE):
                    findings.append(Finding(
                        level=severity,
                        category="RL",
                        filepath=str(page.filepath),
                        line_no=line_no,
                        message=desc,
                        suggestion="Qualify the claim or remove unsupported language",
                        evaluator=self.name,
                    ))

        return findings
