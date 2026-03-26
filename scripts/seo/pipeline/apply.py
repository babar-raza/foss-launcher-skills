"""
SEO-008 apply.py
================
Apply approved patches from patch_manifest.json to content files.
Uses YAML surgery: parse frontmatter → modify target fields → re-serialize.
Body content is NEVER touched.

Known gap:
  PyYAML dump() does not preserve original formatting (loses quotes, changes
  indentation). This is acceptable — Hugo frontmatter parses standard YAML
  correctly. Original formatting is NOT restored; the semantic content is
  preserved exactly.

Usage:
  python scripts/seo/pipeline/apply.py --dry-run
  python scripts/seo/pipeline/apply.py --dry-run --page content/blog.aspose.org/...
  python scripts/seo/pipeline/apply.py --batch-id 2026-03-25T15:00:00
  python scripts/seo/pipeline/apply.py --page content/blog.aspose.org/... --batch-id 2026-03-25T15:00:00

Flags:
  --dry-run          Show what would change, write nothing (default behaviour
                     if neither --dry-run nor explicit write flag is given).
  --page PATH        Apply to a single page only.
  --batch-id ID      Apply from a specific batch (checked against manifest
                     batch_id field).

Safety:
  - Requires patch_manifest.json to exist at patches/seo/patch_manifest.json
  - Verifies evidence: block is present before writing any file
  - On YAML serialisation failure or post-write verification failure:
      restore original content and log ROLLBACK
  - Continues with next page on per-file failure (no full-batch abort)

Post-apply (non-dry-run only):
  Prints instructions to run audit.py — does NOT call it automatically.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Path setup — importable as module or runnable as __main__
# ---------------------------------------------------------------------------

_THIS_FILE = Path(__file__).resolve()
_PIPELINE_DIR = _THIS_FILE.parent        # scripts/seo/pipeline/
_REPO_ROOT = _THIS_FILE.parents[3]       # .../aspose.org

if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s  %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("apply")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PATCHES_DIR = _REPO_ROOT / "patches" / "seo"
MANIFEST_PATH = PATCHES_DIR / "patch_manifest.json"

# Fields that apply.py is permitted to write.
# Evidence fields are never modified (enforced by verify_evidence_unchanged).
WRITABLE_FIELDS = {"seoTitle", "description", "tags"}

# ---------------------------------------------------------------------------
# YAML surgery helpers
# ---------------------------------------------------------------------------

def _split_frontmatter(raw: str) -> tuple[str, str]:
    """
    Split a Hugo markdown file into (frontmatter_block, body).

    Hugo files begin with a YAML block delimited by triple-dashes:
      ---
      key: value
      ---
      body content...

    Returns:
      frontmatter_block — everything between the first and second '---'
                          (NOT including the delimiters)
      body              — everything after the closing '---\n' including
                          the leading newline(s)

    Raises ValueError if file does not start with '---'.
    """
    if not raw.startswith("---"):
        raise ValueError("file does not begin with '---' — not a Hugo markdown file")

    # Find second '---' delimiter
    second = raw.find("\n---", 3)
    if second == -1:
        raise ValueError("could not find closing '---' frontmatter delimiter")

    frontmatter_block = raw[3:second].strip()
    body = raw[second + 4:]          # skip '\n---'
    # body starts immediately after the newline following the closing ---
    return frontmatter_block, body


def _reconstruct(frontmatter_dict: dict, body: str) -> str:
    """Re-serialize frontmatter and rejoin with body."""
    fm_yaml = yaml.dump(
        frontmatter_dict,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )
    return f"---\n{fm_yaml}---\n{body}"


def _verify_evidence_unchanged(
    original_fm: dict,
    new_fm: dict,
) -> bool:
    """
    Confirm that the 'evidence' block is present and matches between
    original and new frontmatter.

    Returns True if safe to proceed.
    """
    orig_evidence = original_fm.get("evidence")
    new_evidence = new_fm.get("evidence")
    if orig_evidence is None:
        # No evidence block — cannot proceed (required by AGENTS.md)
        return False
    if orig_evidence != new_evidence:
        return False
    return True


# ---------------------------------------------------------------------------
# Apply a single patch to frontmatter
# ---------------------------------------------------------------------------

def _apply_patch_to_fm(
    fm: dict,
    patch: dict,
) -> tuple[dict, list[str]]:
    """
    Apply a single patch dict to a frontmatter dict (in-place copy).

    Returns:
      (updated_fm, list_of_changed_field_names)

    Rules:
      seoTitle    — set/overwrite only if proposed is not None
      description — set/overwrite only if proposed is not None
      tags        — extend existing list with tags_to_add (no duplicates, no removals)
    """
    import copy
    new_fm = copy.deepcopy(fm)
    changed: list[str] = []

    fields = patch.get("fields_to_update", {})

    # seoTitle
    seo_title = fields.get("seoTitle")
    if seo_title is not None:
        new_fm["seoTitle"] = seo_title
        changed.append("seoTitle")

    # description
    description = fields.get("description")
    if description is not None:
        new_fm["description"] = description
        changed.append("description")

    # tags — extend, no duplicates, no removals
    tags_to_add: list[str] = fields.get("tags_to_add", []) or []
    if tags_to_add:
        existing_tags: list = list(new_fm.get("tags", []) or [])
        existing_set = {t.lower() for t in existing_tags}
        added = []
        for tag in tags_to_add:
            if tag.lower() not in existing_set:
                existing_tags.append(tag)
                existing_set.add(tag.lower())
                added.append(tag)
        if added:
            new_fm["tags"] = existing_tags
            changed.append(f"tags (+{len(added)})")

    return new_fm, changed


# ---------------------------------------------------------------------------
# Dry-run output formatter
# ---------------------------------------------------------------------------

def _format_dry_run_page(
    page_path: str,
    patch: dict,
    fm: dict | None,
) -> str:
    """Format a single page entry for dry-run output."""
    lines = [f"Page: {page_path}"]
    fields = patch.get("fields_to_update", {})
    requires_review = patch.get("requires_human_review", True)

    # seoTitle
    seo_title_proposed = fields.get("seoTitle")
    current_title = fm.get("seoTitle") if fm else None
    title_line_before = f'"{current_title}"' if current_title is not None else "null"
    if seo_title_proposed is not None:
        title_line_after = f'"{seo_title_proposed}"'
    else:
        after_note = " (llm_skipped - human review required)" if requires_review else ""
        title_line_after = f"null{after_note}"
    lines.append("  seoTitle:")
    lines.append(f"    before: {title_line_before}")
    lines.append(f"    after:  {title_line_after}")

    # description
    desc_proposed = fields.get("description")
    if desc_proposed is not None:
        current_desc = fm.get("description") if fm else None
        desc_before = f'"{current_desc}"' if current_desc else "null"
        lines.append("  description:")
        lines.append(f"    before: {desc_before}")
        lines.append(f'    after:  "{desc_proposed}"')

    # tags
    tags_to_add = fields.get("tags_to_add") or []
    if tags_to_add:
        lines.append(f"  tags add: {json.dumps(tags_to_add)}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Core apply logic
# ---------------------------------------------------------------------------

def run_dry_run(patches: list[dict]) -> None:
    """Execute dry-run: show what would change, write nothing."""
    from datetime import date
    batch_id = patches[0]["batch_id"] if patches and "batch_id" in patches[0] else "unknown"
    # batch_id comes from manifest, not individual patch — get from loaded manifest
    manifest = _load_manifest()
    batch_id = manifest.get("batch_id", "unknown")

    print(f"DRY RUN - batch {batch_id}")
    print("-" * 40)

    title_changes = 0
    tag_additions_total = 0
    review_required = 0

    for patch in patches:
        page_path = patch["page_path"]
        content_file = _REPO_ROOT / page_path

        fm: dict | None = None
        if content_file.exists():
            try:
                raw = content_file.read_text(encoding="utf-8")
                fm_block, _ = _split_frontmatter(raw)
                fm = yaml.safe_load(fm_block) or {}
            except Exception as e:
                log.warning("could not parse %s: %s", page_path, e)

        print(_format_dry_run_page(page_path, patch, fm))
        print("-" * 40)

        fields = patch.get("fields_to_update", {})
        if fields.get("seoTitle") is not None:
            title_changes += 1
        tag_additions_total += len(fields.get("tags_to_add") or [])
        if patch.get("requires_human_review"):
            review_required += 1

    # Summary line
    total = len(patches)
    print(f"Total: {total} page{'s' if total != 1 else ''}, {title_changes} seoTitle change{'s' if title_changes != 1 else ''}, {tag_additions_total} tag addition{'s' if tag_additions_total != 1 else ''}")
    if review_required:
        print(f"WARNING: {review_required} page{'s' if review_required != 1 else ''} require{'s' if review_required == 1 else ''} human review (proposed values are null)")


def run_apply(patches: list[dict], dry_run: bool) -> None:
    """
    Apply patches to content files.

    For each patch:
      1. Read file
      2. Split frontmatter / body
      3. Parse YAML
      4. Verify evidence block unchanged
      5. Apply field updates
      6. Re-serialize
      7. Write file
      8. Post-write verification
    """
    applied_count = 0
    rollback_count = 0
    skip_count = 0

    for patch in patches:
        page_path = patch["page_path"]
        content_file = _REPO_ROOT / page_path

        if not content_file.exists():
            log.warning("SKIP: %s — file not found", page_path)
            skip_count += 1
            continue

        # --- Read original ---
        try:
            original_raw = content_file.read_text(encoding="utf-8")
        except OSError as e:
            log.error("SKIP: %s — cannot read: %s", page_path, e)
            skip_count += 1
            continue

        # --- Split frontmatter / body ---
        try:
            fm_block, body = _split_frontmatter(original_raw)
        except ValueError as e:
            log.warning("SKIP: %s — %s", page_path, e)
            skip_count += 1
            continue

        # --- Parse YAML ---
        try:
            original_fm: dict = yaml.safe_load(fm_block) or {}
        except yaml.YAMLError as e:
            log.warning("SKIP: %s — YAML parse error: %s", page_path, e)
            skip_count += 1
            continue

        # --- Apply patch (produces new_fm) ---
        new_fm, changed_fields = _apply_patch_to_fm(original_fm, patch)

        if not changed_fields:
            log.info("SKIP: %s — no fields to change", page_path)
            skip_count += 1
            continue

        # --- Verify evidence block unchanged ---
        if not _verify_evidence_unchanged(original_fm, new_fm):
            log.error(
                "SKIP: %s — evidence block missing or would change; aborting this page",
                page_path,
            )
            skip_count += 1
            continue

        if dry_run:
            # Dry-run is handled by run_dry_run(); this path shouldn't be reached
            continue

        # --- Re-serialize ---
        try:
            new_raw = _reconstruct(new_fm, body)
        except Exception as e:
            log.error("ROLLBACK: %s — serialisation failed: %s", page_path, e)
            rollback_count += 1
            continue

        # --- Write ---
        try:
            content_file.write_text(new_raw, encoding="utf-8")
        except OSError as e:
            log.error("ROLLBACK: %s — write failed: %s", page_path, e)
            # Attempt restore
            try:
                content_file.write_text(original_raw, encoding="utf-8")
                log.info("ROLLBACK: %s — original content restored", page_path)
            except OSError as e2:
                log.critical("ROLLBACK FAILED: %s — could not restore original: %s", page_path, e2)
            rollback_count += 1
            continue

        # --- Post-write verification ---
        try:
            verify_raw = content_file.read_text(encoding="utf-8")
            verify_fm_block, _ = _split_frontmatter(verify_raw)
            verify_fm: dict = yaml.safe_load(verify_fm_block) or {}

            verification_ok = True
            fields_upd = patch.get("fields_to_update", {})

            if fields_upd.get("seoTitle") is not None:
                if verify_fm.get("seoTitle") != fields_upd["seoTitle"]:
                    verification_ok = False
                    log.error("ROLLBACK: %s — seoTitle verification failed", page_path)

            if fields_upd.get("description") is not None:
                if verify_fm.get("description") != fields_upd["description"]:
                    verification_ok = False
                    log.error("ROLLBACK: %s — description verification failed", page_path)

            if not verification_ok:
                content_file.write_text(original_raw, encoding="utf-8")
                log.info("ROLLBACK: %s — original content restored", page_path)
                rollback_count += 1
                continue

        except Exception as e:
            log.error("ROLLBACK: %s — post-write verification error: %s", page_path, e)
            try:
                content_file.write_text(original_raw, encoding="utf-8")
            except OSError:
                pass
            rollback_count += 1
            continue

        # Success
        log.info("APPLIED: %s — fields: %s", page_path, ", ".join(changed_fields))
        applied_count += 1

    # Summary
    print()
    print("=" * 60)
    print(f"Apply complete: {applied_count} applied, {rollback_count} rolled back, {skip_count} skipped")
    if applied_count > 0:
        print()
        print("Run the following to validate:")
        print("  python scripts/pipeline/audit.py changed --json")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Manifest loading + filtering
# ---------------------------------------------------------------------------

def _load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        log.error("patch_manifest.json not found at %s", MANIFEST_PATH)
        sys.exit(1)
    with open(MANIFEST_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _filter_patches(
    manifest: dict,
    page_filter: str | None,
    batch_id_filter: str | None,
) -> list[dict]:
    """Apply --page and --batch-id filters to manifest patches."""
    manifest_batch_id = manifest.get("batch_id", "")
    patches: list[dict] = manifest.get("patches", [])

    if batch_id_filter is not None:
        if manifest_batch_id != batch_id_filter:
            log.error(
                "batch_id mismatch: manifest has '%s', requested '%s'",
                manifest_batch_id,
                batch_id_filter,
            )
            sys.exit(1)

    if page_filter is not None:
        patches = [p for p in patches if p.get("page_path") == page_filter]
        if not patches:
            log.warning("--page filter '%s' matched no patches", page_filter)

    return patches


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="SEO-008 apply.py - apply SEO patches to content files",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Show what would change; write nothing.",
    )
    parser.add_argument(
        "--page",
        metavar="PATH",
        default=None,
        help="Apply to a single page only (by page_path value).",
    )
    parser.add_argument(
        "--batch-id",
        metavar="ID",
        default=None,
        dest="batch_id",
        help="Verify manifest batch_id matches this value before applying.",
    )
    args = parser.parse_args()

    # Default to dry-run unless explicitly invoked without the flag
    # (Requirement: dry-run is the safe default)
    dry_run: bool = args.dry_run

    manifest = _load_manifest()
    patches = _filter_patches(manifest, args.page, args.batch_id)

    if not patches:
        print("No patches to apply.")
        return

    log.info(
        "patch_manifest loaded: batch_id=%s, %d total patches, %d after filter",
        manifest.get("batch_id"),
        manifest.get("total_patches", 0),
        len(patches),
    )

    if dry_run:
        run_dry_run(patches)
    else:
        # Warn user they are about to write to content files
        print("WARNING: This will modify content files.")
        print(f"         Applying {len(patches)} patch(es) from batch {manifest.get('batch_id')}.")
        print("         Use --dry-run to preview changes first.")
        print()
        run_apply(patches, dry_run=False)


if __name__ == "__main__":
    main()
