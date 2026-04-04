"""Defect sweep — cross-family defect class detection.

H-17: When a defect class (category + evaluator + message pattern) is found
in one family/platform, this module can run the same evaluator across all
other products to detect the same class of defect.

Usage from CLI::

    python -m scripts.pipeline.content_eval evaluate slides python --sweep

After evaluating the target product, the sweep collects FAIL/WARN findings,
extracts defect signatures, and runs targeted evaluators on all other products.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..models import Finding


def extract_defect_signatures(findings: list[Finding]) -> list[dict]:
    """Extract generalizable defect patterns from findings.

    Returns a list of dicts with keys:
        category: str     — finding category code (e.g., "CP", "FT")
        evaluator: str    — evaluator name
        pattern: str      — regex pattern to match similar messages
        severity: str     — original severity level
    """
    signatures: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for f in findings:
        if f.level not in ("FAIL", "WARN"):
            continue
        key = (f.category, f.evaluator)
        if key in seen:
            continue
        seen.add(key)

        # Generalize the message by replacing specific names with wildcards
        generalized = re.sub(r"`[^`]+`", "`...`", f.message)
        generalized = re.sub(r"\b[A-Z][a-zA-Z0-9]+\b", "CLASS", generalized)

        signatures.append({
            "category": f.category,
            "evaluator": f.evaluator,
            "pattern": generalized,
            "severity": f.level,
            "example_message": f.message,
        })

    return signatures


def run_sweep(
    seed_findings: list[Finding],
    all_products: dict[tuple[str, str], list],
    evaluator_runner: callable,
    exclude: tuple[str, str] | None = None,
) -> list[Finding]:
    """Run targeted evaluators on all products for defect classes found in seed.

    Parameters
    ----------
    seed_findings : findings from the target product evaluation
    all_products : dict of (family, platform) → list of Page objects
    evaluator_runner : callable(page, evaluator_names, knowledge) → list[Finding]
    exclude : (family, platform) to skip (the seed product)

    Returns
    -------
    List of findings from the sweep across other products.
    """
    signatures = extract_defect_signatures(seed_findings)
    if not signatures:
        return []

    # Collect unique evaluators to run
    evaluators_to_run = list({s["evaluator"] for s in signatures})

    sweep_findings: list[Finding] = []
    for (family, platform), pages in all_products.items():
        if exclude and (family, platform) == exclude:
            continue
        for page in pages:
            try:
                findings = evaluator_runner(page, evaluators_to_run)
                sweep_findings.extend(findings)
            except Exception:
                continue  # Don't let sweep failures block

    return sweep_findings
