"""enrich_products_cmake_targets.py — ST-054 TC-12
(plans/from_backlog/2026-08-16-st-054-inline-install-command-remediation.md,
governing plan §Q.3a: GitHub-fallback rendering fix).

One-time (re-run as needed, not scheduled) enrichment: for every C++ platform entry
in data/products.json belonging to a currently-unpublished data/package_registry.json
family/platform, run lib.input_manifest.resolve_cpp_target() against the real,
already-cloned source in runs/.clone_cache/ and write the extracted, real
`cmake_project`/`cmake_target` fields onto the matching products.json entry.

Never guesses: a product whose CMakeLists.txt structure is ambiguous (multiple
add_library targets, no ALIAS to disambiguate) or missing gets `cmake_target: null`
-- the GitHub-fallback shortcode (ST-054 TC-13) falls back to a generic,
target-name-free snippet for that one product only when this field is null, never a
guess. Idempotent: re-running overwrites with freshly re-extracted values, safe to
run again after a clone-cache refresh.

CLI:
    PYTHONPATH=scripts/pipeline .venv/Scripts/python -m commands.ops.enrich_products_cmake_targets --dry-run
    PYTHONPATH=scripts/pipeline .venv/Scripts/python -m commands.ops.enrich_products_cmake_targets --execute
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from input_manifest import resolve_cpp_target  # noqa: E402
from package_registry_data import load_registry  # noqa: E402

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
_REPO_ROOT = _DEFAULT_REPO_ROOT
_CLONE_CACHE_ROOT = _REPO_ROOT / "runs" / ".clone_cache"
_PRODUCTS_PATH = _REPO_ROOT / "data" / "products.json"
_REGISTRY_PATH = _REPO_ROOT / "data" / "package_registry.json"


def configure(*, repo_root: "Path | str | None" = None) -> None:
    global _REPO_ROOT, _CLONE_CACHE_ROOT, _PRODUCTS_PATH, _REGISTRY_PATH
    _REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    _CLONE_CACHE_ROOT = _REPO_ROOT / "runs" / ".clone_cache"
    _PRODUCTS_PATH = _REPO_ROOT / "data" / "products.json"
    _REGISTRY_PATH = _REPO_ROOT / "data" / "package_registry.json"


def _unpublished_cpp_pairs(registry: dict[str, Any]) -> set[tuple[str, str]]:
    """(family, platform) pairs where platform == 'cpp' and verification.published
    is False. Not scoped to registry_type == 'nuget' specifically -- the C++
    platforms in this portfolio are classified nuget in the schema today (a separate,
    known inconsistency, see governing plan §Q's own finding) but this enrichment's
    job is purely "is this an unpublished cpp product," independent of that."""
    pairs = set()
    for family, platforms in registry.items():
        if not isinstance(platforms, dict):
            continue
        entry = platforms.get("cpp")
        if not isinstance(entry, dict):
            continue
        if entry.get("verification", {}).get("published") is False:
            pairs.add((family, "cpp"))
    return pairs


def run_enrichment(*, dry_run: bool = True) -> dict[str, Any]:
    registry = load_registry(_REGISTRY_PATH)
    products = json.loads(_PRODUCTS_PATH.read_text(encoding="utf-8"))
    targets = _unpublished_cpp_pairs(registry)

    results = []
    for entry in products:
        family = entry.get("family")
        platform = entry.get("platform")
        if (family, platform) not in targets:
            continue
        repo_name = entry.get("repo_name")
        clone_dir = _CLONE_CACHE_ROOT / f"aspose_{family}_{platform}"
        extraction = resolve_cpp_target(clone_dir)
        entry["cmake_project"] = extraction.get("cmake_project")
        entry["cmake_target"] = extraction.get("cmake_target")
        results.append({
            "family": family, "platform": platform, "repo_name": repo_name,
            "clone_dir": str(clone_dir), **extraction,
        })

    if not dry_run:
        _PRODUCTS_PATH.write_text(json.dumps(products, indent=2) + "\n", encoding="utf-8")

    return {"targets_found": len(targets), "results": results, "dry_run": dry_run}


def main(argv: "list[str] | None" = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="enrich_products_cmake_targets")
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)

    dry_run = not args.execute
    summary = run_enrichment(dry_run=dry_run)

    mode = "DRY-RUN" if dry_run else "EXECUTE"
    print(f"=== enrich_products_cmake_targets [{mode}] ===")
    print(f"unpublished cpp products found in registry: {summary['targets_found']}")
    for r in summary["results"]:
        print(f"  {r['family']}/{r['platform']}: cmake_target={r.get('cmake_target')!r}"
              + (f" ({r.get('reason')})" if r.get("cmake_target") is None else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
