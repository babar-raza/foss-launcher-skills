#!/usr/bin/env python3
"""Grounding ratio gate for backtick API identifiers."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
_REPO_ROOT = _DEFAULT_REPO_ROOT
KNOWLEDGE_ROOT = _REPO_ROOT / "knowledge"

PASS_THRESHOLD = 0.80
WARN_THRESHOLD = 0.60
_IDENTIFIER_RE = re.compile(r"`(\w+(?:\.\w+)*)`")
_FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*\n?", re.DOTALL)


def configure(*, repo_root: Path | str | None = None, knowledge_root: Path | str | None = None) -> None:
    global _REPO_ROOT, KNOWLEDGE_ROOT
    _REPO_ROOT = Path(repo_root).resolve() if repo_root is not None else _DEFAULT_REPO_ROOT
    KNOWLEDGE_ROOT = Path(knowledge_root).resolve() if knowledge_root is not None else _REPO_ROOT / "knowledge"


def _build_known_identifiers(api_surface: list[dict]) -> set[str]:
    known: set[str] = set()
    for cls in api_surface:
        name = cls.get("name", "")
        if name:
            known.add(str(name).lower())
        for method in cls.get("methods", []) + cls.get("method_details", []):
            value = method.get("name", "") if isinstance(method, dict) else method
            if value:
                known.add(str(value).lower())
        for prop in cls.get("properties", []) + cls.get("property_details", []):
            value = prop.get("name", "") if isinstance(prop, dict) else prop
            if value:
                known.add(str(value).lower())
        for member in cls.get("enum_members", []):
            value = member.get("name", "") if isinstance(member, dict) else member
            if value:
                known.add(str(value).lower())
    return known


def compute_grounding_ratio(content_file: Path, api_surface_path: Path) -> tuple[float, int, int, list[str]]:
    if not api_surface_path.exists():
        raise FileNotFoundError(f"api_surface.json not found: {api_surface_path}")
    api_data = json.loads(api_surface_path.read_text(encoding="utf-8"))
    if isinstance(api_data, dict):
        api_surface = api_data.get("classes") or api_data.get("entries") or []
    else:
        api_surface = api_data
    known = _build_known_identifiers(api_surface)
    text = content_file.read_text(encoding="utf-8")
    body = _FRONTMATTER_RE.sub("", text, count=1)
    identifiers = _IDENTIFIER_RE.findall(body)
    if not identifiers:
        return 1.0, 0, 0, []
    matched = 0
    ungrounded: list[str] = []
    for identifier in identifiers:
        parts = identifier.lower().split(".")
        if any(part in known for part in parts):
            matched += 1
        else:
            ungrounded.append(identifier)
    total = len(identifiers)
    return matched / total, matched, total, ungrounded


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("family")
    parser.add_argument("platform")
    parser.add_argument("content_file")
    args = parser.parse_args(argv)
    content_file = Path(args.content_file)
    if not content_file.exists():
        print(f"GROUND_CHECK: ERROR -- file not found: {content_file}", file=sys.stderr)
        return 2
    api_surface_path = KNOWLEDGE_ROOT / args.family / args.platform / "merged" / "api_surface.json"
    try:
        ratio, matched, total, ungrounded = compute_grounding_ratio(content_file, api_surface_path)
    except FileNotFoundError as exc:
        print(f"GROUND_CHECK: FAIL -- {exc}", file=sys.stderr)
        return 2
    if total == 0:
        print("GROUND_CHECK: PASS (no backtick identifiers found -- no grounding required)")
        return 0
    pct = f"{ratio:.0%}"
    if ratio >= PASS_THRESHOLD:
        print(f"GROUND_CHECK: PASS ({pct}) -- {matched}/{total} identifiers grounded")
        return 0
    if ratio >= WARN_THRESHOLD:
        print(f"GROUND_CHECK: WARN ({pct}) -- {matched}/{total} identifiers grounded")
        if ungrounded:
            print("  Ungrounded: " + ", ".join(f"`{item}`" for item in ungrounded[:10]))
        return 1
    print(f"GROUND_CHECK: FAIL ({pct}) -- {matched}/{total} identifiers grounded, {len(ungrounded)} ungrounded")
    if ungrounded:
        print("  Ungrounded: " + ", ".join(f"`{item}`" for item in ungrounded[:20]))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
