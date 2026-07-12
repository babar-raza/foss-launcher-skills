"""
naturalness_check.py — TC-10: Deterministic prose quality gate.

Checks LLM-generated content for injection markers, sentence count drift,
and register shift before it is inserted into content pages.

Output: PASS / WARNING (never FAIL — warnings route to human review queue).

Called by:
  - feature_list_extender.py (before bullet insert)
  - body_refresh.py (Category C updates, after LLM rewrite)

CLI (standalone check):
    PYTHONPATH=scripts/pipeline python -m commands.ops.naturalness_check \\
        --original "Original text..." --generated "Generated text..."
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

# ── Constants ──────────────────────────────────────────────────────────────

# Phrases that signal LLM filler / sycophantic injection (case-insensitive)
_INJECTION_MARKERS: tuple[str, ...] = (
    "note that",
    "it is worth mentioning",
    "it is important to note",
    "additionally,",
    "furthermore,",
    "in conclusion",
    "in summary,",
    "it should be noted",
    "as mentioned above",
    "as noted above",
    "this is because",
    "please note",
    "importantly,",
)

# Max allowed sentence count increase between original and generated text.
# 2 new sentences per rewrite is considered safe; > 2 is a warning.
_SENTENCE_DELTA_WARN_THRESHOLD = 2

# Approximate word count per sentence (used for register shift check).
# If the average sentence length of generated text deviates by more than
# this ratio from the original, flag as a potential register shift.
_REGISTER_RATIO_WARN = 0.40   # 40% deviation


# ── Data classes ───────────────────────────────────────────────────────────

@dataclass
class NaturalnessResult:
    verdict: str                     # "PASS" or "WARNING"
    findings: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.verdict == "PASS"


# ── Internal helpers ───────────────────────────────────────────────────────

def _split_sentences(text: str) -> list[str]:
    """Split text into approximate sentences on .!? followed by whitespace."""
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    return [s for s in sentences if s.strip()]


def _avg_word_count(sentences: Sequence[str]) -> float:
    """Return average word count per sentence."""
    if not sentences:
        return 0.0
    return sum(len(s.split()) for s in sentences) / len(sentences)


def _strip_code_blocks(text: str) -> str:
    """Remove fenced code blocks before prose analysis."""
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"~~~[\s\S]*?~~~", "", text)
    return text


# ── Public API ─────────────────────────────────────────────────────────────

def check(original: str, generated: str) -> NaturalnessResult:
    """
    Run all naturalness checks on generated text vs original text.

    Parameters
    ----------
    original  : The text before the LLM rewrite (or adjacent bullets for
                context when checking a newly inserted bullet).
    generated : The LLM-generated text to validate.

    Returns
    -------
    NaturalnessResult with verdict PASS or WARNING and a list of findings.
    """
    findings: list[str] = []

    orig_prose = _strip_code_blocks(original)
    gen_prose = _strip_code_blocks(generated)

    # Check 1: Injection marker phrases
    gen_lower = gen_prose.lower()
    found_markers = [m for m in _INJECTION_MARKERS if m in gen_lower]
    if found_markers:
        findings.append(
            f"INJECTION_MARKERS: {found_markers!r} detected in generated text"
        )

    # Check 2: Sentence count delta
    orig_sentences = _split_sentences(orig_prose)
    gen_sentences = _split_sentences(gen_prose)
    delta = len(gen_sentences) - len(orig_sentences)
    if delta > _SENTENCE_DELTA_WARN_THRESHOLD:
        findings.append(
            f"SENTENCE_DELTA: generated has {len(gen_sentences)} sentences "
            f"vs {len(orig_sentences)} original (+{delta} over threshold "
            f"of {_SENTENCE_DELTA_WARN_THRESHOLD})"
        )

    # Check 3: Register shift (average sentence length deviation)
    orig_avg = _avg_word_count(orig_sentences)
    gen_avg = _avg_word_count(gen_sentences)
    if orig_avg > 0:
        ratio = abs(gen_avg - orig_avg) / orig_avg
        if ratio > _REGISTER_RATIO_WARN:
            findings.append(
                f"REGISTER_SHIFT: avg sentence length changed from "
                f"{orig_avg:.1f} to {gen_avg:.1f} words "
                f"({ratio:.0%} deviation > {_REGISTER_RATIO_WARN:.0%} threshold)"
            )

    verdict = "WARNING" if findings else "PASS"
    return NaturalnessResult(verdict=verdict, findings=findings)


# ── CLI ────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Naturalness check — PASS/WARNING (never FAIL)."
    )
    p.add_argument("--original", required=True, help="Original text (before rewrite).")
    p.add_argument("--generated", required=True, help="Generated text (after rewrite).")
    p.add_argument("--quiet", action="store_true", help="Print only verdict.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    result = check(args.original, args.generated)
    if args.quiet:
        print(result.verdict)
    else:
        print(f"Verdict: {result.verdict}")
        for f in result.findings:
            print(f"  WARN: {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
