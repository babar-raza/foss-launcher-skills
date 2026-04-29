"""knowledge_coverage.py — Per-claim disposition table for knowledge coverage audit.

Backing script for S-79 (knowledge-coverage-audit). Computes a disposition
for every claim in merged/claims.json and every class in merged/api_surface.json,
classifying each as USED_EVIDENCE, SURFACE_ONLY, EXCLUDED_THRESHOLD,
EXCLUDED_TIER, EXCLUDED_SKIP, EXCLUDED_LIMITATION, DUPLICATE, INTENTIONAL,
or ORPHANED.

Usage:
    python scripts/pipeline/knowledge_coverage.py {family} {platform} [options]

Options:
    --out-dir PATH    Override output directory (default: reports/coverage/{family}/{platform})
    --no-md           Skip writing the Markdown summary
    --json-only       Write JSON output only

CONTRACT: This script is the backing implementation for S-79 (knowledge-coverage-audit).
The skill spec in .agents/skills/knowledge-coverage-audit/SKILL.md documents the same
disposition taxonomy and summary format. Keep them in sync.
verified: 2026-04-07
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap: ensure scripts/pipeline/ is on sys.path for sibling imports
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE.parent.parent.parent.parent))  # scripts/pipeline/
    _LIB_DIR = str(Path(_HERE) / "lib") if isinstance(_HERE, str) else str(_HERE / "lib")
    if _LIB_DIR not in sys.path:
        sys.path.insert(0, _LIB_DIR)

from core.env_loader import load_env  # noqa: E402
load_env()

from content_discovery import discover_content, KNOWLEDGE_ROOT  # noqa: E402
from core.markdown import parse_frontmatter  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[4]
REPORTS_ROOT = REPO_ROOT / "reports" / "coverage"

# Claim kinds that represent structural API facts expressed in reference tables.
# These are SURFACE_ONLY when not cited: they appear as rows in reference page
# tables (generated from api_surface.json), even without explicit evidence.claims.
_STRUCTURAL_KINDS: frozenset[str] = frozenset({
    "api_method",
    "api_class",
    "api_field",
    "api_property",
    "api_enum",
})

# Claim kinds that represent enriched/semantic knowledge intended for prose content.
_PROSE_KINDS: frozenset[str] = frozenset({
    "api",          # ERC-* enriched API descriptions
    "feature",      # ERC-* feature descriptions
    "config",       # configuration facts
    "troubleshoot", # troubleshooting facts
    "format",       # format capability claims
    "format_support",  # format support claims (CLM- structural format facts)
    "install",      # installation instructions
})

# Disposition values (terminal states)
DISPOSITION = {
    "USED_EVIDENCE":       "USED_EVIDENCE",
    "SURFACE_ONLY":        "SURFACE_ONLY",
    "EXCLUDED_THRESHOLD":  "EXCLUDED_THRESHOLD",
    "EXCLUDED_TIER":       "EXCLUDED_TIER",
    "EXCLUDED_SKIP":       "EXCLUDED_SKIP",
    "EXCLUDED_LIMITATION": "EXCLUDED_LIMITATION",
    "DUPLICATE":           "DUPLICATE",
    "INTENTIONAL":         "INTENTIONAL",
    "ORPHANED":            "ORPHANED",
}


# ---------------------------------------------------------------------------
# Loader helpers
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> list | dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_yaml_safe(path: Path) -> dict:
    try:
        import yaml
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _load_site_plan(family: str, platform: str) -> dict:
    plan_path = REPO_ROOT / "reports" / "plans" / family / platform / "site_plan.yaml"
    if not plan_path.exists():
        return {}
    raw = _load_yaml_safe(plan_path)
    # site_plan.yaml wraps everything under a "plan" key
    return raw.get("plan", raw)


def _collect_cited_claims(family: str, platform: str) -> set[str]:
    """Return the set of all claim IDs cited in any content page evidence block."""
    pages = discover_content(family, platform)
    cited: set[str] = set()
    for page in pages:
        try:
            fm = parse_frontmatter(page)
        except Exception:
            continue
        ev = fm.get("evidence") or {}
        ids = ev.get("claims") or []
        if isinstance(ids, list):
            cited.update(str(c) for c in ids if c)
    return cited


def _collect_cited_apis(family: str, platform: str) -> set[str]:
    """Return the set of all API tokens cited in any content page evidence block."""
    pages = discover_content(family, platform)
    cited: set[str] = set()
    for page in pages:
        try:
            fm = parse_frontmatter(page)
        except Exception:
            continue
        ev = fm.get("evidence") or {}
        apis = ev.get("apis") or []
        if isinstance(apis, list):
            cited.update(str(a) for a in apis if a)
    return cited


# ---------------------------------------------------------------------------
# Disposition classifier
# ---------------------------------------------------------------------------

def _blog_blocked(plan: dict) -> bool:
    """True if blog content was blocked in the site plan."""
    return not plan.get("evidence_summary", {}).get("blog_justified", True)


def _kb_blocked(plan: dict) -> bool:
    """True if KB content has zero pages in the site plan."""
    kb = plan.get("sections", {}).get("kb", {})
    return kb.get("page_count", 0) == 0


def _get_excluded_clusters(plan: dict) -> set[str]:
    """Return cluster names that were excluded/skipped in the site plan."""
    excluded: set[str] = set()
    topics = plan.get("evidence_summary", {}).get("excluded_topics", 0)
    # We don't have names here; if clusters are explicitly excluded they'd
    # appear in a separate list. This is a best-effort extraction.
    return excluded


def classify_claim(
    claim: dict,
    cited_claims: set[str],
    blog_blocked: bool,
    kb_blocked: bool,
    has_limitations: bool,
) -> str:
    """Assign a terminal disposition to a single claim dict."""
    cid = claim.get("claim_id", "")
    kind = claim.get("kind", "")

    # 1. Cited in any page evidence block → USED_EVIDENCE
    if cid in cited_claims:
        return DISPOSITION["USED_EVIDENCE"]

    # 2. Structural API kind → SURFACE_ONLY (expressed in reference tables)
    if kind in _STRUCTURAL_KINDS:
        return DISPOSITION["SURFACE_ONLY"]

    # 3. Limitation-type claims that are deliberately excluded
    if kind == "limitation" or has_limitations and "limitation" in (claim.get("text") or "").lower():
        return DISPOSITION["EXCLUDED_LIMITATION"]

    # 4. Non-structural prose claims — route by what blocked them
    if kind in _PROSE_KINDS:
        # Blog-targeted claims (feature/snippet-backed) blocked by threshold
        if blog_blocked and kind in ("feature", "api"):
            return DISPOSITION["EXCLUDED_THRESHOLD"]
        # KB-targeted claims blocked by tier bug or threshold
        if kb_blocked and kind in ("troubleshoot", "config", "install"):
            return DISPOSITION["EXCLUDED_TIER"]
        # format/format_support claims are structural facts for products/docs pages
        if kind in ("format", "format_support"):
            return DISPOSITION["SURFACE_ONLY"]
        # install claims that weren't cited despite docs being generated
        # → these should have been used; mark ORPHANED
        return DISPOSITION["ORPHANED"]

    # 5. Unknown kind → ORPHANED (conservative; needs operator review)
    return DISPOSITION["ORPHANED"]


# ---------------------------------------------------------------------------
# Coverage entry for API classes (separate from claims)
# ---------------------------------------------------------------------------

def _classify_class(
    cls: dict,
    cited_apis: set[str],
) -> str:
    """Assign a disposition to an api_surface class entry."""
    name = cls.get("name", "")
    # Check if any reference to this class (or its methods) appears in cited apis
    if name in cited_apis:
        return DISPOSITION["USED_EVIDENCE"]
    for m in cls.get("methods", []):
        if isinstance(m, dict):
            key = f"{name}.{m.get('name', '')}"
            if key in cited_apis:
                return DISPOSITION["USED_EVIDENCE"]
    # All classes appear in reference page tables
    return DISPOSITION["SURFACE_ONLY"]


# ---------------------------------------------------------------------------
# Main compute function
# ---------------------------------------------------------------------------

def compute_coverage(
    family: str,
    platform: str,
    knowledge_root: Path | None = None,
) -> dict:
    """Compute per-claim coverage disposition for a family/platform.

    Returns a result dict with:
        claims: list of {claim_id, kind, text, disposition, reason}
        classes: list of {name, kind, disposition}
        summary: counts per disposition + totals
    """
    kr = knowledge_root or KNOWLEDGE_ROOT
    merged = kr / family / platform / "merged"

    if not (merged / "claims.json").exists():
        raise FileNotFoundError(
            f"No merged/claims.json for {family}/{platform}. "
            f"Run /knowledge-update {family} {platform} first."
        )

    # Check for stale knowledge
    model_path = merged / "model.yaml"
    if model_path.exists():
        model = _load_yaml_safe(model_path)
        if model.get("stale_since") is not None:
            raise ValueError(
                f"Knowledge model is stale (stale_since={model['stale_since']}). "
                f"Run /knowledge-diff then /knowledge-update {family} {platform} first."
            )

    claims_list: list[dict] = _load_json(merged / "claims.json")  # type: ignore[assignment]
    api_surface: list[dict] = _load_json(merged / "api_surface.json")  # type: ignore[assignment]

    # Load limitations indicator
    limitations_path = merged / "limitations.md"
    has_limitations = (
        limitations_path.exists()
        and bool(limitations_path.read_text(encoding="utf-8").strip())
        and "no " not in limitations_path.read_text(encoding="utf-8").lower()[:60]
    )

    # Load site plan for exclusion context
    plan = _load_site_plan(family, platform)
    blog_is_blocked = _blog_blocked(plan)
    kb_is_blocked = _kb_blocked(plan)

    # Collect cited IDs from all content pages
    cited_claims = _collect_cited_claims(family, platform)
    cited_apis = _collect_cited_apis(family, platform)

    # --- Classify claims ---
    claim_results: list[dict] = []
    disposition_counts: dict[str, int] = {d: 0 for d in DISPOSITION.values()}

    for claim in claims_list:
        cid = claim.get("claim_id", "")
        kind = claim.get("kind", "")
        text = (claim.get("text") or "")[:200]
        disp = classify_claim(claim, cited_claims, blog_is_blocked, kb_is_blocked, has_limitations)
        disposition_counts[disp] = disposition_counts.get(disp, 0) + 1
        claim_results.append({
            "claim_id": cid,
            "kind": kind,
            "text": text,
            "disposition": disp,
        })

    # --- Classify API classes (separate accounting from claims) ---
    class_results: list[dict] = []
    class_disp_counts: dict[str, int] = {d: 0 for d in DISPOSITION.values()}

    for cls in api_surface:
        name = cls.get("name", "")
        kind = cls.get("kind", "")
        disp = _classify_class(cls, cited_apis)
        class_disp_counts[disp] = class_disp_counts.get(disp, 0) + 1
        class_results.append({
            "name": name,
            "kind": kind,
            "disposition": disp,
        })

    # --- Summary ---
    total_claims = len(claims_list)
    total_classes = len(api_surface)
    orphaned_claims = [r for r in claim_results if r["disposition"] == DISPOSITION["ORPHANED"]]

    summary = {
        "family": family,
        "platform": platform,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_claims": total_claims,
        "total_classes": total_classes,
        "claim_dispositions": disposition_counts,
        "class_dispositions": class_disp_counts,
        "blog_blocked": blog_is_blocked,
        "kb_blocked": kb_is_blocked,
        "pages_scanned": len(discover_content(family, platform)),
        "cited_claim_ids": len(cited_claims),
        "orphaned_count": len(orphaned_claims),
        "orphaned_claim_ids": [r["claim_id"] for r in orphaned_claims],
    }

    return {
        "summary": summary,
        "claims": claim_results,
        "classes": class_results,
    }


# ---------------------------------------------------------------------------
# Report writers
# ---------------------------------------------------------------------------

def _write_json(result: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "knowledge_coverage.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _write_md(result: dict, out_dir: Path) -> Path:
    s = result["summary"]
    family = s["family"]
    platform = s["platform"]
    disp = s["claim_dispositions"]
    class_disp = s["class_dispositions"]

    lines = [
        f"# Knowledge Coverage Audit — {family}/{platform}",
        "",
        f"Generated: {s['generated_at']}",
        "",
        "## Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total claims | {s['total_claims']} |",
        f"| Total API classes | {s['total_classes']} |",
        f"| Pages scanned | {s['pages_scanned']} |",
        f"| Cited claim IDs | {s['cited_claim_ids']} |",
        f"| Blog blocked | {s['blog_blocked']} |",
        f"| KB blocked | {s['kb_blocked']} |",
        f"| **Orphaned claims** | **{s['orphaned_count']}** |",
        "",
        "## Claim Dispositions",
        "",
        "| Disposition | Count | % |",
        "|-------------|-------|---|",
    ]
    for d, count in sorted(disp.items(), key=lambda x: -x[1]):
        pct = f"{100 * count / s['total_claims']:.1f}" if s['total_claims'] else "0.0"
        lines.append(f"| {d} | {count} | {pct}% |")

    lines += [
        "",
        "## API Class Dispositions",
        "",
        "| Disposition | Count | % |",
        "|-------------|-------|---|",
    ]
    for d, count in sorted(class_disp.items(), key=lambda x: -x[1]):
        if count == 0:
            continue
        pct = f"{100 * count / s['total_classes']:.1f}" if s['total_classes'] else "0.0"
        lines.append(f"| {d} | {count} | {pct}% |")

    if s["orphaned_count"] > 0:
        lines += [
            "",
            "## Orphaned Claims (operator review required)",
            "",
            "| Claim ID | Kind | Text |",
            "|----------|------|------|",
        ]
        orphaned = [r for r in result["claims"] if r["disposition"] == "ORPHANED"]
        for r in orphaned[:50]:  # cap at 50 in MD; full list in JSON
            text = r["text"][:80].replace("|", "\\|")
            lines.append(f"| `{r['claim_id']}` | {r['kind']} | {text} |")
        if len(orphaned) > 50:
            lines.append(f"| *(+ {len(orphaned) - 50} more — see JSON)* | | |")

    lines += ["", "## Disposition Key", ""]
    defs = {
        "USED_EVIDENCE": "Claim cited in evidence.claims on a content page",
        "SURFACE_ONLY": "Structural API fact expressed in reference page tables",
        "EXCLUDED_THRESHOLD": "Content section blocked by snippet/claim threshold in site plan",
        "EXCLUDED_TIER": "Content section blocked by tier/precondition (e.g. KB tier bug)",
        "EXCLUDED_SKIP": "Cluster explicitly skipped (KB_SKIP_CLUSTERS)",
        "EXCLUDED_LIMITATION": "Intentionally excluded limitation fact",
        "DUPLICATE": "Derived from or overlaps with another claim (Jaccard dedup)",
        "INTENTIONAL": "Operator-marked as not needed",
        "ORPHANED": "No traceable use — requires operator review",
    }
    for d, desc in defs.items():
        lines.append(f"- **{d}**: {desc}")

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "knowledge_coverage.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def run(
    family: str,
    platform: str,
    out_dir: Path | None = None,
    write_md: bool = True,
) -> dict:
    """Run coverage audit. Returns result dict."""
    result = compute_coverage(family, platform)
    s = result["summary"]

    od = out_dir or (REPORTS_ROOT / family / platform)
    json_path = _write_json(result, od)
    print(f"Wrote: {json_path}")

    if write_md:
        md_path = _write_md(result, od)
        print(f"Wrote: {md_path}")

    print()
    print("=== knowledge-coverage-audit summary ===")
    print(f"Family:          {family}")
    print(f"Platform:        {platform}")
    print(f"Total claims:    {s['total_claims']}")
    print(f"Total classes:   {s['total_classes']}")
    print(f"Pages scanned:   {s['pages_scanned']}")
    print(f"Cited claims:    {s['cited_claim_ids']}")
    print()
    print("Claim dispositions:")
    for d, count in sorted(s["claim_dispositions"].items(), key=lambda x: -x[1]):
        if count:
            pct = f"{100 * count / s['total_claims']:.1f}%"
            print(f"  {d:<26} {count:>6}  ({pct})")
    print()
    if s["orphaned_count"] > 0:
        print(f"ORPHANED claims ({s['orphaned_count']}) — operator review required:")
        for cid in s["orphaned_claim_ids"][:20]:
            print(f"  {cid}")
        if len(s["orphaned_claim_ids"]) > 20:
            print(f"  ... and {len(s['orphaned_claim_ids']) - 20} more (see JSON)")
        print()
    else:
        print("No ORPHANED claims.")

    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Per-claim knowledge coverage audit (S-79 backing script)"
    )
    parser.add_argument("family", help="Product family (e.g. cells, email, slides)")
    parser.add_argument("platform", help="Platform (e.g. net, java, python, cpp)")
    parser.add_argument("--out-dir", type=Path, default=None,
                        help="Override output directory")
    parser.add_argument("--no-md", action="store_true",
                        help="Skip writing the Markdown summary")
    parser.add_argument("--json-only", action="store_true",
                        help="Write JSON output only (same as --no-md)")
    args = parser.parse_args()

    write_md = not (args.no_md or args.json_only)
    run(args.family, args.platform, out_dir=args.out_dir, write_md=write_md)


if __name__ == "__main__":
    main()