"""Parameterized knowledge index generator.

Usage:
    python scripts/index.py {family} {platform}   # Single product
    python scripts/index.py all                     # All discovered products
"""
import json
import sys
import yaml
from pathlib import Path

_DEFAULT_KNOWLEDGE_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent / "knowledge"
KNOWLEDGE_ROOT = _DEFAULT_KNOWLEDGE_ROOT


def configure(*, knowledge_root: "Path | str | None" = None) -> None:
    """Override module-level path constants for testing."""
    global KNOWLEDGE_ROOT
    KNOWLEDGE_ROOT = Path(knowledge_root) if knowledge_root is not None else _DEFAULT_KNOWLEDGE_ROOT


def compute_api_confidence(api_total: int, method_pct: float) -> str:
    """Compute api_confidence tier from actual API surface coverage.

    Thresholds are calibrated against the 13 current products (all retain 'high'):
    - Minimum observed: api_total=26 (email/cpp), method_pct=0.347 (slides/python)
    - 'high'   : api_total >= 15 AND method_pct >= 0.20  (all current products)
    - 'medium' : api_total >= 5  AND method_pct >= 0.10
    - 'low'    : anything thinner — triggers §7 hard stop in AGENTS.md

    Args:
        api_total: number of public API classes/entities after _is_public_api_entry filter
        method_pct: fraction of classes with at least one method (0.0 – 1.0)
    """
    if api_total >= 15 and method_pct >= 0.20:
        return "high"
    if api_total >= 5 and method_pct >= 0.10:
        return "medium"
    return "low"


def _install_command(family, platform, version=""):
    """Generate platform-appropriate install command."""
    pkg = f"aspose-{family}-foss"
    if platform == "python":
        return f"pip install {pkg}"
    elif platform == "typescript":
        return f"npm install {pkg}"
    elif platform in ("net", "dotnet"):
        return f"dotnet add package {pkg.replace('-', '.')}"
    elif platform == "java":
        gid = "com.aspose"
        aid = f"aspose-{family}-foss"
        return f"<dependency><groupId>{gid}</groupId><artifactId>{aid}</artifactId></dependency>"
    elif platform == "go":
        module = f"github.com/aspose-{family}-foss/aspose-{family}-foss-for-go"
        return f"go get {module}"
    return f"pip install {pkg}"


def _display_name(family):
    """Generate display name from family."""
    special = {"3d": "3D"}
    return f"Aspose.{special.get(family, family.title())}"


from core.constants import _TEST_PATH_PATTERNS, _INTERNAL_PATH_PATTERNS


def _is_public_api_entry(entry: dict) -> bool:
    """Return True if *entry* represents a developer-visible API class.

    Excludes free functions, private names, test-file entries, and internal
    implementation directories.  Uses only fields already present in every
    api_surface.json record (kind, name, file) so no schema change is needed.

    PY-INIT-001: If the scout set exported_via_package_init=True (see
    extraction/api_surface.py _mark_package_init_exports), the entry is
    public regardless of its physical file path.  This handles packages that
    define classes in _internal/ and re-export them via __init__.py.__all__.
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
    # PY-INIT-001: explicit package-level re-export overrides path filter.
    if entry.get("exported_via_package_init"):
        return True
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

    model = yaml.safe_load((merged_dir / "model.yaml").read_text(encoding="utf-8"))
    claims = json.loads((merged_dir / "claims.json").read_text(encoding="utf-8")) if (merged_dir / "claims.json").exists() else []
    api = json.loads((merged_dir / "api_surface.json").read_text(encoding="utf-8")) if (merged_dir / "api_surface.json").exists() else []
    formats = json.loads((merged_dir / "formats.json").read_text(encoding="utf-8")) if (merged_dir / "formats.json").exists() else []
    class_graph = json.loads((merged_dir / "class_graph.json").read_text(encoding="utf-8")) if (merged_dir / "class_graph.json").exists() else {}

    # Build the public API view once — reused for all downstream metrics.
    # Excludes test functions, private members, test-file classes, and
    # internal implementation classes (see _is_public_api_entry for criteria).
    public_api = [c for c in api if _is_public_api_entry(c)] if isinstance(api, list) else []
    api_total = len(public_api)
    api_with_methods    = sum(1 for c in public_api if c.get("methods"))
    api_with_properties = sum(1 for c in public_api if c.get("properties"))
    api_with_enums      = sum(1 for c in public_api if c.get("enum_members"))

    # SFX-3: Go-specific heuristic removed. api_surface.py (SFX-1) now correctly
    # associates receiver methods with their parent types, so api_with_methods
    # reflects real method counts. If still 0, that indicates a genuine extraction
    # gap — not a false negative to paper over.
    if platform == "go" and api_with_methods == 0:
        import logging as _log
        _log.getLogger(__name__).warning(
            "Go platform: zero method-associations found in api_surface.json. "
            "Run scout with the updated api_surface.py (SFX-1 fix) to populate methods. "
            "api_confidence will reflect actual extraction quality."
        )

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
    known_doc_errors: list[str] = []
    lim_path = merged_dir / "limitations.md"
    if lim_path.exists():
        in_doc_errors = False
        for line in lim_path.read_text(encoding="utf-8").splitlines():
            if "Known Documentation Errors" in line:
                in_doc_errors = True
                continue
            if in_doc_errors:
                if line.startswith("## "):
                    in_doc_errors = False
                elif "|" in line and "---" not in line and "| Bug ID |" not in line:
                    parts = [p.strip() for p in line.split("|")]
                    if len(parts) >= 4 and parts[2]:
                        # Extract backtick-wrapped identifiers from the Item column
                        import re as _re
                        tokens = _re.findall(r"`([^`]+)`", parts[2])
                        known_doc_errors.extend(tokens)
                continue
            if "|" in line and "---" not in line and "Limitations" not in line and "| File |" not in line:
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 5 and parts[3]:
                    limitations.append(f"{parts[3]}.{parts[4]}" if parts[4] else parts[3])

    forbidden = [f"supports {l}" for l in limitations if l.strip()]
    # Known doc errors are forbidden claims verbatim (exact identifiers)
    for tok in known_doc_errors:
        if tok not in forbidden:
            forbidden.append(tok)

    api_confidence = compute_api_confidence(api_total, method_pct)
    stale = model.get("stale_since") is not None

    # class_names derives directly from public_api — same filter, consistent with all metrics
    class_names = sorted(set(c["name"] for c in public_api if "name" in c))

    # HARDEN-A13 (2026-07-22): recompute stats from the LIVE artifacts this
    # function already loaded (claims.json, api_surface.json-derived
    # class_names, forbidden list), instead of copying model.yaml's stats
    # block verbatim. The stats block is a snapshot taken whenever model.yaml
    # was last written by promote.py — if claims.json/api_surface.json are
    # regenerated afterward without a fresh promote(), index.json silently
    # drifts from the artifacts it's supposed to describe. Confirmed live on
    # this exact repo: words/python's committed index.json (class_count: 262,
    # total_claims: 1603) disagreed with its own model.yaml/claims.json
    # (class_count: 146, total_claims: 972) at the time this was found.
    # site_planner.py's evidence_summary (which gates docs/KB/blog page-count
    # scaling — see A13's other half) reads THIS stats block, so a stale
    # value here silently mis-sizes every downstream launch-size decision.
    # Fields not independently recomputable here (scout/enriched/supplemental
    # claim-type breakdown) are carried forward from model.yaml as before —
    # only the fields this function already has live, corroborated data for
    # are overwritten.
    recomputed_stats = dict(model.get("stats", {}))
    recomputed_stats["class_count"] = len(class_names)
    recomputed_stats["total_claims"] = len(claims)
    # R6: match the truncation the emitted "forbidden_claims" array actually
    # uses ([:50], below) — forbidden_count must describe the array readers
    # actually see, not the pre-truncation list length.
    recomputed_stats["forbidden_count"] = len(forbidden[:50])
    snippets_index_path = merged_dir / "snippets" / "snippets_index.json"
    if snippets_index_path.exists():
        try:
            snippets_data = json.loads(snippets_index_path.read_text(encoding="utf-8"))
            if isinstance(snippets_data, list):
                recomputed_stats["snippet_count"] = len(snippets_data)
            elif isinstance(snippets_data, dict):
                recomputed_stats["snippet_count"] = len(
                    snippets_data.get("snippets", snippets_data))
        except (json.JSONDecodeError, OSError):
            pass  # keep model.yaml's recorded snippet_count on a read failure

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
        "stale": stale,
        "has_conflicts": False,
        "api_confidence": api_confidence,
        "repo_sha": model.get("repo_sha", ""),
        "last_merged": model.get("merged_at", ""),
        "vectors_available": vectors_exist,
        "stats": recomputed_stats,  # HARDEN-A13: recomputed from live artifacts, not copied
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

    # Write pipeline state manifest so audit.py and other consumers can
    # detect whether this product's index is current.
    # lazy-import guard: core.manifest is a sibling module; deferred import
    # avoids circular imports at module load time.
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # -> pipeline/
    from core.manifest import write_step_manifest
    state_path = KNOWLEDGE_ROOT / family / platform / ".pipeline_state.json"
    write_step_manifest(state_path, "index", {
        "class_count": len(class_names),
        "claim_count": len(claims),
        "api_confidence": api_confidence,
    })

    return {
        "family": family,
        "platform": platform,
        "display_name": f"{_display_name(family)} for {platform.title()}",
        "api_confidence": api_confidence,
        "stale": stale,
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
    global KNOWLEDGE_ROOT
    # Parse --knowledge-root without changing positional arg handling
    import argparse as _argparse
    _parser = _argparse.ArgumentParser(add_help=False)
    _parser.add_argument("--knowledge-root", default=None)
    _known, _remaining = _parser.parse_known_args()
    if _known.knowledge_root:
        KNOWLEDGE_ROOT = Path(_known.knowledge_root)
    # Rewrite sys.argv to only positional args for the existing logic
    sys.argv = [sys.argv[0]] + _remaining

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
