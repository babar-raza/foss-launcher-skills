#!/usr/bin/env python3
"""Read-only unit-level content truth-audit scaffold."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCOPES = {
    "products": ["products.aspose.org"],
    "docs": ["docs.aspose.org"],
    "blog": ["blog.aspose.org"],
    "kb": ["kb.aspose.org"],
    "reference": ["reference.aspose.org"],
    "all": ["products.aspose.org", "docs.aspose.org", "blog.aspose.org", "kb.aspose.org", "reference.aspose.org"],
}
API_REF_RE = re.compile(r"`(\w+(?:\.\w+)*)(?:\([^)]*\))?`")
CLAIM_VERB_RE = re.compile(r"\b(supports?|provides?|returns?|accepts?|converts?|creates?|loads?|saves?|exports?|imports?)\b", re.I)


def unit_id(path: str, index: int) -> str:
    return hashlib.sha256(f"{path}:{index}".encode()).hexdigest()[:12]


def decompose_markdown(text: str, rel_path: str) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    in_code = False
    code_lines: list[str] = []
    code_start = 0
    for line_no, line in enumerate(text.splitlines(), start=1):
        if line.startswith("```"):
            if in_code:
                content = "\n".join(code_lines)
                units.append({"id": unit_id(rel_path, len(units)), "type": "code_block", "line": code_start, "text": content})
                code_lines = []
                in_code = False
            else:
                in_code = True
                code_start = line_no
            continue
        if in_code:
            code_lines.append(line)
            continue
        stripped = line.strip()
        if not stripped or stripped == "---":
            continue
        if stripped.startswith("#"):
            typ = "heading"
        elif stripped.startswith(("- ", "* ")):
            typ = "list_item"
        elif "|" in stripped and stripped.count("|") >= 2:
            typ = "table_row"
        else:
            typ = "paragraph"
        units.append({"id": unit_id(rel_path, len(units)), "type": typ, "line": line_no, "text": stripped})
    return units


def classify_unit(unit: dict[str, Any]) -> str:
    if unit["type"] == "code_block":
        return "code"
    if unit["type"] == "heading":
        return "structural"
    if API_REF_RE.search(unit["text"]) or CLAIM_VERB_RE.search(unit["text"]):
        return "claim"
    return "structural"


def discover_files(content_root: Path, family: str, platform: str, scope: str) -> list[Path]:
    files: list[Path] = []
    for site in SCOPES[scope]:
        if site == "blog.aspose.org":
            files.extend((content_root / site / family / platform).rglob("*.md") if (content_root / site / family / platform).exists() else [])
        else:
            files.extend((content_root / site / "en" / family / platform).rglob("*.md") if (content_root / site / "en" / family / platform).exists() else [])
    return sorted(path for path in files if path.is_file())


def audit(content_root: Path, family: str, platform: str, *, scope: str = "all", max_units: int | None = None) -> dict[str, Any]:
    units: list[dict[str, Any]] = []
    for path in discover_files(content_root, family, platform, scope):
        rel = path.relative_to(content_root).as_posix()
        for unit in decompose_markdown(path.read_text(encoding="utf-8", errors="replace"), rel):
            unit["file"] = rel
            unit["claim_type"] = classify_unit(unit)
            unit["verdict"] = "UNVERIFIABLE" if unit["claim_type"] in {"claim", "code"} else "VERIFIED"
            units.append(unit)
            if max_units and len(units) >= max_units:
                break
        if max_units and len(units) >= max_units:
            break
    verdict_counts = Counter(unit["verdict"] for unit in units)
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "family": family,
        "platform": platform,
        "scope": scope,
        "content_root": str(content_root),
        "unit_count": len(units),
        "verdict_counts": dict(sorted(verdict_counts.items())),
        "units": units,
        "read_only": True,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [f"# Truth Audit Content: {report['family']}/{report['platform']}", "", f"- Units: `{report['unit_count']}`", f"- Read-only: `{report['read_only']}`", "", "## Verdict Counts", ""]
    for verdict, count in report["verdict_counts"].items():
        lines.append(f"- `{verdict}`: {count}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("family")
    parser.add_argument("platform")
    parser.add_argument("--scope", choices=sorted(SCOPES), default="all")
    parser.add_argument("--content-root", type=Path, default=Path("content"))
    parser.add_argument("--output-root", type=Path, default=Path("reports"))
    parser.add_argument("--max-units", type=int)
    parser.add_argument("--no-llm", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    del args.no_llm
    report = audit(args.content_root, args.family, args.platform, scope=args.scope, max_units=args.max_units)
    if args.dry_run:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    out_dir = args.output_root / "truth-audit"
    state_dir = out_dir / "state"
    out_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    json_path = out_dir / f"{args.family}-{args.platform}-{stamp}.json"
    md_path = out_dir / f"{args.family}-{args.platform}-{stamp}.md"
    state_path = state_dir / f"{args.family}-{args.platform}.json"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    state_path.write_text(json.dumps({"latest": str(json_path), "unit_count": report["unit_count"]}, indent=2), encoding="utf-8")
    print(json_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
