"""TypeScript api_surface completeness check — SH-14 implementation.

Prevents 3d/typescript partial re-scout from being treated as complete.
Compares public TypeScript exports/classes against api_surface and reports
missing public classes.

Usage:
    .venv/Scripts/python scripts/pipeline/commands/diagnostics/typescript_api_completeness.py 3d typescript
    .venv/Scripts/python scripts/pipeline/commands/diagnostics/typescript_api_completeness.py --json

Exit codes:
    0  api_surface covers all public TypeScript exports
    1  Public exports missing from api_surface (incomplete re-scout)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from datetime import datetime, timezone

REPO_ROOT = Path(__file__).resolve().parents[4]
KNOWLEDGE_ROOT = REPO_ROOT / "knowledge"

# TypeScript export patterns to extract class/interface names
TS_EXPORT_RE = re.compile(
    r"export\s+(?:declare\s+)?(?:class|interface|abstract\s+class|enum)\s+(\w+)",
    re.MULTILINE,
)

# Index file patterns
TS_INDEX_EXPORT_RE = re.compile(
    r"export\s*\{([^}]+)\}",
    re.MULTILINE,
)


def load_api_surface_classes(family: str, platform: str) -> set[str]:
    """Load class names from api_surface.json."""
    for sub in ["merged", "scout"]:
        api_path = KNOWLEDGE_ROOT / family / platform / sub / "api_surface.json"
        if api_path.exists():
            try:
                data = json.loads(api_path.read_text(encoding="utf-8"))
                classes = set()
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            classes.add(item.get("name", item.get("class", "")))
                elif isinstance(data, dict):
                    classes.update(data.keys())
                return {c for c in classes if c}
            except (json.JSONDecodeError, OSError):
                pass
    return set()


def extract_ts_exports_from_clone_cache(family: str, platform: str) -> set[str]:
    """Extract exported class/interface names from TypeScript source."""
    cache_dir = REPO_ROOT / "runs" / ".clone_cache"
    product_dir_name = f"aspose_{family}_{platform}"
    clone_dir = cache_dir / product_dir_name

    if not clone_dir.exists():
        return set()

    exported_classes = set()

    # Check .d.ts declaration files (most reliable for public API)
    for ts_file in clone_dir.rglob("*.d.ts"):
        try:
            content = ts_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in TS_EXPORT_RE.finditer(content):
            exported_classes.add(match.group(1))

    # Also check .ts source files if no d.ts found
    if not exported_classes:
        for ts_file in clone_dir.rglob("*.ts"):
            if ts_file.suffix == ".d.ts":
                continue
            try:
                content = ts_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for match in TS_EXPORT_RE.finditer(content):
                exported_classes.add(match.group(1))

    return exported_classes


def main():
    parser = argparse.ArgumentParser(description="TypeScript api_surface completeness check")
    parser.add_argument("family", nargs="?", default="3d", help="Product family")
    parser.add_argument("platform", nargs="?", default="typescript", help="Product platform")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    family = args.family
    platform = args.platform

    api_classes = load_api_surface_classes(family, platform)
    source_exports = extract_ts_exports_from_clone_cache(family, platform)

    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "product": f"{family}/{platform}",
        "api_surface_classes": sorted(api_classes),
        "source_exported_classes": sorted(source_exports),
        "api_surface_count": len(api_classes),
        "source_export_count": len(source_exports),
        "missing_from_api_surface": [],
        "pass": True,
    }

    if source_exports:
        missing = source_exports - api_classes
        # Filter out private-convention names
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
            REPO_ROOT / "runs" / ".clone_cache" / f"aspose_{family}_{platform}"
        ).exists()

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        status = "PASS" if results["pass"] else "FAIL"
        print(f"\n# TypeScript api_surface Completeness Check")
        print(f"Product: {family}/{platform}")
        print(f"Status: {status}")
        print(f"  api_surface classes: {results['api_surface_count']}")
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
            print("  api_surface covers all public TypeScript exports.")

    sys.exit(0 if results["pass"] else 1)


if __name__ == "__main__":
    main()
