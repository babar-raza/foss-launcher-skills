"""registry_coverage_scan.py — Mission MT018-2026-08-01-PACKAGE-IDENTITY-COVERAGE, TC-MT018-03.

Enumeration step for the package-registry backfill: unions two independent
product-discovery sources, diffs the result against `data/package_registry.json`
and `data/registry_exclusions.json`, and produces the authoritative list of
family/platform pairs that need a registry entry.

Root cause this closes: MT015's registry (`data/package_registry.json`) was built
reactively, one incident at a time -- 7 of 31 launched products ever got an entry.
No prior tool ever asked "which of the site's real, launched products are missing
from the registry?" A full-repo audit (2026-08-01) found 14 of the 24 missing
products had genuinely wrong install instructions as a direct result.

Two independent sources, unioned (not just one trusted blindly):
  1. `content_discovery.discover_products()` -- products with a knowledge model
     (has knowledge/{family}/{platform}/merged/api_surface.json).
  2. A direct scan of `content/products.aspose.org/en/*/*/` -- products with a
     live products.aspose.org page.
Confirmed by direct comparison (2026-08-01): both sources currently agree exactly
(31/31) -- the union exists so a future divergence (a product with a live page but
no knowledge model, or vice versa) is caught rather than silently trusted from one
source alone.

`data/registry_exclusions.json` entries are cross-referenced, not filtered out --
a family/platform that is both (a) live under products.aspose.org and (b) flagged
`family_platform`-excluded is a real, separate finding (see cells/typescript, found
2026-08-01: excluded as BLOCKED_REPO_NOT_LAUNCHABLE yet still live with fabricated
install content) and must be reported, not silently dropped from either list.

CLI:
    PYTHONPATH=scripts/pipeline .venv/Scripts/python -m commands.ops.registry_coverage_scan
    PYTHONPATH=scripts/pipeline .venv/Scripts/python -m commands.ops.registry_coverage_scan --json
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

from lib.content_discovery import discover_products  # noqa: E402
from lib import content_discovery  # noqa: E402
from lib.package_registry_data import load_registry  # noqa: E402

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
_REPO_ROOT = _DEFAULT_REPO_ROOT
_CONTENT_ROOT = _DEFAULT_REPO_ROOT / "content"
_EXCLUSIONS_PATH = _DEFAULT_REPO_ROOT / "data" / "registry_exclusions.json"


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """configure() seam (AGENTS.md 16) -- override roots for testing."""
    global _REPO_ROOT, _CONTENT_ROOT, _EXCLUSIONS_PATH
    _REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    _CONTENT_ROOT = _REPO_ROOT / "content"
    _EXCLUSIONS_PATH = _REPO_ROOT / "data" / "registry_exclusions.json"
    content_discovery.configure(repo_root=repo_root)


def _discover_knowledge_products() -> list[tuple[str, str]]:
    """Wraps content_discovery.discover_products() -- tolerates a missing
    knowledge/ directory (real repo always has one; test fixtures may not)."""
    if not content_discovery.KNOWLEDGE_ROOT.is_dir():
        return []
    return discover_products()


def scan_products_directory() -> list[tuple[str, str]]:
    """Enumerate every family/platform with a live products.aspose.org page."""
    base = _CONTENT_ROOT / "products.aspose.org" / "en"
    if not base.is_dir():
        return []
    pairs = []
    for family_dir in sorted(base.iterdir()):
        if not family_dir.is_dir():
            continue
        for platform_dir in sorted(family_dir.iterdir()):
            if not platform_dir.is_dir():
                continue
            if (platform_dir / "_index.md").exists():
                pairs.append((family_dir.name, platform_dir.name))
    return pairs


def load_exclusions() -> list[dict[str, Any]]:
    if not _EXCLUSIONS_PATH.is_file():
        return []
    return json.loads(_EXCLUSIONS_PATH.read_text(encoding="utf-8"))


def _excluded_family_platforms(exclusions: list[dict[str, Any]]) -> set[tuple[str, str]]:
    return {
        (e["family"], e["platform"])
        for e in exclusions
        if e.get("match") == "family_platform"
    }


def scan_coverage() -> dict[str, Any]:
    """Union both discovery sources, diff against the registry, cross-reference
    exclusions. Returns a structured report -- never mutates anything."""
    knowledge_pairs = set(_discover_knowledge_products())
    content_pairs = set(scan_products_directory())
    union_pairs = knowledge_pairs | content_pairs
    divergent = knowledge_pairs ^ content_pairs  # symmetric difference -- disagreement is a finding

    registry_path = _REPO_ROOT / "data" / "package_registry.json"
    registry = load_registry(registry_path) if registry_path.is_file() else {}
    registered_pairs = {
        (family, platform)
        for family, platforms in registry.items()
        if not family.startswith("_")
        for platform in platforms
    }

    exclusions = load_exclusions()
    excluded_pairs = _excluded_family_platforms(exclusions)

    uncovered = sorted(union_pairs - registered_pairs)
    excluded_but_live = sorted(excluded_pairs & content_pairs)

    return {
        "total_discovered": len(union_pairs),
        "total_registered": len(registered_pairs),
        "uncovered_pairs": [f"{f}/{p}" for f, p in uncovered],
        "divergent_pairs": sorted(f"{f}/{p}" for f, p in divergent),
        "excluded_but_still_live": [f"{f}/{p}" for f, p in excluded_but_live],
    }


def main(argv: "list[str] | None" = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="registry_coverage_scan")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    args = parser.parse_args(argv)

    report = scan_coverage()

    if args.json:
        print(json.dumps(report, indent=2))
        return 0 if not report["uncovered_pairs"] else 1

    print(f"=== registry_coverage_scan ===")
    print(f"Discovered products: {report['total_discovered']}")
    print(f"Registered in data/package_registry.json: {report['total_registered']}")
    print(f"Uncovered ({len(report['uncovered_pairs'])}):")
    for pair in report["uncovered_pairs"]:
        print(f"  {pair}")
    if report["divergent_pairs"]:
        print(f"WARNING: knowledge-model vs content-directory discovery disagree on: {report['divergent_pairs']}")
    if report["excluded_but_still_live"]:
        print(f"WARNING: excluded in registry_exclusions.json but still live under products.aspose.org: {report['excluded_but_still_live']}")

    return 0 if not report["uncovered_pairs"] else 1


if __name__ == "__main__":
    sys.exit(main())
