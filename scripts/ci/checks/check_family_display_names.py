#!/usr/bin/env python3
"""Validate family root display names in fixture or external content roots."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

SITES = ("reference.aspose.org", "docs.aspose.org", "kb.aspose.org")


def load_taxonomy(path: Path) -> dict[str, str]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    products = data.get("products", data)
    if not isinstance(products, dict):
        raise ValueError("taxonomy products must be a mapping")
    return {str(key): str(value) for key, value in products.items() if str(key) != "_all"}


def parse_frontmatter(path: Path) -> tuple[dict | None, str | None]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None, "missing frontmatter"
    end = text.find("\n---", 3)
    if end == -1:
        return None, "unclosed frontmatter"
    data = yaml.safe_load(text[3:end]) or {}
    if not isinstance(data, dict):
        return None, "frontmatter is not a mapping"
    return data, None


def check_file(path: Path, family: str, taxonomy: dict[str, str], content_root: Path) -> list[str]:
    violations: list[str] = []
    rel = path.relative_to(content_root)
    frontmatter, error = parse_frontmatter(path)
    if frontmatter is None:
        return [f"FAIL {rel}: V-00 {error}"]
    if "linkTitle" in frontmatter:
        violations.append(f"FAIL {rel}: V-01 linkTitle present")
    canonical = taxonomy.get(family)
    if canonical:
        expected = f"{canonical} FOSS"
        if frontmatter.get("title") != expected:
            violations.append(f"FAIL {rel}: V-02 title={frontmatter.get('title')!r} expected {expected!r}")
    else:
        violations.append(f"WARN {rel}: family {family!r} not in taxonomy")
    return violations


def check(content_root: Path, taxonomy_path: Path) -> list[str]:
    taxonomy = load_taxonomy(taxonomy_path)
    violations: list[str] = []
    for site in SITES:
        en_root = content_root / site / "en"
        if not en_root.exists():
            continue
        for family_dir in sorted(path for path in en_root.iterdir() if path.is_dir()):
            index = family_dir / "_index.md"
            if index.exists():
                violations.extend(check_file(index, family_dir.name, taxonomy, content_root))
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--content-root", type=Path, default=Path("content"))
    parser.add_argument("--taxonomy", type=Path, default=Path("scripts/pipeline/config/metrics_taxonomy.yaml"))
    args = parser.parse_args(argv)
    if not args.taxonomy.exists():
        print(f"ERROR taxonomy not found: {args.taxonomy}", file=sys.stderr)
        return 2
    violations = check(args.content_root, args.taxonomy)
    if violations:
        print("\n".join(violations))
    fails = [item for item in violations if item.startswith("FAIL")]
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
