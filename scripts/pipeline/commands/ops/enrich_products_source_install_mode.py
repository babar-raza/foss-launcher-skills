"""enrich_products_source_install_mode.py — TC-PSD-HRD-10-03c (permanent fix of F-PSD-07).

One-time (re-run as needed, not scheduled) enrichment: for every active entry in
data/products.json, run lib.source_install.determine_source_install_mode() against the real,
already-cloned source in runs/.clone_cache/ and write the real source_install_mode field onto
the matching entry -- same precedent as enrich_products_cmake_targets.py (ST-054 TC-12):
`update_product_registry.py::_merge()` preserves any field not in its explicit overwrite
allowlist, so this field survives a registry regeneration with no extra code needed.

Never guesses: "standard" (the common, default case -- today's unconditional per-platform
behavior is viable) is left ABSENT from the row, keeping the diff minimal and matching the
partial's own `source_install_mode` default (absent == "standard"). Only a genuinely different
mode ("pythonpath") or a genuinely NOT-viable repo (None) is written explicitly, the latter as
the literal JSON value `null` -- a visible signal for `upstream_readiness_check.py`'s U-04, never
silently dropped.

CLI:
    PYTHONPATH=scripts/pipeline .venv/Scripts/python -m commands.ops.enrich_products_source_install_mode --dry-run
    PYTHONPATH=scripts/pipeline .venv/Scripts/python -m commands.ops.enrich_products_source_install_mode --execute
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

from lib.source_install import determine_source_install_mode  # noqa: E402

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
_REPO_ROOT = _DEFAULT_REPO_ROOT
_CLONE_CACHE_ROOT = _REPO_ROOT / "runs" / ".clone_cache"
_PRODUCTS_PATH = _REPO_ROOT / "data" / "products.json"


def configure(*, repo_root: "Path | str | None" = None) -> None:
    global _REPO_ROOT, _CLONE_CACHE_ROOT, _PRODUCTS_PATH
    _REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    _CLONE_CACHE_ROOT = _REPO_ROOT / "runs" / ".clone_cache"
    _PRODUCTS_PATH = _REPO_ROOT / "data" / "products.json"


def run_enrichment(*, dry_run: bool = True) -> dict[str, Any]:
    products = json.loads(_PRODUCTS_PATH.read_text(encoding="utf-8"))

    results = []
    changed = 0
    for entry in products:
        if not entry.get("active"):
            continue
        family, platform = entry.get("family"), entry.get("platform")
        clone_dir = _CLONE_CACHE_ROOT / f"aspose_{family}_{platform}"
        mode = determine_source_install_mode(platform, clone_dir) if clone_dir.is_dir() else None
        before = entry.get("source_install_mode")
        if mode == "standard":
            if "source_install_mode" in entry:
                del entry["source_install_mode"]
                changed += 1
        else:
            if before != mode:
                entry["source_install_mode"] = mode
                changed += 1
        if mode != "standard" or before not in (None, "standard"):
            results.append({"family": family, "platform": platform, "mode": mode, "before": before})

    if not dry_run and changed:
        _PRODUCTS_PATH.write_text(json.dumps(products, indent=2) + "\n", encoding="utf-8")

    return {"changed": changed, "results": results, "dry_run": dry_run}


def main(argv: "list[str] | None" = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="enrich_products_source_install_mode")
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)

    dry_run = not args.execute
    summary = run_enrichment(dry_run=dry_run)

    mode_label = "DRY-RUN" if dry_run else "EXECUTE"
    print(f"=== enrich_products_source_install_mode [{mode_label}] ===")
    print(f"rows changed: {summary['changed']}")
    for r in summary["results"]:
        print(f"  {r['family']}/{r['platform']}: {r['before']!r} -> {r['mode']!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
