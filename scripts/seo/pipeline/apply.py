#!/usr/bin/env python3
"""Apply reviewed SEO frontmatter patches with dry-run support."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

PROTECTED_FIELDS = {"evidence", "model_sha", "claims", "apis", "formats"}
ALLOWED_FIELDS = {"seoTitle", "description", "tags_to_add"}


def split_frontmatter(text: str) -> tuple[dict[str, Any], str] | None:
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end == -1:
        return None
    data = yaml.safe_load(text[4:end]) or {}
    if not isinstance(data, dict):
        data = {}
    return data, text[end + len("\n---\n") :]


def render_frontmatter(data: dict[str, Any], body: str) -> str:
    return "---\n" + yaml.safe_dump(data, sort_keys=False, allow_unicode=True).rstrip() + "\n---\n" + body


def validate_patch(patch: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not patch.get("safety_checks_passed"):
        errors.append("safety_checks_passed is not true")
    fields = patch.get("fields_to_update") or {}
    unknown = set(fields) - ALLOWED_FIELDS
    if unknown:
        errors.append(f"unknown fields: {sorted(unknown)}")
    protected = set(fields) & PROTECTED_FIELDS
    if protected:
        errors.append(f"protected fields: {sorted(protected)}")
    description = fields.get("description")
    if description is not None and not (130 <= len(str(description)) <= 160):
        errors.append("description must be 130-160 characters")
    if not patch.get("page_path"):
        errors.append("missing page_path")
    return errors


def apply_patch(repo_root: Path, patch: dict[str, Any], *, dry_run: bool = True) -> dict[str, Any]:
    errors = validate_patch(patch)
    page_path = Path(str(patch.get("page_path", "")))
    if page_path.is_absolute():
        target = page_path
    else:
        target = repo_root / page_path
    if not target.exists():
        errors.append(f"page not found: {target}")
    if errors:
        return {"page_path": str(page_path), "status": "error", "errors": errors}

    parsed = split_frontmatter(target.read_text(encoding="utf-8"))
    if parsed is None:
        return {"page_path": str(page_path), "status": "error", "errors": ["missing frontmatter"]}
    frontmatter, body = parsed
    before = dict(frontmatter)
    fields = patch.get("fields_to_update") or {}
    if fields.get("seoTitle") is not None:
        frontmatter["seoTitle"] = fields["seoTitle"]
    if fields.get("description") is not None:
        frontmatter["description"] = fields["description"]
    tags_to_add = fields.get("tags_to_add") or []
    if tags_to_add:
        existing = list(frontmatter.get("tags") or [])
        for tag in tags_to_add:
            if tag not in existing:
                existing.append(tag)
        frontmatter["tags"] = existing
    changed = before != frontmatter
    if changed and not dry_run:
        target.write_text(render_frontmatter(frontmatter, body), encoding="utf-8")
    return {"page_path": str(page_path), "status": "would_update" if dry_run and changed else "updated" if changed else "unchanged", "changed": changed}


def load_manifest(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    patches = data.get("patches", [])
    if not isinstance(patches, list):
        raise ValueError("patches must be a list")
    return [item for item in patches if isinstance(item, dict)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("patches/seo/patch_manifest.json"))
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true", help="Actually write approved SEO frontmatter updates")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if not args.manifest.exists():
        print(f"error: manifest not found: {args.manifest}", file=sys.stderr)
        return 1
    dry_run = not args.apply or args.dry_run
    results = [apply_patch(args.repo_root, patch, dry_run=dry_run) for patch in load_manifest(args.manifest)]
    payload = {
        "dry_run": dry_run,
        "total": len(results),
        "errors": sum(1 for item in results if item["status"] == "error"),
        "changed": sum(1 for item in results if item.get("changed")),
        "results": results,
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"SEO apply {'dry-run' if dry_run else 'apply'}: {payload['changed']} changed, {payload['errors']} errors")
    return 1 if payload["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
