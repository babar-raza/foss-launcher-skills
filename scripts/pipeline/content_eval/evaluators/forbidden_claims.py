"""Forbidden claims evaluator — matches prose against known false claims."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..models import Finding, Page
from . import BaseEvaluator

KNOWLEDGE_ROOT = Path("knowledge")


def _load_forbidden_claims(family: str, platform: str) -> list[str]:
    """Load forbidden_claims from merged/index.json."""
    index_path = KNOWLEDGE_ROOT / family / platform / "merged" / "index.json"
    if not index_path.exists():
        return []
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
        return data.get("forbidden_claims", [])
    except (json.JSONDecodeError, KeyError):
        return []


def _tokenize(text: str) -> set[str]:
    """Extract lowercase word tokens for matching."""
    return set(re.findall(r"[a-z][a-z0-9_]+", text.lower()))


class ForbiddenClaimsEvaluator(BaseEvaluator):
    """Detects content that matches known false/forbidden claims.

    Loads forbidden_claims from index.json (derived from limitations.md)
    and checks each prose line for matches using token overlap scoring.
    """

    name = "forbidden_claims"

    def evaluate(self, page: Page, knowledge: Any) -> list[Finding]:
        if not page.family or not page.platform:
            return []

        forbidden = _load_forbidden_claims(page.family, page.platform)
        if not forbidden:
            return []

        findings: list[Finding] = []

        # Tokenize forbidden claims
        forbidden_tokens = [(fc, _tokenize(fc)) for fc in forbidden if len(fc) > 5]

        for line_no, line_text in page.prose_lines:
            line_tokens = _tokenize(line_text)
            if len(line_tokens) < 3:
                continue

            for fc_text, fc_tokens in forbidden_tokens:
                if len(fc_tokens) < 2:
                    continue
                overlap = line_tokens & fc_tokens
                # Require high overlap ratio relative to the forbidden claim
                if len(overlap) >= len(fc_tokens) * 0.7 and len(overlap) >= 3:
                    findings.append(Finding(
                        level="FAIL",
                        category="FC",
                        filepath=str(page.filepath),
                        line_no=line_no,
                        message=f"Content matches forbidden claim: \"{fc_text}\"",
                        suggestion="Remove or rewrite this claim — it contradicts repo evidence",
                        evaluator=self.name,
                    ))

        return findings
