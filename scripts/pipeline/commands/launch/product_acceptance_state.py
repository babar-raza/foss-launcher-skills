#!/usr/bin/env python3
"""product_acceptance_state.py — read-only acceptance-state projection for one product.

R-1 (MT040-2026-08-28-PDF-TYPESCRIPT-LAUNCH TC-MT040-49). Regenerates ONE
consolidated status view for {family}/{platform} from the artifacts that
independently claim to describe it -- readiness.md (readiness_scorecard.py),
the H-gate sign-off sample files (human_review_sampler.py /
readiness_scorecard.py), and (best-effort, when present) locale-staleness
and refresh-run reports. This is a PROJECTION, never a second source of
truth: it reads existing artifacts and reports what they say, including when
they disagree or have gone stale — it does not decide anything, write
anything, or replace readiness_scorecard.py / S-90 (publish-readiness-review)
as the actual acceptance authority.

Root problem this closes (W9, see
reports/sprint/pdf-typescript-hardening/preflight/design.md): observed live
that cells/typescript's own readiness.md (2026-06-15, NOT READY) and its S-90
final-verdict.md (2026-06-06, PUBLISH) directly contradict each other, and
both predate the product's later knowledge re-sync -- there was no single
place to see that contradiction and staleness mechanically; a human had to
notice the dates by hand.

Usage:
    python scripts/pipeline/commands/launch/product_acceptance_state.py --family pdf --platform typescript
    python scripts/pipeline/commands/launch/product_acceptance_state.py --family pdf --platform typescript --json

Exit codes:
    0  status computed successfully (regardless of what the status says --
       this is a read-only report, not a gate)
    1  no readiness.md and no final-verdict.md found at all for this product
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_DEFAULT_ROOT = Path(__file__).resolve().parents[4]
_ROOT = _DEFAULT_ROOT


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Override module-level path constants for testing."""
    global _ROOT
    _ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_ROOT


def _import_acceptance_bindings():
    lib_dir = str(_ROOT / "scripts" / "pipeline" / "lib")
    if lib_dir not in sys.path:
        sys.path.insert(0, lib_dir)
    import acceptance_bindings
    acceptance_bindings.configure(repo_root=_ROOT)
    return acceptance_bindings


def _read_readiness_md(family: str, platform: str) -> "dict | None":
    path = _ROOT / "reports" / family / platform / "readiness.md"
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    verdict_m = re.search(r"^\*\*Verdict\*\*:\s*(.+?)\s*$", text, re.MULTILINE)
    return {
        "path": str(path),
        "verdict": verdict_m.group(1) if verdict_m else None,
        "raw_text": text,
        "mtime": path.stat().st_mtime,
    }


def _read_latest_final_verdict(family: str, platform: str) -> "dict | None":
    """S-90's final-verdict.md is agent-authored prose, one per review run,
    under reports/publish-review/{family}-{platform}-{YYYYMMDD}/. Pick the
    most recently modified one (there is no other ordering signal — the
    directory name's date is the review date, not necessarily today)."""
    review_root = _ROOT / "reports" / "publish-review"
    if not review_root.is_dir():
        return None
    candidates = sorted(
        review_root.glob(f"{family}-{platform}-*/final-verdict.md"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return None
    path = candidates[0]
    text = path.read_text(encoding="utf-8", errors="replace")
    # Real shape (verified against reports/publish-review/*/final-verdict.md):
    # a "## Final Recommendation" heading, a blank line, then the verdict
    # word alone on its own bold line, e.g. "**PUBLISH**".
    verdict_m = re.search(
        r"^##\s*Final Recommendation\s*\n+\s*\*\*(\w+)\*\*",
        text, re.MULTILINE,
    )
    if not verdict_m:
        # Fallback: a bare PUBLISH/BLOCKED/CONDITIONAL word on its own
        # emphasized line anywhere in the doc (older/differently-shaped
        # reports).
        verdict_m = re.search(r"^\*\*(PUBLISH|BLOCKED|CONDITIONAL)\*\*\s*$", text, re.MULTILINE)
    return {
        "path": str(path),
        "verdict": verdict_m.group(1) if verdict_m else None,
        "raw_text": text,
        "mtime": path.stat().st_mtime,
    }


def _read_hgate_bindings_summary(family: str, platform: str, ab_mod) -> dict:
    """Best-effort per-gate bindings-staleness summary, independent of
    readiness_scorecard.py (which requires the full grade/checkpoint/
    coverage pipeline to run) — this only needs the sample files themselves
    to exist on disk."""
    review_dir = _ROOT / "reports" / "human-review"
    gates = ["h01", "h02", "h03", "h04", "h05"]
    current = ab_mod.compute_bindings(family, platform)
    summary: dict[str, str] = {}
    for gate in gates:
        sample_file = review_dir / f"{family}-{platform}-{gate}-sample.md"
        if not sample_file.is_file():
            summary[gate] = "no_sample_file"
            continue
        text = sample_file.read_text(encoding="utf-8", errors="replace")
        stored = ab_mod.parse_bindings_yaml(text)
        summary[gate] = ab_mod.bindings_status(stored, current)
    return summary


def compute_product_state(family: str, platform: str) -> dict:
    """Read-only: assemble one consolidated status dict for {family}/{platform}.

    Never raises on a missing individual artifact — each source degrades to
    None/"not_available" independently; only the TOTAL absence of every
    source is reported as an error by the caller (main()'s exit code), not
    by this function.
    """
    ab_mod = _import_acceptance_bindings()
    current_bindings = ab_mod.compute_bindings(family, platform)

    readiness = _read_readiness_md(family, platform)
    readiness_bindings_status = "not_available"
    if readiness is not None:
        stored = ab_mod.parse_bindings_yaml(readiness["raw_text"])
        readiness_bindings_status = ab_mod.bindings_status(stored, current_bindings)

    final_verdict = _read_latest_final_verdict(family, platform)
    final_verdict_bindings_status = "not_available"
    if final_verdict is not None:
        # S-90's final-verdict.md is agent-authored prose; it may or may not
        # carry a bindings: block depending on whether the skill doc
        # (skills/publish-readiness-review.md) has been updated to embed one
        # -- as of this card, that skill-doc update is a separate follow-up
        # (see this module's own docstring / the mission's Phase C card), so
        # "not_available" here for most existing reports is expected, not a
        # bug.
        stored = ab_mod.parse_bindings_yaml(final_verdict["raw_text"])
        final_verdict_bindings_status = ab_mod.bindings_status(stored, current_bindings)

    hgate_bindings = _read_hgate_bindings_summary(family, platform, ab_mod)

    # Cross-artifact agreement check: do readiness.md and final-verdict.md
    # even agree on a yes/no verdict, independent of staleness? This is the
    # exact contradiction observed live for cells/typescript.
    def _normalize_verdict(v: "str | None") -> "str | None":
        if v is None:
            return None
        v = v.upper()
        if "READY TO SHIP" in v or v == "PUBLISH":
            return "ACCEPT"
        if "NOT READY" in v or v in ("BLOCKED", "FAIL"):
            return "REJECT"
        return "OTHER"

    r_norm = _normalize_verdict(readiness["verdict"] if readiness else None)
    f_norm = _normalize_verdict(final_verdict["verdict"] if final_verdict else None)
    artifacts_agree = None
    if r_norm is not None and f_norm is not None:
        artifacts_agree = r_norm == f_norm

    # Overall consolidated status.
    any_stale = readiness_bindings_status == "stale" or final_verdict_bindings_status == "stale" \
        or any(v == "stale" for v in hgate_bindings.values())
    any_current = readiness_bindings_status == "current" or final_verdict_bindings_status == "current"
    if readiness is None and final_verdict is None:
        overall = "no_acceptance_artifact_found"
    elif artifacts_agree is False:
        overall = "artifacts_disagree"
    elif any_stale:
        overall = "stale_verdict"
    elif any_current:
        overall = "current"
    else:
        overall = "unverifiable"

    return {
        "family": family,
        "platform": platform,
        "current_bindings": current_bindings,
        "readiness_md": {
            "path": readiness["path"] if readiness else None,
            "verdict": readiness["verdict"] if readiness else None,
            "bindings_status": readiness_bindings_status,
        },
        "final_verdict_md": {
            "path": final_verdict["path"] if final_verdict else None,
            "verdict": final_verdict["verdict"] if final_verdict else None,
            "bindings_status": final_verdict_bindings_status,
        },
        "hgate_bindings_status": hgate_bindings,
        "artifacts_agree": artifacts_agree,
        "overall_status": overall,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only acceptance-state projection for one product")
    parser.add_argument("--family", required=True)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    state = compute_product_state(args.family, args.platform)

    if args.json:
        print(json.dumps(state, indent=2))
    else:
        print(f"=== Product State: {args.family}/{args.platform} ===\n")
        print(f"Overall status: {state['overall_status'].upper()}\n")
        rm = state["readiness_md"]
        print(f"readiness.md:      verdict={rm['verdict']!r:20}  bindings={rm['bindings_status']}")
        fv = state["final_verdict_md"]
        print(f"final-verdict.md:  verdict={fv['verdict']!r:20}  bindings={fv['bindings_status']}")
        if state["artifacts_agree"] is False:
            print("\n  WARNING: readiness.md and final-verdict.md disagree on accept/reject.")
        print("\nH-gate bindings status:")
        for gate, status in state["hgate_bindings_status"].items():
            print(f"  {gate}: {status}")

    if state["readiness_md"]["path"] is None and state["final_verdict_md"]["path"] is None:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
