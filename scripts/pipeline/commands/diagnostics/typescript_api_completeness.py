"""TypeScript api_surface completeness check — SH-14 implementation.

Prevents a partial TypeScript re-scout from being treated as complete.
Two independent signals, both advisory findings (never a hard requirement
the other must agree with):

1. Barrel-export completeness (TC-MT040-22, G-TS-10/G-TS-09) — the
   authoritative signal when available. Resolves the package's real
   barrel/entry point via extraction/lang/typescript.py's export_surface()
   (the same G-TS-02a adapter TC-17's reference filter and TC-20's
   evaluator live-fallback both consume) and compares its export set
   against api_surface.json:
     - barrel_exports_missing_from_api_surface: names the barrel actually
       exports that never made it into api_surface.json at all (a real
       scout gap).
     - exported_but_marked_unreachable: names the barrel exports (so they
       ARE reachable) but whose api_surface.json entry says
       reachable: False (an internal scout/reachability inconsistency).
   Fail-safe: when the barrel can't be resolved (no dist/ built, no bare
   index.ts -- e.g. 3d/typescript's real clone as of 2026-08-29), this
   signal is entirely absent from the report rather than guessing.

2. Regex source scan (pre-existing, hardened here) — a coarse fallback
   that greps *.d.ts/*.ts for `export class|interface|enum` declarations.
   Kept because it doesn't depend on barrel resolution succeeding, but now
   excludes node_modules/dist/build/test dirs (previously unfiltered,
   producing false "missing" findings from third-party .d.ts files) and
   only used as a secondary/fallback signal, not compared 1:1 against the
   barrel signal.

Usage:
    .venv/Scripts/python scripts/pipeline/commands/diagnostics/typescript_api_completeness.py 3d typescript
    .venv/Scripts/python scripts/pipeline/commands/diagnostics/typescript_api_completeness.py --json

Exit codes:
    0  no completeness findings
    1  a completeness finding was reported (see "pass": false in --json output)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from datetime import datetime, timezone

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
_REPO_ROOT = _DEFAULT_REPO_ROOT
_KNOWLEDGE_ROOT = _REPO_ROOT / "knowledge"
_CLONE_CACHE_ROOT = _REPO_ROOT / "runs" / ".clone_cache"


def configure(*, repo_root: "Path | None" = None) -> None:
    """Test seam: redirect repo-relative roots. Pass repo_root=None to reset
    to the real repo (module import time default)."""
    global _REPO_ROOT, _KNOWLEDGE_ROOT, _CLONE_CACHE_ROOT
    _REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    _KNOWLEDGE_ROOT = _REPO_ROOT / "knowledge"
    _CLONE_CACHE_ROOT = _REPO_ROOT / "runs" / ".clone_cache"


# Directories that never carry public product API surface -- excluding
# these from the regex source scan is what G-TS-10 calls out as the fix for
# false "missing from api_surface" findings sourced from vendored/build
# output rather than the product's own source.
_NON_PUBLIC_DIRS = frozenset({
    "node_modules", "dist", "build", "test", "tests", "__tests__",
    "coverage", ".git",
})

# TypeScript export patterns to extract class/interface/enum names.
TS_EXPORT_RE = re.compile(
    r"export\s+(?:declare\s+)?(?:class|interface|abstract\s+class|enum)\s+(\w+)",
    re.MULTILINE,
)

# Top-level exported function/const names, for the "count functions/constants"
# requirement (G-TS-10) -- source-scan signal only (the barrel-completeness
# signal above already covers these via export_surface()'s full name set).
TS_FUNCTION_CONST_EXPORT_RE = re.compile(
    r"export\s+(?:declare\s+)?(?:async\s+)?(?:function|const)\s+(\w+)",
    re.MULTILINE,
)

# Index/barrel re-export lists (`export { A, B } from './x'`). Not consumed
# directly by this module (extraction/lang/typescript.py's export_surface()
# is the authoritative barrel parser) -- kept as a recognizable pattern
# constant for callers that want a quick "does this file re-export
# anything" probe without a full barrel resolution.
TS_INDEX_EXPORT_RE = re.compile(
    r"export\s*\{([^}]+)\}",
    re.MULTILINE,
)


def _is_non_public_path(rel_parts: "tuple[str, ...]") -> bool:
    return any(part in _NON_PUBLIC_DIRS for part in rel_parts)


def load_api_surface_entries(family: str, platform: str) -> "list[dict]":
    """Load raw api_surface.json entries (merged preferred, scout fallback)."""
    for sub in ["merged", "scout"]:
        api_path = _KNOWLEDGE_ROOT / family / platform / sub / "api_surface.json"
        if api_path.exists():
            try:
                data = json.loads(api_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if isinstance(data, list):
                return [e for e in data if isinstance(e, dict)]
            if isinstance(data, dict):
                return [{"name": k, **(v if isinstance(v, dict) else {})} for k, v in data.items()]
    return []


def load_api_surface_classes(family: str, platform: str) -> "set[str]":
    """Load class/interface/enum names from api_surface.json."""
    return {e.get("name", "") for e in load_api_surface_entries(family, platform) if e.get("name")}


def load_api_surface_counts(family: str, platform: str) -> "dict[str, int]":
    """Count api_surface.json entries by kind (functions/constants included,
    not just classes -- G-TS-10)."""
    counts: "dict[str, int]" = {}
    for e in load_api_surface_entries(family, platform):
        kind = e.get("kind") or ("class" if "properties" in e or "methods" in e else "unknown")
        counts[kind] = counts.get(kind, 0) + 1
        for m in e.get("properties", []) or []:
            if isinstance(m, dict) and m.get("kind") == "constant":
                counts["constant"] = counts.get("constant", 0) + 1
    return counts


def extract_ts_exports_from_clone_cache(family: str, platform: str) -> "set[str]":
    """Regex fallback: exported class/interface/enum names from TypeScript
    source, excluding node_modules/dist/build/test directories."""
    clone_dir = _CLONE_CACHE_ROOT / f"aspose_{family}_{platform}"
    if not clone_dir.exists():
        return set()

    exported_classes: "set[str]" = set()

    def _scan(pattern: str) -> "set[str]":
        names: "set[str]" = set()
        for ts_file in clone_dir.rglob(pattern):
            rel_parts = ts_file.relative_to(clone_dir).parts[:-1]
            if _is_non_public_path(rel_parts):
                continue
            try:
                content = ts_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for match in TS_EXPORT_RE.finditer(content):
                names.add(match.group(1))
        return names

    # .d.ts declaration files are the most reliable signal for public API.
    exported_classes = _scan("*.d.ts")

    # Fall back to .ts source files only when no .d.ts declarations exist.
    if not exported_classes:
        names: "set[str]" = set()
        for ts_file in clone_dir.rglob("*.ts"):
            if ts_file.suffix == ".d.ts":
                continue
            rel_parts = ts_file.relative_to(clone_dir).parts[:-1]
            if _is_non_public_path(rel_parts):
                continue
            try:
                content = ts_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for match in TS_EXPORT_RE.finditer(content):
                names.add(match.group(1))
        exported_classes = names

    return exported_classes


def compute_barrel_completeness(family: str, platform: str) -> "dict | None":
    """Barrel-export completeness via the G-TS-02a adapter. Returns None
    (fail-safe -- no finding) when the barrel/entry point can't be resolved,
    matching lang.typescript.export_surface()'s own fail-safe contract."""
    _here = Path(__file__).resolve().parents[2]  # scripts/pipeline
    if str(_here) not in sys.path:
        sys.path.insert(0, str(_here))
    try:
        from extraction import lang
        from extraction.package_root import detect_package_root
        from core.clone_cache import clone_path
    except ImportError:
        return None

    repo = clone_path(family, platform)
    if not repo.is_dir():
        return None
    pkg_root = detect_package_root(repo, "typescript")
    names, _entry = lang.typescript.export_surface(repo, pkg_root)
    if names is None:
        return None

    entries = load_api_surface_entries(family, platform)
    by_name = {e.get("name"): e for e in entries if e.get("name")}

    missing = sorted(n for n in names if n not in by_name)
    exported_but_unreachable = sorted(
        n for n in names if n in by_name and by_name[n].get("reachable") is False
    )
    return {
        "barrel_export_count": len(names),
        "barrel_exports_missing_from_api_surface": missing,
        "exported_but_marked_unreachable": exported_but_unreachable,
    }


def main():
    parser = argparse.ArgumentParser(description="TypeScript api_surface completeness check")
    parser.add_argument("family", nargs="?", default="3d", help="Product family")
    parser.add_argument("platform", nargs="?", default="typescript", help="Product platform")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    family = args.family
    platform = args.platform

    api_classes = load_api_surface_classes(family, platform)
    api_counts = load_api_surface_counts(family, platform)
    source_exports = extract_ts_exports_from_clone_cache(family, platform)
    barrel = compute_barrel_completeness(family, platform)

    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "product": f"{family}/{platform}",
        "api_surface_classes": sorted(api_classes),
        "api_surface_count": len(api_classes),
        "api_surface_kind_counts": api_counts,
        "source_exported_classes": sorted(source_exports),
        "source_export_count": len(source_exports),
        "missing_from_api_surface": [],
        "barrel_completeness": barrel,
        "pass": True,
    }

    if source_exports:
        missing = source_exports - api_classes
        # Filter out private-convention names.
        missing = {m for m in missing if not m.startswith("_")}
        results["missing_from_api_surface"] = sorted(missing)
        if missing:
            results["pass"] = False
            results["coverage_percent"] = round(
                100 * len(api_classes.intersection(source_exports)) / len(source_exports), 1
            ) if source_exports else 0
    else:
        results["warning"] = "No TypeScript source exports found in clone cache"
        results["clone_cache_present"] = (
            _CLONE_CACHE_ROOT / f"aspose_{family}_{platform}"
        ).exists()

    if barrel is not None and (
        barrel["barrel_exports_missing_from_api_surface"]
        or barrel["exported_but_marked_unreachable"]
    ):
        results["pass"] = False

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        status = "PASS" if results["pass"] else "FAIL"
        print(f"\n# TypeScript api_surface Completeness Check")
        print(f"Product: {family}/{platform}")
        print(f"Status: {status}")
        print(f"  api_surface classes: {results['api_surface_count']}")
        print(f"  api_surface kind counts: {results['api_surface_kind_counts']}")
        print(f"  source exports found: {results['source_export_count']}")

        if results.get("warning"):
            print(f"  WARNING: {results['warning']}")
            print(f"  Clone cache present: {results.get('clone_cache_present', 'unknown')}")

        if results["missing_from_api_surface"]:
            print(f"  Missing from api_surface ({len(results['missing_from_api_surface'])}):")
            for cls in results["missing_from_api_surface"][:20]:
                print(f"    - {cls}")
            if len(results["missing_from_api_surface"]) > 20:
                print(f"    ... and {len(results['missing_from_api_surface']) - 20} more")
            print(f"\n  FIX: Run /repo-scout {family} {platform} then /truth-merge {family} {platform}")
        elif not results.get("warning"):
            print("  api_surface covers all public TypeScript exports (source-scan signal).")

        if barrel is None:
            print("  Barrel completeness: unresolvable (fail-safe -- no finding)")
        else:
            print(f"  Barrel completeness: {barrel['barrel_export_count']} barrel exports")
            if barrel["barrel_exports_missing_from_api_surface"]:
                print(f"    Missing from api_surface ({len(barrel['barrel_exports_missing_from_api_surface'])}):")
                for cls in barrel["barrel_exports_missing_from_api_surface"][:20]:
                    print(f"      - {cls}")
            if barrel["exported_but_marked_unreachable"]:
                print(f"    Exported but marked reachable:false ({len(barrel['exported_but_marked_unreachable'])}):")
                for cls in barrel["exported_but_marked_unreachable"][:20]:
                    print(f"      - {cls}")
            if not barrel["barrel_exports_missing_from_api_surface"] and not barrel["exported_but_marked_unreachable"]:
                print("    No barrel-completeness findings.")

    sys.exit(0 if results["pass"] else 1)


if __name__ == "__main__":
    main()
