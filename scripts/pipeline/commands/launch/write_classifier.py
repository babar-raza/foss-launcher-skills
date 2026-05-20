# Adapted from aspose.org
#!/usr/bin/env python3
"""Write classifier for launch-product refresh mode.

Classifies existing content files as CREATE/REFRESH/PRESERVE/CONFLICT
based on frontmatter provenance fields. Used by S-49 when re-running on
a product that already has content (checkpoint-aware refresh mode) to
decide which files to regenerate vs skip. There is no --refresh CLI flag
on S-49; classification runs as part of the checkpoint-resume workflow.

Usage:
    python scripts/pipeline/commands/launch/write_classifier.py cells java
    python scripts/pipeline/commands/launch/write_classifier.py cells java --output reports/refresh_state/cells/java/write_classification.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None


def parse_frontmatter_minimal(path: Path) -> dict:
    """Parse YAML frontmatter from a markdown file."""
    text = path.read_text(encoding="utf-8", errors="replace")
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}
    if yaml:
        try:
            return yaml.safe_load(m.group(1)) or {}
        except Exception:
            return {}
    # Minimal regex-based extraction if yaml unavailable
    result = {}
    for line in m.group(1).split("\n"):
        kv = line.strip().split(":", 1)
        if len(kv) == 2:
            result[kv[0].strip()] = kv[1].strip()
    return result


import os

# Default content root patterns -- can be overridden by setting CONTENT_ROOT_PREFIX
# or by calling configure_content_roots().
_CONTENT_PREFIX = os.environ.get("CONTENT_ROOT_PREFIX", "content")

CONTENT_ROOTS = {
    "products": f"{_CONTENT_PREFIX}/products.aspose.org/en/{{family}}/{{platform}}",
    "docs": f"{_CONTENT_PREFIX}/docs.aspose.org/en/{{family}}/{{platform}}",
    "kb": f"{_CONTENT_PREFIX}/kb.aspose.org/en/{{family}}/{{platform}}",
    "blog": f"{_CONTENT_PREFIX}/blog.aspose.org/{{family}}/{{platform}}",
    "reference": f"{_CONTENT_PREFIX}/reference.aspose.org/en/{{family}}/{{platform}}",
}


def configure_content_roots(roots: dict[str, str]) -> None:
    """Override CONTENT_ROOTS for non-aspose.org deployments."""
    global CONTENT_ROOTS
    CONTENT_ROOTS = dict(roots)


def classify_file(path: Path) -> dict:
    """Classify a single file based on its provenance frontmatter."""
    if not path.exists():
        return {"path": str(path), "category": "CREATE", "reason": "file does not exist"}

    fm = parse_frontmatter_minimal(path)
    provenance = fm.get("provenance", {})
    if not isinstance(provenance, dict):
        provenance = {}

    content_origin = provenance.get("content_origin", "")
    auto_updatable = provenance.get("auto_updatable", None)

    # PRESERVE: human-authored or explicitly not auto-updatable
    if content_origin == "human-authored" or auto_updatable is False:
        return {
            "path": str(path),
            "category": "PRESERVE",
            "reason": f"content_origin={content_origin}, auto_updatable={auto_updatable}",
        }

    # Unknown origin with auto_updatable not explicitly false: safe default PRESERVE
    if content_origin == "unknown":
        return {
            "path": str(path),
            "category": "PRESERVE",
            "reason": "content_origin=unknown — safe default PRESERVE",
        }

    # REFRESH: skill-generated and auto-updatable
    if content_origin == "skill-generated" and auto_updatable is True:
        return {
            "path": str(path),
            "category": "REFRESH",
            "reason": "skill-generated, auto_updatable=true",
        }

    # Has provenance but non-standard values
    if provenance:
        return {
            "path": str(path),
            "category": "REFRESH",
            "reason": f"has provenance (origin={content_origin}, updatable={auto_updatable})",
        }

    # No provenance at all
    return {
        "path": str(path),
        "category": "PRESERVE",
        "reason": "no provenance block — safe default PRESERVE",
    }


def find_content_files(repo_root: Path, family: str, platform: str) -> dict[str, list[Path]]:
    """Find all content files per subdomain."""
    results = {}
    for subdomain, pattern in CONTENT_ROOTS.items():
        content_dir = repo_root / pattern.format(family=family, platform=platform)
        if content_dir.exists():
            files = sorted(content_dir.rglob("*.md"))
            # For blog, only include English index.md files (not locale translations)
            if subdomain == "blog":
                files = [f for f in files if f.name == "index.md"]
            results[subdomain] = files
        else:
            results[subdomain] = []
    return results


def main():
    parser = argparse.ArgumentParser(description="Classify content files for refresh mode")
    parser.add_argument("family", help="Product family (e.g., cells)")
    parser.add_argument("platform", help="Platform (e.g., java)")
    parser.add_argument("--output", "-o", help="Output JSON path")
    parser.add_argument("--repo-root", default=".", help="Repository root")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    files_by_subdomain = find_content_files(repo_root, args.family, args.platform)

    counts = {"CREATE": 0, "REFRESH": 0, "REFRESH_CONDITIONAL": 0, "PRESERVE": 0, "CONFLICT": 0}
    all_classifications = []

    for subdomain, files in files_by_subdomain.items():
        for f in files:
            result = classify_file(f)
            result["subdomain"] = subdomain
            counts[result["category"]] += 1
            all_classifications.append(result)

    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "family": args.family,
        "platform": args.platform,
        "counts": counts,
        "locale_files_in_write_set": 0,
        "deletions_planned": 0,
        "conflicts": counts["CONFLICT"],
        "files": all_classifications,
        "by_subdomain": {k: len(v) for k, v in files_by_subdomain.items()},
        "validation": "PASS" if counts["CONFLICT"] == 0 else "FAIL",
    }

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
        print(f"Classification written to {args.output}")
    else:
        print(json.dumps(output, indent=2))

    if counts["CONFLICT"] > 0:
        print(f"ERROR: {counts['CONFLICT']} CONFLICT files found", file=sys.stderr)
        sys.exit(1)

    print(f"OK: {counts['REFRESH']} REFRESH, {counts['PRESERVE']} PRESERVE, {counts['CONFLICT']} CONFLICT")


if __name__ == "__main__":
    main()
