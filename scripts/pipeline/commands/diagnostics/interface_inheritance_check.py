# Adapted from aspose.org
"""Interface inheritance precheck — SH-13 implementation.

Detects when api_surface.json has interfaces/classes with empty method lists
where clone cache source suggests inheritance should provide methods.
Specifically targets the slides/java ISlide false-positive pattern.

This is a precheck that BLOCKS unsafe verdicts when interface inheritance
data is missing. It does NOT fix the api_surface — that requires /repo-scout.

Exit codes:
    0  No suspicious empty-method interfaces found
    1  One or more interfaces with empty methods found where inheritance expected
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from datetime import datetime, timezone

REPO_ROOT = Path(os.environ.get("FOSS_REPO_ROOT", Path(__file__).resolve().parents[4]))
KNOWLEDGE_ROOT = REPO_ROOT / "knowledge"

# Clone cache location — override via FOSS_CLONE_CACHE env var
CLONE_CACHE = Path(os.environ.get("FOSS_CLONE_CACHE", REPO_ROOT / "runs" / ".clone_cache"))

# Interfaces commonly expected to have inherited methods
INTERFACE_PREFIXES = ("ISlide", "IShape", "IPresentation", "IBaseSlide", "ITextFrame")


def load_api_surface(family: str, platform: str) -> dict:
    """Load api_surface.json for a product."""
    for sub in ["merged", "scout"]:
        api_path = KNOWLEDGE_ROOT / family / platform / sub / "api_surface.json"
        if api_path.exists():
            try:
                data = json.loads(api_path.read_text(encoding="utf-8"))
                return {"path": str(api_path), "data": data}
            except (json.JSONDecodeError, OSError):
                pass
    return {"path": None, "data": None}


def find_empty_interface_methods(family: str, platform: str) -> list[dict]:
    """Find interfaces with empty method lists in api_surface."""
    surface = load_api_surface(family, platform)
    if not surface["data"]:
        return []

    data = surface["data"]
    findings = []

    items = data if isinstance(data, list) else list(data.values()) if isinstance(data, dict) else []

    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("name", item.get("class", ""))
        methods = item.get("methods", [])
        is_interface = (
            name.startswith("I") and name[1:2].isupper()
            or item.get("kind", "") in ("interface", "abstract")
        )
        extends = item.get("extends", item.get("parent", item.get("implements", [])))

        if is_interface and len(methods) == 0 and extends:
            findings.append({
                "class": name,
                "methods_count": 0,
                "extends": extends if isinstance(extends, list) else [extends],
                "api_surface_path": surface["path"],
                "warning": (
                    f"Interface '{name}' has 0 methods but extends {extends}. "
                    f"Inherited methods may not be captured — /repo-scout may need "
                    f"interface inheritance traversal."
                ),
            })

    return findings


def check_clone_cache_for_inheritance(family: str, platform: str) -> list[str]:
    """Check clone cache for interfaces that extend parents with methods."""
    product_dir_name = f"aspose_{family}_{platform}"
    clone_dir = CLONE_CACHE / product_dir_name

    if not clone_dir.exists():
        return []

    inheritance_evidence = []
    for java_file in clone_dir.rglob("*.java"):
        try:
            content = java_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        m = re.search(r"interface\s+(\w+)\s+extends\s+([\w, ]+)\s*\{", content)
        if m:
            iface_name = m.group(1)
            parent_names = [p.strip() for p in m.group(2).split(",")]
            inheritance_evidence.append(
                f"{java_file.name}: {iface_name} extends {', '.join(parent_names)}"
            )

    return inheritance_evidence[:20]


def main():
    parser = argparse.ArgumentParser(description="Interface inheritance precheck")
    parser.add_argument("family", nargs="?", default="slides", help="Product family")
    parser.add_argument("platform", nargs="?", default="java", help="Product platform")
    parser.add_argument("--all-java", action="store_true", help="Check all Java products")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    if args.all_java:
        products = [("slides", "java"), ("cells", "java"), ("3d", "java"), ("email", "java")]
    else:
        products = [(args.family, args.platform)]

    all_results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "products": [],
        "total_empty_interface_methods": 0,
        "pass": True,
    }

    for family, platform in products:
        empty = find_empty_interface_methods(family, platform)
        clone_evidence = check_clone_cache_for_inheritance(family, platform)
        product_result = {
            "product": f"{family}/{platform}",
            "empty_interface_findings": empty,
            "clone_cache_inheritance_examples": clone_evidence,
            "pass": len(empty) == 0,
        }
        all_results["products"].append(product_result)
        all_results["total_empty_interface_methods"] += len(empty)

    if all_results["total_empty_interface_methods"] > 0:
        all_results["pass"] = False

    if args.json:
        print(json.dumps(all_results, indent=2))
    else:
        status = "PASS" if all_results["pass"] else "FAIL"
        print(f"\n# Interface Inheritance Precheck")
        print(f"Status: {status} — {all_results['total_empty_interface_methods']} empty-method interface(s) with parent\n")
        for pr in all_results["products"]:
            if pr["empty_interface_findings"]:
                print(f"  FAIL [{pr['product']}]:")
                for f in pr["empty_interface_findings"]:
                    print(f"    {f['class']}: {f['warning']}")
                if pr["clone_cache_inheritance_examples"]:
                    print(f"    Clone cache confirms inheritance:")
                    for ex in pr["clone_cache_inheritance_examples"][:3]:
                        print(f"      {ex}")
                print(f"    FIX: Run /repo-scout {pr['product'].replace('/', ' ')} then /truth-merge")
            else:
                print(f"  PASS [{pr['product']}]")

    sys.exit(0 if all_results["pass"] else 1)


if __name__ == "__main__":
    main()
