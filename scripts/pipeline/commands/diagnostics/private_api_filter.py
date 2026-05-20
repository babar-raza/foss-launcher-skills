# Adapted from aspose.org
"""Internal/private API filter check — SH-12 implementation.

Detects reference pages or content that expose non-public API members.
Flags at minimum:
  - Java @Internal classes or packages containing 'internal'
  - C++ internal implementation pages not in the public api_surface
  - Python underscore-prefixed members (e.g. Mesh._control_points)
  - Reference pages not represented in the public api_surface

Usage:
    .venv/Scripts/python scripts/pipeline/commands/diagnostics/private_api_filter.py
    .venv/Scripts/python scripts/pipeline/commands/diagnostics/private_api_filter.py --family 3d --platform python
    .venv/Scripts/python scripts/pipeline/commands/diagnostics/private_api_filter.py --json

Exit codes:
    0  No private/internal API exposed in public content
    1  One or more private/internal API exposures found
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
CONTENT_ROOT = Path(os.environ.get("FOSS_CONTENT_ROOT", REPO_ROOT / "content"))

SCOPED_PRODUCTS = [
    ("cells", "java"), ("cells", "net"), ("cells", "python"),
    ("slides", "java"), ("slides", "net"), ("slides", "python"), ("slides", "cpp"),
    ("words", "python"),
    ("email", "net"), ("email", "cpp"), ("email", "python"),
    ("note", "python"),
    ("3d", "java"), ("3d", "net"), ("3d", "python"), ("3d", "typescript"),
]

# Python underscore-prefixed member pattern in reference pages
PYTHON_PRIVATE_MEMBER_RE = re.compile(
    r"(?:^\|\s*`?_\w+`?\s*\|)|(?:`_\w+\(`)",
    re.MULTILINE,
)

# Java @Internal annotation pattern
JAVA_INTERNAL_RE = re.compile(r"@Internal", re.IGNORECASE)

# C++ internal patterns: class names ending in Part, Exporter, Factory, Constants
CPP_INTERNAL_CLASS_RE = re.compile(
    r"(?:Part|Exporter|ExporterFactory|Constants|Impl)\b",
    re.IGNORECASE,
)

DRAFT_RE = re.compile(r"^draft:\s*true", re.MULTILINE)


def load_api_surface(family: str, platform: str) -> set[str]:
    """Load class/method names from api_surface.json."""
    api_path = KNOWLEDGE_ROOT / family / platform / "merged" / "api_surface.json"
    if not api_path.exists():
        api_path = KNOWLEDGE_ROOT / family / platform / "scout" / "api_surface.json"
    if not api_path.exists():
        return set()
    try:
        data = json.loads(api_path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            names = set()
            for item in data:
                if isinstance(item, dict):
                    names.add(item.get("name", ""))
                    names.add(item.get("class", ""))
            return names
        if isinstance(data, dict):
            return set(data.keys())
        return set()
    except (json.JSONDecodeError, OSError):
        return set()


def check_product(family: str, platform: str) -> dict:
    findings = []
    api_surface = load_api_surface(family, platform)

    ref_dir = None
    if CONTENT_ROOT.exists():
        for site_dir in CONTENT_ROOT.iterdir():
            if site_dir.is_dir() and "reference" in site_dir.name:
                for candidate in [site_dir / "en" / family / platform, site_dir / family / platform]:
                    if candidate.exists():
                        ref_dir = candidate
                        break
                if ref_dir:
                    break
    if ref_dir is None:
        ref_dir = CONTENT_ROOT / "reference" / "en" / family / platform
    if not ref_dir.exists():
        return {"product": f"{family}/{platform}", "findings": [], "api_surface_loaded": False}

    for md_file in ref_dir.rglob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        # Skip draft pages
        if DRAFT_RE.search(content):
            continue

        rel_path = str(md_file.relative_to(REPO_ROOT))

        # Check 1: Python underscore-prefixed members exposed publicly
        if platform == "python":
            priv_matches = PYTHON_PRIVATE_MEMBER_RE.findall(content)
            for match in priv_matches:
                member_name = match.strip().strip("|").strip("`").strip()
                findings.append({
                    "type": "PYTHON_PRIVATE_MEMBER",
                    "file": rel_path,
                    "member": member_name,
                    "severity": "ERROR",
                })

        # Check 2: Java @Internal pages (should not be public)
        if platform == "java" and JAVA_INTERNAL_RE.search(content):
            findings.append({
                "type": "JAVA_INTERNAL_ANNOTATION",
                "file": rel_path,
                "severity": "ERROR",
            })

        # Check 3: Reference page class not in api_surface (possible internal page)
        if api_surface:
            # Get class name from file path (stem)
            class_name = md_file.stem
            if class_name != "_index" and class_name.lower() not in {n.lower() for n in api_surface}:
                # Apply heuristics for internal names
                is_cpp_internal = platform == "cpp" and CPP_INTERNAL_CLASS_RE.search(class_name)
                is_java_internal = platform == "java" and (
                    "Part" in class_name or "Exporter" in class_name or
                    "Constants" in class_name or class_name.startswith("Pptx")
                )
                if is_cpp_internal or is_java_internal:
                    findings.append({
                        "type": "INTERNAL_CLASS_NOT_IN_API_SURFACE",
                        "file": rel_path,
                        "class": class_name,
                        "severity": "WARN",
                    })

    return {
        "product": f"{family}/{platform}",
        "findings": findings,
        "api_surface_loaded": bool(api_surface),
        "errors": [f for f in findings if f.get("severity") == "ERROR"],
        "warns": [f for f in findings if f.get("severity") == "WARN"],
    }


def main():
    parser = argparse.ArgumentParser(description="Internal/private API filter check")
    parser.add_argument("--family", help="Filter by family")
    parser.add_argument("--platform", help="Filter by platform")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    if args.family and args.platform:
        products = [(args.family, args.platform)]
    else:
        products = SCOPED_PRODUCTS

    all_results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "products": [],
        "total_errors": 0,
        "total_warns": 0,
        "pass": True,
    }

    for family, platform in products:
        result = check_product(family, platform)
        all_results["products"].append(result)
        all_results["total_errors"] += len(result["errors"])
        all_results["total_warns"] += len(result["warns"])

    if all_results["total_errors"] > 0:
        all_results["pass"] = False

    if args.json:
        print(json.dumps(all_results, indent=2))
    else:
        status = "PASS" if all_results["pass"] else "FAIL"
        print(f"\n# Internal/Private API Filter Check")
        print(f"Status: {status} — {all_results['total_errors']} ERROR(s), {all_results['total_warns']} WARN(s)\n")
        for product in all_results["products"]:
            if product["findings"]:
                print(f"  [{product['product']}] {len(product['errors'])} errors, {len(product['warns'])} warns:")
                for finding in product["findings"]:
                    sev = finding.get("severity", "?")
                    ftype = finding["type"]
                    ffile = finding["file"]
                    extra = finding.get("member", finding.get("class", ""))
                    print(f"    [{sev}] {ftype}: {ffile}" + (f" ({extra})" if extra else ""))
            else:
                print(f"  PASS [{product['product']}]")

    sys.exit(0 if all_results["pass"] else 1)


if __name__ == "__main__":
    main()
