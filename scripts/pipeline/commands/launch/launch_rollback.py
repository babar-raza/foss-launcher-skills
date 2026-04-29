"""launch_rollback.py — Revert one product's generated content after a flawed launch.

Backing script for S-79 (launch-rollback). Reads reports/plans/{family}/{platform}/site_plan.yaml
to enumerate generated content files, then git-reverts (or deletes) each one.

Only content/ paths are ever touched — system files (scripts/, .agents/, reports/,
knowledge/) are explicitly protected.

Usage:
    python scripts/pipeline/launch_rollback.py {family} {platform} [--dry-run] [--include-locales]

Options:
    --dry-run         Print rollback manifest; do NOT execute any git/fs operations.
    --include-locales Also revert locale translation variants (ar, bg, ca, ... zh prefixes).
    --no-manifest     Skip writing the manifest file (dry-run still prints to stdout).

CONTRACT: This script is the backing implementation for S-79 (launch-rollback).
The skill spec in .agents/skills/launch-rollback/SKILL.md documents the same
behaviour. Keep them in sync.
verified: 2026-04-07
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
REPO_ROOT = _DEFAULT_REPO_ROOT
PLANS_DIR = REPO_ROOT / "reports" / "plans"
ROLLBACK_DIR = REPO_ROOT / "reports" / "rollback"
CONTENT_ROOT = REPO_ROOT / "content"


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Override module-level path constants for testing."""
    global REPO_ROOT, PLANS_DIR, ROLLBACK_DIR, CONTENT_ROOT
    REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    PLANS_DIR = REPO_ROOT / "reports" / "plans"
    ROLLBACK_DIR = REPO_ROOT / "reports" / "rollback"
    CONTENT_ROOT = REPO_ROOT / "content"

# Locale codes used in content/docs.aspose.org/{locale}/... paths
_LOCALE_CODES = [
    "ar", "bg", "ca", "cs", "da", "de", "el", "es", "fa", "fi",
    "fr", "he", "hi", "hr", "hu", "id", "it", "ja", "ko", "lt",
    "lv", "ms", "nl", "no", "pl", "pt", "ro", "ru", "sk", "sr",
    "sv", "th", "tr", "uk", "vi", "zh",
]

# Paths that must NEVER be reverted by this script
_PROTECTED_PREFIXES = (
    "scripts/",
    ".agents/",
    ".claude/",
    ".kilocode/",
    "reports/",
    "knowledge/",
    "configs/",
    "layouts/",
    "static/",
    "themes/",
)


# ---------------------------------------------------------------------------
# Safety check
# ---------------------------------------------------------------------------

def _is_content_path(path: str) -> bool:
    """Return True only for paths that start with content/."""
    return path.startswith("content/") or path.startswith("content\\")


def _is_protected(path: str) -> bool:
    """Return True if the path is in a protected (non-content) directory."""
    for prefix in _PROTECTED_PREFIXES:
        if path.startswith(prefix):
            return True
    return False


# ---------------------------------------------------------------------------
# Site plan reading
# ---------------------------------------------------------------------------

def _read_site_plan(family: str, platform: str) -> list[str]:
    """Return list of relative file paths from the site plan.

    Also includes reference class pages, which batch_reference.py writes directly
    into the reference content directory rather than listing individually in the plan.
    """
    plan_path = PLANS_DIR / family / platform / "site_plan.yaml"
    if not plan_path.exists():
        raise FileNotFoundError(
            f"Site plan not found at {plan_path}. "
            f"Run '/site-plan {family} {platform}' first."
        )
    with open(plan_path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    plan = raw.get("plan", raw)
    paths: list[str] = []

    sections = plan.get("sections", {})
    for _section_name, section_data in sections.items():
        if not isinstance(section_data, dict):
            continue
        for page in section_data.get("pages", []):
            p = page.get("path", "")
            if p:
                paths.append(p)

    # batch_reference.py generates one .md file per class in the reference content dir,
    # but these individual class pages are NOT listed in site_plan.yaml (only the _index is).
    # Discover them by scanning the reference content directory.
    ref_content_dir = REPO_ROOT / "content" / "reference.aspose.org" / "en" / family / platform
    if ref_content_dir.exists():
        for md_file in ref_content_dir.glob("*.md"):
            rel = md_file.relative_to(REPO_ROOT).as_posix()
            if rel not in paths:
                paths.append(rel)

    return paths


def _expand_locale_paths(en_paths: list[str], family: str, platform: str) -> list[str]:
    """Derive locale-variant paths from English content paths.

    Only expands paths that are under content/docs.aspose.org/en/{family}/{platform}/
    since locale translations only exist for docs pages.
    """
    locale_paths: list[str] = []
    docs_en_prefix = f"content/docs.aspose.org/en/{family}/{platform}/"

    for path in en_paths:
        # Normalize backslashes
        norm = path.replace("\\", "/")
        if norm.startswith(docs_en_prefix):
            relative_suffix = norm[len(docs_en_prefix):]
            for locale in _LOCALE_CODES:
                locale_path = f"content/docs.aspose.org/{locale}/{family}/{platform}/{relative_suffix}"
                locale_paths.append(locale_path)

    return locale_paths


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def _git_in_index(path: str) -> bool:
    """Return True if path is tracked in the git index (exists in git history)."""
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", path],
        capture_output=True,
        cwd=str(REPO_ROOT),
    )
    return result.returncode == 0


def _git_checkout(path: str) -> tuple[bool, str]:
    """Run git checkout HEAD -- path. Returns (success, error_msg)."""
    result = subprocess.run(
        ["git", "checkout", "HEAD", "--", path],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    if result.returncode != 0:
        return False, result.stderr.strip()
    return True, ""


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def _classify_files(
    paths: list[str],
) -> tuple[list[str], list[str], list[str], list[str]]:
    """Classify paths into revert, delete, skip, and protected.

    Returns (to_revert, to_delete, to_skip, protected_violations).
    """
    to_revert: list[str] = []
    to_delete: list[str] = []
    to_skip: list[str] = []
    protected: list[str] = []

    for raw_path in paths:
        norm = raw_path.replace("\\", "/")

        if _is_protected(norm):
            protected.append(norm)
            continue

        if not _is_content_path(norm):
            # Non-content, non-protected path — unexpected; treat as skip
            to_skip.append(norm)
            continue

        full = REPO_ROOT / norm
        if not full.exists():
            to_skip.append(norm)
            continue

        if _git_in_index(norm):
            to_revert.append(norm)
        else:
            to_delete.append(norm)

    return to_revert, to_delete, to_skip, protected


# ---------------------------------------------------------------------------
# Manifest writing
# ---------------------------------------------------------------------------

def _write_manifest(
    family: str,
    platform: str,
    to_revert: list[str],
    to_delete: list[str],
    to_skip: list[str],
    protected: list[str],
    dry_run: bool,
) -> Path:
    """Write rollback manifest and return its path."""
    ROLLBACK_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    manifest_path = ROLLBACK_DIR / family / platform / f"{date_str}.md"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        f"# Rollback Manifest — {family}/{platform}",
        f"",
        f"**Date**: {date_str}",
        f"**Dry run**: {dry_run}",
        f"",
        f"## Summary",
        f"",
        f"| Action | Count |",
        f"|--------|-------|",
        f"| Revert (git checkout HEAD) | {len(to_revert)} |",
        f"| Delete (untracked files) | {len(to_delete)} |",
        f"| Skip (not present) | {len(to_skip)} |",
        f"| Protected (NOT touched) | {len(protected)} |",
        f"",
    ]

    if to_revert:
        lines += ["## Files Reverted", ""]
        for p in sorted(to_revert):
            lines.append(f"- `{p}`")
        lines.append("")

    if to_delete:
        lines += ["## Files Deleted", ""]
        for p in sorted(to_delete):
            lines.append(f"- `{p}`")
        lines.append("")

    if to_skip:
        lines += ["## Files Skipped (not found)", ""]
        for p in sorted(to_skip):
            lines.append(f"- `{p}`")
        lines.append("")

    if protected:
        lines += ["## Protected Paths (NOT touched)", ""]
        for p in sorted(protected):
            lines.append(f"- `{p}` ⚠️  PROTECTED — not reverted")
        lines.append("")

    manifest_path.write_text("\n".join(lines), encoding="utf-8")
    return manifest_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(
    family: str,
    platform: str,
    dry_run: bool = False,
    include_locales: bool = False,
    no_manifest: bool = False,
) -> int:
    """Execute rollback. Returns exit code (0=success, 1=error, 2=protected-paths-found)."""

    print(f"[launch_rollback] Starting rollback for {family}/{platform}")
    print(f"[launch_rollback] Dry run: {dry_run}")

    # --- Read site plan ---
    try:
        en_paths = _read_site_plan(family, platform)
    except FileNotFoundError as exc:
        print(f"[launch_rollback] ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"[launch_rollback] Site plan lists {len(en_paths)} English content files")

    # --- Expand locales if requested ---
    all_paths = list(en_paths)
    if include_locales:
        locale_paths = _expand_locale_paths(en_paths, family, platform)
        all_paths.extend(locale_paths)
        print(f"[launch_rollback] Including {len(locale_paths)} locale translation variants")

    # --- Classify ---
    to_revert, to_delete, to_skip, protected = _classify_files(all_paths)

    if protected:
        print(
            f"[launch_rollback] SAFETY VIOLATION: {len(protected)} paths are in protected "
            "directories. These will NOT be reverted.",
            file=sys.stderr,
        )
        for p in protected:
            print(f"  PROTECTED: {p}", file=sys.stderr)
        # Write manifest and return error
        if not no_manifest:
            mpath = _write_manifest(
                family, platform, to_revert, to_delete, to_skip, protected, dry_run
            )
            print(f"[launch_rollback] Manifest written to {mpath}")
        return 2

    # --- Write manifest ---
    if not no_manifest:
        mpath = _write_manifest(
            family, platform, to_revert, to_delete, to_skip, protected, dry_run
        )
        print(f"[launch_rollback] Manifest written to {mpath}")

    # --- Print summary ---
    print(
        f"[launch_rollback] Plan: {len(to_revert)} revert, "
        f"{len(to_delete)} delete, {len(to_skip)} skip"
    )

    if dry_run:
        print("[launch_rollback] DRY RUN — no changes made.")
        return 0

    # --- Execute ---
    revert_ok = 0
    revert_fail = 0
    for path in to_revert:
        ok, err = _git_checkout(path)
        if ok:
            revert_ok += 1
        else:
            print(f"[launch_rollback] WARN: git checkout failed for {path}: {err}", file=sys.stderr)
            revert_fail += 1

    delete_ok = 0
    for path in to_delete:
        full = REPO_ROOT / path
        try:
            full.unlink()
            delete_ok += 1
        except OSError as exc:
            print(f"[launch_rollback] WARN: delete failed for {path}: {exc}", file=sys.stderr)

    print(
        f"[launch_rollback] Done: {revert_ok} reverted "
        f"({revert_fail} failed), {delete_ok} deleted."
    )

    return 0 if revert_fail == 0 else 1


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Revert one product's generated content after a flawed launch.",
    )
    parser.add_argument("family", help="Product family (e.g. cells, slides)")
    parser.add_argument("platform", help="Platform (e.g. net, python, java)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print rollback manifest without executing any changes.",
    )
    parser.add_argument(
        "--include-locales",
        action="store_true",
        help="Also revert locale translation variants of docs pages.",
    )
    parser.add_argument(
        "--no-manifest",
        action="store_true",
        help="Skip writing the manifest file to disk.",
    )
    args = parser.parse_args(argv)

    return run(
        family=args.family,
        platform=args.platform,
        dry_run=args.dry_run,
        include_locales=args.include_locales,
        no_manifest=args.no_manifest,
    )


if __name__ == "__main__":
    sys.exit(_main())
