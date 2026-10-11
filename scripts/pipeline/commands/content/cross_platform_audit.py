#!/usr/bin/env python3
"""Detect format-support differences across platforms in the same family."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _normalize_directions(tokens: set[str]) -> str:
    """Collapse a set of per-entry direction/support tokens into one comparable value.

    A format is commonly represented by multiple formats.json entries (a separate
    *Importer and *Exporter file, or separate Load/Save option classes) -- each
    contributes its own "import"/"export" token for the SAME format. Aggregate
    them instead of picking whichever entry happened to be read last: {"import",
    "export"} (in either order, with or without a literal "both" already present)
    normalizes to "both", matching the literal "both" value some extractors already
    write directly (e.g. a single class handling both directions).
    """
    tokens = {t for t in tokens if t}
    if not tokens:
        return ""
    if "both" in tokens or {"import", "export"} <= tokens:
        rest = tokens - {"import", "export", "both"}
        return "both" if not rest else "both+" + "+".join(sorted(rest))
    if len(tokens) == 1:
        return next(iter(tokens))
    return "+".join(sorted(tokens))


def compare_family(family: str, *, knowledge_root: Path = Path("knowledge")) -> dict:
    family_root = knowledge_root / family
    if not family_root.exists():
        raise FileNotFoundError(f"Family knowledge not found: {family_root}")

    platform_formats: dict[str, dict[str, str]] = {}
    for platform_dir in sorted(family_root.iterdir()):
        if not platform_dir.is_dir():
            continue
        fmt_path = platform_dir / "merged" / "formats.json"
        if not fmt_path.exists():
            continue
        data = json.loads(fmt_path.read_text(encoding="utf-8"))
        raw: dict[str, set[str]] = {}
        for item in data:
            fmt = (item.get("format") or item.get("ext") or "").lower()
            if not fmt:
                continue
            token = (item.get("direction") or item.get("support") or "").lower()
            raw.setdefault(fmt, set()).add(token)
        platform_formats[platform_dir.name] = {
            fmt: _normalize_directions(tokens) for fmt, tokens in raw.items()
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
            issues.append({
                "format": fmt,
                "platforms": present,
            })

    return {
        "family": family,
        "platforms_scanned": sorted(platform_formats),
        "issue_count": len(issues),
        "issues": issues,
    }


def _to_markdown(report: dict) -> str:
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

    lines.extend([
        "| Format | Platform Support |",
        "|---|---|",
    ])
    for issue in report["issues"]:
        detail = ", ".join(f"{p}={d}" for p, d in sorted(issue["platforms"].items()))
        lines.append(f"| `{issue['format']}` | {detail} |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cross_platform_audit",
        description="Compare knowledge-backed format support across platforms",
    )
    parser.add_argument("family", help="Product family")
    parser.add_argument("--knowledge-root", type=Path, default=Path("knowledge"))
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of markdown")
    parser.add_argument("--output", type=Path, help="Optional report output path")
    args = parser.parse_args(argv)

    report = compare_family(args.family, knowledge_root=args.knowledge_root)
    output = json.dumps(report, indent=2, ensure_ascii=False) if args.json else _to_markdown(report)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    sys.stdout.buffer.write(output.encode("utf-8"))
    sys.stdout.buffer.write(b"\n")
    return 1 if report["issue_count"] else 0


if __name__ == "__main__":
    sys.exit(main())
