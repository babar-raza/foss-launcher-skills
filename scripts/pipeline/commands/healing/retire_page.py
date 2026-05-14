#!/usr/bin/env python3
"""Retire or un-retire Markdown pages using Hugo frontmatter flags."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[4]


def configure(*, repo_root: Path | str | None = None) -> None:
    global REPO_ROOT
    REPO_ROOT = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[4]


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str] | None:
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end == -1:
        return None
    yaml_body = text[4:end]
    body = text[end + len("\n---\n") :]
    data = yaml.safe_load(yaml_body) or {}
    if not isinstance(data, dict):
        data = {}
    return data, body


def _write_frontmatter(path: Path, data: dict[str, Any], body: str) -> None:
    new_text = "---\n" + yaml.safe_dump(data, sort_keys=False, allow_unicode=True).rstrip() + "\n---\n" + body
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(new_text, encoding="utf-8")
    tmp.replace(path)


def retire_page(path: Path, *, dry_run: bool = False) -> str:
    if not path.is_file():
        return "error"
    parsed = _split_frontmatter(path.read_text(encoding="utf-8"))
    if parsed is None:
        return "error"
    data, body = parsed
    if data.get("draft") is True:
        return "skipped"
    if dry_run:
        return "dry_run"
    data["draft"] = True
    data["retired_at"] = datetime.now(timezone.utc).date().isoformat()
    _write_frontmatter(path, data, body)
    return "retired"


def un_retire_page(path: Path, *, dry_run: bool = False) -> str:
    if not path.is_file():
        return "error"
    parsed = _split_frontmatter(path.read_text(encoding="utf-8"))
    if parsed is None:
        return "error"
    data, body = parsed
    if data.get("draft") is not True:
        return "skipped"
    if dry_run:
        return "dry_run"
    data.pop("draft", None)
    data.pop("retired_at", None)
    _write_frontmatter(path, data, body)
    return "un_retired"


def _load_plan(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError("plan root must be a mapping")
    return raw.get("plan", raw)


def retire_from_plan(plan_path: Path, *, dry_run: bool = False) -> dict[str, Any]:
    plan = _load_plan(plan_path)
    pages = ((plan.get("delta") or {}).get("pages_to_remove") or [])
    counts = {"retired": 0, "skipped": 0, "errors": 0, "dry_run_count": 0, "dry_run": dry_run}
    for item in pages:
        page = Path(str(item))
        if not page.is_absolute():
            page = REPO_ROOT / page
        result = retire_page(page, dry_run=dry_run)
        if result == "retired":
            counts["retired"] += 1
        elif result == "skipped":
            counts["skipped"] += 1
        elif result == "dry_run":
            counts["dry_run_count"] += 1
        else:
            counts["errors"] += 1
    return counts


def un_retire_from_delta(family: str, platform: str, *, dry_run: bool = False) -> dict[str, Any]:
    delta_path = REPO_ROOT / "knowledge" / family / platform / "merged" / "knowledge_delta.json"
    ref_root = REPO_ROOT / "content" / "reference.aspose.org" / "en" / family / platform
    counts = {"un_retired": 0, "skipped": 0, "errors": 0, "dry_run_count": 0, "dry_run": dry_run}
    if not delta_path.exists() or not ref_root.exists():
        return counts
    delta = json.loads(delta_path.read_text(encoding="utf-8"))
    resurrected = {str(item).lower() for item in delta.get("resurrected_apis", [])}
    for path in ref_root.glob("*.md"):
        if path.stem.lower() not in resurrected:
            continue
        result = un_retire_page(path, dry_run=dry_run)
        if result == "un_retired":
            counts["un_retired"] += 1
        elif result == "skipped":
            counts["skipped"] += 1
        elif result == "dry_run":
            counts["dry_run_count"] += 1
        else:
            counts["errors"] += 1
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("page", nargs="?")
    group.add_argument("--from-plan")
    group.add_argument("--from-delta", nargs=2, metavar=("FAMILY", "PLATFORM"))
    parser.add_argument("--un-retire", action="store_true")
    parser.add_argument("--repo-root")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.repo_root:
        configure(repo_root=args.repo_root)

    if args.from_plan:
        result: Any = retire_from_plan(Path(args.from_plan), dry_run=args.dry_run)
    elif args.un_retire and args.from_delta:
        result = un_retire_from_delta(args.from_delta[0], args.from_delta[1], dry_run=args.dry_run)
    else:
        page = Path(args.page or "")
        if not page.is_absolute():
            page = Path.cwd() / page
        result = un_retire_page(page, dry_run=args.dry_run) if args.un_retire else retire_page(page, dry_run=args.dry_run)
    print(json.dumps(result, indent=2) if args.json else result)
    if isinstance(result, dict):
        return 1 if result.get("errors") else 0
    return 0 if result in {"retired", "un_retired", "skipped", "dry_run"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
