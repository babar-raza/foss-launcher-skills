#!/usr/bin/env python3
"""Validate generated blog slug conventions in a content root."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml


def parse_frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    data = yaml.safe_load(text[3:end]) or {}
    return data if isinstance(data, dict) else {}


def check_blog_file(path: Path, content_root: Path) -> list[str]:
    violations: list[str] = []
    rel = path.relative_to(content_root).as_posix()
    fm = parse_frontmatter(path)
    if path.name != "index.md" and re.match(r"index\.[a-z]{2}\.md$", path.name) is None:
        violations.append(f"FAIL {rel}: P-05 blog posts must use leaf bundle index.md files")
    for alias in fm.get("aliases") or []:
        if any(part.lower().startswith("test") for part in str(alias).split("/")):
            violations.append(f"FAIL {rel}: P-06 alias contains test path segment: {alias}")
    evidence = fm.get("evidence") or {}
    provenance = fm.get("provenance") or {}
    if provenance.get("content_origin") != "manual-remediation":
        if not evidence.get("claims"):
            violations.append(f"FAIL {rel}: P-03 evidence.claims must be non-empty")
        if not evidence.get("apis"):
            violations.append(f"FAIL {rel}: P-04 evidence.apis must be non-empty")
    return violations


def check(content_root: Path) -> list[str]:
    blog_root = content_root / "blog.aspose.org"
    if not blog_root.exists():
        return []
    return [violation for path in sorted(blog_root.rglob("*.md")) for violation in check_blog_file(path, content_root)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--content-root", type=Path, default=Path("content"))
    args = parser.parse_args(argv)
    violations = check(args.content_root)
    if violations:
        print("\n".join(violations))
        return 1
    print("Blog slug validation: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
