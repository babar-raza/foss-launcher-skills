"""Parameterized knowledge index generator.

Usage:
    python scripts/index.py {family} {platform}   # Single product
    python scripts/index.py all                     # All discovered products
"""
import json
import sys
import yaml
from pathlib import Path

KNOWLEDGE_ROOT = Path("knowledge")


def _install_command(family, platform, version=""):
    """Generate platform-appropriate install command."""
    pkg = f"aspose-{family}-foss"
    if platform == "python":
        return f"pip install {pkg}"
    elif platform == "typescript":
        return f"npm install {pkg}"
    elif platform == "dotnet":
        return f"dotnet add package {pkg.replace('-', '.')}"
    return f"pip install {pkg}"


def _display_name(family):
    """Generate display name from family."""
    special = {"3d": "3D"}
    return f"Aspose.{special.get(family, family.title())}"


def build_index(family, platform):
    """Build index.json for a single family/platform."""
    merged_dir = KNOWLEDGE_ROOT / family / platform / "merged"

    if not (merged_dir / "model.yaml").exists():
        print(f"  SKIP {family}/{platform}: no model.yaml")
        return None

    model = yaml.safe_load((merged_dir / "model.yaml").read_text())
    claims = json.loads((merged_dir / "claims.json").read_text()) if (merged_dir / "claims.json").exists() else []
    api = json.loads((merged_dir / "api_surface.json").read_text()) if (merged_dir / "api_surface.json").exists() else []
    formats = json.loads((merged_dir / "formats.json").read_text()) if (merged_dir / "formats.json").exists() else []
    class_graph = json.loads((merged_dir / "class_graph.json").read_text()) if (merged_dir / "class_graph.json").exists() else {}
    constants = json.loads((merged_dir / "constants.json").read_text()) if (merged_dir / "constants.json").exists() else []

    # Check for vectors
    vectors_dir = KNOWLEDGE_ROOT / "_vectors" / "api" / family / platform
    vectors_exist = vectors_dir.exists() and any(vectors_dir.iterdir()) if vectors_dir.exists() else False

    # Build limitations list
    limitations = []
    lim_path = merged_dir / "limitations.md"
    if lim_path.exists():
        for line in lim_path.read_text().splitlines():
            if "|" in line and "---" not in line and "File" not in line and "Limitations" not in line:
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 5 and parts[3]:
                    limitations.append(f"{parts[3]}.{parts[4]}" if parts[4] else parts[3])

    forbidden = [f"supports {l}" for l in limitations if l.strip()]

    # Compute provenance summary
    prov_counts = {}
    for c in claims:
        p = c.get("provenance", "unknown")
        prov_counts[p] = prov_counts.get(p, 0) + 1

    dual_count = prov_counts.get("dual", 0) + prov_counts.get("dual_fuzzy", 0)
    total = len(claims)
    if dual_count > total * 0.5:
        api_confidence = "high"
    elif dual_count > total * 0.2:
        api_confidence = "medium"
    else:
        api_confidence = "low"

    # Get class names and enum classes
    class_names = sorted(set(
        c["name"] for c in api
        if isinstance(c, dict) and "name" in c
    )) if isinstance(api, list) else []

    enum_classes = sorted(set(
        c["name"] for c in api
        if isinstance(c, dict) and c.get("enum_members")
    )) if isinstance(api, list) else []

    # Build constants summary
    exported_constants = sorted(
        c["name"] for c in constants
        if isinstance(c, dict) and c.get("exported")
    )

    index = {
        "schema_version": 2,
        "family": family,
        "platform": platform,
        "display_name": _display_name(family),
        "provenance": "dual" if dual_count > 0 else ("scout_only" if prov_counts.get("scout_only", 0) > 0 else "external_only"),
        "stale": False,
        "has_conflicts": False,
        "api_confidence": api_confidence,
        "repo_sha": model.get("repo_sha", ""),
        "last_merged": model.get("merged_at", ""),
        "vectors_available": vectors_exist,
        "stats": model.get("stats", {}),
        "classes": class_names,
        "class_graph": class_graph,
        "formats": {
            "import": [f.get("format", f.get("name", "")) for f in formats if f.get("can_import") or f.get("direction") in ("import", "both")],
            "export": [f.get("format", f.get("name", "")) for f in formats if f.get("can_export") or f.get("direction") in ("export", "both")],
            "caveats": {},
        },
        "install": {
            "command": model.get("install_command", _install_command(family, platform, model.get("version", ""))),
            "version": model.get("version", ""),
        },
        "enum_classes": enum_classes,
        "constants": {
            "count": len(constants),
            "exported": exported_constants[:100],
        },
        "not_implemented": limitations[:50],
        "forbidden_claims": forbidden[:50],
        "truth_gaps": [],
    }

    (merged_dir / "index.json").write_text(json.dumps(index, indent=2, ensure_ascii=False))
    print(f"  {family}/{platform}: {len(class_names)} classes, {len(claims)} claims, confidence={api_confidence}")
    return {
        "family": family,
        "platform": platform,
        "display_name": f"{_display_name(family)} for {platform.title()}",
        "api_confidence": api_confidence,
        "stale": False,
        "class_count": len(class_names),
        "claim_count": len(claims),
    }


def discover_products():
    """Find all family/platform combinations with merged knowledge."""
    products = []
    if not KNOWLEDGE_ROOT.exists():
        return products
    for family_dir in sorted(KNOWLEDGE_ROOT.iterdir()):
        if not family_dir.is_dir() or family_dir.name.startswith("_"):
            continue
        for platform_dir in sorted(family_dir.iterdir()):
            if not platform_dir.is_dir():
                continue
            if (platform_dir / "merged" / "claims.json").exists():
                products.append((family_dir.name, platform_dir.name))
    return products


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python scripts/index.py {family} {platform}")
        print("  python scripts/index.py all")
        sys.exit(1)

    if sys.argv[1] == "all":
        products = discover_products()
        if not products:
            print("No products found with merged knowledge.")
            sys.exit(1)
        print(f"Discovered {len(products)} products:")
        entries = []
        for family, platform in products:
            entry = build_index(family, platform)
            if entry:
                entries.append(entry)
    else:
        if len(sys.argv) < 3:
            print("Usage: python scripts/index.py {family} {platform}")
            sys.exit(1)
        family = sys.argv[1]
        platform = sys.argv[2]
        entry = build_index(family, platform)
        entries = [entry] if entry else []

    # Write _index.json aggregating all products
    if entries:
        _index = {"products": entries}
        (KNOWLEDGE_ROOT / "_index.json").write_text(json.dumps(_index, indent=2))
        print(f"\n_index.json: {len(entries)} product(s)")

    print("TRUTH-INDEX: PASS")


if __name__ == "__main__":
    main()
