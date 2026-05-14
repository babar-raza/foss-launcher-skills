#!/usr/bin/env python3
"""Detect format-support differences across platforms in one family."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def compare_family(family: str, *, knowledge_root: Path = Path("knowledge")) -> dict:
    family_root = knowledge_root / family
    if not family_root.exists():
        raise FileNotFoundError(f"Family knowledge not found: {family_root}")

    platform_formats: dict[str, dict[str, str]] = {}
    for platform_dir in sorted(family_root.iterdir()):
        if not platform_dir.is_dir():
            continue
        formats_path = platform_dir / "merged" / "formats.json"
        if not formats_path.exists():
            continue
        data = json.loads(formats_path.read_text(encoding="utf-8"))
        platform_formats[platform_dir.name] = {
            (item.get("format") or item.get("ext") or "").lower(): (item.get("direction") or item.get("support") or "").lower()
            for item in data
            if item.get("format") or item.get("ext")
        }

    issues = []
    all_formats = sorted({fmt for mapping in platform_formats.values() for fmt in mapping})
    for fmt in all_formats:
        present = {
            platform: mapping[fmt]
            for platform, mapping in platform_formats.items()
            if fmt in mapping
        }
        if len(set(present.values())) > 1:
            issues.append({"format": fmt, "platforms": present})

    return {
        "family": family,
        "platforms_scanned": sorted(platform_formats),
        "issue_count": len(issues),
        "issues": issues,
    }


def to_markdown(report: dict) -> str:
    lines = [
        f"# Cross-Platform Audit: {report['family']}",
        "",
        f"- Platforms scanned: {', '.join(report['platforms_scanned']) or '(none)'}",
        f"- Issues: {report['issue_count']}",
        "",
    ]
    if not report["issues"]:
        lines.append("No cross-platform format inconsistencies detected.")
        return "\n".join(lines)
    lines.extend(["| Format | Platform Support |", "|---|---|"])
    for issue in report["issues"]:
        detail = ", ".join(f"{platform}={support}" for platform, support in sorted(issue["platforms"].items()))
        lines.append(f"| `{issue['format']}` | {detail} |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("family")
    parser.add_argument("--knowledge-root", type=Path, default=Path("knowledge"))
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = compare_family(args.family, knowledge_root=args.knowledge_root)
    output = json.dumps(report, indent=2, ensure_ascii=False) if args.json else to_markdown(report)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    sys.stdout.write(output + "\n")
    return 1 if report["issue_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
