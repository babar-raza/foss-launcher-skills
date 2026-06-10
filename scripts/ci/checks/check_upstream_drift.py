#!/usr/bin/env python3
"""Check upstream FOSS repositories for SHA drift against committed baselines.

Reads data/upstream_baselines.json (committed) and data/products.json,
fetches HEAD SHA from each active product's GitHub repo, and reports drift.

Exit codes:
  0 — no drift detected (all SHAs match)
  1 — drift detected (at least one HIGH or MEDIUM change)
  2 — configuration error

Requires GH_TOKEN environment variable for GitHub API access.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
BASELINES_PATH = REPO_ROOT / "data" / "upstream_baselines.json"
PRODUCTS_PATH = REPO_ROOT / "data" / "products.json"

SOURCE_EXTENSIONS = frozenset({
    ".py", ".java", ".cs", ".ts", ".js", ".cpp", ".h", ".hpp",
    ".go", ".rs", ".kt", ".swift", ".rb",
})


def _gh_api(endpoint: str) -> str | None:
    """Call gh api and return stdout, or None on failure."""
    try:
        result = subprocess.run(
            ["gh", "api", endpoint, "--jq", ".sha"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def _gh_compare(owner_repo: str, base: str, head: str) -> str:
    """Compare two SHAs and classify the change impact."""
    try:
        result = subprocess.run(
            ["gh", "api", f"repos/{owner_repo}/compare/{base}...{head}",
             "--jq", "[.files[].filename] | join(\"\\n\")"],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            return "MEDIUM"  # cannot determine
        files = result.stdout.strip().split("\n") if result.stdout.strip() else []
        for f in files:
            if any(f.endswith(ext) for ext in SOURCE_EXTENSIONS):
                return "HIGH"
        return "LOW" if files else "NO_CHANGE"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return "MEDIUM"


def main() -> int:
    if not BASELINES_PATH.exists():
        print(f"ERROR: {BASELINES_PATH} not found", file=sys.stderr)
        return 2
    if not PRODUCTS_PATH.exists():
        print(f"ERROR: {PRODUCTS_PATH} not found", file=sys.stderr)
        return 2

    if not os.environ.get("GH_TOKEN") and not os.environ.get("GITHUB_TOKEN"):
        print("ERROR: GH_TOKEN or GITHUB_TOKEN required", file=sys.stderr)
        return 2

    baselines: dict[str, str] = json.loads(BASELINES_PATH.read_text())
    products: list[dict] = json.loads(PRODUCTS_PATH.read_text())

    active_products = [p for p in products if p.get("active", False)]

    findings: list[dict] = []
    no_drift_count = 0
    error_count = 0

    for product in active_products:
        key = f"{product['family']}/{product['platform']}"
        stored_sha = baselines.get(key, "")
        repo_url = product.get("repo_url", "")

        if not repo_url:
            print(f"  SKIP {key}: no repo_url")
            continue

        owner_repo = repo_url.replace("https://github.com/", "").rstrip("/")
        head_sha = _gh_api(f"repos/{owner_repo}/commits/HEAD")

        if not head_sha:
            findings.append({"product": key, "level": "MEDIUM", "reason": "API_FETCH_FAILED"})
            error_count += 1
            print(f"  MEDIUM {key}: could not fetch HEAD SHA")
            continue

        if not stored_sha:
            findings.append({"product": key, "level": "HIGH", "reason": "NO_BASELINE", "head": head_sha})
            print(f"  HIGH {key}: no baseline SHA stored")
            continue

        if head_sha == stored_sha:
            no_drift_count += 1
            continue

        level = _gh_compare(owner_repo, stored_sha, head_sha)
        if level == "NO_CHANGE":
            no_drift_count += 1
            continue

        findings.append({
            "product": key,
            "level": level,
            "stored": stored_sha[:12],
            "head": head_sha[:12],
        })
        print(f"  {level} {key}: {stored_sha[:12]} -> {head_sha[:12]}")

    print(f"\nSummary: {no_drift_count} unchanged, {len(findings)} drift, {error_count} errors")

    high_medium = [f for f in findings if f["level"] in ("HIGH", "MEDIUM")]
    if high_medium:
        print(f"\nACTION REQUIRED: {len(high_medium)} product(s) have upstream changes")
        for f in high_medium:
            print(f"  - {f['product']}: {f['level']}")
        return 1

    print("\nAll baselines current.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
