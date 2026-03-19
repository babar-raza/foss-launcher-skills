"""Mental Model Builder — derive structured summary from PEF.

Usage:
    python scripts/mental_model.py {family} {platform}
    python scripts/mental_model.py all
"""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

EVIDENCE_ROOT = Path("evidence")

# Page types that should exist for a product
EXPECTED_PAGES = {
    "docs": ["installation", "quick-start"],
    "blog": ["intro"],
    "kb": ["faq", "howto"],
    "reference": [],  # populated dynamically from tier-1 classes
}


def _hash_pef(pef):
    content = json.dumps(pef, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _read_json(path, default=None):
    if default is None:
        default = {}
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _classify_tiers(api_surface, claims):
    """Classify API classes into capability tiers based on method count and evidence density."""
    # Build claim counts per class
    class_claim_counts = {}
    class_dual_counts = {}
    for c in claims:
        text = c.get("text", "")
        for api_entry in api_surface:
            name = api_entry.get("name", "")
            if name and name in text:
                class_claim_counts[name] = class_claim_counts.get(name, 0) + 1
                if c.get("provenance") in ("dual", "dual_fuzzy"):
                    class_dual_counts[name] = class_dual_counts.get(name, 0) + 1

    tier_1 = []
    tier_2 = []
    tier_3 = []

    for entry in api_surface:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name", "")
        methods = entry.get("methods", [])
        method_count = len(methods) if isinstance(methods, list) else 0
        has_doc = bool(entry.get("doc") or entry.get("docstring"))
        claim_count = class_claim_counts.get(name, 0)
        dual_count = class_dual_counts.get(name, 0)
        dual_pct = round(dual_count / claim_count * 100, 1) if claim_count > 0 else 0.0

        info = {
            "class": name,
            "method_count": method_count,
            "has_doc": has_doc,
            "claim_count": claim_count,
            "dual_confirmed_pct": dual_pct,
        }

        if method_count >= 5:
            tier_1.append(info)
        elif method_count >= 2:
            tier_2.append(info)
        else:
            tier_3.append(info)

    # Sort each tier by method count descending
    tier_1.sort(key=lambda x: x["method_count"], reverse=True)
    tier_2.sort(key=lambda x: x["method_count"], reverse=True)
    tier_3.sort(key=lambda x: x["method_count"], reverse=True)

    return {
        "tier_1_core": tier_1,
        "tier_2_supporting": tier_2,
        "tier_3_utility": tier_3,
    }


def _build_format_matrix(formats):
    """Build format import/export matrix from PEF formats array."""
    imports = []
    exports = []
    for f in formats:
        if not isinstance(f, dict):
            continue
        name = f.get("format", f.get("name", ""))
        direction = f.get("direction", "")
        can_import = f.get("can_import", False) or direction in ("import", "both")
        can_export = f.get("can_export", False) or direction in ("export", "both")
        if can_import:
            imports.append({"format": name, "confirmed": True})
        if can_export:
            exports.append({"format": name, "confirmed": True})
    return {"import": imports, "export": exports}


def _scan_page_coverage(family, platform, content_root=None):
    """Scan for existing content pages across site types."""
    if content_root is None:
        # Try output/ first (local), then content repo
        content_root = Path("output/content")

    coverage = {"docs": {}, "blog": {}, "kb": {}, "reference": {}}

    site_paths = {
        "docs": content_root / "docs.aspose.org" / "en" / family / platform,
        "blog": content_root / "blog.aspose.org" / family / platform,
        "kb": content_root / "kb.aspose.org" / "en" / family / platform,
        "reference": content_root / "reference.aspose.org" / "en" / family / platform,
    }

    for site_type, base_path in site_paths.items():
        if not base_path.exists():
            continue
        for md_file in base_path.rglob("*.md"):
            slug = md_file.stem
            if slug == "_index":
                continue
            rel_path = str(md_file.relative_to(content_root))
            coverage[site_type][slug] = {
                "status": "exists",
                "path": rel_path,
                "last_verified": None,
            }

    return coverage


def _analyze_gaps(tiers, page_coverage, pef):
    """Identify content gaps."""
    # Tier-1 classes without reference pages
    ref_pages = set(page_coverage.get("reference", {}).keys())
    tier1_classes = [t["class"] for t in tiers.get("tier_1_core", [])]
    uncovered_tier1 = [c for c in tier1_classes if c.lower() not in {p.lower() for p in ref_pages}]

    # Missing standard page types
    missing_pages = []
    for site_type, expected in EXPECTED_PAGES.items():
        existing = set(page_coverage.get(site_type, {}).keys())
        for slug in expected:
            if slug not in existing:
                missing_pages.append(f"{site_type}/{slug}")

    # Undocumented formats
    formats = pef.get("formats", [])
    format_names = {f.get("format", f.get("name", "")).upper() for f in formats if isinstance(f, dict)}
    # Check if any docs/kb pages mention formats
    undocumented = list(format_names)  # Simplified — assume all undocumented unless proven

    forbidden_count = len(pef.get("forbidden_claims", []))

    return {
        "uncovered_tier1_classes": uncovered_tier1,
        "undocumented_formats": undocumented,
        "missing_page_types": missing_pages,
        "forbidden_claim_count": forbidden_count,
    }


def _assess_readiness(pef, gaps):
    """Determine overall launch/maintenance readiness."""
    blockers = []
    warnings = []

    dual_pct = pef.get("provenance_summary", {}).get("dual_pct", 0)
    api_confidence = pef.get("api_confidence", "low")
    total_claims = pef.get("provenance_summary", {}).get("total", 0)

    if api_confidence == "low":
        blockers.append("api_confidence is low (dual-confirmed claims < 20%)")
    if total_claims == 0:
        blockers.append("no claims found in evidence")
    if len(pef.get("api_surface", [])) == 0:
        blockers.append("no API surface extracted")

    missing = gaps.get("missing_page_types", [])
    if missing:
        warnings.append(f"{len(missing)} standard page types missing: {', '.join(missing)}")

    uncovered = gaps.get("uncovered_tier1_classes", [])
    if uncovered:
        warnings.append(f"{len(uncovered)} tier-1 classes without reference pages")

    if blockers:
        overall = "blocked"
    elif warnings:
        overall = "needs_work"
    else:
        overall = "launch_ready"

    return {
        "overall": overall,
        "blockers": blockers,
        "warnings": warnings,
        "dual_confirmed_pct": dual_pct,
        "api_confidence": api_confidence,
    }


def build_mental_model(family, platform, content_root=None):
    """Build mental model from PEF. Returns mental model dict."""
    evidence_dir = EVIDENCE_ROOT / family / platform
    pef_path = evidence_dir / "pef.json"

    if not pef_path.exists():
        print(f"  SKIP {family}/{platform}: no pef.json (run materialize first)")
        return None

    pef = json.loads(pef_path.read_text(encoding="utf-8"))

    tiers = _classify_tiers(pef.get("api_surface", []), pef.get("claims", []))
    format_matrix = _build_format_matrix(pef.get("formats", []))
    page_coverage = _scan_page_coverage(family, platform, content_root)
    gaps = _analyze_gaps(tiers, page_coverage, pef)
    readiness = _assess_readiness(pef, gaps)

    model = {
        "schema_version": 1,
        "family": family,
        "platform": platform,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_pef_hash": _hash_pef(pef),
        "capability_tiers": tiers,
        "format_matrix": format_matrix,
        "page_coverage": page_coverage,
        "gap_analysis": gaps,
        "readiness": readiness,
    }

    model_path = evidence_dir / "mental_model.json"
    model_path.write_text(json.dumps(model, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  {family}/{platform}: readiness={readiness['overall']}, "
          f"tier1={len(tiers['tier_1_core'])}, gaps={len(gaps['missing_page_types'])}")
    return model


def discover_products():
    """Find all family/platform combinations with evidence."""
    products = []
    if not EVIDENCE_ROOT.exists():
        return products
    for family_dir in sorted(EVIDENCE_ROOT.iterdir()):
        if not family_dir.is_dir():
            continue
        for platform_dir in sorted(family_dir.iterdir()):
            if not platform_dir.is_dir():
                continue
            if (platform_dir / "pef.json").exists():
                products.append((family_dir.name, platform_dir.name))
    return products


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python scripts/mental_model.py {family} {platform}")
        print("  python scripts/mental_model.py all")
        sys.exit(1)

    if sys.argv[1] == "all":
        products = discover_products()
        if not products:
            print("No products found with evidence. Run materialize first.")
            sys.exit(1)
        print(f"Building mental models for {len(products)} products:")
        for family, platform in products:
            build_mental_model(family, platform)
    else:
        if len(sys.argv) < 3:
            print("Usage: python scripts/mental_model.py {family} {platform}")
            sys.exit(1)
        result = build_mental_model(sys.argv[1], sys.argv[2])
        if not result:
            sys.exit(1)

    print("MENTAL-MODEL: PASS")


if __name__ == "__main__":
    main()
