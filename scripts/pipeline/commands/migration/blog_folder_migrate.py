# Adapted from aspose.org
#!/usr/bin/env python3
"""blog_folder_migrate.py — Governed folder slug migration for [a-zA-Z0-9.\-]+.

Renames blog post folders that have been identified as MIGRATION_READY by
blog_slug_inventory.py. Operates from a repair candidates JSON file.

SAFETY RULES (enforced):
- Never adds slug: to any frontmatter
- Only adds aliases: to the English index.md of a renamed post (to preserve old URL)
- Never adds aliases: to locale files (index.*.md)
- Never modifies post body content (other than inbound link rewrites)
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

sys.path.insert(0, str(_PIPELINE_ROOT))

import yaml
from lib.blog_slug_policy import (
    MIGRATION_READY,
    classify_folder_slug_quality,
    validate_folder_slug,
)

_FM_RE = re.compile(r"^(---\s*\n)(.*?)(\n---\s*(?:\n|$))", re.DOTALL)


# ---------------------------------------------------------------------------
# Pure-function utilities (Step E)
# ---------------------------------------------------------------------------

def split_frontmatter_and_body(text: str) -> tuple[str, str]:
    """Split text into (frontmatter_block, body).

    frontmatter_block includes the --- delimiters.
    Contract: frontmatter_block + body == text (lossless).
    If no frontmatter: returns ("", text).
    """
    m = _FM_RE.match(text)
    if not m:
        return "", text
    fm_block = m.group(0)
    body = text[m.end():]
    return fm_block, body


# Regex for detecting blog slug references in body text.
# Matches /{family}/{platform}/{slug} followed by / ? # " ' ) whitespace or EOL.
# Also matches absolute URLs: https?://[a-zA-Z0-9.\-]+/... and protocol-relative //the content domain/...
def _build_slug_pattern(family: str, platform: str, slug: str) -> re.Pattern:
    esc_family = re.escape(family)
    esc_platform = re.escape(platform)
    esc_slug = re.escape(slug)
    tail = r"(?=[/?#\"'\)\s]|$)"
    # Root-relative form: /{family}/{platform}/{slug}
    # Negative lookbehind prevents matching /blog/3d/java/slug when family=3d
    path_form = rf"(?<![a-zA-Z0-9_./\-])/{esc_family}/{esc_platform}/{esc_slug}{tail}"
    # Absolute: https://[a-zA-Z0-9.\-]+/family/platform/slug...
    abs_form = rf"https?://blog\.aspose\.org/{esc_family}/{esc_platform}/{esc_slug}{tail}"
    # Protocol-relative
    proto_form = rf"//blog\.aspose\.org/{esc_family}/{esc_platform}/{esc_slug}{tail}"
    combined = f"(?:{abs_form}|{proto_form}|{path_form})"
    return re.compile(combined)


def find_blog_slug_references(
    body: str,
    family: str,
    platform: str,
    slug: str,
) -> list[dict]:
    """Scan body-only text for links to /{family}/{platform}/{slug}/.

    Returns list of match dicts: {match, start, end, link_form}.
    Never operates on frontmatter — caller must pass body only.

    False-positive protections:
    - Partial slug match prevention: slug must be followed by /, ?, #, ", ', ), whitespace, or EOL
    - Unrelated family/platform: match must include exact /{family}/{platform}/{slug} prefix
    """
    pattern = _build_slug_pattern(family, platform, slug)
    results = []
    for m in pattern.finditer(body):
        match_str = m.group(0)
        # Determine link_form
        if match_str.startswith("https://") or match_str.startswith("http://"):
            link_form = "absolute"
        elif match_str.startswith("//"):
            link_form = "protocol-relative"
        else:
            link_form = "root-relative"
        results.append({
            "match": match_str,
            "start": m.start(),
            "end": m.end(),
            "link_form": link_form,
        })
    return results


def rewrite_blog_slug_references(
    body: str,
    family: str,
    platform: str,
    old_slug: str,
    new_slug: str,
) -> tuple[str, int]:
    """Rewrite all body-text references from old_slug to new_slug.

    Returns (new_body, count).
    Preserves link text, query strings, fragments, trailing slash style, line endings.
    Idempotent: second run on already-rewritten content returns count=0.
    """
    pattern = _build_slug_pattern(family, platform, old_slug)
    count = 0

    def _replace(m: re.Match) -> str:
        nonlocal count
        original = m.group(0)
        # Determine the prefix (absolute, proto-relative, root-relative)
        if original.startswith("https://[a-zA-Z0-9.\-]+"):
            old_prefix = f"https://[a-zA-Z0-9.\-]+/{family}/{platform}/{old_slug}"
            new_prefix = f"https://[a-zA-Z0-9.\-]+/{family}/{platform}/{new_slug}"
        elif original.startswith("http://[a-zA-Z0-9.\-]+"):
            old_prefix = f"http://[a-zA-Z0-9.\-]+/{family}/{platform}/{old_slug}"
            new_prefix = f"http://[a-zA-Z0-9.\-]+/{family}/{platform}/{new_slug}"
        elif original.startswith("//[a-zA-Z0-9.\-]+"):
            old_prefix = f"//[a-zA-Z0-9.\-]+/{family}/{platform}/{old_slug}"
            new_prefix = f"//[a-zA-Z0-9.\-]+/{family}/{platform}/{new_slug}"
        else:
            old_prefix = f"/{family}/{platform}/{old_slug}"
            new_prefix = f"/{family}/{platform}/{new_slug}"

        suffix = original[len(old_prefix):]
        count += 1
        return new_prefix + suffix

    new_body = pattern.sub(_replace, body)
    return new_body, count


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

    # Only update source_file — never add slug: or aliases:
    provenance = fm_dict.get("provenance") or {}
    if not isinstance(provenance, dict):
        return content, False

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


# ---------------------------------------------------------------------------
# Migration safety verifier (Step G — replaces _verify_no_slug_aliases_added)
# ---------------------------------------------------------------------------

def _verify_migration_safety(
    content_before: str,
    content_after: str,
    filepath: str,
    allowed_alias: str | None = None,
) -> None:
    """Verify migration did not introduce disallowed changes.

    Always blocked:
    - Any addition of slug: field

    Alias rules:
    - If allowed_alias is None: aliases: must not have been added (locale files, other files)
    - If allowed_alias is given: aliases: may be added, but ONLY to contain allowed_alias
      (plus any pre-existing aliases). No other aliases may appear.

    Raises RuntimeError on violation.
    """
    def _has_slug(text: str) -> bool:
        return bool(re.search(r"^\s*slug\s*:", text, re.MULTILINE))

    def _has_aliases(text: str) -> bool:
        return bool(re.search(r"^\s*aliases\s*:", text, re.MULTILINE))

    # slug: must never be added
    if not _has_slug(content_before) and _has_slug(content_after):
        raise RuntimeError(
            f"SAFETY VIOLATION: slug: field was added to {filepath} — aborting"
        )

    if not _has_aliases(content_before) and _has_aliases(content_after):
        if allowed_alias is None:
            raise RuntimeError(
                f"SAFETY VIOLATION: aliases: field was added to {filepath} — aborting"
            )
        # aliases was allowed — verify it only contains allowed_alias
        # Parse the after-state frontmatter to check alias values
        fm_m = _FM_RE.match(content_after)
        if fm_m:
            try:
                fm_dict = yaml.safe_load(fm_m.group(2))
                if isinstance(fm_dict, dict):
                    aliases_in_after = fm_dict.get("aliases", [])
                    if not isinstance(aliases_in_after, list):
                        raise RuntimeError(
                            f"SAFETY VIOLATION: aliases: is not a list in {filepath}"
                        )
                    # Any alias that wasn't in before must be allowed_alias
                    fm_before = _FM_RE.match(content_before)
                    aliases_before = []
                    if fm_before:
                        try:
                            fm_before_dict = yaml.safe_load(fm_before.group(2))
                            if isinstance(fm_before_dict, dict):
                                aliases_before = fm_before_dict.get("aliases", [])
                                if not isinstance(aliases_before, list):
                                    aliases_before = []
                        except yaml.YAMLError:
                            pass
                    new_aliases = [a for a in aliases_in_after if a not in aliases_before]
                    for alias in new_aliases:
                        if alias != allowed_alias:
                            raise RuntimeError(
                                f"SAFETY VIOLATION: unexpected alias '{alias}' added to {filepath}. "
                                f"Only '{allowed_alias}' is permitted."
                            )
            except yaml.YAMLError as e:
                raise RuntimeError(
                    f"SAFETY VIOLATION: could not parse frontmatter of {filepath} after write: {e}"
                )


# ---------------------------------------------------------------------------
# Alias addition helper (Step F)
# ---------------------------------------------------------------------------

def add_alias_to_english_index(
    index_path: Path,
    old_url: str,
    dry_run: bool,
) -> dict:
    """Add old_url to aliases: in English index.md frontmatter.

    Rules:
    - Only touches the aliases: block in frontmatter. All other fields and formatting preserved.
    - Surgical insertion: does NOT round-trip through yaml.dump to avoid churn on unrelated fields.
    - Appends old_url if not already present (idempotent).
    - Does NOT add slug:.
    - Does NOT touch body content.
    - Raises RuntimeError if frontmatter is absent or invalid YAML.
    - In dry-run mode: returns what would change without writing.

    Returns:
        {
            "file": str(index_path),
            "old_url": old_url,
            "added": bool,
            "already_present": bool,
            "dry_run": bool,
        }
    """
    text = index_path.read_text(encoding="utf-8")
    content_before = text

    m = _FM_RE.match(text)
    if not m:
        raise RuntimeError(f"no frontmatter in {index_path}")

    fm_body = m.group(2)

    try:
        fm_data = yaml.safe_load(fm_body)
    except yaml.YAMLError as e:
        raise RuntimeError(f"malformed frontmatter in {index_path}: {e}")

    if not isinstance(fm_data, dict):
        raise RuntimeError(
            f"frontmatter in {index_path} is not a mapping (got {type(fm_data).__name__})"
        )

    # Check existing aliases via parsed data (do not touch text yet)
    existing_aliases = fm_data.get("aliases", [])
    if not isinstance(existing_aliases, list):
        existing_aliases = [existing_aliases] if existing_aliases else []

    if old_url in existing_aliases:
        return {
            "file": str(index_path),
            "old_url": old_url,
            "added": False,
            "already_present": True,
            "dry_run": dry_run,
        }

    # Surgical text modification: locate the aliases: block or insert one
    # Strategy: find closing --- and insert aliases: block just before it,
    # OR if aliases: already exists (but old_url not present), append to it.
    alias_re = re.compile(r"^(aliases:\s*\n(?:[ \t]*-[^\n]*\n)*)", re.MULTILINE)
    closing_re = re.compile(r"^---\s*$", re.MULTILINE)

    fm_start = m.start(2)  # start of fm body within text
    fm_end = m.end(2)      # end of fm body within text (before closing ---)

    fm_text = text[fm_start:fm_end]

    alias_match = alias_re.search(fm_text)
    if alias_match:
        # Append new alias entry to existing aliases: block
        insertion_point = fm_start + alias_match.end()
        new_line = f"- {old_url}\n"
        new_text = text[:insertion_point] + new_line + text[insertion_point:]
    else:
        # Insert new aliases: block just before the closing ---
        # The closing --- is at the end of the FM block (m.group(3) starts with \n---)
        close_start = m.start(3)  # position of \n--- in text
        new_block = f"aliases:\n- {old_url}\n"
        new_text = text[:close_start] + "\n" + new_block + text[close_start:]

    # Safety verification
    _verify_migration_safety(content_before, new_text, str(index_path), allowed_alias=old_url)

    if not dry_run:
        from core.fs import atomic_write  # noqa: E402
        atomic_write(index_path, new_text)

    return {
        "file": str(index_path),
        "old_url": old_url,
        "added": True,
        "already_present": False,
        "dry_run": dry_run,
    }


# ---------------------------------------------------------------------------
# Inbound link scanner and rewriter (Step H)
# ---------------------------------------------------------------------------

def _update_inbound_links(
    content_root: Path,
    family: str,
    platform: str,
    old_slug: str,
    new_slug: str,
    dry_run: bool,
) -> list[dict]:
    """Scan *.md files under content_root for body links to old_slug and rewrite them.

    Uses split_frontmatter_and_body() to operate on body text only.
    Never modifies frontmatter, aliases, source_file, url, slug, or provenance fields.
    Aborts (raises RuntimeError) if rewrite verification fails on any file.
    Returns list of change records.
    """
    changes = []
    for md_file in content_root.rglob("*.md"):
        text = md_file.read_text(encoding="utf-8")
        fm_block, body = split_frontmatter_and_body(text)

        refs = find_blog_slug_references(body, family, platform, old_slug)
        if not refs:
            continue

        new_body, count = rewrite_blog_slug_references(body, family, platform, old_slug, new_slug)
        if count == 0:
            continue  # No actual changes (shouldn't happen given refs, but guard it)

        new_text = fm_block + new_body

        # Verify frontmatter was not touched
        new_fm_block, _ = split_frontmatter_and_body(new_text)
        if new_fm_block != fm_block:
            raise RuntimeError(
                f"SAFETY VIOLATION: frontmatter changed in {md_file} during inbound link rewrite"
            )

        change_record = {
            "file": str(md_file),
            "old_url": f"/{family}/{platform}/{old_slug}/",
            "new_url": f"/{family}/{platform}/{new_slug}/",
            "count": count,
            "dry_run": dry_run,
        }
        changes.append(change_record)

        if not dry_run:
            md_file.write_text(new_text, encoding="utf-8")

    return changes


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
    # Replace slug: old_slug -> slug: new_slug (only exact slug value)
    slug_re = re.compile(r"(slug:\s*)" + re.escape(old_slug) + r"(\s*$)", re.MULTILINE)
    if slug_re.search(new_content):
        new_content = slug_re.sub(r"\g<1>" + new_slug + r"\2", new_content)
        changes.append(f"  slug: {old_slug} -> {new_slug}")

    # Replace path fragment
    if old_path_fragment in new_content:
        new_content = new_content.replace(old_path_fragment, new_path_fragment)
        changes.append(f"  path: ...{old_path_fragment}... -> ...{new_path_fragment}...")

    if changes and not dry_run:
        site_plan_path.write_text(new_content, encoding="utf-8")

    return changes


# ---------------------------------------------------------------------------
# Migration execution (Step I — updated 8-step order)
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

    # Content root is configurable via --content-subdir
    blog_root = repo_root / "content"

    for cand in candidates:
        old_slug = cand["old_folder_slug"]
        new_slug = cand["new_folder_slug"]
        family = cand["family"]
        platform = cand["platform"]
        title = cand.get("title", "")
        auto_updatable = cand.get("auto_updatable", True)

        prefix = "[DRY-RUN] " if dry_run else ""

        # --- Step 1: Pre-flight checks ---

        # 1a. auto_updatable guard
        if not auto_updatable:
            skipped.append({
                "old_folder_slug": old_slug,
                "reason": "auto_updatable=false — governance block",
            })
            print(f"  SKIP {old_slug}: auto_updatable=false")
            continue

        # 1b. New slug must pass policy validation
        violations = validate_folder_slug(new_slug, title, family, platform)
        if violations:
            skipped.append({
                "old_folder_slug": old_slug,
                "reason": f"New slug fails policy: {'; '.join(violations)}",
            })
            print(f"  SKIP {old_slug}: new slug '{new_slug}' fails policy: {violations}")
            continue

        # 1c. Source folder must exist
        old_folder = blog_root / family / platform / old_slug
        new_folder = blog_root / family / platform / new_slug

        if not old_folder.is_dir():
            skipped.append({
                "old_folder_slug": old_slug,
                "reason": f"Source folder not found: {old_folder}",
            })
            print(f"  SKIP {old_slug}: source folder not found")
            continue

        # 1d. Target folder must NOT exist
        if new_folder.exists():
            print(f"  STOP: target folder already exists: {new_folder}", file=sys.stderr)
            print(f"  Cannot safely rename {old_slug} -> {new_slug}", file=sys.stderr)
            sys.exit(1)

        # 1e. English index.md frontmatter must be present and valid
        english_index = old_folder / "index.md"
        if not english_index.exists():
            skipped.append({
                "old_folder_slug": old_slug,
                "reason": "English index.md not found",
            })
            print(f"  SKIP {old_slug}: English index.md not found")
            continue

        english_text = english_index.read_text(encoding="utf-8")
        fm_m = _FM_RE.match(english_text)
        if not fm_m:
            skipped.append({
                "old_folder_slug": old_slug,
                "reason": "English index.md has no frontmatter — alias addition not possible",
            })
            print(f"  SKIP {old_slug}: English index.md has no frontmatter")
            continue

        try:
            fm_data = yaml.safe_load(fm_m.group(2))
            if not isinstance(fm_data, dict):
                raise ValueError(f"frontmatter is not a mapping: {type(fm_data).__name__}")
        except (yaml.YAMLError, ValueError) as e:
            skipped.append({
                "old_folder_slug": old_slug,
                "reason": f"English index.md has malformed frontmatter: {e}",
            })
            print(f"  SKIP {old_slug}: English index.md frontmatter is malformed: {e}")
            continue

        # Count files before move
        files_before = list(old_folder.iterdir())
        file_count = len(files_before)

        old_url = f"/{family}/{platform}/{old_slug}/"
        new_url = f"/{family}/{platform}/{new_slug}/"

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
            "alias_update": None,
            "inbound_link_updates": [],
            "seo_risk": (
                f"Old URL {old_url} redirected via aliases: in English index.md. "
                "Hugo build will generate a redirect HTML file at the old path."
            ),
        }

        if not dry_run:
            # --- Step 2: Move folder ---
            shutil.move(str(old_folder), str(new_folder))
            print(f"  Moved folder: {old_folder.name} -> {new_folder.name}")

            # --- Step 3: Update source_file in locale files ---
            old_sf = f"[a-zA-Z0-9.\-]+/{family}/{platform}/{old_slug}/index.md"
            new_sf = f"[a-zA-Z0-9.\-]+/{family}/{platform}/{new_slug}/index.md"

            for update in cand.get("source_file_updates", []):
                locale_filename = Path(update["file"]).name
                locale_path = new_folder / locale_filename

                if not locale_path.exists():
                    print(f"  WARN: locale file not found after move: {locale_path}")
                    continue

                content_before = locale_path.read_text(encoding="utf-8")
                content_after, changed = _update_source_file_in_frontmatter(
                    content_before, update["old_value"], update["new_value"]
                )

                if changed:
                    _verify_migration_safety(content_before, content_after, str(locale_path),
                                             allowed_alias=None)
                    locale_path.write_text(content_after, encoding="utf-8")
                    result_entry["source_file_updates"].append({
                        "file": str(locale_path.relative_to(repo_root).as_posix()),
                        "old_value": update["old_value"],
                        "new_value": update["new_value"],
                    })
                    print(f"  Updated source_file: {locale_filename}")

            # --- Step 4: Add alias to English index.md ---
            new_english_index = new_folder / "index.md"
            alias_result = add_alias_to_english_index(
                index_path=new_english_index,
                old_url=old_url,
                dry_run=False,
            )
            result_entry["alias_update"] = alias_result
            if alias_result["added"]:
                print(f"  Added alias {old_url} to English index.md")
            elif alias_result["already_present"]:
                print(f"  Alias {old_url} already present in English index.md")

            # --- Step 5: Update inbound body links ---
            inbound_changes = _update_inbound_links(
                content_root=blog_root,
                family=family,
                platform=platform,
                old_slug=old_slug,
                new_slug=new_slug,
                dry_run=False,
            )
            result_entry["inbound_link_updates"] = inbound_changes
            if inbound_changes:
                print(f"  Updated {len(inbound_changes)} file(s) with inbound link rewrites")

            # --- Step 6: Update site_plan.yaml ---
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

            # --- Step 7: Final safety verification ---
            final_english_text = new_english_index.read_text(encoding="utf-8")
            # Verify alias is present
            final_fm_m = _FM_RE.match(final_english_text)
            if final_fm_m:
                final_fm = yaml.safe_load(final_fm_m.group(2))
                if isinstance(final_fm, dict):
                    final_aliases = final_fm.get("aliases", [])
                    if old_url not in final_aliases:
                        raise RuntimeError(
                            f"SAFETY VIOLATION: alias {old_url} not found in {new_english_index} "
                            "after migration — aborting"
                        )
                    # Verify no slug: field
                    if "slug" in final_fm:
                        raise RuntimeError(
                            f"SAFETY VIOLATION: slug: field found in {new_english_index} — aborting"
                        )

            # Verify no locale file has aliases:
            for loc_file in new_folder.glob("index.*.md"):
                loc_text = loc_file.read_text(encoding="utf-8")
                if re.search(r"^\s*aliases\s*:", loc_text, re.MULTILINE):
                    raise RuntimeError(
                        f"SAFETY VIOLATION: locale file {loc_file} has aliases: after migration"
                    )

        else:
            # Dry-run: report what would happen
            print(f"  Would move: {old_folder}")
            print(f"  Would create: {new_folder}")
            for update in cand.get("source_file_updates", []):
                print(f"  Would update source_file in: {Path(update['file']).name}")

            # Simulate alias addition
            existing_aliases = fm_data.get("aliases", [])
            if not isinstance(existing_aliases, list):
                existing_aliases = [existing_aliases] if existing_aliases else []
            alias_already_present = old_url in existing_aliases
            result_entry["alias_update"] = {
                "file": str(english_index),
                "old_url": old_url,
                "added": not alias_already_present,
                "already_present": alias_already_present,
                "dry_run": True,
            }
            print(f"  Would add alias {old_url} to English index.md" if not alias_already_present
                  else f"  Alias {old_url} already present")

            # Simulate inbound link scan
            inbound_changes = _update_inbound_links(
                content_root=blog_root,
                family=family,
                platform=platform,
                old_slug=old_slug,
                new_slug=new_slug,
                dry_run=True,
            )
            result_entry["inbound_link_updates"] = inbound_changes
            if inbound_changes:
                print(f"  Would rewrite {len(inbound_changes)} file(s) with inbound links")

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

    # --- Step 8: Write manifests ---
    manifest = {
        "timestamp": timestamp,
        "mode": "dry-run" if dry_run else "applied",
        "renames": results,
        "skipped": skipped,
        "seo_note": (
            "Old URLs are preserved via aliases: in migrated English index.md files. "
            "Hugo build generates redirect HTML pages at old paths. "
            "enableRedirects: true in [a-zA-Z0-9.\-]+ config."
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
            "instructions": "Run these commands to undo the migration:",
            "rollback_commands": [],
            "undo_notes": [],
        }
        for r in results:
            rollback["rollback_commands"].append(
                f"git mv content/[a-zA-Z0-9.\-]+/{r['family']}/{r['platform']}/{r['new_folder_slug']} "
                f"content/[a-zA-Z0-9.\-]+/{r['family']}/{r['platform']}/{r['old_folder_slug']}"
            )
            if r.get("site_plan_changes"):
                rollback["rollback_commands"].append(
                    f"git checkout reports/plans/{r['family']}/{r['platform']}/site_plan.yaml"
                )
            # Alias rollback instruction
            if r.get("alias_update") and r["alias_update"].get("added"):
                new_index = (
                    f"content/[a-zA-Z0-9.\-]+/{r['family']}/{r['platform']}/"
                    f"{r['new_folder_slug']}/index.md"
                )
                old_url = r["alias_update"]["old_url"]
                rollback["undo_notes"].append(
                    f"undo_alias: Remove aliases: ['{old_url}'] from {new_index} "
                    f"OR: git checkout {new_index}"
                )
            # Inbound link rollback
            for link_change in r.get("inbound_link_updates", []):
                rollback["undo_notes"].append(
                    f"undo_inbound_links: git checkout {link_change['file']}"
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
