# Adapted from aspose.org
"""Sync provider skill copies from canonical skills/ directory.

Updates .agents/skills/, .claude/commands/, and .kilocode/skills/ to match canonical skills/,
preserving each provider's YAML frontmatter and structural notes.

Also generates skills/registry.json — a machine-readable skill catalog for structured
discovery by any agent platform.

Usage:
    python scripts/pipeline/commands/ops/sync_providers.py --dry-run           # preview changes
    python scripts/pipeline/commands/ops/sync_providers.py                     # apply changes
    python scripts/pipeline/commands/ops/sync_providers.py --create-missing    # also create missing mirrors
    python scripts/pipeline/commands/ops/sync_providers.py --create-missing --dry-run  # preview creation
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
import os

_DEFAULT_REPO_ROOT = Path(os.environ.get("FOSS_REPO_ROOT", str(Path(__file__).resolve().parent.parent.parent.parent.parent)))
_REPO_ROOT = _DEFAULT_REPO_ROOT

_DEFAULT_CANONICAL_DIR = _DEFAULT_REPO_ROOT / "skills"
CANONICAL_DIR = _DEFAULT_CANONICAL_DIR

_DEFAULT_PROVIDERS = {
    "agents": _DEFAULT_REPO_ROOT / ".agents" / "skills",
    "claude": _DEFAULT_REPO_ROOT / ".claude" / "commands",
    "kilocode": _DEFAULT_REPO_ROOT / ".kilocode" / "skills",
}
PROVIDERS = _DEFAULT_PROVIDERS

# These slugs are intentionally provider-specific; never sync them from canonical
_DEFAULT_SKIP_SLUGS: dict = {
    "claude": {"translate", "seo-review", "translate-batch", "translate-page"},
}
SKIP_SLUGS = _DEFAULT_SKIP_SLUGS


def configure(
    *,
    canonical_dir: "Path | str | None" = None,
    providers: "dict | None" = None,
    skip_slugs: "dict | None" = None,
) -> None:
    """Override module-level path constants for testing."""
    global CANONICAL_DIR, PROVIDERS, SKIP_SLUGS
    if canonical_dir is None and providers is None and skip_slugs is None:
        CANONICAL_DIR = _DEFAULT_CANONICAL_DIR
        PROVIDERS = _DEFAULT_PROVIDERS
        SKIP_SLUGS = _DEFAULT_SKIP_SLUGS
        return
    if canonical_dir is not None:
        CANONICAL_DIR = Path(canonical_dir)
    if providers is not None:
        PROVIDERS = providers
    if skip_slugs is not None:
        SKIP_SLUGS = skip_slugs

CROSS_SKILL_NOTE = (
    "> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.\n\n"
)

_LIB_DIR = str(Path(__file__).resolve().parents[2] / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from _skill_constants import INTERNAL_SKILLS

_ID_RE = re.compile(r"^#\s+(S-\d+):")
_PURPOSE_RE = re.compile(r"^##\s+Purpose\s*$", re.MULTILINE)
_ARGS_RE = re.compile(r"\*\*Arguments\*\*:\s*(.+)")


def _extract_id_from_content(text: str) -> str | None:
    """Extract S-XX ID from the first 1500 chars of skill content."""
    for line in text[:1500].splitlines():
        m = _ID_RE.match(line)
        if m:
            return m.group(1)
    return None


def _extract_description(text: str) -> str:
    """Extract first sentence after ## Purpose as a description."""
    m = _PURPOSE_RE.search(text)
    if not m:
        return "Skill description pending"
    after_purpose = text[m.end():].lstrip("\n")
    # Take the first non-empty line
    for line in after_purpose.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and not line.startswith("**"):
            # Truncate at first sentence boundary
            if ". " in line:
                return line[:line.index(". ") + 1]
            return line
    return "Skill description pending"


def _extract_args(text: str) -> str:
    """Extract arguments pattern from **Arguments**: line."""
    m = _ARGS_RE.search(text[:1000])
    if m:
        args_text = m.group(1).strip()
        # Remove $ARGUMENTS placeholder
        args_text = args_text.replace("$ARGUMENTS", "").strip()
        if args_text:
            return args_text
    return ""


def _generate_frontmatter(slug: str, canonical_content: str) -> str:
    """Generate YAML frontmatter block for a provider mirror file."""
    skill_id = _extract_id_from_content(canonical_content) or "NONE"
    description = _extract_description(canonical_content)
    args = _extract_args(canonical_content)

    lines = ["---", f"name: {slug}", f"id: {skill_id}"]
    lines.append(f"description: >")
    lines.append(f"  {description}")
    if args:
        lines.append(f'args: "{args}"')
    lines.append("---")
    return "\n".join(lines) + "\n"


def _extract_frontmatter(text: str) -> tuple[str, str]:
    """Return (frontmatter_block, body) for YAML-frontmatter files."""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            fm = "---" + parts[1] + "---\n"
            return fm, parts[2].lstrip("\n")
    return "", text


def _has_cross_skill_note(text: str) -> bool:
    return "> Cross-skill references like" in text


def sync_provider(provider: str, dry_run: bool = False,
                   create_missing: bool = False) -> tuple[list[str], list[str]]:
    """Sync all canonical skills into a provider.

    Returns (changed_slugs, created_slugs).
    """
    base = PROVIDERS[provider]
    skip = SKIP_SLUGS.get(provider, set())
    changed = []
    created = []

    for canonical_path in sorted(CANONICAL_DIR.glob("*.md")):
        slug = canonical_path.stem
        if slug.lower() == "readme":
            continue
        if slug in skip:
            continue

        canonical_raw = canonical_path.read_text(encoding="utf-8", errors="replace")
        # Strip canonical frontmatter — mirrors have their own provider-specific frontmatter
        _, canonical_content = _extract_frontmatter(canonical_raw)

        if provider == "claude":
            provider_path = base / f"{slug}.md"
        else:
            provider_path = base / slug / "SKILL.md"

        if not provider_path.exists():
            if not create_missing:
                continue  # don't create new files unless explicitly requested

            # Skip internal skills for Claude (they are sub-routines, never user-callable)
            if provider == "claude" and slug in INTERNAL_SKILLS:
                continue

            # Guard: skip creation if canonical has no S-XX ID
            sid = _extract_id_from_content(canonical_content)
            if sid is None:
                print(f"  SKIP {slug}: no S-XX ID in canonical heading", file=sys.stderr)
                continue

            # Generate new provider file
            frontmatter = _generate_frontmatter(slug, canonical_content)
            new_content = frontmatter + "\n"
            if provider in ("agents", "kilocode"):
                new_content += CROSS_SKILL_NOTE
            new_content += canonical_content

            created.append(slug)
            if not dry_run:
                provider_path.parent.mkdir(parents=True, exist_ok=True)
                provider_path.write_text(new_content, encoding="utf-8")
                print(f"  created {provider}/{slug}")
            else:
                print(f"  [dry-run] would create {provider}/{slug}")
            continue

        existing = provider_path.read_text(encoding="utf-8", errors="replace")
        frontmatter, _ = _extract_frontmatter(existing)
        has_note = _has_cross_skill_note(existing)

        # Build new provider content
        if frontmatter:
            new_content = frontmatter + "\n"
            if has_note or provider in ("agents", "kilocode"):
                new_content += CROSS_SKILL_NOTE
            new_content += canonical_content
        else:
            # Claude files: no frontmatter, no cross-skill note
            new_content = canonical_content

        if new_content == existing:
            continue

        changed.append(slug)
        if not dry_run:
            provider_path.write_text(new_content, encoding="utf-8")
            print(f"  synced {provider}/{slug}")
        else:
            print(f"  [dry-run] would sync {provider}/{slug}")

    return changed, created


REGISTRY_PATH = CANONICAL_DIR / "registry.json"


def _extract_title(text: str) -> str:
    """Extract skill title from the # S-XX: Title heading."""
    for line in text[:1500].splitlines():
        m = re.match(r"^#\s+S-\d+:\s*(.+)", line)
        if m:
            # Strip trailing markup like " — Foo" keeping " — Foo" as part of the name
            return m.group(1).strip()
    return ""


def generate_registry(dry_run: bool = False) -> bool:
    """Generate skills/registry.json from canonical skills/*.md.

    Returns True if the registry was updated (or would be in dry-run mode).
    """
    skills = []
    for canonical_path in sorted(CANONICAL_DIR.glob("*.md")):
        slug = canonical_path.stem
        if slug.lower() == "readme":
            continue

        raw = canonical_path.read_text(encoding="utf-8", errors="replace")
        _, content = _extract_frontmatter(raw)

        skill_id = _extract_id_from_content(content)
        if skill_id is None:
            continue

        title = _extract_title(content)
        description = _extract_description(content)
        args = _extract_args(content)
        internal = slug in INTERNAL_SKILLS

        entry = {
            "id": skill_id,
            "slug": slug,
            "name": title,
            "description": description,
            "internal": internal,
            "canonical_path": f"skills/{slug}.md",
        }
        if args:
            entry["args"] = args

        skills.append(entry)

    # Sort by numeric ID
    def _sort_key(e):
        try:
            return int(e["id"].split("-")[1])
        except (IndexError, ValueError):
            return 999
    skills.sort(key=_sort_key)

    registry = {
        "schema_version": 1,
        "generated_from": "skills/*.md",
        "generated_by": "scripts/pipeline/commands/ops/sync_providers.py",
        "skill_count": len(skills),
        "skills": skills,
    }

    new_content = json.dumps(registry, indent=2, ensure_ascii=False) + "\n"

    if REGISTRY_PATH.exists():
        existing = REGISTRY_PATH.read_text(encoding="utf-8", errors="replace")
        if existing == new_content:
            return False

    if not dry_run:
        REGISTRY_PATH.write_text(new_content, encoding="utf-8")
        print(f"  updated skills/registry.json ({len(skills)} skills)")
    else:
        print(f"  [dry-run] would update skills/registry.json ({len(skills)} skills)")

    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync provider skill copies from canonical.")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--check", action="store_true",
                        help="Exit non-zero if any files need syncing or creation (implies --dry-run)")
    parser.add_argument("--create-missing", action="store_true",
                        help="Create missing provider mirror files for canonical skills")
    parser.add_argument("--provider", choices=["agents", "claude", "kilocode"],
                        help="Sync one provider only")
    args = parser.parse_args(argv)

    dry_run = args.dry_run or args.check

    providers = [args.provider] if args.provider else list(PROVIDERS)
    total_changed = 0
    total_created = 0
    would = "would be " if dry_run else ""
    for prov in providers:
        print(f"\nSyncing {prov}...")
        changed, created = sync_provider(prov, dry_run=dry_run,
                                          create_missing=args.create_missing)
        total_changed += len(changed)
        total_created += len(created)
        parts = []
        if changed:
            parts.append(f"{len(changed)} {would}updated")
        if created:
            parts.append(f"{len(created)} {would}created")
        if not parts:
            parts.append("0 changes")
        print(f"  {', '.join(parts)}")

    # Generate skills/registry.json
    print("\nGenerating skills/registry.json...")
    registry_changed = generate_registry(dry_run=dry_run)
    if not registry_changed:
        print("  0 changes")

    # Auto-fix README count claims to match disk reality
    if not dry_run:
        fix_script = _REPO_ROOT / "scripts" / "ci" / "check_skill_readme_coverage.py"
        if fix_script.exists():
            print("\nUpdating README skill counts...")
            import subprocess
            result = subprocess.run(
                [sys.executable, str(fix_script), "--fix"],
                cwd=str(_REPO_ROOT),
                capture_output=True,
                text=True,
            )
            # Print only the fix_counts output, not the subsequent check output
            for line in result.stdout.splitlines():
                if line.startswith("  [OK]") or line.startswith("  [FIXED]"):
                    print(line)
                elif line.startswith("All counts") or line.startswith("Fixed"):
                    print(f"  {line}")
                    break  # stop before check() output
            if result.returncode != 0:
                print(f"  WARNING: README count check exited {result.returncode}")

    print(f"\nTotal: {total_changed} {would}updated, {total_created} {would}created")

    if args.check:
        if total_changed or total_created or registry_changed:
            parts = []
            if total_changed:
                parts.append(f"{total_changed} to sync")
            if total_created:
                parts.append(f"{total_created} to create")
            if registry_changed:
                parts.append("registry.json outdated")
            print(f"\nFAIL: {', '.join(parts)}")
            return 1
        print("\nPASS: all provider mirrors and registry.json up to date")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())