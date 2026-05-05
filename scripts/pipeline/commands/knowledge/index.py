"""Parameterized knowledge index generator.

Usage:
    python scripts/index.py {family} {platform}   # Single product
    python scripts/index.py all                     # All discovered products
"""
import json
import sys
import yaml
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config_loader import resolve_knowledge_root as _resolve_knowledge_root

KNOWLEDGE_ROOT = _resolve_knowledge_root()


def _install_command(family, platform, version=""):
    """Generate platform-appropriate install command."""
    pkg = f"aspose-{family}-foss"
    if platform == "python":
        return f"pip install {pkg}"
    elif platform == "typescript":
        return f"npm install {pkg}"
    elif platform == "dotnet":
        return f"dotnet add package {pkg.replace('-', '.')}"
    elif platform == "java":
        gid = "com.aspose"
        aid = f"aspose-{family}-foss"
        return f"<dependency><groupId>{gid}</groupId><artifactId>{aid}</artifactId></dependency>"
    return f"pip install {pkg}"


def _display_name(family):
    """Generate display name from family."""
    special = {"3d": "3D"}
    return f"Aspose.{special.get(family, family.title())}"


# Paths that identify test code or internal implementation — excluded from public API.
_TEST_PATH_PATTERNS = ("tests/", "/tests/", "/test_", "test_", "conftest")
_INTERNAL_PATH_PATTERNS = ("/_internal/", "/_private/", "/_impl/")


def _is_public_api_entry(entry: dict) -> bool:
    """Return True if *entry* represents a developer-visible API class.

    Excludes free functions, private names, test-file entries, and internal
    implementation directories.  Uses only fields already present in every
    api_surface.json record (kind, name, file) so no schema change is needed.
    """
    if not isinstance(entry, dict):
        return False
    if entry.get("kind") == "function":
        return False
    name = entry.get("name", "")
    if not name or name.startswith("_"):
        return False
    file = entry.get("file", "")
    if any(pat in file for pat in _TEST_PATH_PATTERNS):
        return False
    if any(pat in file for pat in _INTERNAL_PATH_PATTERNS):
        return False
    return True


def _has_surface(entry: dict) -> bool:
    """Return True if *entry* has at least one documentable surface member."""
    return bool(entry.get("methods") or entry.get("properties") or entry.get("enum_members"))


def _is_interface_name(name: str) -> bool:
    """Return True if *name* follows the IXxx interface naming convention.

    Requires: I + uppercase letter + lowercase letter (e.g. IShape, ISlide).
    Excludes IO-prefixed concrete classes (IOService, IOConfig) where 'IO'
    means Input/Output rather than the interface marker 'I'.
    """
    return len(name) > 2 and name[0] == "I" and name[1].isupper() and name[2].islower()


def _snippets_coverage(
    merged_dir: Path,
    api_total: int,
    public_class_names: set,
    concrete_class_names: set | None = None,
    interface_class_names: set | None = None,
) -> dict:
    """Compute snippet coverage — numerator and denominator both restricted to public API.

    Without *public_class_names* filtering the numerator would include test
    helper names (e.g. tmp_pptx, test_add_author) that appear in snippets
    extracted from test files, making the ratio incoherent.

    When *concrete_class_names* and *interface_class_names* are provided,
    adds sub-metrics:
    - ``concrete_coverage``: coverage of non-interface, non-empty-surface classes
    - ``interface_coverage``: coverage of I-prefixed interface classes (structurally ~0)
    - ``effective_denominator``: testable class count (excludes zero-surface markers)
    """
    snip_index_path = merged_dir / "snippets" / "snippets_index.json"
    empty = {
        "total_snippets": 0,
        "classes_with_snippet": 0,
        "classes_total": api_total,
        "coverage_ratio": 0.0,
    }
    if concrete_class_names is not None:
        ct = len(concrete_class_names)
        it = len(interface_class_names) if interface_class_names is not None else 0
        empty["effective_denominator"] = ct + it
        empty["concrete_coverage"] = {"classes_total": ct, "classes_with_snippet": 0, "coverage_ratio": 0.0}
        empty["interface_coverage"] = {"classes_total": it, "classes_with_snippet": 0, "coverage_ratio": 0.0}
    if not snip_index_path.exists():
        return empty
    try:
        snip_index = json.loads(snip_index_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        snip_index = []
    classes_covered = set()
    for entry in snip_index:
        for c in entry.get("classes_used", []):
            if c in public_class_names:
                classes_covered.add(c)
    result = {
        "total_snippets": len(snip_index),
        "classes_with_snippet": len(classes_covered),
        "classes_total": api_total,
        "coverage_ratio": round(len(classes_covered) / api_total, 2) if api_total else 0.0,
    }
    if concrete_class_names is not None:
        concrete_covered = classes_covered & concrete_class_names
        ct = len(concrete_class_names)
        result["effective_denominator"] = ct + (len(interface_class_names) if interface_class_names else 0)
        result["concrete_coverage"] = {
            "classes_total": ct,
            "classes_with_snippet": len(concrete_covered),
            "coverage_ratio": round(len(concrete_covered) / ct, 2) if ct else 0.0,
        }
    if interface_class_names is not None:
        interface_covered = classes_covered & interface_class_names
        it = len(interface_class_names)
        result["interface_coverage"] = {
            "classes_total": it,
            "classes_with_snippet": len(interface_covered),
            "coverage_ratio": round(len(interface_covered) / it, 2) if it else 0.0,
        }
    return result


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
    constants_raw = json.loads((merged_dir / "constants.json").read_text()) if (merged_dir / "constants.json").exists() else []

    # Build the public API view once — reused for all downstream metrics.
    # Excludes test functions, private members, test-file classes, and
    # internal implementation classes (see _is_public_api_entry for criteria).
    public_api = [c for c in api if _is_public_api_entry(c)] if isinstance(api, list) else []
    api_total = len(public_api)
    api_with_methods    = sum(1 for c in public_api if c.get("methods"))
    api_with_properties = sum(1 for c in public_api if c.get("properties"))
    api_with_enums      = sum(1 for c in public_api if c.get("enum_members"))

    if api_total > 0:
        method_pct = api_with_methods / api_total
        prop_pct = api_with_properties / api_total
    else:
        method_pct = prop_pct = 0.0

    if method_pct >= 0.70:
        surface_tier = 1
    elif method_pct >= 0.40:
        surface_tier = 2
    else:
        surface_tier = 3

    if surface_tier == 3:
        print(f"  WARNING: {family}/{platform} surface_tier=3 (methods={method_pct*100:.0f}%). "
              f"Content verification will be weak.")

    # Check for vectors
    vectors_dir = KNOWLEDGE_ROOT / "_vectors" / "api"
    vectors_exist = vectors_dir.exists() and any(vectors_dir.iterdir()) if vectors_dir.exists() else False

    # Build limitations list
    limitations = []
    lim_path = merged_dir / "limitations.md"
    if lim_path.exists():
        for line in lim_path.read_text().splitlines():
            if "|" in line and "---" not in line and "Limitations" not in line and "| File |" not in line:
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 5 and parts[3]:
                    limitations.append(f"{parts[3]}.{parts[4]}" if parts[4] else parts[3])

    forbidden = [f"supports {l}" for l in limitations if l.strip()]

    # Scout-only: api_confidence is always "high" (deterministic code analysis)
    api_confidence = "high"

    # class_names derives directly from public_api — same filter, consistent with all metrics
    class_names = sorted(set(c["name"] for c in public_api if "name" in c))

    # enum classes: public API entries that have enum_members
    enum_class_names = sorted(
        c["name"] for c in public_api
        if c.get("enum_members") is not None and "name" in c
    )

    # constants summary
    exported_const_names = sorted(
        c["name"] for c in constants_raw
        if isinstance(c, dict) and c.get("exported")
    )
    constants_index = {
        "count": len(constants_raw),
        "exported": exported_const_names,
    }

    # Classify public classes for snippet-coverage sub-metrics.
    # "Testable" classes have at least one method, property, or enum_member —
    # zero-surface marker classes (pure structural placeholders) are excluded
    # from the effective denominator because no snippet can demonstrate them.
    # "Interface" classes follow the IXxx naming convention (see _is_interface_name).
    testable_names = {c["name"] for c in public_api if "name" in c and _has_surface(c)}
    interface_names = frozenset(n for n in testable_names if _is_interface_name(n))
    concrete_names = frozenset(testable_names - interface_names)

    index = {
        "schema_version": 2,
        "family": family,
        "platform": platform,
        "display_name": _display_name(family),
        "provenance": "scout_only",
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
        "not_implemented": limitations[:50],
        "forbidden_claims": forbidden[:50],
        "truth_gaps": [],
        "enum_classes": enum_class_names,
        "constants": constants_index,
        "api_coverage": {
            "total_classes": api_total,
            "with_methods": api_with_methods,
            "with_properties": api_with_properties,
            "with_enums": api_with_enums,
            "method_pct": round(method_pct * 100, 1),
            "property_pct": round(prop_pct * 100, 1),
            "surface_tier": surface_tier,
        },
        "snippets_coverage": _snippets_coverage(
            merged_dir, api_total, set(class_names), concrete_names, interface_names
        ),
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
