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
_DEFAULT_FOSS_PACKAGES_PATH = Path(__file__).resolve().parent.parent.parent.parent.parent / "data" / "package_registry.json"
FOSS_PACKAGES_PATH = _DEFAULT_FOSS_PACKAGES_PATH


def configure(*, knowledge_root: "Path | str | None" = None, foss_packages_path: "Path | str | None" = None) -> None:
    """Override module-level path constants for testing."""
    global KNOWLEDGE_ROOT, FOSS_PACKAGES_PATH
    KNOWLEDGE_ROOT = Path(knowledge_root) if knowledge_root is not None else _DEFAULT_KNOWLEDGE_ROOT
    FOSS_PACKAGES_PATH = Path(foss_packages_path) if foss_packages_path is not None else _DEFAULT_FOSS_PACKAGES_PATH
    # TC-VEC-03-C: keep vector_store's own knowledge_root in lockstep with this
    # module's KNOWLEDGE_ROOT (same FRESH-001 rationale as refresh_run.py's
    # cascade to freshness_guard/page_impact_matrix/batch_reference, and
    # run.py's cascade added in this same taskcard) -- without this, a test
    # redirecting KNOWLEDGE_ROOT would still have build_index()'s new
    # vectors_current field silently reading the real live repo's vectors.
    _lib_dir = str(Path(__file__).resolve().parents[2] / "lib")
    if _lib_dir not in sys.path:
        sys.path.insert(0, _lib_dir)
    import vector_store  # noqa: PLC0415
    vector_store.configure(knowledge_root=KNOWLEDGE_ROOT)


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


def _java_install_command(family):
    """Generate the Java Maven <dependency> block from data/package_registry.json.

    This is the ONLY source for the Java groupId/artifactId — never hardcoded.
    See plans/master-plan.md Mission MT008 (D-04): a hardcoded, wrong-groupId
    fallback lived here for 3 months because promote.py strips `install_command`
    from merged/model.yaml (AF-03), so this fallback fired for every Java-FOSS
    page. Returns a "not yet published" placeholder — never a coordinate — when
    no entry exists or the family isn't confirmed live on Maven Central.

    MT015 update (2026-08-01): repointed from the retired data/foss_packages.json
    to the unified data/package_registry.json; `entry["confirmed"]` -> single
    `entry["candidate"]`, `entry["published"]` -> `entry["verification"]["published"]`.
    """
    try:
        packages = json.loads(FOSS_PACKAGES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "<!-- Maven coordinate unavailable: data/package_registry.json missing or invalid -->"

    entry = packages.get(family, {}).get("java")
    if not entry or not entry.get("verification", {}).get("published") or not entry.get("candidate"):
        return f"<!-- aspose-{family}-foss is not yet published on Maven Central -- build from source -->"

    c = entry["candidate"]
    return (
        f"<dependency><groupId>{c['group_id']}</groupId>"
        f"<artifactId>{c['artifact_id']}</artifactId>"
        f"<version>{c['version']}</version></dependency>"
    )


def _typescript_install_command(family):
    """Generate the npm install command from data/package_registry.json.

    Mirrors _java_install_command's pattern: never fabricate a real command
    for an unpublished/unconfirmed npm package. Mission
    MT040-2026-08-28-PDF-TYPESCRIPT-LAUNCH (TC-MT040-46): replaces the old
    unconditional `npm install aspose-{family}-foss` hardcode, which was the
    wrong shape for a real npm-scoped package name and ignored
    data/package_registry.json entirely.

    Package-NAME resolution goes through lib/product_registry.py's
    get_package_name() (the shared loader this taskcard introduced -- also
    used by commands/ops/batch_gen_missing.py). That function deliberately
    returns a bare name with no opinion on publish state -- it prefers the
    registry's own candidate name (even unpublished, e.g. cells/typescript's
    real candidate "excel-cells") over a generic naming-convention guess,
    because a scouted/recorded name is more truthful than a guess even
    before it's confirmed live. This function is therefore the one place
    that decides "safe to render as a live command" vs. "not yet published"
    placeholder, by independently checking verification.published on the
    SAME registry file -- exactly as _java_install_command already does for
    Maven.
    """
    import sys as _sys
    _pipeline_root = str(Path(__file__).resolve().parents[2])  # -> pipeline/
    if _pipeline_root not in _sys.path:
        _sys.path.insert(0, _pipeline_root)
    from lib import product_registry

    product_registry.configure(package_registry_path=FOSS_PACKAGES_PATH)
    name = product_registry.get_package_name(family, "typescript", "npm")

    try:
        packages = json.loads(FOSS_PACKAGES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "<!-- npm package unavailable: data/package_registry.json missing or invalid -->"

    entry = packages.get(family, {}).get("typescript")
    published = bool(entry and entry.get("verification", {}).get("published"))
    if not name or not published:
        return f"<!-- aspose-{family}-foss is not yet published on npm -- build from source -->"

    candidate = entry.get("candidate") or {}
    version = candidate.get("version", "")
    if version:
        return f"npm install {name}@{version}"
    return f"npm install {name}"


def _install_command(family, platform, version=""):
    """Generate platform-appropriate install command."""
    pkg = f"aspose-{family}-foss"
    if platform == "python":
        return f"pip install {pkg}"
    elif platform == "typescript":
        return _typescript_install_command(family)
    elif platform in ("net", "dotnet"):
        return f"dotnet add package {pkg.replace('-', '.')}"
    elif platform == "java":
        return _java_install_command(family)
    elif platform == "go":
        module = f"github.com/aspose-{family}-foss/aspose-{family}-foss-for-go"
        return f"go get {module}"
    return f"pip install {pkg}"


def _display_name(family):
    """Generate display name from family."""
    special = {"3d": "3D"}
    return f"Aspose.{special.get(family, family.title())}"


from lib.class_stats import compute_class_stats, is_public_api_entry as _is_public_api_entry
# MT067-2026-09-10 TC-04: this function's body moved to lib/class_stats.py so scout-side
# (outputs.py/promote.py) and index-side stats share one implementation instead of two that
# could drift -- the mechanism that produced barcode/python's 26-vs-79 split. Re-exported
# under its original name here since tests/callers import `_is_public_api_entry` from this
# module directly (see test_index.py).


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
    # MT067-2026-09-10 TC-04: full total_declared/public_documented/raw_entries breakdown,
    # computed from the same raw `api` list class_names was derived from -- class_stats
    # ["public_documented"] is guaranteed == len(class_names) (same filter, same dedup).
    class_stats = compute_class_stats(api) if isinstance(api, list) else compute_class_stats([])

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
    # MT067-2026-09-10 TC-04: class_count is deprecated (kept as this file's pre-existing
    # public_documented semantic -- do NOT silently change its meaning to total_declared
    # here, that would be a breaking change for every existing reader of index.json's
    # class_count). New readers should use the namespaced "classes" block instead.
    recomputed_stats["class_count"] = class_stats["public_documented"]
    recomputed_stats["classes"] = class_stats
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
        "class_count": class_stats["public_documented"],
        "claim_count": len(claims),
        "api_confidence": api_confidence,
    })

    # TC-VEC-03-C (RC2): surface the active gap-index vector profile's
    # currency here, distinct from api_surface.json/claims.json staleness
    # ("stale" above) -- reuses vector_store.py (TC-VEC-03-A) rather than
    # reimplementing the source_hash comparison. Note: this is intentionally
    # NOT the same field as the pre-existing "vectors_available" written into
    # merged/index.json (line ~399 in this file) -- that field checks a fixed
    # knowledge/_vectors/api/ path (the legacy flat standard-mode directory)
    # and is unrelated to gap-index's real per-product profile directory;
    # found live while building this fix, out of scope for this taskcard
    # (knowledge/_index.json only), recorded in the plan for a future fix.
    _lib_dir = str(Path(__file__).resolve().parents[2] / "lib")
    if _lib_dir not in sys.path:
        sys.path.insert(0, _lib_dir)
    import vector_store as _vector_store  # noqa: PLC0415

    # Self-sufficient regardless of whether index.py's own configure() has
    # been called with the current KNOWLEDGE_ROOT — main()'s --knowledge-root
    # CLI flag mutates the module global directly, bypassing configure()
    # entirely (a pre-existing gap, found live while wiring this in; not
    # fixed here, out of scope for this taskcard, but this call must not
    # silently inherit a stale/default vector_store root because of it).
    _vector_store.configure(knowledge_root=KNOWLEDGE_ROOT)
    vec_status = _vector_store.vector_status(family, platform)
    VectorStatus = _vector_store.VectorStatus
    vectors_generated_at = None
    if vec_status != VectorStatus.MISSING:
        try:
            active = json.loads(
                (KNOWLEDGE_ROOT / "_vectors" / family / platform / "active.json").read_text(
                    encoding="utf-8"
                )
            )
            manifest_path = (
                KNOWLEDGE_ROOT / "_vectors" / family / platform / "profiles"
                / active["profile_id"] / "manifest.json"
            )
            vectors_generated_at = json.loads(
                manifest_path.read_text(encoding="utf-8")
            ).get("generated_at")
        except (OSError, KeyError, json.JSONDecodeError):
            pass

    return {
        "family": family,
        "platform": platform,
        "display_name": f"{_display_name(family)} for {platform.title()}",
        "api_confidence": api_confidence,
        "stale": stale,
        "class_count": class_stats["public_documented"],
        "claim_count": len(claims),
        "vectors_current": vec_status == VectorStatus.CURRENT,
        "vectors_status": vec_status,
        "vectors_generated_at": vectors_generated_at,
    }


def _existing_summary_entry(family, platform, prior_index_entries=None):
    """Build a BYSTANDER product's _index.json cross-product summary entry
    from its own existing merged/index.json plus (for the 3 fields that
    file never stores) the prior _index.json's own entry for it, without
    calling build_index() -- which has real filesystem side effects
    (rewrites that product's own merged/index.json and .pipeline_state.json)
    and recomputes environment-dependent fields (class_graph from a
    possibly-absent class_graph.json, vectors_available from a possibly-
    absent local _vectors/ directory) from THIS checkout's current local
    state.

    TC-PSD-HRD-9N-6 (found live, MT076 psd/net launch): a single-product
    `index.py {family} {platform}` invocation looped build_index() over
    EVERY discovered product (not just the one requested) to rebuild the
    cross-product _index.json summary (HARDEN-words-net, 2026-07-22) --
    but build_index()'s side effects then silently destroyed bystander
    products' own already-committed merged/index.json files whenever this
    checkout's local environment state differed from whatever environment
    last correctly built them (e.g. a missing class_graph.json wiped a
    real, previously-committed class_graph to {}; a missing local
    _vectors/ dir flipped a real vectors_available: true to false).

    `vectors_current`/`vectors_status`/`vectors_generated_at` are NEVER
    persisted into merged/index.json at all (confirmed by direct source
    read -- build_index() only computes them for its OWN return dict, used
    exclusively to build _index.json); the only place a bystander's prior,
    correct value for these 3 fields can be recovered from is the prior
    _index.json's own entry for that product, passed in via
    `prior_index_entries` (a dict keyed by (family, platform), built once
    by the caller from the on-disk _index.json before this loop starts --
    found live in an earlier, incomplete version of this fix, which left
    these 3 fields defaulting to "missing"/null for every bystander on
    every single-product run, silently discarding real prior values just
    as destructively as the original bug, only via a different field set).

    `display_name` is likewise never stored with its _index.json-specific
    " for {Platform}" suffix inside merged/index.json's own schema (that
    file stores just the bare family display name) -- recomputed here via
    the same pure, deterministic, environment-independent formatting
    build_index() itself uses, never read from either file.

    Returns None if no existing merged/index.json is found at all, so the
    caller can fall back to a real build_index() call for a product that
    has genuinely never been built before.
    """
    idx_path = KNOWLEDGE_ROOT / family / platform / "merged" / "index.json"
    if not idx_path.exists():
        return None
    try:
        existing = json.loads(idx_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    stats = existing.get("stats", {}) if isinstance(existing.get("stats"), dict) else {}
    prior = (prior_index_entries or {}).get((family, platform), {})
    return {
        "family": existing.get("family", family),
        "platform": existing.get("platform", platform),
        "display_name": f"{_display_name(family)} for {platform.title()}",
        "api_confidence": existing.get("api_confidence", "high"),
        "stale": existing.get("stale", False),
        "class_count": stats.get("class_count", len(existing.get("classes", []) or [])),
        "claim_count": stats.get("total_claims", 0),
        "vectors_current": prior.get("vectors_current", False),
        "vectors_status": prior.get("vectors_status", "missing"),
        "vectors_generated_at": prior.get("vectors_generated_at"),
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
        # HARDEN-words-net (2026-07-22): _index.json is documented as a
        # CROSS-PRODUCT summary (knowledge/_index.json, "products" array) —
        # a single-product invocation must never truncate it down to just
        # the one product being processed. Found live: running
        # `index.py words net` overwrote a ~26-product _index.json down to
        # 1 entry, silently discarding every other product's summary.
        # Rebuild the full cross-product list from every discovered
        # product. The EXPLICITLY REQUESTED product's own entry is always
        # freshly rebuilt (never read back from a prior stale _index.json
        # entry — that would reintroduce the per-product staleness bug A13
        # already fixed elsewhere in this file). A BYSTANDER product's
        # entry is a different case (TC-PSD-HRD-9N-6): reusing its own
        # already-correct prior state is exactly what must happen, since
        # nothing about this run is supposed to be re-verifying bystanders
        # at all -- see _existing_summary_entry()'s own docstring for why
        # it needs both the bystander's own merged/index.json AND the
        # prior _index.json's entry for it (two different, non-overlapping
        # field sets neither file alone can fully supply).
        prior_index_entries = {}
        _prior_index_path = KNOWLEDGE_ROOT / "_index.json"
        if _prior_index_path.exists():
            try:
                _prior = json.loads(_prior_index_path.read_text(encoding="utf-8"))
                for _p in _prior.get("products", []):
                    if "family" in _p and "platform" in _p:
                        prior_index_entries[(_p["family"], _p["platform"])] = _p
            except (OSError, json.JSONDecodeError):
                pass

        entries = []
        if entry:
            for fam, plat in discover_products():
                if (fam, plat) == (family, platform):
                    e = entry
                else:
                    # TC-PSD-HRD-9N-6: never call build_index() (real
                    # filesystem writes + environment-dependent recompute)
                    # for a product that was not explicitly requested --
                    # reuse its own already-committed state verbatim. Only
                    # fall back to a real build when that product has
                    # genuinely never been built before (no merged/
                    # index.json exists for it at all yet).
                    e = _existing_summary_entry(fam, plat, prior_index_entries)
                    if e is None:
                        e = build_index(fam, plat)
                if e:
                    entries.append(e)
            # HARDEN-words-net (adversarial re-review, 2026-07-22): a product
            # with model.yaml but no claims.json builds a valid `entry`
            # (build_index() defaults an absent claims.json to an empty
            # list rather than failing) but never appears in
            # discover_products()'s scan (which requires claims.json to
            # exist) — so the loop above never matches this exact tuple and
            # the just-explicitly-requested product's OWN entry would be
            # silently dropped from _index.json. Guarantee it's always
            # included regardless of discover_products()'s candidacy rules.
            if not any(e.get("family") == family and e.get("platform") == platform
                       for e in entries):
                entries.append(entry)

    # Write _index.json aggregating all products
    if entries:
        _index = {"products": entries}
        (KNOWLEDGE_ROOT / "_index.json").write_text(json.dumps(_index, indent=2))
        print(f"\n_index.json: {len(entries)} product(s)")

    print("TRUTH-INDEX: PASS")


if __name__ == "__main__":
    main()
