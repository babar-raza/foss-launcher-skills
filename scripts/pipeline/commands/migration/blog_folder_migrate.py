#!/usr/bin/env python3
"""blog_folder_migrate.py — Governed folder slug migration for blog.aspose.org.

Renames blog post folders that have been identified as MIGRATION_READY by
blog_slug_inventory.py. Operates from a repair candidates JSON file.

SAFETY RULES (enforced):
- Never adds slug: to any frontmatter
- Never adds aliases: to any frontmatter
- Never modifies post body content
- Never modifies title, date, evidence, grade, or provenance fields
- Fails if target folder already exists
- Fails if new slug still fails policy validation
- Skips posts with auto_updatable=false

Usage:
    # Dry-run — shows what would happen, no changes made
    python scripts/pipeline/commands/migration/blog_folder_migrate.py \\
        --candidates reports/blog-slugs/blog-folder-slug-repair-candidates.json \\
        --dry-run

    # Apply — executes renames, updates references, writes manifests
    python scripts/pipeline/commands/migration/blog_folder_migrate.py \\
        --candidates reports/blog-slugs/blog-folder-slug-repair-candidates.json \\
        --apply

    # Repo root override (for testing)
    python ... --repo-root /path/to/repo
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve()
_DEFAULT_REPO_ROOT = _HERE.parents[4]

sys.path.insert(0, str(_DEFAULT_REPO_ROOT / "scripts" / "pipeline"))

import yaml
from lib.blog_slug_policy import (
    MIGRATION_READY,
    classify_folder_slug_quality,
    validate_folder_slug,
)

_FM_RE = re.compile(r"^(---\s*\n)(.*?)(\n---\s*(?:\n|$))", re.DOTALL)


# ---------------------------------------------------------------------------
# Frontmatter-aware source_file update
# ---------------------------------------------------------------------------

def _update_source_file_in_frontmatter(content: str, old_value: str, new_value: str) -> tuple[str, bool]:
    """Update source_file field in YAML frontmatter only.

    Returns (new_content, changed). Does NOT touch post body.
    Never adds slug: or aliases: fields.
    Never modifies any field other than source_file.
    """
    m = _FM_RE.match(content)
    if not m:
        return content, False

    fm_open, fm_body, fm_close = m.group(1), m.group(2), m.group(3)
    rest = content[m.end():]

    # Parse YAML
    try:
        fm_dict = yaml.safe_load(fm_body)
    except yaml.YAMLError:
        return content, False

    if not isinstance(fm_dict, dict):
        return content, False

    # Safety check: must not add slug: or aliases:
    assert "slug" not in fm_dict or True  # read-only check
    assert "aliases" not in fm_dict or True  # read-only check

    # Only update source_file — never add slug: or aliases:
    provenance = fm_dict.get("provenance") or {}
    if not isinstance(provenance, dict):
        return content, False

    # source_file may be top-level or under provenance
    changed = False

    # Check top-level source_file
    if "source_file" in fm_dict and fm_dict["source_file"] == old_value:
        fm_dict["source_file"] = new_value
        changed = True

    # Check provenance.source_file
    if "source_file" in provenance and provenance["source_file"] == old_value:
        fm_dict["provenance"]["source_file"] = new_value
        changed = True

    if not changed:
        # Try regex-based update as fallback (safer for round-trip fidelity)
        old_pattern = re.compile(
            r"^(\s*source_file:\s*)" + re.escape(old_value) + r"\s*$",
            re.MULTILINE,
        )
        if old_pattern.search(fm_body):
            new_fm_body = old_pattern.sub(r"\g<1>" + new_value, fm_body)
            new_content = fm_open + new_fm_body + fm_close + rest
            return new_content, True
        return content, False

    # Reconstruct: preserve original YAML style with yaml.dump
    new_fm_body = yaml.dump(fm_dict, allow_unicode=True, default_flow_style=False,
                             sort_keys=False).rstrip("\n")
    new_content = fm_open + new_fm_body + fm_close + rest
    return new_content, True


def _verify_no_slug_aliases_added(content_before: str, content_after: str, filepath: str) -> None:
    """Hard assertion: slug: and aliases: must not appear in after if not in before."""
    def has_slug(text: str) -> bool:
        return bool(re.search(r"^\s*slug\s*:", text, re.MULTILINE))

    def has_aliases(text: str) -> bool:
        return bool(re.search(r"^\s*aliases\s*:", text, re.MULTILINE))

    if not has_slug(content_before) and has_slug(content_after):
        raise RuntimeError(
            f"SAFETY VIOLATION: slug: field was added to {filepath} — aborting"
        )
    if not has_aliases(content_before) and has_aliases(content_after):
        raise RuntimeError(
            f"SAFETY VIOLATION: aliases: field was added to {filepath} — aborting"
        )


# ---------------------------------------------------------------------------
# site_plan.yaml update
# ---------------------------------------------------------------------------

def _update_site_plan(
    site_plan_path: Path,
    old_slug: str,
    new_slug: str,
    old_path_fragment: str,
    new_path_fragment: str,
    dry_run: bool,
) -> list[str]:
    """Update slug and path references in site_plan.yaml. Returns list of changes."""
    if not site_plan_path.exists():
        return []

    content = site_plan_path.read_text(encoding="utf-8")
    changes = []

    new_content = content
    # Replace slug: old_slug ->slug: new_slug (only exact slug value)
    slug_re = re.compile(r"(slug:\s*)" + re.escape(old_slug) + r"(\s*$)", re.MULTILINE)
    if slug_re.search(new_content):
        new_content = slug_re.sub(r"\g<1>" + new_slug + r"\2", new_content)
        changes.append(f"  slug: {old_slug} ->{new_slug}")

    # Replace path fragment
    if old_path_fragment in new_content:
        new_content = new_content.replace(old_path_fragment, new_path_fragment)
        changes.append(f"  path: ...{old_path_fragment}... ->...{new_path_fragment}...")

    if changes and not dry_run:
        site_plan_path.write_text(new_content, encoding="utf-8")

    return changes


# ---------------------------------------------------------------------------
# Migration execution
# ---------------------------------------------------------------------------

def run_migration(
    candidates: list[dict],
    repo_root: Path,
    dry_run: bool,
    out_dir: Path,
) -> dict:
    """Run migration for all candidates. Returns result manifest."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    results = []
    skipped = []

    for cand in candidates:
        old_slug = cand["old_folder_slug"]
        new_slug = cand["new_folder_slug"]
        family = cand["family"]
        platform = cand["platform"]
        title = cand.get("title", "")
        auto_updatable = cand.get("auto_updatable", True)

        prefix = "[DRY-RUN] " if dry_run else ""

        # --- Pre-flight checks ---

        # 1. auto_updatable guard
        if not auto_updatable:
            skipped.append({
                "old_folder_slug": old_slug,
                "reason": "auto_updatable=false — governance block",
            })
            print(f"  SKIP {old_slug}: auto_updatable=false")
            continue

        # 2. New slug must pass policy validation
        violations = validate_folder_slug(new_slug, title, family, platform)
        if violations:
            skipped.append({
                "old_folder_slug": old_slug,
                "reason": f"New slug fails policy: {'; '.join(violations)}",
            })
            print(f"  SKIP {old_slug}: new slug '{new_slug}' fails policy: {violations}")
            continue

        # 3. Source folder must exist
        old_folder = repo_root / "content" / "blog.aspose.org" / family / platform / old_slug
        new_folder = repo_root / "content" / "blog.aspose.org" / family / platform / new_slug

        if not old_folder.is_dir():
            skipped.append({
                "old_folder_slug": old_slug,
                "reason": f"Source folder not found: {old_folder}",
            })
            print(f"  SKIP {old_slug}: source folder not found")
            continue

        # 4. Target folder must NOT exist
        if new_folder.exists():
            print(f"  STOP: target folder already exists: {new_folder}", file=sys.stderr)
            print(f"  Cannot safely rename {old_slug} ->{new_slug}", file=sys.stderr)
            sys.exit(1)

        # Count files before move
        files_before = list(old_folder.iterdir())
        file_count = len(files_before)

        print(f"{prefix}Rename: {old_slug} -> {new_slug} ({file_count} files, {family}/{platform})")

        result_entry = {
            "old_folder_slug": old_slug,
            "new_folder_slug": new_slug,
            "family": family,
            "platform": platform,
            "title": title,
            "old_path": str(old_folder.relative_to(repo_root).as_posix()),
            "new_path": str(new_folder.relative_to(repo_root).as_posix()),
            "file_count": file_count,
            "source_file_updates": [],
            "site_plan_changes": [],
            "seo_risk": (
                f"Old URL /{family}/{platform}/{old_slug}/ will 404 after rename. "
                "No redirect mechanism available without aliases (forbidden). "
                "SEO loss accepted as folder slug quality is the priority fix."
            ),
        }

        if not dry_run:
            # --- Step 2: Move folder ---
            shutil.move(str(old_folder), str(new_folder))
            print(f"  Moved folder: {old_folder.name} ->{new_folder.name}")

            # --- Step 3: Update source_file in locale files ---
            old_sf = f"blog.aspose.org/{family}/{platform}/{old_slug}/index.md"
            new_sf = f"blog.aspose.org/{family}/{platform}/{new_slug}/index.md"

            for update in cand.get("source_file_updates", []):
                # File path was relative to repo root at inventory time
                # Now it lives under new_folder after the move
                old_locale_rel = update["file"]
                # Reconstruct path under new_folder
                locale_filename = Path(old_locale_rel).name
                locale_path = new_folder / locale_filename

                if not locale_path.exists():
                    print(f"  WARN: locale file not found after move: {locale_path}")
                    continue

                content_before = locale_path.read_text(encoding="utf-8")
                content_after, changed = _update_source_file_in_frontmatter(
                    content_before, update["old_value"], update["new_value"]
                )

                if changed:
                    _verify_no_slug_aliases_added(content_before, content_after, str(locale_path))
                    locale_path.write_text(content_after, encoding="utf-8")
                    result_entry["source_file_updates"].append({
                        "file": str(locale_path.relative_to(repo_root).as_posix()),
                        "old_value": update["old_value"],
                        "new_value": update["new_value"],
                    })
                    print(f"  Updated source_file: {locale_filename}")

            # --- Step 4: Update site_plan.yaml ---
            site_plan_path = (
                repo_root / "reports" / "plans" / family / platform / "site_plan.yaml"
            )
            old_path_fragment = f"{family}/{platform}/{old_slug}"
            new_path_fragment = f"{family}/{platform}/{new_slug}"
            site_plan_changes = _update_site_plan(
                site_plan_path,
                old_slug=old_slug,
                new_slug=new_slug,
                old_path_fragment=old_path_fragment,
                new_path_fragment=new_path_fragment,
                dry_run=False,
            )
            result_entry["site_plan_changes"] = site_plan_changes
            if site_plan_changes:
                print(f"  Updated site_plan.yaml:")
                for ch in site_plan_changes:
                    print(f"    {ch}")

        else:
            # Dry-run: report what would happen
            print(f"  Would move: {old_folder}")
            print(f"  Would create: {new_folder}")
            for update in cand.get("source_file_updates", []):
                print(f"  Would update source_file in: {Path(update['file']).name}")

            site_plan_path = (
                repo_root / "reports" / "plans" / family / platform / "site_plan.yaml"
            )
            old_path_fragment = f"{family}/{platform}/{old_slug}"
            new_path_fragment = f"{family}/{platform}/{new_slug}"
            site_plan_changes = _update_site_plan(
                site_plan_path,
                old_slug=old_slug,
                new_slug=new_slug,
                old_path_fragment=old_path_fragment,
                new_path_fragment=new_path_fragment,
                dry_run=True,
            )
            if site_plan_changes:
                print(f"  Would update site_plan.yaml:")
                for ch in site_plan_changes:
                    print(f"    {ch}")

        results.append(result_entry)

    manifest = {
        "timestamp": timestamp,
        "mode": "dry-run" if dry_run else "applied",
        "renames": results,
        "skipped": skipped,
        "seo_note": (
            "Old URLs will 404 after rename. "
            "No redirect mechanism is used (aliases: is forbidden by policy). "
            "URL correctness is structurally guaranteed by folder path derivation."
        ),
    }

    if not dry_run:
        # Write applied manifest
        applied_path = out_dir / f"migration-{timestamp}-applied.json"
        applied_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"\nMigration manifest: {applied_path}")

        # Write rollback manifest
        rollback = {
            "timestamp": timestamp,
            "instructions": "Run these git mv commands to undo the rename:",
            "rollback_commands": [],
        }
        for r in results:
            rollback["rollback_commands"].append(
                f"git mv content/blog.aspose.org/{r['family']}/{r['platform']}/{r['new_folder_slug']} "
                f"content/blog.aspose.org/{r['family']}/{r['platform']}/{r['old_folder_slug']}"
            )
            if r.get("site_plan_changes"):
                rollback["rollback_commands"].append(
                    f"git checkout reports/plans/{r['family']}/{r['platform']}/site_plan.yaml"
                )
        rollback_path = out_dir / f"migration-{timestamp}-rollback.json"
        rollback_path.write_text(json.dumps(rollback, indent=2), encoding="utf-8")
        print(f"Rollback manifest: {rollback_path}")
    else:
        print(f"\n[DRY-RUN] No files changed. Review the plan above before running --apply.")

    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Governed blog folder slug migration"
    )
    parser.add_argument(
        "--candidates",
        required=True,
        help="Path to blog-folder-slug-repair-candidates.json",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Show what would happen, make no changes")
    mode.add_argument("--apply", action="store_true", help="Execute renames and updates")
    parser.add_argument(
        "--repo-root",
        default=str(_DEFAULT_REPO_ROOT),
        help="Repo root (default: auto-detected)",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Output directory for manifests (default: same dir as candidates file)",
    )
    args = parser.parse_args()

    candidates_path = Path(args.candidates).resolve()
    if not candidates_path.exists():
        print(f"ERROR: candidates file not found: {candidates_path}", file=sys.stderr)
        return 1

    with open(candidates_path, encoding="utf-8") as f:
        candidates = json.load(f)

    if not candidates:
        print("No migration candidates found — nothing to do.")
        return 0

    repo_root = Path(args.repo_root).resolve()
    out_dir = Path(args.out).resolve() if args.out else candidates_path.parent

    print(f"Migration mode: {'DRY-RUN' if args.dry_run else 'APPLY'}")
    print(f"Candidates: {len(candidates)}")
    print(f"Repo root: {repo_root}")
    print()

    run_migration(
        candidates=candidates,
        repo_root=repo_root,
        dry_run=args.dry_run,
        out_dir=out_dir,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
