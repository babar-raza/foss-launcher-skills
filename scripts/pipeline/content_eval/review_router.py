"""review_router.py — GW-01: Automated Tier 1 human review routing.

Classifies content pages into risk tiers and generates a review queue for
pages that require human review before publication.

Risk tiers (from AGENTS.md §7b):
  Tier 1: Code-heavy reference, blog posts, capability claims → full human review
  Tier 2: Docs, KB how-to, FAQ → spot-check (5 pages per platform)
  Tier 3: Locale files, structural pages, products landing → automated gates only

Usage:
  python -m content_eval.review_router slides net
  python -m content_eval.review_router --all
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Resolve project root for sibling imports
_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
_LIB_DIR = str(Path(_HERE) / "lib") if isinstance(_HERE, str) else str(_HERE / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from content_discovery import _REPO_ROOT  # noqa: E402

CONTENT_ROOT = _REPO_ROOT / "content"


# ---------------------------------------------------------------------------
# Tier classification constants
# ---------------------------------------------------------------------------

# Tier 1 triggers (AGENTS.md §7b): any of these → full human review
_TIER1_SUBDOMAINS = {"blog", "reference"}
_TIER1_PAGE_ROLES = {"blog", "reference"}

# Capability-claim patterns in prose that trigger Tier 1
_CAPABILITY_CLAIM_RE = re.compile(
    r"\b(?:support(?:s|ed)?|convert|export|import|render|generate|create|"
    r"manipulate|process|extract|merge|split)\b.*\b(?:format|file|document)\b",
    re.IGNORECASE,
)

# Code block detection (>= 2 code blocks with API calls → Tier 1)
_CODE_FENCE_RE = re.compile(r"^```\w+", re.MULTILINE)
_API_CALL_RE = re.compile(r"\b[A-Z][A-Za-z]+\s*\.\s*[a-z_]\w*\s*\(")

# Tier 3 indicators: locale files, structural pages
_TIER3_PATTERNS = {
    "/_index.md",  # section index (structural)
    "/locale/",    # locale files
}


def classify_tier(filepath: Path, frontmatter: dict, body: str) -> int:
    """Classify a page into risk tier 1, 2, or 3.

    Returns:
        1: Full human review required
        2: Spot-check sampling
        3: Automated gates only
    """
    rel = str(filepath).replace("\\", "/")

    # Tier 3: locale files and structural pages
    for pattern in _TIER3_PATTERNS:
        if pattern in rel:
            # Exception: products _index.md pages have capability claims
            if "products.aspose.org" in rel and pattern == "/_index.md":
                break  # fall through to further checks
            return 3

    # Detect subdomain
    subdomain = ""
    for sd in ("blog", "reference", "docs", "kb", "products"):
        if f"{sd}.aspose.org" in rel:
            subdomain = sd
            break

    # Tier 1: blog and reference subdomains
    if subdomain in _TIER1_SUBDOMAINS:
        return 1

    # Tier 1: pages with code blocks containing API calls
    code_blocks = _CODE_FENCE_RE.findall(body)
    if len(code_blocks) >= 2:
        api_calls = _API_CALL_RE.findall(body)
        if len(api_calls) >= 3:
            return 1

    # Tier 1: capability claims in products pages
    if subdomain == "products" and _CAPABILITY_CLAIM_RE.search(body):
        return 1

    # Tier 2: docs and KB
    if subdomain in ("docs", "kb"):
        return 2

    # Default: Tier 2
    return 2


def _needs_review(tier: int, frontmatter: dict) -> bool:
    """Determine if a page needs human review based on tier and state.

    Tier 1 pages always need review unless already reviewed.
    Tier 2 pages need review only if they have WARN/FAIL findings.
    Tier 3 pages never need human review.
    """
    if tier == 3:
        return False

    # Already reviewed? Check frontmatter
    if frontmatter.get("human_reviewed"):
        return False

    if tier == 1:
        return True

    # Tier 2: only if grade is below B or has WARN/FAIL findings
    grade = frontmatter.get("grade", "")
    if grade in ("C", "D", "F"):
        return True

    return False


def route_pages(family: str, platform: str) -> list[dict[str, Any]]:
    """Classify all pages for a product and return the review queue.

    Returns a list of dicts: {path, tier, needs_review, reason, subdomain}
    """
    import yaml

    _FM_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)

    queue: list[dict[str, Any]] = []

    # Scan all content subdomains for this family/platform
    for sd in ("products", "docs", "kb", "reference", "blog"):
        if sd == "products":
            content_dir = CONTENT_ROOT / f"{sd}.aspose.org" / "en" / family
        elif sd == "blog":
            content_dir = CONTENT_ROOT / f"{sd}.aspose.org" / family / platform
        else:
            content_dir = CONTENT_ROOT / f"{sd}.aspose.org" / "en" / family / platform

        if not content_dir.exists():
            continue

        for md_file in content_dir.rglob("*.md"):
            rel = str(md_file.relative_to(CONTENT_ROOT)).replace("\\", "/")
            try:
                raw = md_file.read_text(encoding="utf-8")
            except OSError:
                continue

            # Parse frontmatter
            fm: dict = {}
            body = raw
            m = _FM_RE.match(raw)
            if m:
                try:
                    fm = yaml.safe_load(m.group(1)) or {}
                except yaml.YAMLError:
                    pass
                body = raw[m.end():]

            tier = classify_tier(md_file, fm, body)
            review = _needs_review(tier, fm)

            reason = ""
            if tier == 1:
                reason = "Tier 1: requires full human review"
            elif review:
                reason = f"Tier 2: grade {fm.get('grade', 'unknown')} needs spot-check"

            queue.append({
                "path": rel,
                "tier": tier,
                "needs_review": review,
                "reason": reason,
                "subdomain": sd,
                "grade": fm.get("grade", ""),
            })

    return queue


def write_review_queue(family: str, platform: str, output_dir: Path | None = None) -> Path:
    """Generate and write the review queue JSON for a product."""
    queue = route_pages(family, platform)
    needs_review = [p for p in queue if p["needs_review"]]

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "family": family,
        "platform": platform,
        "total_pages": len(queue),
        "tier_1_count": sum(1 for p in queue if p["tier"] == 1),
        "tier_2_count": sum(1 for p in queue if p["tier"] == 2),
        "tier_3_count": sum(1 for p in queue if p["tier"] == 3),
        "needs_review_count": len(needs_review),
        "pages_needing_review": needs_review,
    }

    if output_dir is None:
        output_dir = Path("reports") / "review-queue"
    output_dir.mkdir(parents=True, exist_ok=True)

    out_path = output_dir / f"{family}_{platform}_review_queue.json"
    out_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return out_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="GW-01: Classify pages into risk tiers and generate human review queue"
    )
    parser.add_argument("family", help="Product family (e.g. slides, cells)")
    parser.add_argument("platform", help="Platform (e.g. net, python, java)")
    parser.add_argument("--output-dir", type=Path, default=None,
                        help="Output directory for review queue JSON")
    parser.add_argument("--summary", action="store_true",
                        help="Print summary to stdout")

    args = parser.parse_args()

    out_path = write_review_queue(args.family, args.platform, args.output_dir)
    print(f"Review queue written to: {out_path}")

    if args.summary:
        data = json.loads(out_path.read_text(encoding="utf-8"))
        print(f"\nTotal pages: {data['total_pages']}")
        print(f"  Tier 1 (full review): {data['tier_1_count']}")
        print(f"  Tier 2 (spot-check):  {data['tier_2_count']}")
        print(f"  Tier 3 (automated):   {data['tier_3_count']}")
        print(f"  Needs review: {data['needs_review_count']}")
        if data["pages_needing_review"]:
            print("\nPages needing human review:")
            for p in data["pages_needing_review"][:20]:
                print(f"  [{p['tier']}] {p['path']} — {p['reason']}")
            if len(data["pages_needing_review"]) > 20:
                print(f"  ... and {len(data['pages_needing_review']) - 20} more")


if __name__ == "__main__":
    main()