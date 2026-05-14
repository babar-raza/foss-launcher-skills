"""Deterministic semantic content audit — classifies prose by evidence tier.

Extracts every prose paragraph from content files and classifies each against
the knowledge model: SUPPORTED, PROBABLE, WEAK, UNSUPPORTED, or CONTRADICTED.
Code blocks are delegated to audit.py's verify_tokens for API accuracy.

Usage:
    python scripts/pipeline/content_audit.py {family} {platform}
    python scripts/pipeline/content_audit.py --files path1.md path2.md
    python scripts/pipeline/content_audit.py all --json

Exit codes:
    0  No CONTRADICTED findings
    1  One or more CONTRADICTED findings
"""
import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Resolve imports from sibling modules (audit.py, content_eval)
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

# --- Standalone repo path resolution via config_loader ---
_HERE = Path(__file__).resolve().parent
_PIPELINE = _HERE.parents[1]
_SCRIPTS = _HERE.parents[2]
_COMMANDS = _HERE.parent
import sys as _sys
for _path in (
    _SCRIPTS,
    _PIPELINE,
    _PIPELINE / "content_eval",
    _COMMANDS / "knowledge",
    _COMMANDS / "ops",
):
    if str(_path) not in _sys.path:
        _sys.path.insert(0, str(_path))
from config_loader import (                       # noqa: E402
    resolve_knowledge_root as _resolve_knowledge_root,
    resolve_content_repo as _resolve_content_repo,
)
# --------------------------------------------------------

from knowledge_core import (  # noqa: E402
    Knowledge,
    discover_content,
    discover_products,
    infer_product,
    PLATFORM_MAP,
)
from token_ops import extract_tokens, verify_tokens  # noqa: E402
from content_eval.models import Page  # noqa: E402


def _log(*args, **kwargs):
    """Print to stderr so stdout stays clean for --json."""
    print(*args, file=sys.stderr, **kwargs)


KNOWLEDGE_ROOT = _resolve_knowledge_root()
REPORTS_DIR = Path("reports") / "audit"

# ---------------------------------------------------------------------------
# Regex helpers (reuse patterns from prose_truth / forbidden_claims)
# ---------------------------------------------------------------------------
_API_REF_RE = re.compile(r"`(\w+(?:\.\w+)*)`")
_FORMAT_CLAIM_RE = re.compile(
    r"(?:supports?|import|export|convert|load|save|read|write)\w*\s+"
    r"(?:the\s+)?(?:to\s+|from\s+)?(\w{2,6})\s+(?:format|file|document)",
    re.IGNORECASE,
)


def _tokenize(text: str) -> set[str]:
    """Extract lowercase word tokens (3+ chars)."""
    return set(re.findall(r"[a-z][a-z0-9_]+", text.lower()))


# ---------------------------------------------------------------------------
# Knowledge helpers
# ---------------------------------------------------------------------------
def _load_claims(family: str, platform: str) -> list[dict]:
    path = KNOWLEDGE_ROOT / family / platform / "merged" / "claims.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, KeyError):
        return []


def _load_formats(family: str, platform: str) -> list[dict]:
    path = KNOWLEDGE_ROOT / family / platform / "merged" / "formats.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, KeyError):
        return []


def _load_forbidden_claims(family: str, platform: str) -> list[str]:
    index_path = KNOWLEDGE_ROOT / family / platform / "merged" / "index.json"
    if not index_path.exists():
        return []
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
        return data.get("forbidden_claims", [])
    except (json.JSONDecodeError, KeyError):
        return []


# ---------------------------------------------------------------------------
# Paragraph classifier
# ---------------------------------------------------------------------------
TIER_SUPPORTED = "SUPPORTED"
TIER_PROBABLE = "PROBABLE"
TIER_WEAK = "WEAK"
TIER_UNSUPPORTED = "UNSUPPORTED"
TIER_CONTRADICTED = "CONTRADICTED"


def _classify_paragraph(
    line_no: int,
    text: str,
    knowledge: Knowledge,
    claim_tokens: list[tuple[str, set[str]]],
    forbidden_tokens: list[tuple[str, set[str]]],
    format_support: dict[str, str],
) -> dict:
    """Classify a single prose paragraph against knowledge.

    Returns a dict with keys: line_no, text, tier, details.
    """
    details = []
    tokens = _tokenize(text)

    # --- 1. Check forbidden claims (token overlap >= 0.7) ---
    for fc_text, fc_toks in forbidden_tokens:
        if len(fc_toks) < 2:
            continue
        overlap = tokens & fc_toks
        if len(overlap) >= len(fc_toks) * 0.7 and len(overlap) >= 3:
            return {
                "line_no": line_no,
                "text": text,
                "tier": TIER_CONTRADICTED,
                "details": [f"Matches forbidden claim: \"{fc_text}\""],
            }

    # --- 2. Extract and verify API references (backtick identifiers) ---
    api_refs = _API_REF_RE.findall(text)
    api_verified = True
    api_checked = False
    if api_refs and knowledge.available:
        for ref in api_refs:
            parts = ref.split(".")
            cls_name = parts[0]
            if cls_name not in knowledge.classes:
                continue  # Not a known class — skip, don't penalize
            api_checked = True
            if len(parts) >= 2:
                member = parts[1]
                if not knowledge.has_method(cls_name, member) and \
                   not knowledge.has_property(cls_name, member):
                    api_verified = False
                    details.append(f"API ref `{ref}` member not found in knowledge")

    # --- 3. Check format claims against formats.json ---
    format_ok = True
    for m in _FORMAT_CLAIM_RE.finditer(text):
        claimed = m.group(1).lower()
        if claimed in format_support:
            direction = format_support[claimed]
            text_lower = text.lower()
            if "export" in text_lower and direction == "import":
                format_ok = False
                details.append(f"Claims {claimed.upper()} export but knowledge shows import-only")
            elif "import" in text_lower and direction == "export":
                format_ok = False
                details.append(f"Claims {claimed.upper()} import but knowledge shows export-only")

    if not format_ok:
        return {
            "line_no": line_no,
            "text": text,
            "tier": TIER_CONTRADICTED,
            "details": details,
        }

    # --- 4. Compute token overlap with claims ---
    best_overlap = 0.0
    best_claim = ""
    for claim_text, ct in claim_tokens:
        if not ct:
            continue
        overlap = len(tokens & ct) / max(len(ct), 1)
        if overlap > best_overlap:
            best_overlap = overlap
            best_claim = claim_text

    # --- 5. Classify tier ---
    if api_checked and api_verified and best_overlap >= 0.5:
        tier = TIER_SUPPORTED
        details.append(f"API refs verified, claim overlap {best_overlap:.2f}")
    elif api_checked and api_verified:
        tier = TIER_PROBABLE
        details.append(f"API refs verified, claim overlap {best_overlap:.2f}")
    elif best_overlap >= 0.5:
        tier = TIER_PROBABLE
        details.append(f"Claim overlap {best_overlap:.2f} with: \"{best_claim[:80]}\"")
    elif best_overlap >= 0.3:
        tier = TIER_PROBABLE
        details.append(f"Claim overlap {best_overlap:.2f}")
    elif best_overlap > 0:
        tier = TIER_WEAK
        details.append(f"Low claim overlap {best_overlap:.2f}")
    else:
        tier = TIER_UNSUPPORTED
        details.append("No matching evidence found")

    return {
        "line_no": line_no,
        "text": text,
        "tier": tier,
        "details": details,
    }


# ---------------------------------------------------------------------------
# Audit a single page
# ---------------------------------------------------------------------------
def audit_page(page: Page, knowledge: Knowledge) -> dict:
    """Audit a page, returning structured results.

    Returns dict with keys: file, paragraphs, code_findings, summary.
    """
    family = page.family or knowledge.family
    platform = page.platform or knowledge.platform

    # Load knowledge artifacts
    claims = _load_claims(family, platform)
    forbidden = _load_forbidden_claims(family, platform)
    formats = _load_formats(family, platform)

    # Pre-compute token sets
    claim_tokens = [
        (c.get("text", ""), _tokenize(c.get("text", "")))
        for c in claims if c.get("text")
    ]
    forbidden_tokens = [
        (fc, _tokenize(fc)) for fc in forbidden if len(fc) > 5
    ]
    format_support: dict[str, str] = {}
    for fmt in formats:
        ext = (fmt.get("format") or fmt.get("ext") or "").lower()
        direction = (fmt.get("direction") or fmt.get("support") or "").lower()
        if ext:
            format_support[ext] = direction

    # Classify each prose paragraph
    paragraphs = []
    for line_no, text in page.prose_lines:
        if len(_tokenize(text)) < 3:
            continue  # Skip trivially short lines
        result = _classify_paragraph(
            line_no, text, knowledge, claim_tokens, forbidden_tokens, format_support
        )
        paragraphs.append(result)

    # Verify code blocks via audit.py's token extraction
    code_findings = []
    if knowledge.available:
        tokens = extract_tokens(page.filepath, knowledge.platform)
        findings = verify_tokens(tokens, knowledge, str(page.filepath))
        for f in findings:
            code_findings.append({
                "level": f.level,
                "line_no": f.line_no,
                "message": f.message,
                "suggestion": getattr(f, "suggestion", ""),
            })

    # Summary stats
    tier_counts = defaultdict(int)
    for p in paragraphs:
        tier_counts[p["tier"]] += 1
    total = len(paragraphs)

    summary = {
        "total_paragraphs": total,
        "tiers": {},
    }
    for tier in [TIER_SUPPORTED, TIER_PROBABLE, TIER_WEAK, TIER_UNSUPPORTED, TIER_CONTRADICTED]:
        count = tier_counts.get(tier, 0)
        pct = round(count / total * 100, 1) if total else 0.0
        summary["tiers"][tier] = {"count": count, "percent": pct}

    summary["code_issues"] = len(code_findings)

    return {
        "file": str(page.filepath),
        "paragraphs": paragraphs,
        "code_findings": code_findings,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="content_audit",
        description="Deterministic semantic content audit (S-32)",
    )
    parser.add_argument("target", nargs="*", default=[],
                        help="'family platform', 'all', or omit when using --files")
    parser.add_argument("--files", nargs="+",
                        help="Specific .md files to audit")
    parser.add_argument("--json", action="store_true",
                        help="Machine-readable JSON output")
    args = parser.parse_args(argv)

    # --- Resolve pages and knowledge ---
    pages_by_product: dict[tuple[str, str], list[Page]] = {}

    if args.files:
        from content_eval.loader import load_files  # noqa: E402
        pages = load_files(args.files)
        for page in pages:
            fam = page.family
            plat = page.platform
            if fam and plat:
                plat = PLATFORM_MAP.get(plat, plat)
                pages_by_product.setdefault((fam, plat), []).append(page)
            else:
                fam2, plat2 = infer_product(page.filepath)
                if fam2 and plat2:
                    pages_by_product.setdefault((fam2, plat2), []).append(page)
                else:
                    _log(f"Cannot infer product for {page.filepath}, skipping")
    elif args.target == ["all"] or (len(args.target) == 1 and args.target[0] == "all"):
        products = discover_products()
        for family, platform in products:
            files = discover_content(family, platform)
            if files:
                pages = [Page.load(f) for f in files]
                pages_by_product[(family, platform)] = pages
    elif len(args.target) == 2:
        family, platform = args.target
        platform = PLATFORM_MAP.get(platform, platform)
        files = discover_content(family, platform)
        pages = [Page.load(f) for f in files]
        pages_by_product[(family, platform)] = pages
    else:
        parser.print_help()
        sys.exit(0)

    if not pages_by_product:
        _log("No pages found to audit")
        sys.exit(0)

    # --- Run audit ---
    all_results = []
    has_contradicted = False

    for (family, platform), pages in sorted(pages_by_product.items()):
        _log(f"Auditing {family}/{platform}: {len(pages)} pages")
        knowledge = Knowledge(family, platform)

        for page in pages:
            result = audit_page(page, knowledge)
            all_results.append(result)
            if result["summary"]["tiers"].get(TIER_CONTRADICTED, {}).get("count", 0) > 0:
                has_contradicted = True

    # --- Output ---
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "files_audited": len(all_results),
        "results": all_results,
    }

    # Aggregate summary
    agg = defaultdict(int)
    total_paragraphs = 0
    total_code_issues = 0
    for r in all_results:
        s = r["summary"]
        total_paragraphs += s["total_paragraphs"]
        total_code_issues += s["code_issues"]
        for tier, info in s["tiers"].items():
            agg[tier] += info["count"]

    report["aggregate"] = {
        "total_paragraphs": total_paragraphs,
        "total_code_issues": total_code_issues,
        "tiers": {
            tier: {
                "count": agg.get(tier, 0),
                "percent": round(agg.get(tier, 0) / total_paragraphs * 100, 1) if total_paragraphs else 0.0,
            }
            for tier in [TIER_SUPPORTED, TIER_PROBABLE, TIER_WEAK, TIER_UNSUPPORTED, TIER_CONTRADICTED]
        },
    }

    if args.json:
        sys.stdout.buffer.write(json.dumps(report, indent=2, ensure_ascii=False).encode("utf-8"))
        sys.stdout.buffer.write(b"\n")
    else:
        # Human-readable summary
        print(f"Content Audit — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print(f"Files: {len(all_results)}  |  Paragraphs: {total_paragraphs}  |  Code issues: {total_code_issues}")
        print()
        for tier in [TIER_SUPPORTED, TIER_PROBABLE, TIER_WEAK, TIER_UNSUPPORTED, TIER_CONTRADICTED]:
            info = report["aggregate"]["tiers"][tier]
            print(f"  {tier:14s}: {info['count']:4d}  ({info['percent']:.1f}%)")
        print()

        # Show CONTRADICTED details
        for r in all_results:
            contras = [p for p in r["paragraphs"] if p["tier"] == TIER_CONTRADICTED]
            if contras:
                print(f"CONTRADICTED in {r['file']}:")
                for p in contras:
                    print(f"  L{p['line_no']}: {p['text'][:100]}")
                    for d in p["details"]:
                        print(f"    → {d}")
                print()

    # Write report file
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    # Determine label
    if len(pages_by_product) == 1:
        (fam, plat) = list(pages_by_product.keys())[0]
        label = f"{fam}-{plat}"
    else:
        label = "batch"
    report_path = REPORTS_DIR / f"{label}-content-audit-{timestamp}.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    _log(f"Report written to {report_path}")

    sys.exit(1 if has_contradicted else 0)


if __name__ == "__main__":
    main()
