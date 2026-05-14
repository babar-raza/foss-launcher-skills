#!/usr/bin/env python3
"""Build or execute a rollback manifest for one generated product surface."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
PLANS_DIR = REPO_ROOT / "reports" / "plans"
ROLLBACK_DIR = REPO_ROOT / "reports" / "rollback"
PROTECTED_PREFIXES = ("scripts/", ".agents/", ".claude/", ".kilocode/", "reports/", "knowledge/", "configs/", "layouts/", "static/", "themes/")
LOCALE_CODES = ("ar", "bg", "ca", "de", "es", "fr", "it", "ja", "ko", "pt", "ru", "zh")


def configure(*, repo_root: Path | str | None = None) -> None:
    global REPO_ROOT, PLANS_DIR, ROLLBACK_DIR
    REPO_ROOT = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[4]
    PLANS_DIR = REPO_ROOT / "reports" / "plans"
    ROLLBACK_DIR = REPO_ROOT / "reports" / "rollback"


def _load_yaml_or_json(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
    else:
        try:
            import yaml  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("PyYAML is required for YAML site plans") from exc
        data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        raise ValueError("site plan must be a mapping")
    return data


def read_site_plan(family: str, platform: str) -> list[str]:
    base = PLANS_DIR / family / platform
    plan_path = base / "site_plan.yaml"
    if not plan_path.exists():
        plan_path = base / "site_plan.json"
    if not plan_path.exists():
        raise FileNotFoundError(f"site plan not found under {base}")
    raw = _load_yaml_or_json(plan_path)
    plan = raw.get("plan", raw)
    paths: list[str] = []
    for section_data in (plan.get("sections") or {}).values():
        if not isinstance(section_data, dict):
            continue
        for page in section_data.get("pages") or []:
            if isinstance(page, dict) and page.get("path"):
                paths.append(str(page["path"]).replace("\\", "/"))
    ref_root = REPO_ROOT / "content" / "reference.aspose.org" / "en" / family / platform
    if ref_root.exists():
        for md_file in ref_root.glob("*.md"):
            rel = md_file.relative_to(REPO_ROOT).as_posix()
            if rel not in paths:
                paths.append(rel)
    return paths


def expand_locale_paths(paths: list[str], family: str, platform: str) -> list[str]:
    prefix = f"content/docs.aspose.org/en/{family}/{platform}/"
    result: list[str] = []
    for path in paths:
        norm = path.replace("\\", "/")
        if norm.startswith(prefix):
            suffix = norm[len(prefix):]
            result.extend(f"content/docs.aspose.org/{locale}/{family}/{platform}/{suffix}" for locale in LOCALE_CODES)
    return result


def is_content_path(path: str) -> bool:
    return path.startswith("content/")


def is_protected(path: str) -> bool:
    return path.startswith(PROTECTED_PREFIXES)


def git_tracked(path: str) -> bool:
    return subprocess.run(["git", "ls-files", "--error-unmatch", path], cwd=REPO_ROOT, capture_output=True).returncode == 0


def classify_files(paths: list[str]) -> dict[str, list[str]]:
    result = {"revert": [], "delete": [], "skip": [], "protected": []}
    for raw in paths:
        path = raw.replace("\\", "/")
        if is_protected(path) or not is_content_path(path):
            result["protected" if is_protected(path) else "skip"].append(path)
            continue
        full = REPO_ROOT / path
        if not full.exists():
            result["skip"].append(path)
        elif git_tracked(path):
            result["revert"].append(path)
        else:
            result["delete"].append(path)
    return result


def write_manifest(family: str, platform: str, classified: dict[str, list[str]], *, dry_run: bool) -> Path:
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = ROLLBACK_DIR / family / platform / f"{date}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Rollback Manifest - {family}/{platform}",
        "",
        f"- Dry run: `{dry_run}`",
        f"- Revert: `{len(classified['revert'])}`",
        f"- Delete: `{len(classified['delete'])}`",
        f"- Skip: `{len(classified['skip'])}`",
        f"- Protected: `{len(classified['protected'])}`",
        "",
    ]
    for key in ("revert", "delete", "skip", "protected"):
        lines.extend([f"## {key.title()}", ""])
        lines.extend(f"- `{item}`" for item in sorted(classified[key]))
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def run(family: str, platform: str, *, dry_run: bool = False, include_locales: bool = False, no_manifest: bool = False) -> int:
    try:
        paths = read_site_plan(family, platform)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if include_locales:
        paths.extend(expand_locale_paths(paths, family, platform))
    classified = classify_files(paths)
    if not no_manifest:
        print(write_manifest(family, platform, classified, dry_run=dry_run))
    if classified["protected"]:
        print("error: protected paths found; refusing rollback", file=sys.stderr)
        return 2
    print(json.dumps({key: len(value) for key, value in classified.items()}, sort_keys=True))
    if dry_run:
        return 0
    failures = 0
    for path in classified["revert"]:
        failures += subprocess.run(["git", "checkout", "HEAD", "--", path], cwd=REPO_ROOT).returncode != 0
    for path in classified["delete"]:
        try:
            (REPO_ROOT / path).unlink()
        except OSError:
            failures += 1
    return 0 if failures == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("family")
    parser.add_argument("platform")
    parser.add_argument("--repo-root")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--include-locales", action="store_true")
    parser.add_argument("--no-manifest", action="store_true")
    args = parser.parse_args(argv)
    if args.repo_root:
        configure(repo_root=args.repo_root)
    return run(args.family, args.platform, dry_run=args.dry_run, include_locales=args.include_locales, no_manifest=args.no_manifest)


if __name__ == "__main__":
    raise SystemExit(main())
