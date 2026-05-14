#!/usr/bin/env python3
"""Standalone batch reference page scaffold from api_surface.json."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from scripts.content_repo_adapter import assert_write_allowed, resolve_content_root  # noqa: E402
from scripts.pipeline.extraction.tree_helpers import CLASS_KINDS_BY_PLATFORM, ENUM_KINDS  # noqa: E402


@dataclass(frozen=True)
class ReferenceCandidate:
    name: str
    kind: str
    output_path: Path
    exists: bool


def _slug(name: str) -> str:
    value = re.sub(r"(?<!^)(?=[A-Z])", "-", name).replace("_", "-")
    return re.sub(r"-+", "-", value).strip("-").lower()


def _api_surface_path(family: str, platform: str) -> Path:
    return REPO_ROOT / "knowledge" / family / platform / "merged" / "api_surface.json"


def _load_api_surface(family: str, platform: str) -> list[dict[str, Any]]:
    path = _api_surface_path(family, platform)
    if not path.is_file():
        raise FileNotFoundError(f"api_surface.json not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    for key in ("classes", "entries", "types"):
        if isinstance(data.get(key), list):
            return [item for item in data[key] if isinstance(item, dict)]
    return []


def _entry_kind(entry: dict[str, Any], platform: str) -> str:
    raw = str(entry.get("kind") or entry.get("type") or "")
    bases = {str(item) for item in entry.get("bases", [])} if isinstance(entry.get("bases"), list) else set()
    if raw in ENUM_KINDS or bases.intersection({"Enum", "enum.Enum"}):
        return "enum"
    if raw in CLASS_KINDS_BY_PLATFORM.get(platform, set()) or entry.get("name"):
        return "class"
    return raw or "class"


def collect_candidates(
    family: str,
    platform: str,
    *,
    kind: str = "all",
    content_root: Path,
    limit: int | None = None,
) -> list[ReferenceCandidate]:
    entries = _load_api_surface(family, platform)
    output_dir = content_root / "reference.aspose.org" / "en" / family / platform
    candidates: list[ReferenceCandidate] = []
    for entry in entries:
        name = str(entry.get("name") or entry.get("class") or "").strip()
        if not name or name.startswith("_"):
            continue
        entry_kind = _entry_kind(entry, platform)
        if kind != "all" and entry_kind != kind:
            continue
        path = output_dir / f"{_slug(name)}.md"
        candidates.append(ReferenceCandidate(name, entry_kind, path, path.exists()))
        if limit is not None and len(candidates) >= limit:
            break
    return candidates


def render_page(candidate: ReferenceCandidate, family: str, platform: str) -> str:
    title = candidate.name
    return (
        "---\n"
        "layout: reference-single\n"
        f"title: \"{title}\"\n"
        f"linkTitle: \"{title}\"\n"
        f"description: \"API reference for {title}.\"\n"
        "provenance:\n"
        "  content_origin: skill-generated\n"
        "  last_mechanism: batch-reference\n"
        "  auto_updatable: true\n"
        "evidence:\n"
        "  model_sha: \"\"\n"
        "  model_version: \"\"\n"
        "  claims: []\n"
        f"  apis: [\"{title}\"]\n"
        "---\n\n"
        f"# {title}\n\n"
        f"`{title}` is a {candidate.kind} in the {family}/{platform} API surface.\n\n"
        "This standalone scaffold preserves the batch-reference write contract. "
        "Run evidence attachment and content evaluation before publication.\n"
    )


def run(
    family: str,
    platform: str,
    *,
    kind: str = "all",
    limit: int | None = None,
    dry_run: bool = False,
    content_root: Path | None = None,
) -> dict[str, Any]:
    if content_root is None:
        content_root = resolve_content_root({"content_root": "content"} if (REPO_ROOT / "content").exists() else None)
    candidates = collect_candidates(family, platform, kind=kind, content_root=content_root, limit=limit)
    generated: list[str] = []
    skipped_existing: list[str] = []
    for candidate in candidates:
        if candidate.exists:
            skipped_existing.append(str(candidate.output_path))
            continue
        if dry_run:
            generated.append(str(candidate.output_path))
            continue
        assert_write_allowed(candidate.output_path, dry_run=False)
        candidate.output_path.parent.mkdir(parents=True, exist_ok=True)
        candidate.output_path.write_text(render_page(candidate, family, platform), encoding="utf-8")
        generated.append(str(candidate.output_path))
    return {
        "family": family,
        "platform": platform,
        "kind": kind,
        "dry_run": dry_run,
        "candidates": len(candidates),
        "generated": generated,
        "skipped_existing": skipped_existing,
        "summary": {
            "generated": len(generated),
            "skipped_existing": len(skipped_existing),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("family")
    parser.add_argument("platform")
    parser.add_argument("--kind", choices=("class", "enum", "all"), default="all")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--update", action="store_true", help="Accepted for compatibility; scaffold still skips existing pages.")
    parser.add_argument("--rebuild-all", action="store_true", help="Accepted for compatibility; scaffold does not overwrite existing pages.")
    parser.add_argument("--confirm-rebuild", action="store_true")
    parser.add_argument("--content-root")
    args = parser.parse_args(argv)
    del args.update, args.rebuild_all, args.confirm_rebuild

    try:
        content_root = Path(args.content_root).resolve() if args.content_root else None
        report = run(
            args.family,
            args.platform,
            kind=args.kind,
            limit=args.limit,
            dry_run=args.dry_run,
            content_root=content_root,
        )
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print("=== batch-reference summary ===")
    print(json.dumps(report["summary"], indent=2))
    for path in report["generated"]:
        prefix = "WOULD GENERATE" if args.dry_run else "GENERATED"
        print(f"{prefix}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
