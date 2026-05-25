"""V-04: Platform linkTitle presence and canonical label validator.

Checks every platform-level _index.md across all subdomains to ensure:
  1. linkTitle (or linktitle) frontmatter field is present.
  2. The linkTitle value matches the canonical platform display name
     from data/platforms.json.
  3. Platform badge labels do not contain forbidden patterns like
     "Knowledge Base", "Documentation", "Reference", or "FOSS for".

Usage:
    .venv/Scripts/python scripts/ci/validators/v04_platform_linktitle.py

Exit codes:
    0  All platform pages pass.
    1  One or more violations found.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

SUBDOMAINS = {
    "kb": REPO_ROOT / "content" / "kb.aspose.org" / "en",
    "docs": REPO_ROOT / "content" / "docs.aspose.org" / "en",
    "reference": REPO_ROOT / "content" / "reference.aspose.org" / "en",
    "blog": REPO_ROOT / "content" / "blog.aspose.org",
}

FORBIDDEN_IN_BADGE = ["Knowledge Base", "Documentation", "API Reference", "FOSS for"]


def load_platforms():
    with open(REPO_ROOT / "data" / "platforms.json", encoding="utf-8") as f:
        return json.load(f)


def extract_field(fpath, field_name):
    text = fpath.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    for line in parts[1].splitlines():
        stripped = line.strip()
        if stripped.lower().startswith(field_name.lower() + ":"):
            return stripped.split(":", 1)[1].strip().strip('"').strip("'")
    return None


def main():
    platforms = load_platforms()
    violations = []

    for subdomain, base in SUBDOMAINS.items():
        if not base.exists():
            continue
        for family_dir in sorted(base.iterdir()):
            if not family_dir.is_dir() or family_dir.name.startswith("."):
                continue
            for platform_dir in sorted(family_dir.iterdir()):
                if not platform_dir.is_dir():
                    continue
                idx = platform_dir / "_index.md"
                if not idx.exists():
                    continue

                slug = platform_dir.name
                expected = platforms.get(slug)
                lt = extract_field(idx, "linktitle")
                title = extract_field(idx, "title") or ""

                rel = idx.relative_to(REPO_ROOT)

                if expected is None:
                    violations.append(
                        f"UNKNOWN_PLATFORM_SLUG: {rel} -- slug '{slug}' not in data/platforms.json"
                    )

                if lt is None:
                    violations.append(f"MISSING_LINKTITLE: {rel}")

                if expected and lt and lt != expected:
                    violations.append(
                        f"WRONG_LINKTITLE: {rel} -- got '{lt}', expected '{expected}'"
                    )

                rendered = lt or title
                for pattern in FORBIDDEN_IN_BADGE:
                    if pattern in rendered:
                        violations.append(
                            f"FORBIDDEN_BADGE_TEXT: {rel} -- '{rendered}' contains '{pattern}'"
                        )

    if violations:
        print(f"V-04 FAIL: {len(violations)} violation(s)")
        for v in violations:
            print(f"  {v}")
        return 1
    else:
        print("V-04 PASS: All platform _index.md files have valid linkTitle")
        return 0


if __name__ == "__main__":
    sys.exit(main())
