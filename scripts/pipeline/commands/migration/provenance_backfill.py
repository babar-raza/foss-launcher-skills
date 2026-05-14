#!/usr/bin/env python3
"""Backfill minimal provenance frontmatter for Markdown content fixtures."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


def split_frontmatter(text: str) -> tuple[dict[str, Any], str] | None:
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end == -1:
        return None
    data = yaml.safe_load(text[4:end]) or {}
    return (data if isinstance(data, dict) else {}, text[end + len("\n---\n") :])


def write_frontmatter(path: Path, data: dict[str, Any], body: str) -> None:
    path.write_text("---\n" + yaml.safe_dump(data, sort_keys=False).rstrip() + "\n---\n" + body, encoding="utf-8")


def is_locale(path: Path) -> bool:
    parts = set(path.parts)
    return bool(parts & {"ar", "de", "es", "fr", "it", "ja", "ko", "pt", "ru", "zh"}) or ".fr.md" in path.name


def backfill(content_root: Path, *, dry_run: bool = False, family: str | None = None, platform: str | None = None) -> dict[str, int]:
    stats = {"backfilled": 0, "skipped": 0, "errors": 0}
    for path in sorted(content_root.rglob("*.md")):
        rel_parts = set(path.relative_to(content_root).parts)
        if family and family not in rel_parts:
            continue
        if platform and platform not in rel_parts:
            continue
        parsed = split_frontmatter(path.read_text(encoding="utf-8"))
        if parsed is None:
            stats["errors"] += 1
            continue
        frontmatter, body = parsed
        if "provenance" in frontmatter:
            stats["skipped"] += 1
            continue
        frontmatter["provenance"] = {
            "translation_origin" if is_locale(path) else "content_origin": "unknown",
            "last_mechanism": "unknown",
            "auto_updatable": True,
            "backfilled_at": datetime.now(timezone.utc).date().isoformat(),
        }
        if not dry_run:
            write_frontmatter(path, frontmatter, body)
        stats["backfilled"] += 1
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--content-root", type=Path, default=Path("content"))
    parser.add_argument("--family")
    parser.add_argument("--platform")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    stats = backfill(args.content_root, dry_run=args.dry_run, family=args.family, platform=args.platform)
    print(json.dumps(stats, indent=2, sort_keys=True) if args.json else stats)
    return 1 if stats["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
