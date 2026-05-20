# Adapted from aspose.org
"""Layer 2 body-prose scanner for refresh pipeline triage.

Complements the Layer 1 SHA-based staleness detection in refresh_knowledge.py
with a content-level scan that detects when page body prose references
API classes or knowledge claims that have changed or been removed.

RH-201: P-8 diagnostic — missing Layer 2 detection causes false negatives where
the knowledge SHA has not changed but the page's rendered prose is stale relative
to the current knowledge state (e.g., after a partial refresh cycle).

Usage::

    from triage_confirm import triage_confirm

    result = triage_confirm(page_path, knowledge)
    if result['stale']:
        for reason in result['reasons']:
            print(reason)
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def triage_confirm(
    page_path: str | Path,
    knowledge: dict[str, Any],
) -> dict[str, Any]:
    """Scan page body for stale prose relative to current knowledge.

    Layer 2 complement to the SHA-based (Layer 1) staleness gate.  Reads the
    page at *page_path*, checks it against the supplied *knowledge* dict, and
    returns a verdict dict.

    Args:
        page_path: Absolute or relative path to a Hugo content page (.md).
        knowledge: Dict with any combination of:
            'api_surface'  — list of current API class dicts (name, methods, properties)
            'claims'       — list of current claim dicts (claim_id, text, …)
            'delta'        — knowledge_delta.json contents (new/removed/modified lists)

    Returns:
        {
            'stale':      bool   — True if any staleness signal detected,
            'reasons':    list[str],
            'confidence': float  — 0.0 (no signal) to 1.0 (high confidence stale),
        }
    """
    page_path = Path(page_path)
    reasons: list[str] = []
    confidence = 0.0

    # Read the page; if unreadable return a distinct "read_error" verdict (TC-2).
    # Callers must treat "read_error" as unknown — NOT as "current".
    try:
        body = page_path.read_text(encoding="utf-8")
    except Exception as exc:
        return {
            "stale": False,
            "verdict": "read_error",
            "reasons": [f"could not read page: {exc}"],
            "confidence": 0.0,
        }

    delta: dict[str, Any] = knowledge.get("delta") or {}
    api_surface: list[dict] = knowledge.get("api_surface") or []
    current_api_names: set[str] = {
        e["name"] for e in api_surface if isinstance(e, dict) and "name" in e
    }

    # --- Signal 1: page body mentions APIs that have been removed ---
    removed_apis: list[str] = delta.get("removed_apis") or []
    for api_name in removed_apis:
        # Word-boundary match to avoid false positives (e.g. "Workbook" in "WorkbookSettings")
        if re.search(rf"\b{re.escape(api_name)}\b", body):
            reasons.append(f"body references removed API '{api_name}'")
            confidence = max(confidence, 0.9)

    # --- Signal 2: page body mentions APIs that have been modified ---
    modified_apis: list[str] = delta.get("modified_apis") or []
    for api_name in modified_apis:
        if re.search(rf"\b{re.escape(api_name)}\b", body):
            reasons.append(f"body references modified API '{api_name}'")
            confidence = max(confidence, 0.6)

    # --- Signal 3: page slug references a class not in current api_surface ---
    slug = page_path.stem  # e.g. "Workbook" from "Workbook.md"
    if current_api_names and slug and slug[0].isupper():
        if slug not in current_api_names:
            reasons.append(f"page slug '{slug}' not found in current api_surface")
            confidence = max(confidence, 0.8)

    # --- Signal 4: page body contains a removed claim ID ---
    removed_claims: list[str] = delta.get("removed_claims") or []
    for claim_id in removed_claims:
        if claim_id in body:
            reasons.append(f"body contains removed claim ID '{claim_id}'")
            confidence = max(confidence, 0.7)

    stale = bool(reasons)
    return {"stale": stale, "reasons": reasons, "confidence": confidence}
