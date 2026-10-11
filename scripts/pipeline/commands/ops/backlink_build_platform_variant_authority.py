"""
backlink_build_platform_variant_authority.py — Layer 0.6

Reads Layer 0.4 (enterprise_target_candidate_inventory.json) plus
platform_canonical_overrides.yaml and builds a deterministic per-request-key
variant authority.

Selection policy (in order):
  1. Exact slug HTTP 200 in inventory -> AUTO_APPROVE_EXACT
  2. Explicit canonical override in YAML -> EXPLICIT_OVERRIDE
  3. Single verified variant in inventory -> AUTO_APPROVE_SINGLE_VARIANT
  4. Multiple verified variants, no policy -> REVIEW_REQUIRED (BLOCKED for generation)
  5. No verified variants -> VARIANT_CANDIDATES_NOT_IN_MAP (fall through to A3)

Output: data/backlinks/workspace/platform_variant_authority.json (gitignored)

Usage:
    python backlink_build_platform_variant_authority.py [--subdomain reference] [--output PATH]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline"))

from lib.backlink_targets import HOST_MAP


def _load_inventory(path: Path) -> dict:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("inventory", data)


def _load_overrides(path: Path) -> dict:
    if not path.exists():
        return {}
    import yaml
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return raw.get("overrides", {})


def build_variant_authority(inventory: dict, overrides: dict) -> list:
    """
    For each (subdomain, family, canonical_platform) entry in the inventory,
    produce exactly one authority record per request_key.
    """
    records: list = []

    for sd_key, families in inventory.items():
        for family, canonicals in families.items():
            for canonical, rec in canonicals.items():
                variants = rec.get("variants", [])
                exact_verified = rec.get("exact_slug_verified", False)

                # Build request_key for the canonical (local) platform
                request_key = f"{sd_key}/{family}/{canonical}"

                # Collect verified variant slugs
                verified_variants = [v for v in variants if v.get("http_status") == 200]

                # Step 1: Exact slug verified?
                if exact_verified:
                    target_url = f"https://{HOST_MAP.get(sd_key, sd_key + '.aspose.com')}/{family}/{canonical}/"
                    records.append({
                        "request_key": request_key,
                        "source_prefix": sd_key,
                        "family": family,
                        "local_slug": canonical,
                        "canonical_base": canonical,
                        "expected_path": f"{sd_key}/{family}/{canonical}",
                        "expected_status": "verified_200",
                        "canonical_target_path": f"{sd_key}/{family}/{canonical}",
                        "canonical_target_url": target_url,
                        "decision": "AUTO_APPROVE_EXACT",
                        "allowed_for_generation": True,
                        "alternatives": [{"slug": v["slug"], "status": "verified_200" if v["http_status"] == 200 else "missing_or_unverified"} for v in variants],
                        "selection_reason": "exact_slug_verified_in_all_urls",
                        "review_reason": None,
                    })
                    # Also add request_keys for each bridge variant slug
                    for v in variants:
                        if v["slug"] != canonical:
                            bridge_rk = f"{sd_key}/{family}/{v['slug']}"
                            bridge_status = "verified_200" if v["http_status"] == 200 else "missing_or_unverified"
                            bridge_url = v.get("url") if v["http_status"] == 200 else None
                            records.append({
                                "request_key": bridge_rk,
                                "source_prefix": sd_key,
                                "family": family,
                                "local_slug": v["slug"],
                                "canonical_base": canonical,
                                "expected_path": v["path"],
                                "expected_status": bridge_status,
                                "canonical_target_path": v["path"] if v["http_status"] == 200 else None,
                                "canonical_target_url": bridge_url,
                                "decision": "AUTO_APPROVE_EXACT" if v["http_status"] == 200 else "BLOCKED",
                                "allowed_for_generation": v["http_status"] == 200,
                                "alternatives": [],
                                "selection_reason": "bridge_slug_exact_verified" if v["http_status"] == 200 else None,
                                "review_reason": None if v["http_status"] == 200 else "bridge_slug_not_verified",
                            })
                    continue

                # Step 2: Explicit canonical override?
                ovr = overrides.get(request_key)
                if ovr and ovr.get("http_verified") and ovr.get("canonical_target_url"):
                    records.append({
                        "request_key": request_key,
                        "source_prefix": sd_key,
                        "family": family,
                        "local_slug": canonical,
                        "canonical_base": canonical,
                        "expected_path": f"{sd_key}/{family}/{canonical}",
                        "expected_status": "override",
                        "canonical_target_path": None,
                        "canonical_target_url": ovr["canonical_target_url"],
                        "decision": "EXPLICIT_OVERRIDE",
                        "allowed_for_generation": True,
                        "alternatives": [{"slug": v["slug"], "status": "verified_200" if v["http_status"] == 200 else "missing"} for v in variants],
                        "selection_reason": "explicit_canonical_override",
                        "review_reason": None,
                    })
                    continue

                # Step 3: Single verified variant auto-select?
                if len(verified_variants) == 1:
                    v = verified_variants[0]
                    records.append({
                        "request_key": request_key,
                        "source_prefix": sd_key,
                        "family": family,
                        "local_slug": canonical,
                        "canonical_base": canonical,
                        "expected_path": f"{sd_key}/{family}/{canonical}",
                        "expected_status": "missing_404",
                        "canonical_target_path": v["path"],
                        "canonical_target_url": v["url"],
                        "decision": "AUTO_APPROVE_SINGLE_VARIANT",
                        "allowed_for_generation": True,
                        "alternatives": [{"slug": v["slug"], "status": "verified_200"}],
                        "selection_reason": "single_verified_variant_auto_select",
                        "review_reason": None,
                    })
                    continue

                # Step 4: Multiple verified variants -> REVIEW_REQUIRED
                if len(verified_variants) > 1:
                    records.append({
                        "request_key": request_key,
                        "source_prefix": sd_key,
                        "family": family,
                        "local_slug": canonical,
                        "canonical_base": canonical,
                        "expected_path": f"{sd_key}/{family}/{canonical}",
                        "expected_status": "missing_404",
                        "canonical_target_path": None,
                        "canonical_target_url": None,
                        "decision": "REVIEW_REQUIRED",
                        "allowed_for_generation": False,
                        "alternatives": [{"slug": v["slug"], "status": "verified_200" if v["http_status"] == 200 else "missing"} for v in variants],
                        "selection_reason": None,
                        "review_reason": "multiple_verified_variants_no_canonical_rule",
                    })
                    continue

                # Step 5: No verified variants -> VARIANT_CANDIDATES_NOT_IN_MAP
                if not verified_variants:
                    # Check if there are any (unverified) variants at all
                    if variants:
                        reason = "variant_candidates_unverified"
                    else:
                        reason = "no_variant_candidates_found"
                    records.append({
                        "request_key": request_key,
                        "source_prefix": sd_key,
                        "family": family,
                        "local_slug": canonical,
                        "canonical_base": canonical,
                        "expected_path": f"{sd_key}/{family}/{canonical}",
                        "expected_status": "sitemap_coverage_gap",
                        "canonical_target_path": None,
                        "canonical_target_url": None,
                        "decision": "VARIANT_CANDIDATES_NOT_IN_MAP",
                        "allowed_for_generation": False,
                        "alternatives": [{"slug": v["slug"], "status": "missing_or_unverified"} for v in variants],
                        "selection_reason": None,
                        "review_reason": reason,
                    })

    return records


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build platform variant authority (Layer 0.6)"
    )
    parser.add_argument("--subdomain", default=None, help="Filter to one subdomain key")
    parser.add_argument(
        "--inventory",
        default=str(REPO_ROOT / "data" / "backlinks" / "workspace" / "enterprise_target_candidate_inventory.json"),
    )
    parser.add_argument(
        "--overrides",
        default=str(REPO_ROOT / "data" / "backlinks" / "platform_canonical_overrides.yaml"),
    )
    parser.add_argument(
        "--output",
        default=str(REPO_ROOT / "data" / "backlinks" / "workspace" / "platform_variant_authority.json"),
    )
    parser.add_argument("--dry-run", action="store_true", help="Print summary; do not write")
    args = parser.parse_args()

    inventory_path = Path(args.inventory)
    if not inventory_path.exists():
        print(f"ERROR: inventory not found at {inventory_path}", file=sys.stderr)
        print("Run backlink_build_enterprise_candidate_inventory.py first.", file=sys.stderr)
        sys.exit(1)

    print(f"Loading inventory from {inventory_path} ...")
    inventory = _load_inventory(inventory_path)

    if args.subdomain:
        inventory = {k: v for k, v in inventory.items() if k == args.subdomain}

    print(f"Loading overrides from {args.overrides} ...")
    overrides = _load_overrides(Path(args.overrides))

    print("Building variant authority ...")
    records = build_variant_authority(inventory, overrides)

    # Summary
    approved = sum(1 for r in records if r.get("allowed_for_generation"))
    review = sum(1 for r in records if r.get("decision") == "REVIEW_REQUIRED")
    blocked = sum(1 for r in records if not r.get("allowed_for_generation") and r.get("decision") != "REVIEW_REQUIRED")
    print(
        f"Authority: {len(records)} records — "
        f"{approved} approved, {review} REVIEW_REQUIRED, {blocked} blocked"
    )

    if args.dry_run:
        print("Dry-run: output not written.")
        return

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({"schema_version": "1.0.0", "authority": records}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Written: {out_path}")


if __name__ == "__main__":
    main()
