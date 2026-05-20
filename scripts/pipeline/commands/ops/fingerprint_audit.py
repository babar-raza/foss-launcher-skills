# Adapted from aspose.org
"""fingerprint_audit.py — Durable live fingerprint audit for the S-84 refresh pipeline.

FOLLOWUP-MON-001: Creates a persistent report of live fingerprint collection results
across all configured products and surfaces, verifying that required fingerprints
are non-None and collection errors are empty.

Usage:
    .venv/Scripts/python scripts/pipeline/commands/ops/fingerprint_audit.py [--output PATH] [--surfaces SURFACE...]

Exit codes:
    0 -- all required fingerprints non-None, no collection errors
    1 -- one or more required fingerprints are None, or collection errors occurred
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[3]

for _p in [str(_REPO_ROOT / "scripts" / "pipeline" / "lib"),
           str(_REPO_ROOT / "scripts" / "pipeline")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from dependency_registry import load_registry  # noqa: E402
try:
    from fingerprint_collector import collect_input_fingerprints  # noqa: E402
except ImportError:
    collect_input_fingerprints = None  # Not available in foss; stub for portability


_DEFAULT_OUTPUT = (
    _REPO_ROOT / "reports" / "serene-jingling-rain" / "monitoring" / "live-fingerprint-audit.json"
)


def _load_products(repo_root: Path) -> list[str]:
    """Load active products from data/products.json as 'family/platform' slugs."""
    products_file = repo_root / "data" / "products.json"
    data = json.loads(products_file.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [
            f"{e['family']}/{e['platform']}"
            for e in data
            if e.get("active", True) and e.get("family") and e.get("platform")
        ]
    return []


def run_audit(
    surfaces: list[str] | None = None,
    output_path: Path | None = None,
    repo_root: Path | None = None,
) -> dict:
    root = repo_root or _REPO_ROOT
    out = output_path or _DEFAULT_OUTPUT
    registry = load_registry(root / "data" / "refresh-dependencies.json")
    audit_surfaces = surfaces or registry.surface_names()
    products = _load_products(root)

    results = []
    all_ok = True

    for surface_name in audit_surfaces:
        try:
            surface = registry.get_surface(surface_name)
        except Exception as exc:
            results.append({"surface": surface_name, "error": str(exc)})
            all_ok = False
            continue

        required = surface.fingerprints_required

        for product in products:
            if collect_input_fingerprints is None:
                results.append({"surface": surface_name, "product": product, "error": "fingerprint_collector not available"})
                all_ok = False
                continue
            fp = collect_input_fingerprints(product, surface_name, registry, repo_root=root)
            live = fp.to_dict()
            missing_required = [k for k in required if live.get(k) is None]
            # TC-A7-007: fingerprints that are None but NOT in fingerprints_required
            # are N/A for this surface (e.g. skill_version_hash for validate_only surfaces).
            # They are reported as WARN, not FAIL.
            not_applicable = [k for k in live if k not in required and live.get(k) is None]
            errors = fp.collection_errors

            if missing_required or errors:
                status = "FAIL"
                all_ok = False
            elif not_applicable:
                status = "WARN_NA"  # Not a failure — fingerprint is N/A for this surface
            else:
                status = "OK"

            results.append({
                "product": product,
                "surface": surface_name,
                "status": status,
                "missing_required": missing_required,
                "not_applicable": not_applicable,
                "collection_errors": errors,
                "fingerprints": {
                    k: (v[:40] if isinstance(v, str) and len(v) > 40 else v)
                    for k, v in live.items()
                    if v is not None
                },
            })

    report = {
        "run_date": datetime.now(timezone.utc).isoformat(),
        "overall": "PASS" if all_ok else "FAIL",
        "surfaces_audited": audit_surfaces,
        "products_count": len(products),
        "results_count": len(results),
        "fail_count": sum(1 for r in results if r.get("status") == "FAIL"),
        # TC-A7-007: WARN_NA = fingerprint is None but not required for this surface (not a failure)
        "warn_na_count": sum(1 for r in results if r.get("status") == "WARN_NA"),
        "results": results,
    }

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Live fingerprint audit for S-84 refresh pipeline"
    )
    parser.add_argument(
        "--output", type=Path, default=_DEFAULT_OUTPUT,
        help="Output JSON report path",
    )
    parser.add_argument(
        "--surfaces", nargs="+",
        help="Surfaces to audit (default: all configured)",
    )
    args = parser.parse_args(argv)

    report = run_audit(surfaces=args.surfaces, output_path=args.output)

    print(f"Fingerprint audit: {report['overall']}")
    print(f"  Products: {report['products_count']}  Surfaces: {len(report['surfaces_audited'])}")
    print(f"  Failures: {report['fail_count']}/{report['results_count']}")
    print(f"  WARN_NA:  {report['warn_na_count']}/{report['results_count']}  (N/A fingerprints — not failures)")
    print(f"  Report:   {args.output}")

    if report["overall"] == "FAIL":
        for r in report["results"]:
            if r.get("status") == "FAIL":
                print(
                    f"  FAIL  {r['product']}/{r['surface']}: "
                    f"missing={r['missing_required']} errors={r['collection_errors']}"
                )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
