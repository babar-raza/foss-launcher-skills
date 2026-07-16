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

CONTRACT: scripts/pipeline/lib/reconcile_triage.py (RPR-F-03)
  purpose: real CLI wrapping reconcile_triage_page() across every page for a product.
  inputs:  content pages for {family}/{platform}; knowledge/{family}/{platform}/merged/
           {api_surface.json,claims.json,knowledge_delta.json,model.yaml}
  outputs: reports/refresh_review/{family}/{platform}/reconcile_triage.json
  idempotent: yes; exit 0 = all current, 1 = >=1 needs_update/missing, 2 = error
  known simplification: the page_spec source (missing/extra vs. site_plan.yaml) is not
    wired into this CLI path — it always reports page_spec as "current" (no signal),
    since that requires loading and diffing against reports/plans/{family}/{platform}/
    site_plan.yaml, out of scope for RPR-F-03. layer1_triage IS wired, sourced from
    model.yaml's stale_since field. This means the CLI path is a 2-of-3-source
    reconciliation, not the full 3-source design the library function supports when
    called directly with explicit page_spec_missing/page_spec_extra arguments.

Usage::

    from reconcile_triage import reconcile_triage_page, TriageSource

    result = reconcile_triage_page(
        page_path=page,
        knowledge=knowledge_dict,
        layer1_stale=True,
    )
    print(result.final_verdict)  # "needs_update"
    print(result.to_dict())      # machine-readable 3-source report

CLI usage::

    PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/lib/reconcile_triage.py pdf net
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[3]  # lib/ -> pipeline/ -> scripts/ -> repo root
_REPO_ROOT = _DEFAULT_REPO_ROOT
if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.triage_confirm import triage_confirm, _load_knowledge  # noqa: E402


def configure(*, repo_root=None):
    """Redirect module-level paths for testing. Call with no args to reset."""
    global _REPO_ROOT
    _REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT


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


# ── CLI (RPR-F-03) ───────────────────────────────────────────────────────────

def _layer1_stale_from_model_yaml(family: str, platform: str, repo_root: Path) -> tuple[bool, list[str]]:
    """Source layer1_stale from model.yaml's stale_since field (non-null == stale)."""
    model_path = repo_root / "knowledge" / family / platform / "merged" / "model.yaml"
    if not model_path.exists():
        return False, []
    try:
        import yaml
        data = yaml.safe_load(model_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return False, []
    stale_since = data.get("stale_since")
    if stale_since:
        return True, [f"model.yaml stale_since={stale_since}"]
    return False, []


def run(family: str, platform: str, *, repo_root: Path | None = None, files: list[str] | None = None) -> dict[str, Any]:
    """Run 3-source (2-of-3 wired, see module docstring) reconciliation across a product."""
    root = repo_root or _REPO_ROOT
    merged_dir = root / "knowledge" / family / platform / "merged"
    if not merged_dir.exists():
        raise FileNotFoundError(
            f"knowledge/{family}/{platform}/merged/ not found at {merged_dir} — "
            f"run knowledge bootstrap (S-54) before reconcile-triage"
        )

    knowledge = _load_knowledge(family, platform, root)
    layer1_stale, layer1_reasons = _layer1_stale_from_model_yaml(family, platform, root)

    if files:
        pages = [Path(f) for f in files]
    else:
        sys.path.insert(0, str(root / "scripts" / "pipeline" / "lib"))
        from content_discovery import discover_content  # noqa: E402
        pages = discover_content(family, platform, skip_drafts=True)

    results = []
    needs_update = 0
    missing = 0
    unknown = 0
    for page in pages:
        r = reconcile_triage_page(
            page, knowledge,
            layer1_stale=layer1_stale, layer1_reasons=layer1_reasons,
            family=family, platform=platform,
        )
        results.append(r.to_dict())
        if r.final_verdict == "needs_update":
            needs_update += 1
        elif r.final_verdict == "missing":
            missing += 1
        elif r.final_verdict == "unknown":
            unknown += 1

    return {
        "family": family,
        "platform": platform,
        "pages_checked": len(pages),
        "needs_update_count": needs_update,
        "missing_count": missing,
        "unknown_count": unknown,
        "results": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="reconcile_triage — 3-source (2-of-3 wired) triage reconciliation CLI (RPR-F-03).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/lib/reconcile_triage.py pdf net

Exit codes:
  0 = all pages current
  1 = >=1 page needs_update or missing
  2 = error (knowledge/{family}/{platform}/merged/ not found)
        """,
    )
    parser.add_argument("family")
    parser.add_argument("platform")
    parser.add_argument("--files", nargs="*")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        summary = run(args.family, args.platform, files=args.files)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    out_dir = _REPO_ROOT / "reports" / "refresh_review" / args.family / args.platform
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "reconcile_triage.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"reconcile_triage: {args.family}/{args.platform}")
        print(f"  pages checked : {summary['pages_checked']}")
        print(f"  needs_update  : {summary['needs_update_count']}")
        print(f"  missing       : {summary['missing_count']}")
        print(f"  unknown       : {summary['unknown_count']}")

    blocking = summary["needs_update_count"] + summary["missing_count"]
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
