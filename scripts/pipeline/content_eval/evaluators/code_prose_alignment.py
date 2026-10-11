"""Code-prose alignment evaluator — detects mismatches between prose and code.

Checks whether prose descriptions align with what the adjacent code blocks
actually demonstrate. Uses TF-IDF cosine similarity between extracted prose
intent and code API calls.

Design constraints:
  - EXPERIMENTAL: starts with no grade impact; requires promotion after
    calibration to move to DEFAULT_EVALUATORS.
  - TF-IDF based, no LLM dependency — fully deterministic.
  - WARN at < 0.65, FAIL at < 0.50 (thresholds for calibration).
  - Skips pages with no code blocks or no preceding prose.

TC-EVAL-003: New evaluator for the largest uncovered quality dimension.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

from ..models import Finding, Page
from . import BaseEvaluator

# ---------------------------------------------------------------------------
# TF-IDF helpers (self-contained, no cross-module deps)
# ---------------------------------------------------------------------------

_STOPWORDS = frozenset(
    "a about above after again against all am an and any are as at be because "
    "been before being below between both but by can could did do does doing "
    "down during each few for from further get got had has have having he her "
    "here hers herself him himself his how i if in into is it its itself just "
    "let like me might more most my myself no nor not now of off on once only "
    "or other our ours ourselves out over own re same shall she should so some "
    "such than that the their theirs them themselves then there these they this "
    "those through to too under until up us very was we were what when where "
    "which while who whom why will with you your yours yourself yourselves "
    "import from return def class self none true false".split()
)

_FAIL_THRESHOLD = 0.30   # below this → FAIL (EXPERIMENTAL: calibrate before promotion)
_WARN_THRESHOLD = 0.45   # below this → WARN (TF-IDF 2-doc IDF needs lower thresholds)

# Minimum lengths to evaluate
_MIN_PROSE_TOKENS = 5
_MIN_CODE_TOKENS = 3


def _tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-z][a-z0-9_]*", text.lower())
    return [w for w in words if len(w) > 2 and w not in _STOPWORDS]


def _cosine(vec1: dict[str, float], vec2: dict[str, float]) -> float:
    keys = set(vec1) & set(vec2)
    if not keys:
        return 0.0
    dot = sum(vec1[k] * vec2[k] for k in keys)
    mag1 = math.sqrt(sum(v * v for v in vec1.values()))
    mag2 = math.sqrt(sum(v * v for v in vec2.values()))
    if mag1 == 0 or mag2 == 0:
        return 0.0
    return dot / (mag1 * mag2)


def _to_tfidf(tokens: list[str], idf: dict[str, float]) -> dict[str, float]:
    tf = Counter(tokens)
    total = len(tokens) or 1
    return {t: (c / total) * idf.get(t, 0.0) for t, c in tf.items()}


# ---------------------------------------------------------------------------
# Code block + prose extraction
# ---------------------------------------------------------------------------

_CODE_BLOCK_RE = re.compile(r"^```(\w*)\n(.*?)^```", re.MULTILINE | re.DOTALL)


def _extract_code_prose_pairs(body: str) -> list[tuple[str, str]]:
    """Extract (preceding_prose, code_block) pairs from page body.

    For each fenced code block, captures the prose paragraph immediately
    before it and the code block content.
    """
    pairs: list[tuple[str, str]] = []
    # Split body into segments between code blocks
    parts = _CODE_BLOCK_RE.split(body)
    # parts: [before, lang1, code1, between, lang2, code2, ...]
    # Structure: text, (lang, code, text)*
    i = 0
    while i < len(parts):
        if i + 2 < len(parts):
            preceding_text = parts[i].strip()
            code = parts[i + 2].strip()
            if preceding_text and code:
                # Take last paragraph of preceding text
                paragraphs = preceding_text.split("\n\n")
                last_para = paragraphs[-1].strip() if paragraphs else ""
                if last_para:
                    pairs.append((last_para, code))
            i += 3
        else:
            break
    return pairs


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------

class CodeProseAlignmentEvaluator(BaseEvaluator):
    """Check that prose descriptions align with adjacent code examples.

    EXPERIMENTAL — starts with no grade impact. Requires 2-week calibration
    before promotion to DEFAULT_EVALUATORS.
    """

    name = "code_prose_alignment"

    def evaluate(self, page: Page, knowledge: Any) -> list[Finding]:
        findings: list[Finding] = []

        # Only evaluate pages with code blocks
        if not page.body or "```" not in page.body:
            return findings

        # Skip reference pages (they have tables, not prose-code pairs)
        if page.subdomain == "reference":
            return findings

        pairs = _extract_code_prose_pairs(page.body)
        if not pairs:
            return findings

        for prose, code in pairs:
            prose_tokens = _tokenize(prose)
            code_tokens = _tokenize(code)

            if len(prose_tokens) < _MIN_PROSE_TOKENS or len(code_tokens) < _MIN_CODE_TOKENS:
                continue

            # Build IDF from both documents
            all_docs = [prose_tokens, code_tokens]
            df: dict[str, int] = {}
            for doc in all_docs:
                for term in set(doc):
                    df[term] = df.get(term, 0) + 1
            idf = {term: math.log(1 + 2 / count) for term, count in df.items()}

            prose_vec = _to_tfidf(prose_tokens, idf)
            code_vec = _to_tfidf(code_tokens, idf)
            similarity = _cosine(prose_vec, code_vec)

            if similarity < _FAIL_THRESHOLD:
                findings.append(Finding(
                    level="WARN",  # EXPERIMENTAL: WARN only, never FAIL
                    category="CPA",
                    filepath=str(page.filepath),
                    line_no=0,
                    message=(
                        f"Prose-code alignment low ({similarity:.2f}): "
                        f"prose may not describe what code demonstrates"
                    ),
                    suggestion="Verify that the prose paragraph accurately describes the code example below it",
                    evaluator=self.name,
                ))
            elif similarity < _WARN_THRESHOLD:
                findings.append(Finding(
                    level="WARN",
                    category="CPA",
                    filepath=str(page.filepath),
                    line_no=0,
                    message=(
                        f"Prose-code alignment marginal ({similarity:.2f}): "
                        f"consider strengthening prose-code connection"
                    ),
                    suggestion="Add API class/method names from the code block to the preceding prose",
                    evaluator=self.name,
                ))

        return findings
