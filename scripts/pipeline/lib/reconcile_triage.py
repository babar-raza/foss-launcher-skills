# Adapted from aspose.org
"""3-source triage reconciliation for the refresh pipeline.

Combines three independent staleness signals into a single ``final_verdict``
per page, giving downstream planners and the S-84 refresh chain an observable,
structured record of why a page needs action.

RH-203: P-4/P-5 observability gaps — prior reconciliation only tracked SHA
differences (Layer 1) with no body-prose or page-plan dimensions.

The three sources:
  layer1_triage  — SHA heuristic (refresh_knowledge.py / knowledge_delta.json)
  layer2_triage  — Body-prose scanner (triage_confirm.py)
  page_spec      — Page plan reconciliation (page_spec.py: missing/extra)

Final verdict rules (conservative — any stale signal triggers action):
  1. page_spec.verdict == "missing"     → final_verdict = "missing"
  2. layer1_triage.verdict == "needs_update"
     OR layer2_triage.verdict == "needs_update" → final_verdict = "needs_update"
  3. All sources clean                  → final_verdict = "current"

Usage::

    from reconcile_triage import reconcile_triage_page, TriageSource

    result = reconcile_triage_page(
        page_path=page,
        knowledge=knowledge_dict,
        layer1_stale=True,
    )
    print(result.final_verdict)  # "needs_update"
    print(result.to_dict())      # machine-readable 3-source report
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from triage_confirm import triage_confirm


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class TriageSource:
    """Result from a single triage source."""

    name: str
    """Identifier: 'layer1_triage' | 'layer2_triage' | 'page_spec'."""

    verdict: str
    """One of: 'needs_update' | 'current' | 'missing' | 'unknown' | 'read_error'."""

    confidence: float = 0.0
    """Confidence in the verdict; 0.0 = no signal, 1.0 = high certainty."""

    reasons: list[str] = field(default_factory=list)
    """Human-readable reason strings explaining the verdict."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "verdict": self.verdict,
            "confidence": self.confidence,
            "reasons": self.reasons,
        }


@dataclass
class ReconcileTriage:
    """3-source triage reconciliation for a single page.

    Aggregates Layer 1 (SHA), Layer 2 (body prose), and page_spec
    (plan coverage) signals into a single ``final_verdict``.
    """

    family: str
    platform: str
    page_path: str

    layer1_triage: TriageSource
    layer2_triage: TriageSource
    page_spec: TriageSource

    final_verdict: str
    """'needs_update' | 'current' | 'missing' | 'unknown'."""

    final_confidence: float
    final_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "platform": self.platform,
            "page_path": self.page_path,
            "sources": {
                "layer1_triage": self.layer1_triage.to_dict(),
                "layer2_triage": self.layer2_triage.to_dict(),
                "page_spec": self.page_spec.to_dict(),
            },
            "final_verdict": self.final_verdict,
            "final_confidence": self.final_confidence,
            "final_reasons": self.final_reasons,
        }


# ---------------------------------------------------------------------------
# Verdict computation
# ---------------------------------------------------------------------------

def _compute_final_verdict(
    layer1: TriageSource,
    layer2: TriageSource,
    spec: TriageSource,
) -> tuple[str, float, list[str]]:
    """Apply conservative combination rules and return (verdict, confidence, reasons)."""
    reasons: list[str] = []

    # Rule 1: page_spec missing takes highest priority
    if spec.verdict == "missing":
        reasons.extend(spec.reasons)
        return "missing", spec.confidence or 1.0, reasons

    # Rule 2: any layer signals needs_update
    needs_update = False
    confidence = 0.0

    if layer1.verdict == "needs_update":
        needs_update = True
        confidence = max(confidence, layer1.confidence)
        reasons.extend(layer1.reasons)

    if layer2.verdict == "needs_update":
        needs_update = True
        confidence = max(confidence, layer2.confidence)
        reasons.extend(layer2.reasons)

    if needs_update:
        return "needs_update", confidence, reasons

    # Rule 3: layer2 read_error — cannot confirm current; surface as unknown (TC-2)
    if layer2.verdict == "read_error":
        return "unknown", 0.0, layer2.reasons

    # Rule 4: all sources clean
    return "current", 0.0, []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def reconcile_triage_page(
    page_path: str | Path,
    knowledge: dict[str, Any],
    *,
    layer1_stale: bool = False,
    layer1_reasons: list[str] | None = None,
    page_spec_missing: bool = False,
    page_spec_extra: bool = False,
    family: str = "",
    platform: str = "",
) -> ReconcileTriage:
    """Compute 3-source triage reconciliation for a single page.

    Args:
        page_path: Path to the content page (.md file).
        knowledge: Knowledge dict passed to triage_confirm (api_surface, claims, delta).
        layer1_stale: True if Layer 1 (SHA comparison) reports the page is stale.
        layer1_reasons: Optional reasons from the Layer 1 check.
        page_spec_missing: True if the page is in the plan but absent from disk.
        page_spec_extra: True if the page is on disk but absent from the plan.
        family: Product family (for the output record).
        platform: Product platform (for the output record).

    Returns:
        ReconcileTriage with all three sources populated and final_verdict set.
    """
    page_path = Path(page_path)

    # --- Layer 1: SHA heuristic ---
    if layer1_stale:
        l1 = TriageSource(
            name="layer1_triage",
            verdict="needs_update",
            confidence=1.0,
            reasons=list(layer1_reasons or ["SHA mismatch: knowledge updated since last refresh"]),
        )
    else:
        l1 = TriageSource(name="layer1_triage", verdict="current", confidence=0.0)

    # --- Layer 2: body-prose scanner ---
    l2_result = triage_confirm(page_path, knowledge)
    if l2_result.get("verdict") == "read_error":
        # TC-2: unreadable page — cannot confirm current; must NOT be classified as "current"
        l2 = TriageSource(
            name="layer2_triage",
            verdict="read_error",
            confidence=0.0,
            reasons=l2_result.get("reasons", ["page unreadable"]),
        )
    elif l2_result["stale"]:
        l2 = TriageSource(
            name="layer2_triage",
            verdict="needs_update",
            confidence=l2_result["confidence"],
            reasons=l2_result["reasons"],
        )
    else:
        l2 = TriageSource(name="layer2_triage", verdict="current", confidence=0.0)

    # --- Page spec: plan coverage ---
    if page_spec_missing:
        spec = TriageSource(
            name="page_spec",
            verdict="missing",
            confidence=1.0,
            reasons=[f"page '{page_path.name}' is in the site plan but absent from disk"],
        )
    elif page_spec_extra:
        spec = TriageSource(
            name="page_spec",
            verdict="needs_update",
            confidence=0.5,
            reasons=[f"page '{page_path.name}' exists on disk but is not in the site plan"],
        )
    else:
        spec = TriageSource(name="page_spec", verdict="current", confidence=0.0)

    # --- Combine ---
    verdict, conf, reasons = _compute_final_verdict(l1, l2, spec)

    return ReconcileTriage(
        family=family,
        platform=platform,
        page_path=str(page_path),
        layer1_triage=l1,
        layer2_triage=l2,
        page_spec=spec,
        final_verdict=verdict,
        final_confidence=conf,
        final_reasons=reasons,
    )
