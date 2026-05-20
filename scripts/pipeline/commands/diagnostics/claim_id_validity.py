# Adapted from aspose.org
"""Claim ID validity evaluator — TC-FN-001B implementation.

Detects stale, orphaned, or invalid claim IDs in content evidence blocks.
A claim ID is stale/orphaned if it appears in evidence.sections[*].claims
but does not exist in the product's knowledge/claims.json.

Exit codes:
    0  No stale or orphaned claim IDs found
    1  One or more stale/orphaned claim IDs found
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(os.environ.get("FOSS_REPO_ROOT", Path(__file__).resolve().parents[4]))
KNOWLEDGE_ROOT = REPO_ROOT / "knowledge"
CONTENT_ROOT = Path(os.environ.get("FOSS_CONTENT_ROOT", REPO_ROOT / "content"))

# Scoped products — override via FOSS_SCOPED_PRODUCTS_TUPLES env var
# Format: "family:platform,family:platform,..."
_DEFAULT_SCOPED_PRODUCTS = [
    ("cells", "java"), ("cells", "net"), ("cells", "python"),
    ("slides", "java"), ("slides", "net"), ("slides", "python"), ("slides", "cpp"),
    ("words", "python"),
    ("email", "net"), ("email", "cpp"), ("email", "python"),
    ("note", "python"),
    ("3d", "java"), ("3d", "net"), ("3d", "python"), ("3d", "typescript"),
]

def _load_scoped_products() -> list[tuple[str, str]]:
    env = os.environ.get("FOSS_SCOPED_PRODUCTS_TUPLES")
    if env:
        return [tuple(p.split(":")) for p in env.split(",") if ":" in p]
    return _DEFAULT_SCOPED_PRODUCTS

SCOPED_PRODUCTS = _load_scoped_products()

# Claim ID patterns
CLAIM_ID_PATTERN = re.compile(r"\b((?:CLM|ERC)-[\w-]+)\b")

# Configurable content subdirectories — override via FOSS_CONTENT_SITES env var
# Default sites that contain content for products
_DEFAULT_CONTENT_SITES = [
    "blog",
    "docs",
    "kb",
    "reference",
]

def _get_content_sites() -> list[str]:
    env = os.environ.get("FOSS_CONTENT_SITES")
    if env:
        return [s.strip() for s in env.split(",")]
    return _DEFAULT_CONTENT_SITES


def load_valid_claim_ids(family: str, platform: str) -> set[str]:
    """Load all valid claim IDs from the knowledge claims.json for a product."""
    claims_path = KNOWLEDGE_ROOT / family / platform / "merged" / "claims.json"
    if not claims_path.exists():
        claims_path = KNOWLEDGE_ROOT / family / platform / "scout" / "claims.json"
    if not claims_path.exists():
        return set()

    try:
        data = json.loads(claims_path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return {item.get("claim_id") or item.get("id", "") for item in data if isinstance(item, dict)}
        if isinstance(data, dict):
            return set(data.keys())
        return set()
    except (json.JSONDecodeError, OSError):
        return set()


def extract_claim_ids_from_content(content: str) -> list[str]:
    """Extract all claim IDs from an evidence block in a content file."""
    ids = []
    in_evidence = False
    in_claims = False

    for line in content.splitlines():
        stripped = line.strip()
        if stripped == "evidence:":
            in_evidence = True
        elif in_evidence and stripped.startswith("claims:"):
            in_claims = True
        elif in_claims and stripped.startswith("- "):
            candidate = stripped[2:].strip()
            if CLAIM_ID_PATTERN.match(candidate):
                ids.append(candidate)
        elif in_claims and not stripped.startswith("- ") and stripped:
            if ":" in stripped and not stripped.startswith("#"):
                in_claims = False

    return ids


def check_product(family: str, platform: str) -> dict:
    """Check a single product for stale claim IDs."""
    valid_ids = load_valid_claim_ids(family, platform)
    findings = []

    # Build content directories to search — adapts to whatever site layout exists
    content_dirs = []
    for site in _get_content_sites():
        # Try both with and without /en/ prefix (different site layouts)
        for variant in [
            CONTENT_ROOT / site / family / platform,
            CONTENT_ROOT / site / "en" / family / platform,
        ]:
            if variant.exists():
                content_dirs.append(variant)

    for content_dir in content_dirs:
        for md_file in content_dir.rglob("*.md"):
            try:
                content = md_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            claim_ids = CLAIM_ID_PATTERN.findall(content)
            if not claim_ids:
                continue

            stale = []
            for claim_id in claim_ids:
                if valid_ids and claim_id not in valid_ids:
                    stale.append(claim_id)

            if stale:
                findings.append({
                    "file": str(md_file.relative_to(REPO_ROOT)),
                    "stale_claim_ids": stale,
                    "total_claim_ids": len(claim_ids),
                    "valid_ids_available": bool(valid_ids),
                })

    return {
        "product": f"{family}/{platform}",
        "valid_ids_loaded": len(valid_ids),
        "files_with_stale": len(findings),
        "findings": findings,
    }


def main():
    parser = argparse.ArgumentParser(description="Claim ID validity evaluator (TC-FN-001B)")
    parser.add_argument("family", nargs="?", help="Product family (e.g. words)")
    parser.add_argument("platform", nargs="?", help="Product platform (e.g. python)")
    parser.add_argument("--all", action="store_true", help="Check all scoped products")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    if args.all:
        products_to_check = SCOPED_PRODUCTS
    elif args.family and args.platform:
        products_to_check = [(args.family, args.platform)]
    else:
        parser.error("Provide family and platform, or --all")

    all_results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "products": [],
        "total_files_with_stale": 0,
        "pass": True,
    }

    for family, platform in products_to_check:
        result = check_product(family, platform)
        all_results["products"].append(result)
        all_results["total_files_with_stale"] += result["files_with_stale"]

    if all_results["total_files_with_stale"] > 0:
        all_results["pass"] = False

    if args.json:
        print(json.dumps(all_results, indent=2))
    else:
        status = "PASS" if all_results["pass"] else "FAIL"
        print(f"\n# Claim ID Validity Evaluator (TC-FN-001B)")
        print(f"Timestamp: {all_results['timestamp']}")
        print(f"Status: {status} — {all_results['total_files_with_stale']} file(s) with stale/orphaned claim IDs\n")

        for product in all_results["products"]:
            if product["files_with_stale"]:
                print(f"  FAIL [{product['product']}] — {product['files_with_stale']} file(s):")
                for finding in product["findings"]:
                    print(f"    {finding['file']}: {finding['stale_claim_ids']}")
            else:
                valid_note = f"({product['valid_ids_loaded']} valid IDs loaded)"
                print(f"  PASS [{product['product']}] {valid_note}")

    sys.exit(0 if all_results["pass"] else 1)


if __name__ == "__main__":
    main()
