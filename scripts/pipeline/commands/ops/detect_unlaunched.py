"""detect_unlaunched.py — Scan for products with knowledge but no content.

Reads the knowledge directory for products that have a merged/model.yaml
(indicating a fully bootstrapped knowledge model) but have zero non-draft
content files across all 5 content subdomains.

These "unlaunched" products are invisible to the normal audit/coverage
pipeline and represent missed launch opportunities.

Usage:
    python detect_unlaunched.py [--knowledge-root PATH] [--content-root PATH]
    python detect_unlaunched.py --json  # machine-readable output

Exit codes:
    0  - scan complete (warnings are non-blocking)
"""
from __future__ import annotations

import argparse
import json
import sys
import re
from pathlib import Path

_HERE = Path(__file__).resolve().parent.parent.parent.parent.parent
_KNOWLEDGE_ROOT = _HERE / "knowledge"
_CONTENT_ROOT = _HERE / "content"

# Substantive content subdomains (docs, blog, kb, reference).
# products.aspose.org is a marketing landing page, not developer content,
# so it is tracked separately but does not count toward "launched" status.
_CONTENT_SUBDOMAINS = [
    "docs.aspose.org",
    "blog.aspose.org",
    "kb.aspose.org",
    "reference.aspose.org",
]
_MARKETING_SUBDOMAINS = [
    "products.aspose.org",
]

# Subdomain-specific subdirectory patterns for family/platform content
# Docs/KB/Reference use content/{subdomain}/en/{family}/{platform}/
# Blog uses content/blog.aspose.org/{family}/{platform}/
# Products uses content/products.aspose.org/en/{family}/ (no platform subdir)
_SUBDOMAIN_PATTERNS = {
    "docs.aspose.org": "en/{family}/{platform}",
    "blog.aspose.org": "{family}/{platform}",
    "kb.aspose.org": "en/{family}/{platform}",
    "products.aspose.org": "en/{family}",
    "reference.aspose.org": "en/{family}/{platform}",
}

_DRAFT_PATTERN = re.compile(r"^draft:\s*true", re.MULTILINE)


def _count_non_draft_pages(content_dir: Path) -> int:
    """Count .md files in a directory tree that are NOT draft:true."""
    if not content_dir.exists():
        return 0
    count = 0
    for md in content_dir.rglob("*.md"):
        try:
            text = md.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not _DRAFT_PATTERN.search(text[:500]):  # only scan frontmatter area
            count += 1
    return count


def _load_model_yaml(model_path: Path) -> dict:
    """Parse a model.yaml file into a dict (minimal YAML parser for known keys)."""
    data: dict = {}
    try:
        text = model_path.read_text(encoding="utf-8")
    except OSError:
        return data
    for line in text.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            data[key.strip()] = val.strip().strip("'\"")
    return data


def _scan_products(knowledge_root: Path, content_root: Path) -> list[dict]:
    """Scan for products with any model.yaml and count their content pages.

    Checks both merged/model.yaml (fully promoted) and scout/model.yaml
    (scouted but not yet promoted). Scout-only products are flagged with
    a 'scout_only' marker to indicate they need /truth-merge before launch.
    """
    results = []
    if not knowledge_root.exists():
        return results

    for family_dir in sorted(knowledge_root.iterdir()):
        if not family_dir.is_dir() or family_dir.name.startswith("_"):
            continue
        family = family_dir.name
        for platform_dir in sorted(family_dir.iterdir()):
            if not platform_dir.is_dir():
                continue
            platform = platform_dir.name
            merged_model = platform_dir / "merged" / "model.yaml"
            scout_model = platform_dir / "scout" / "model.yaml"

            if merged_model.exists():
                model = _load_model_yaml(merged_model)
                scout_only = False
            elif scout_model.exists():
                model = _load_model_yaml(scout_model)
                scout_only = True
            else:
                continue

            # Count substantive content pages (docs/blog/kb/reference only)
            total_pages = 0
            subdomain_counts = {}
            for subdomain in _CONTENT_SUBDOMAINS + _MARKETING_SUBDOMAINS:
                pattern = _SUBDOMAIN_PATTERNS[subdomain]
                rel_path = pattern.format(family=family, platform=platform)
                content_dir = content_root / subdomain / rel_path
                count = _count_non_draft_pages(content_dir)
                subdomain_counts[subdomain] = count
                if subdomain in _CONTENT_SUBDOMAINS:
                    total_pages += count

            results.append({
                "family": family,
                "platform": platform,
                "total_pages": total_pages,
                "subdomain_counts": subdomain_counts,
                "scout_only": scout_only,
                "class_count": _parse_int(None, "class_count", model),
                "total_claims": _parse_int(None, "total_claims", model),
                "stale_since": model.get("stale_since", ""),
                "repo_sha": model.get("repo_sha", ""),
            })

    return results


def _parse_int(stats_dict, key, model_dict) -> int:
    """Extract integer stat from model.yaml — handles both flat and nested formats."""
    # model.yaml stats block is multi-line nested YAML; our minimal parser flattens it
    # so values like "class_count: 42" appear directly in model_dict
    val = model_dict.get(key, 0)
    if isinstance(val, int):
        return val
    try:
        return int(val)
    except (TypeError, ValueError):
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Detect products with knowledge but no content (unlaunched)."
    )
    parser.add_argument("--knowledge-root", type=str, default=None,
                        help="Override default knowledge root path")
    parser.add_argument("--content-root", type=str, default=None,
                        help="Override default content root path")
    parser.add_argument("--json", action="store_true",
                        help="Output machine-readable JSON")
    parser.add_argument("--threshold", type=int, default=0,
                        help="Page count threshold below which a product is 'unlaunched' (default: 0)")
    args = parser.parse_args(argv)

    knowledge_root = Path(args.knowledge_root) if args.knowledge_root else _KNOWLEDGE_ROOT
    content_root = Path(args.content_root) if args.content_root else _CONTENT_ROOT

    products = _scan_products(knowledge_root, content_root)
    unlaunched = [p for p in products if p["total_pages"] <= args.threshold]
    launched = [p for p in products if p["total_pages"] > args.threshold]

    if args.json:
        print(json.dumps({
            "unlaunched": unlaunched,
            "launched_count": len(launched),
            "total_products": len(products),
        }, indent=2, ensure_ascii=False))
        return 0

    # Human-readable output
    print(f"[detect-unlaunched] Scanned {len(products)} products with merged knowledge.")
    print(f"[detect-unlaunched] Launched: {len(launched)}  Unlaunched: {len(unlaunched)}")

    if unlaunched:
        print()
        print("[detect-unlaunched] WARN: The following products have knowledge but no content:")
        for p in unlaunched:
            family = p["family"]
            platform = p["platform"]
            classes = p["class_count"]
            claims = p["total_claims"]
            stale = p["stale_since"] or "current"
            scout_tag = " [scout-only — run /truth-merge first]" if p.get("scout_only") else ""
            print(f"  UNLAUNCHED  {family}/{platform}  "
                  f"({classes} classes, {claims} claims, stale_since={stale}){scout_tag}")
            for subdomain, count in p["subdomain_counts"].items():
                if count > 0:
                    print(f"    {subdomain}: {count} pages")
        print()
        print("[detect-unlaunched] ACTION: Run /launch-product {family} {platform} to generate content.")
    else:
        print("[detect-unlaunched] OK: all products with merged knowledge have content.")

    # Always exit 0 — this check is advisory/non-blocking
    return 0


if __name__ == "__main__":
    sys.exit(main())
