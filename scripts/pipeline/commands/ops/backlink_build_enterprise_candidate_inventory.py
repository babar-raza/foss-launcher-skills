"""
backlink_build_enterprise_candidate_inventory.py — Layer 0.4

Builds a normalized enterprise target candidate inventory by reading
data/aspose_com_targets.json (all_urls) and grouping variant slugs by
their canonical base platform per family and subdomain.

Output: data/backlinks/workspace/enterprise_target_candidate_inventory.json (gitignored)

Usage:
    python backlink_build_enterprise_candidate_inventory.py [--subdomain reference] [--output PATH]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

# Resolve repo root
REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline"))

from lib.backlink_targets import PLATFORM_ALIASES, load_target_map


def build_inventory(target_map: dict, subdomain_filter: str | None = None) -> dict:
    """
    Build candidate inventory from target_map["all_urls"].

    Returns:
        {
            "subdomain": {
                "family": {
                    "canonical_platform": {
                        "canonical_slug": str,
                        "variants": [{"slug": str, "path": str, "url": str|None, "http_status": int}],
                        "exact_slug_verified": bool
                    }
                }
            }
        }
    """
    all_urls: dict = target_map.get("all_urls", {})
    # group by (subdomain_key, family, canonical_platform) -> list of variant entries
    # URL format: https://subdomain.aspose.com/family/platform/...
    inventory: dict = {}

    SUBDOMAIN_KEYS = {
        "reference.aspose.com": "reference",
        "docs.aspose.com": "docs",
        "kb.aspose.com": "kb",
        "products.aspose.com": "products",
        "blog.aspose.com": "blog",
    }

    # We only care about platform-root level URLs (depth 4: https://host/family/platform/)
    # Pattern: https://{host}/{family}/{slug}/
    for url, entry in all_urls.items():
        parts = url.rstrip("/").split("/")
        # parts: ['https:', '', 'host', 'family', 'slug']
        if len(parts) != 5:
            continue
        host = parts[2]
        sd_key = SUBDOMAIN_KEYS.get(host)
        if sd_key is None:
            continue
        if subdomain_filter and sd_key != subdomain_filter:
            continue
        family = parts[3]
        slug = parts[4]
        canonical = PLATFORM_ALIASES.get(slug)
        if canonical is None:
            continue  # unknown slug — skip

        if sd_key not in inventory:
            inventory[sd_key] = {}
        if family not in inventory[sd_key]:
            inventory[sd_key][family] = {}
        if canonical not in inventory[sd_key][family]:
            inventory[sd_key][family][canonical] = {
                "canonical_slug": canonical,
                "variants": [],
                "exact_slug_verified": False,
            }

        rec = inventory[sd_key][family][canonical]
        http_status = entry.get("http_status", 0)
        rec["variants"].append({
            "slug": slug,
            "path": f"{sd_key}/{family}/{slug}",
            "url": url,
            "http_status": http_status,
        })
        # Mark exact_slug_verified if the slug exactly matches the canonical key
        if slug == canonical and http_status == 200:
            rec["exact_slug_verified"] = True

    return inventory


def main() -> None:
    parser = argparse.ArgumentParser(description="Build enterprise target candidate inventory (Layer 0.4)")
    parser.add_argument("--subdomain", default=None, help="Filter to one subdomain key (e.g. reference)")
    parser.add_argument(
        "--output",
        default=str(REPO_ROOT / "data" / "backlinks" / "workspace" / "enterprise_target_candidate_inventory.json"),
    )
    parser.add_argument("--dry-run", action="store_true", help="Print summary; do not write")
    args = parser.parse_args()

    map_path = REPO_ROOT / "data" / "aspose_com_targets.json"
    if not map_path.exists():
        print(f"ERROR: target map not found at {map_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading target map from {map_path} ...")
    target_map = load_target_map(REPO_ROOT)

    print(f"Building inventory (subdomain={args.subdomain or 'all'}) ...")
    inventory = build_inventory(target_map, subdomain_filter=args.subdomain)

    # Summary
    total_families = sum(len(fams) for fams in inventory.values())
    total_canonical = sum(
        len(plats) for fams in inventory.values() for plats in fams.values()
    )
    total_variants = sum(
        len(rec["variants"])
        for fams in inventory.values()
        for plats in fams.values()
        for rec in plats.values()
    )
    print(
        f"Inventory: {len(inventory)} subdomains, {total_families} families, "
        f"{total_canonical} canonical platforms, {total_variants} variant URLs"
    )

    if args.dry_run:
        print("Dry-run: output not written.")
        return

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({"schema_version": "1.0.0", "inventory": inventory}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Written: {out_path}")


if __name__ == "__main__":
    main()
