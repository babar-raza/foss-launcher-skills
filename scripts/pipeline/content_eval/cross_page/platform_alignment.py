"""Cross-platform alignment checker — detects inconsistencies across platforms."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from ..models import Finding, Page

KNOWLEDGE_ROOT = Path("knowledge")


def check_platform_alignment(pages: list[Page]) -> list[Finding]:
    """Check that same features are described consistently across platforms.

    Compares format matrices across platforms within the same family.
    """
    findings: list[Finding] = []

    # Group pages by (family, page_slug)
    family_platforms: dict[str, set[str]] = defaultdict(set)
    for page in pages:
        if page.family and page.platform:
            family_platforms[page.family].add(page.platform)

    for family, platforms in family_platforms.items():
        if len(platforms) < 2:
            continue

        # Compare format support matrices across platforms
        platform_formats: dict[str, dict[str, str]] = {}
        for platform in platforms:
            fmt_path = KNOWLEDGE_ROOT / family / platform / "merged" / "formats.json"
            if fmt_path.exists():
                try:
                    fmts = json.loads(fmt_path.read_text(encoding="utf-8"))
                    platform_formats[platform] = {
                        (f.get("format") or f.get("ext") or "").lower():
                        (f.get("direction") or f.get("support") or "")
                        for f in fmts
                    }
                except (json.JSONDecodeError, KeyError):
                    pass

        if len(platform_formats) < 2:
            continue

        # Find formats that differ across platforms
        all_formats = set()
        for fmts in platform_formats.values():
            all_formats.update(fmts.keys())

        for fmt in sorted(all_formats):
            present_in = {p: fmts.get(fmt, "") for p, fmts in platform_formats.items() if fmt in fmts}
            if len(present_in) < 2:
                continue
            directions = set(present_in.values())
            if len(directions) > 1:
                # Different direction support across platforms — flag for review
                detail = ", ".join(f"{p}={d}" for p, d in sorted(present_in.items()))
                findings.append(Finding(
                    level="INFO",
                    category="XP",
                    filepath=f"knowledge/{family}/*/merged/formats.json",
                    line_no=0,
                    message=f"Format `{fmt.upper()}` has different support across platforms: {detail}",
                    suggestion="Verify each platform's content matches its actual format support",
                ))

    return findings
