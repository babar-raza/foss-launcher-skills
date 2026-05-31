"""
discover.py — Detect stale, fresh, and missing products from knowledge/ model.yaml.

Reads knowledge/{family}/{platform}/merged/model.yaml for every product.
  stale_since != null  -> stale_products
  stale_since == null  -> fresh_products
  missing model.yaml   -> missing_products

Optionally reads reports/change-sweep/ if present.

Exit 0 always (including when stale products found — not a fatal condition).
Exit 1 only on fatal internal errors.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
from _common import REPO_ROOT, base_args, safe_emit


def discover(repo_root=None):
    """
    Walk knowledge/{family}/{platform}/merged/model.yaml.
    Returns dict with stale_products, fresh_products, missing_products, warnings, source_files_read.
    """
    root = Path(repo_root or REPO_ROOT)
    knowledge_dir = root / "knowledge"

    result = {
        "stale_products": [],
        "fresh_products": [],
        "missing_products": [],
        "warnings": [],
        "source_files_read": [],
        "knowledge_dir_exists": False,
        "change_sweep_reports": [],
    }

    if not knowledge_dir.exists():
        result["warnings"].append(f"knowledge/ directory not found at {knowledge_dir}")
        return result

    result["knowledge_dir_exists"] = True

    # Walk family/platform structure
    for family_dir in sorted(knowledge_dir.iterdir()):
        if not family_dir.is_dir():
            continue
        family = family_dir.name
        # Skip non-family entries (e.g. _index.json, *.json files)
        if family.startswith("_") or "." in family:
            continue

        for platform_dir in sorted(family_dir.iterdir()):
            if not platform_dir.is_dir():
                continue
            platform = platform_dir.name

            model_path = platform_dir / "merged" / "model.yaml"
            result["source_files_read"].append(str(model_path.relative_to(root)))

            if not model_path.exists():
                result["missing_products"].append({
                    "family": family,
                    "platform": platform,
                    "reason": "merged/model.yaml not found",
                    "path": str(model_path.relative_to(root)),
                })
                continue

            try:
                text = model_path.read_text(encoding="utf-8")
                # Parse key fields from YAML without requiring pyyaml dependency
                stale_match = re.search(r"^stale_since:\s*(.+)$", text, re.MULTILINE)
                version_match = re.search(r"^version:\s*(.+)$", text, re.MULTILINE)
                sha_match = re.search(r"^repo_sha:\s*(.+)$", text, re.MULTILINE)
                source_match = re.search(r"^source:\s*(.+)$", text, re.MULTILINE)

                stale_raw = stale_match.group(1).strip() if stale_match else "unknown"
                is_stale = stale_raw not in ("null", "~", "", "''")

                entry = {
                    "family": family,
                    "platform": platform,
                    "stale_since": None if stale_raw in ("null", "~", "", "''") else stale_raw,
                    "version": version_match.group(1).strip() if version_match else "unknown",
                    "repo_sha": sha_match.group(1).strip() if sha_match else "unknown",
                    "source": source_match.group(1).strip() if source_match else "unknown",
                    "model_path": str(model_path.relative_to(root)),
                }

                if is_stale:
                    result["stale_products"].append(entry)
                else:
                    result["fresh_products"].append(entry)

            except Exception as exc:
                result["warnings"].append(
                    f"Could not parse {model_path.relative_to(root)}: {exc}"
                )

    # Optionally read change-sweep reports
    cs_dir = root / "reports" / "change-sweep"
    if cs_dir.exists():
        for f in sorted(cs_dir.glob("*.json"))[:5]:
            result["change_sweep_reports"].append(f.name)

    return result


def main():
    parser = base_args("Discover stale products from knowledge/ model.yaml files")
    args = parser.parse_args()

    data = discover()

    summary = {
        "status": "DISCOVERY_COMPLETE",
        "stale_count": len(data["stale_products"]),
        "fresh_count": len(data["fresh_products"]),
        "missing_count": len(data["missing_products"]),
        "warning_count": len(data["warnings"]),
        "files_read": len(data["source_files_read"]),
        **data,
    }

    if args.output:
        safe_emit(summary, args.output)
        print(f"Discovery complete: {summary['stale_count']} stale, "
              f"{summary['fresh_count']} fresh, {summary['missing_count']} missing")
        print(f"Written to {args.output}")
    else:
        print(json.dumps(summary, indent=2, default=str))

    return 0


if __name__ == "__main__":
    sys.exit(main())
