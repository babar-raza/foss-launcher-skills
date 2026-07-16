"""Layer 2 body-prose scanner for refresh pipeline triage.

Complements the Layer 1 SHA-based staleness detection in refresh_knowledge.py
with a content-level scan that detects when page body prose references
API classes or knowledge claims that have changed or been removed.

RH-201: P-8 diagnostic — missing Layer 2 detection causes false negatives where
the knowledge SHA has not changed but the page's rendered prose is stale relative
to the current knowledge state (e.g., after a partial refresh cycle).

CONTRACT: scripts/pipeline/lib/triage_confirm.py (RPR-F-03, S-111)
  purpose: real CLI for the S-92 triage-confirm Layer 2 scan, replacing the
           documented-but-nonexistent invocation the SKILL.md previously described
           (this file had no argparse/__main__ prior to RPR-F-03 — the documented
           command silently no-op'd if run literally as written).
  inputs:  content pages for {family}/{platform} (via content_discovery.discover_content)
           knowledge/{family}/{platform}/merged/{api_surface.json,claims.json,knowledge_delta.json}
  outputs: reports/refresh_review/{family}/{platform}/triage_verdict.yaml
  idempotent: yes — overwrites output on each run; pure read+scan, no content writes
  exit codes: 0 = confirmed (no page scored stale), 1 = unresolved (>=1 page stale),
              2 = error (knowledge artifacts unreadable/absent)

Library usage::

    from triage_confirm import triage_confirm

    result = triage_confirm(page_path, knowledge)
    if result['stale']:
        for reason in result['reasons']:
            print(reason)

CLI usage::

    PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/lib/triage_confirm.py pdf net
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

_LIB_DIR = Path(__file__).resolve().parents[0]
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))
_PIPELINE_ROOT = Path(__file__).resolve().parents[1]  # lib/ -> pipeline/
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[3]  # lib/ -> pipeline/ -> scripts/ -> repo root
_REPO_ROOT = _DEFAULT_REPO_ROOT


def configure(*, repo_root=None):
    """Redirect module-level paths for testing. Call with no args to reset."""
    global _REPO_ROOT
    _REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT


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


# ── CLI (RPR-F-03) ───────────────────────────────────────────────────────────

def _load_knowledge(family: str, platform: str, repo_root: Path) -> dict[str, Any]:
    """Load the knowledge dict shape triage_confirm() expects from merged/ artifacts."""
    merged = repo_root / "knowledge" / family / platform / "merged"
    knowledge: dict[str, Any] = {}

    api_surface_path = merged / "api_surface.json"
    if api_surface_path.exists():
        try:
            data = json.loads(api_surface_path.read_text(encoding="utf-8"))
            knowledge["api_surface"] = data if isinstance(data, list) else data.get("classes", [])
        except (json.JSONDecodeError, OSError):
            knowledge["api_surface"] = []
    else:
        knowledge["api_surface"] = []

    claims_path = merged / "claims.json"
    if claims_path.exists():
        try:
            data = json.loads(claims_path.read_text(encoding="utf-8"))
            knowledge["claims"] = data if isinstance(data, list) else data.get("claims", [])
        except (json.JSONDecodeError, OSError):
            knowledge["claims"] = []
    else:
        knowledge["claims"] = []

    delta_path = merged / "knowledge_delta.json"
    if delta_path.exists():
        try:
            knowledge["delta"] = json.loads(delta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            knowledge["delta"] = {}
    else:
        knowledge["delta"] = {}

    return knowledge


def run(family: str, platform: str, *, repo_root: Path | None = None, files: list[str] | None = None) -> dict[str, Any]:
    """Run the Layer 2 scan across every English content page for a product.

    Returns a summary dict; also the basis for the CLI's exit code and the
    written triage_verdict.yaml. Raises FileNotFoundError only when the
    product has no reachable knowledge/merged/ directory at all (a genuine
    error, distinct from "merged/ exists but individual files are absent",
    which degrades gracefully to empty lists per _load_knowledge above).
    """
    root = repo_root or _REPO_ROOT
    merged_dir = root / "knowledge" / family / platform / "merged"
    if not merged_dir.exists():
        raise FileNotFoundError(
            f"knowledge/{family}/{platform}/merged/ not found at {merged_dir} — "
            f"run knowledge bootstrap (S-54) before triage-confirm"
        )

    knowledge = _load_knowledge(family, platform, root)

    if files:
        pages = [Path(f) for f in files]
    else:
        sys.path.insert(0, str(root / "scripts" / "pipeline" / "lib"))
        from content_discovery import discover_content  # noqa: E402  (import here: only needed for this path)
        pages = discover_content(family, platform, skip_drafts=True)

    results = []
    stale_count = 0
    error_count = 0
    for page in pages:
        result = triage_confirm(page, knowledge)
        result["page_path"] = str(page)
        results.append(result)
        if result.get("verdict") == "read_error":
            error_count += 1
        elif result.get("stale"):
            stale_count += 1

    return {
        "family": family,
        "platform": platform,
        "pages_checked": len(pages),
        "stale_count": stale_count,
        "error_count": error_count,
        "results": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "triage_confirm — S-92 Layer 2 body-prose staleness scanner. "
            "Real CLI (RPR-F-03) replacing the previously-documented-but-nonexistent invocation."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/lib/triage_confirm.py pdf net
  PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/lib/triage_confirm.py pdf net --json

Exit codes:
  0 = confirmed (no page scored stale)
  1 = unresolved (>=1 page scored stale — the caller should re-run the relevant content update step)
  2 = error (knowledge/{family}/{platform}/merged/ not found)
        """,
    )
    parser.add_argument("family", help="Product family (e.g. pdf, 3d)")
    parser.add_argument("platform", help="Platform (e.g. net, java)")
    parser.add_argument("--files", nargs="*", help="Specific page paths to check (default: all discovered English pages)")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON summary")
    args = parser.parse_args(argv)

    try:
        summary = run(args.family, args.platform, files=args.files)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    out_dir = _REPO_ROOT / "reports" / "refresh_review" / args.family / args.platform
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "triage_verdict.yaml"
    try:
        import yaml
        out_path.write_text(yaml.dump(summary, sort_keys=False, allow_unicode=True), encoding="utf-8")
    except ImportError:
        out_path.with_suffix(".json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"triage_confirm: {args.family}/{args.platform}")
        print(f"  pages checked : {summary['pages_checked']}")
        print(f"  stale         : {summary['stale_count']}")
        print(f"  read errors   : {summary['error_count']}")
        if summary["stale_count"]:
            print("  STALE PAGES:")
            for r in summary["results"]:
                if r.get("stale"):
                    print(f"    - {r['page_path']}: {'; '.join(r['reasons'])}")

    if summary["error_count"] and summary["stale_count"] == 0:
        # Unreadable pages alone (no confirmed staleness) still can't be called "confirmed"
        return 1
    return 1 if summary["stale_count"] else 0


if __name__ == "__main__":
    sys.exit(main())
