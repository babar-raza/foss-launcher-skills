# Adapted from aspose.org
"""check_knowledge_completeness.py — Validate knowledge completeness before downstream use.

Checks that each product's knowledge artifacts meet minimum quality thresholds after
FL removal. A product that passes is safe for content generation and validation.

Thresholds (configurable via flags):
  --min-enrichment-ratio  enriched_claims / class_count  (default 0.25)
  --min-snippet-ratio     snippet_count / class_count    (default 0.10)

Output:
  COMPLETENESS: PASS            — all products passed
  COMPLETENESS: WARN:{reasons}  — warnings (non-blocking)
  COMPLETENESS: FAIL:{reasons}  — failures (blocking)

Usage:
  python scripts/pipeline/commands/knowledge/check_knowledge_completeness.py {family} {platform}
  python scripts/pipeline/commands/knowledge/check_knowledge_completeness.py --all
  python scripts/pipeline/commands/knowledge/check_knowledge_completeness.py --all --strict
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[4]
_KNOWLEDGE_ROOT = Path(
    os.environ.get("KNOWLEDGE_ROOT", str(_REPO_ROOT / "knowledge"))
)

# New-schema field name for promoted_at
_NEW_SCHEMA_FIELD = "promoted_at"
# Old-schema field (merge.py era) — must NOT appear in compliant artifacts
_OLD_SCHEMA_FIELD = "merged_at"

_DEFAULT_MIN_ENRICHMENT_RATIO = 0.25
_DEFAULT_MIN_SNIPPET_RATIO = 0.10


def _discover_products() -> list[tuple[str, str]]:
    """Return all (family, platform) pairs that have a merged/model.yaml."""
    products = []
    for model_path in sorted(_KNOWLEDGE_ROOT.glob("*/*/merged/model.yaml")):
        parts = model_path.parts
        # parts: ..., knowledge, family, platform, merged, model.yaml
        idx = next((i for i, p in enumerate(parts) if p == "knowledge"), None)
        if idx is not None and len(parts) >= idx + 3:
            products.append((parts[idx + 1], parts[idx + 2]))
    return products


def check_product(family: str, platform: str,
                  min_enrichment_ratio: float = _DEFAULT_MIN_ENRICHMENT_RATIO,
                  min_snippet_ratio: float = _DEFAULT_MIN_SNIPPET_RATIO,
                  strict: bool = False) -> dict:
    """Check one product. Returns a result dict with status, warnings, failures."""
    base = _KNOWLEDGE_ROOT / family / platform
    merged_dir = base / "merged"
    model_path = merged_dir / "model.yaml"

    result = {
        "family": family,
        "platform": platform,
        "status": "PASS",
        "warnings": [],
        "failures": [],
    }

    # 1. merged/model.yaml must exist
    if not model_path.exists():
        result["failures"].append("merged/model.yaml missing")
        result["status"] = "FAIL"
        return result

    try:
        model = yaml.safe_load(model_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        result["failures"].append(f"model.yaml unreadable: {exc}")
        result["status"] = "FAIL"
        return result

    # 2. Schema freshness — must have promoted_at, not merged_at
    if _OLD_SCHEMA_FIELD in model:
        result["failures"].append(
            f"old schema: model.yaml has '{_OLD_SCHEMA_FIELD}' (run promote.py to migrate)")
        result["status"] = "FAIL"

    if _NEW_SCHEMA_FIELD not in model:
        result["failures"].append(
            f"new schema field '{_NEW_SCHEMA_FIELD}' missing (run promote.py)")
        result["status"] = "FAIL"

    # 3. stale_since must be null
    if model.get("stale_since") is not None:
        msg = f"stale_since={model['stale_since']} (run refresh_knowledge.py)"
        if strict:
            result["failures"].append(msg)
            result["status"] = "FAIL"
        else:
            result["warnings"].append(msg)
            if result["status"] == "PASS":
                result["status"] = "WARN"

    # 4. Enrichment ratio
    stats = model.get("stats", {})
    class_count = stats.get("class_count", 0)
    enriched_claims = stats.get("enriched_claims", 0)
    snippet_count = stats.get("snippet_count", 0)

    if class_count > 0:
        enrichment_ratio = enriched_claims / class_count
        if enrichment_ratio < min_enrichment_ratio:
            msg = (f"enrichment ratio {enrichment_ratio:.2f} < {min_enrichment_ratio:.2f} "
                   f"({enriched_claims} enriched / {class_count} classes) "
                   f"— run enrich.py --min-coverage {min_enrichment_ratio}")
            if strict:
                result["failures"].append(msg)
                result["status"] = "FAIL"
            else:
                result["warnings"].append(msg)
                if result["status"] == "PASS":
                    result["status"] = "WARN"

        snippet_ratio = snippet_count / class_count
        if snippet_ratio < min_snippet_ratio:
            msg = (f"snippet ratio {snippet_ratio:.2f} < {min_snippet_ratio:.2f} "
                   f"({snippet_count} snippets / {class_count} classes) "
                   f"— run scout.py to regenerate snippets")
            # snippets only warn, not fail (even in strict mode)
            result["warnings"].append(msg)
            if result["status"] == "PASS":
                result["status"] = "WARN"

    # 5. Critical artifact files must exist
    for fname in ["api_surface.json", "claims.json", "index.json"]:
        if not (merged_dir / fname).exists():
            result["failures"].append(f"merged/{fname} missing")
            result["status"] = "FAIL"

    return result


def _print_result(r: dict, verbose: bool = True) -> None:
    tag = f"{r['family']}/{r['platform']}"
    status = r["status"]
    if verbose:
        print(f"  {tag}: {status}")
        for w in r["warnings"]:
            print(f"    WARN: {w}")
        for f in r["failures"]:
            print(f"    FAIL: {f}")
    else:
        issues = r["warnings"] + r["failures"]
        if issues:
            print(f"  {tag}: {status} — {'; '.join(issues)}")
        else:
            print(f"  {tag}: {status}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate knowledge completeness after FL removal.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("family", nargs="?", help="Product family (e.g. '3d')")
    parser.add_argument("platform", nargs="?", help="Platform (e.g. 'python')")
    group.add_argument("--all", action="store_true",
                       help="Check all discovered products")
    parser.add_argument("--strict", action="store_true",
                        help="Treat warnings as failures")
    parser.add_argument("--min-enrichment-ratio", type=float,
                        default=_DEFAULT_MIN_ENRICHMENT_RATIO,
                        help=f"Min enriched/class ratio (default {_DEFAULT_MIN_ENRICHMENT_RATIO})")
    parser.add_argument("--min-snippet-ratio", type=float,
                        default=_DEFAULT_MIN_SNIPPET_RATIO,
                        help=f"Min snippet/class ratio (default {_DEFAULT_MIN_SNIPPET_RATIO})")
    parser.add_argument("--knowledge-root", type=Path, default=None,
                        help="Override knowledge root directory")
    args = parser.parse_args()

    if args.knowledge_root is not None:
        global _KNOWLEDGE_ROOT
        _KNOWLEDGE_ROOT = args.knowledge_root

    kwargs = {
        "min_enrichment_ratio": args.min_enrichment_ratio,
        "min_snippet_ratio": args.min_snippet_ratio,
        "strict": args.strict,
    }

    if args.all:
        products = _discover_products()
        if not products:
            print("No products found under knowledge/")
            sys.exit(1)
        print(f"Checking {len(products)} products...")
        results = [check_product(f, p, **kwargs) for f, p in products]
    else:
        if not args.family or not args.platform:
            parser.error("Provide {family} {platform} or --all")
        results = [check_product(args.family, args.platform, **kwargs)]

    any_fail = False
    any_warn = False
    for r in results:
        _print_result(r)
        if r["status"] == "FAIL":
            any_fail = True
        elif r["status"] == "WARN":
            any_warn = True

    if any_fail:
        overall = "FAIL"
    elif any_warn:
        overall = "WARN"
    else:
        overall = "PASS"

    print(f"\nCOMPLETENESS: {overall}")
    sys.exit(0 if overall in ("PASS", "WARN") else 1)


if __name__ == "__main__":
    main()
