"""
SEO-008 apply.py
================
Apply approved patches from patch_manifest.json to content files.
Uses ruamel.yaml round-trip YAML surgery: parse frontmatter (preserving
comments/quote-style/key-order) -> modify target fields only -> re-serialize.
Body content is NEVER touched.

Governance gates (SEO-APPLY-HARDEN, closing the confirmed bypasses from the
2026-03-27 incident audit):
  1. requires_human_review must be explicitly False -- a patch missing this
     field, or with it True/absent, is REJECTED, not silently written.
  2. auto_updatable:false targets are never written (provenance.is_auto_updatable).
  3. Every write is checked against no_downgrade_guard.compare_content() before
     landing -- BLOCK rejects the write, WARN logs and proceeds.
  4. WRITABLE_FIELDS is site-scoped: {description, keywords} everywhere except
     blog.aspose.org, which also gets seoTitle (the only theme that renders it,
     via SEO-BLOG-WIRE-OG-TWITTER's Open Graph/Twitter Card wiring). tags_to_add
     is retired -- no theme renders apply.py's old tags field as SEO signal.
  5. A single run is capped at MAX_BATCH_SIZE files, so a bad batch is always
     revertable with one git revert without touching unrelated commits.

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
import copy
import io
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
_MAIN_PIPELINE = _REPO_ROOT / "scripts" / "pipeline"

if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_MAIN_PIPELINE) not in sys.path:
    sys.path.insert(0, str(_MAIN_PIPELINE))

try:
    from ruamel.yaml import YAML
    from ruamel.yaml.error import YAMLError
except ImportError:
    print(
        "ERROR: ruamel.yaml is required for format-preserving writes. "
        "Install with: pip install ruamel.yaml",
        file=sys.stderr,
    )
    sys.exit(1)

from lib.provenance import is_auto_updatable  # noqa: E402
from commands.governance.no_downgrade_guard import (  # noqa: E402
    compare_content,
    DECISION_BLOCK,
    DECISION_WARN,
)

try:
    from scripts.seo.pipeline import autonomy_state  # type: ignore  # noqa: E402
except ImportError as exc:
    sys.exit(
        f"apply.py: cannot import autonomy_state.py — {exc}\n"
        "Run from repo root: python scripts/seo/pipeline/apply.py"
    )

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

# A single apply run is capped so a bad batch is always revertable with one
# git revert without touching unrelated commits (Finding #9 / SEO-APPLY-HARDEN).
MAX_BATCH_SIZE = 50

# Round-trip YAML instance: preserves comments, quote style, key order, and
# block/flow style for every untouched key. allow_unicode + explicit utf-8
# file I/O everywhere is required for non-ASCII values (em-dashes, curly
# quotes, non-English text) to round-trip byte-for-byte -- verified directly
# against this repo's own content during SEO-APPLY-HARDEN's implementation.
_yaml = YAML()
_yaml.preserve_quotes = True
_yaml.allow_unicode = True
_yaml.width = 4096  # avoid unwanted line-wrapping of long description/title values


def _writable_fields_for(page_path: str) -> set[str]:
    """Fields apply.py may write, scoped by site.

    seoTitle renders on zero themes except blog.aspose.org (confirmed via an
    exhaustive repo-wide theme grep during this mission) -- blog's head.html
    sources its Open Graph/Twitter Card title from seoTitle with a .Title
    fallback. Every other site gets {description, keywords} only. tags_to_add
    is retired entirely: no theme renders apply.py's old tags field as SEO
    signal, and the field was never load-bearing for ranking.
    """
    normalized = page_path.replace("\\", "/")
    if "content/blog.aspose.org/" in normalized:
        return {"description", "keywords", "seoTitle"}
    return {"description", "keywords"}


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


def _parse_frontmatter(fm_block: str) -> Any:
    """Parse a frontmatter block with the round-trip YAML loader."""
    return _yaml.load(fm_block)


def _reconstruct(frontmatter_dict: Any, body: str) -> str:
    """Re-serialize frontmatter (round-trip preserving) and rejoin with body."""
    buf = io.StringIO()
    _yaml.dump(frontmatter_dict, buf)
    fm_yaml = buf.getvalue()
    return f"---\n{fm_yaml}---\n{body}"


def _verify_evidence_unchanged(
    original_fm: Any,
    new_fm: Any,
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


def _verify_only_intended_keys_changed(
    original_fm: Any,
    new_fm: Any,
    intended_fields: list[str],
) -> list[str]:
    """Return any top-level key that changed but was NOT in intended_fields.

    Defense-in-depth on top of ruamel's round-trip preservation and
    _apply_patch_to_fm's targeted-assignment-only design: an empty return
    list is required before any write proceeds.
    """
    unexpected: list[str] = []
    all_keys = set(original_fm.keys()) | set(new_fm.keys())
    for key in all_keys:
        if key in intended_fields:
            continue
        if original_fm.get(key) != new_fm.get(key):
            unexpected.append(key)
    return unexpected


# ---------------------------------------------------------------------------
# Apply a single patch to frontmatter
# ---------------------------------------------------------------------------

def _apply_patch_to_fm(
    fm: Any,
    patch: dict,
    page_path: str,
) -> tuple[Any, list[str], list[str]]:
    """
    Apply a single patch dict to a frontmatter mapping (in-place copy).

    Returns:
      (updated_fm, changed_field_names, rejected_field_names)

    Only fields in _writable_fields_for(page_path) are ever written; anything
    else present in fields_to_update is rejected (logged, never applied) —
    this is the WRITABLE_FIELDS enforcement point (Finding #16).
    """
    new_fm = copy.deepcopy(fm)
    changed: list[str] = []
    rejected: list[str] = []
    writable = _writable_fields_for(page_path)

    fields = patch.get("fields_to_update", {})

    for field_name in ("seoTitle", "description", "keywords"):
        if field_name not in fields:
            continue
        value = fields.get(field_name)
        if value is None:
            continue
        if field_name not in writable:
            rejected.append(field_name)
            continue
        new_fm[field_name] = value
        changed.append(field_name)

    # tags_to_add is retired (Finding #16) — no theme renders it as SEO signal.
    if fields.get("tags_to_add"):
        rejected.append("tags_to_add")

    return new_fm, changed, rejected


# ---------------------------------------------------------------------------
# Dry-run output formatter
# ---------------------------------------------------------------------------

def _format_dry_run_page(
    page_path: str,
    patch: dict,
    fm: Any | None,
) -> str:
    """Format a single page entry for dry-run output."""
    lines = [f"Page: {page_path}"]
    fields = patch.get("fields_to_update", {})
    requires_review = patch.get("requires_human_review", True)
    writable = _writable_fields_for(page_path)

    if requires_review is not False:
        lines.append("  ** WOULD BE REJECTED: requires_human_review is not explicitly False **")

    # seoTitle
    if "seoTitle" not in writable and fields.get("seoTitle") is not None:
        lines.append("  seoTitle: ** WOULD BE REJECTED — not a writable field on this site **")
    else:
        seo_title_proposed = fields.get("seoTitle")
        current_title = fm.get("seoTitle") if fm else None
        title_line_before = f'"{current_title}"' if current_title is not None else "null"
        if seo_title_proposed is not None:
            title_line_after = f'"{seo_title_proposed}"'
        else:
            after_note = " (llm_skipped - human review required)" if requires_review else ""
            title_line_after = f"null{after_note}"
        if seo_title_proposed is not None or current_title is not None:
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

    # keywords
    keywords_proposed = fields.get("keywords")
    if keywords_proposed is not None:
        current_keywords = fm.get("keywords") if fm else None
        lines.append("  keywords:")
        lines.append(f"    before: {json.dumps(list(current_keywords) if current_keywords else [])}")
        lines.append(f"    after:  {json.dumps(list(keywords_proposed))}")

    # retired field
    if fields.get("tags_to_add"):
        lines.append("  tags_to_add: ** RETIRED FIELD — no longer writable, will be rejected **")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Core apply logic
# ---------------------------------------------------------------------------

def run_dry_run(patches: list[dict]) -> None:
    """Execute dry-run: show what would change, write nothing."""
    manifest = _load_manifest()
    batch_id = manifest.get("batch_id", "unknown")

    print(f"DRY RUN - batch {batch_id}")
    print("-" * 40)

    title_changes = 0
    keyword_changes = 0
    review_required = 0
    would_reject = 0

    for patch in patches:
        page_path = patch["page_path"]
        content_file = _REPO_ROOT / page_path

        fm: Any | None = None
        if content_file.exists():
            try:
                raw = content_file.read_text(encoding="utf-8")
                fm_block, _ = _split_frontmatter(raw)
                fm = _parse_frontmatter(fm_block) or {}
            except Exception as e:
                log.warning("could not parse %s: %s", page_path, e)

        print(_format_dry_run_page(page_path, patch, fm))
        print("-" * 40)

        fields = patch.get("fields_to_update", {})
        writable = _writable_fields_for(page_path)
        if fields.get("seoTitle") is not None and "seoTitle" in writable:
            title_changes += 1
        if fields.get("keywords") is not None:
            keyword_changes += 1
        if patch.get("requires_human_review") is not False:
            review_required += 1
            would_reject += 1

    total = len(patches)
    print(
        f"Total: {total} page{'s' if total != 1 else ''}, "
        f"{title_changes} seoTitle change{'s' if title_changes != 1 else ''}, "
        f"{keyword_changes} keywords change{'s' if keyword_changes != 1 else ''}"
    )
    if review_required:
        print(
            f"WARNING: {review_required} page{'s' if review_required != 1 else ''} "
            f"would be REJECTED — requires_human_review is not explicitly False"
        )


def run_apply(patches: list[dict], dry_run: bool) -> None:
    """
    Apply patches to content files.

    For each patch:
      1. Governance gate: requires_human_review must be explicitly False
      2. Governance gate: auto_updatable (skip if false)
      3. Read file, split frontmatter/body, parse YAML (round-trip)
      4. Apply field updates (writable-fields-scoped)
      5. Verify evidence block unchanged; verify only intended keys changed
      6. Re-serialize (round-trip preserving)
      7. Governance gate: no_downgrade_guard.compare_content (BLOCK rejects)
      8. Write file
      9. Post-write verification
    """
    applied_count = 0
    rollback_count = 0
    skip_count = 0
    rejected_governance_count = 0

    for patch in patches:
        page_path = patch["page_path"]
        content_file = _REPO_ROOT / page_path

        # --- Governance gate 1: requires_human_review ---
        if patch.get("requires_human_review") is not False:
            log.error(
                "REJECT: %s — requires_human_review is not explicitly False; "
                "independent-agent/human sign-off required before this patch can be applied",
                page_path,
            )
            rejected_governance_count += 1
            continue

        if not content_file.exists():
            log.warning("SKIP: %s — file not found", page_path)
            skip_count += 1
            continue

        # --- Governance gate 2: auto_updatable ---
        if not is_auto_updatable(content_file):
            log.warning(
                "SKIP: %s — auto_updatable:false (manually curated); queued for "
                "manual/S-116 review, never auto-written",
                page_path,
            )
            skip_count += 1
            continue

        # --- Governance gate 2.5: autonomy state (Contract I / Contract J
        # invariant 11 "autonomy_state_eligible_or_dry_run") ---
        # dry_run is never gated here (run_dry_run() is a separate code path
        # that never calls run_apply(); Contract J explicitly permits
        # --dry-run regardless of state) -- only the real-write path checks.
        if not dry_run:
            family = autonomy_state.family_from_page_path(page_path)
            if family is None or not autonomy_state.is_autonomously_eligible(
                family, "title_description_writes"
            ):
                status = (
                    "no family resolved for this path"
                    if family is None
                    else autonomy_state.get_status(family, "title_description_writes")
                )
                log.warning(
                    "SKIP: %s — autonomy state for title_description_writes is not "
                    "AUTONOMOUSLY_ELIGIBLE (%s); a family not yet cleared for this "
                    "mechanism is never auto-written",
                    page_path, status,
                )
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

        # --- Parse YAML (round-trip) ---
        try:
            original_fm: Any = _parse_frontmatter(fm_block)
            if original_fm is None:
                original_fm = _yaml.map()  # type: ignore[attr-defined]
        except YAMLError as e:
            log.warning("SKIP: %s — YAML parse error: %s", page_path, e)
            skip_count += 1
            continue

        # --- Apply patch (produces new_fm), enforcing writable-fields ---
        new_fm, changed_fields, rejected_fields = _apply_patch_to_fm(original_fm, patch, page_path)

        if rejected_fields:
            log.warning(
                "%s — field(s) rejected (not writable on this site or retired): %s",
                page_path, ", ".join(rejected_fields),
            )

        if not changed_fields:
            log.info("SKIP: %s — no writable fields to change", page_path)
            skip_count += 1
            continue

        # --- Verify evidence block unchanged ---
        # Products and reference _index.md pages are metadata pages without
        # evidence blocks — only require evidence for blog/docs/kb content pages.
        page_path_str = str(page_path)
        is_metadata_page = (
            "products.aspose.org" in page_path_str
            or "reference.aspose.org" in page_path_str
        ) and page_path_str.endswith("_index.md")
        if not is_metadata_page and not _verify_evidence_unchanged(original_fm, new_fm):
            log.error(
                "SKIP: %s — evidence block missing or would change; aborting this page",
                page_path,
            )
            skip_count += 1
            continue

        # --- Verify only intended keys changed (defense in depth) ---
        unexpected = _verify_only_intended_keys_changed(original_fm, new_fm, changed_fields)
        if unexpected:
            log.error(
                "SKIP: %s — unexpected key(s) would change: %s (only %s were intended)",
                page_path, unexpected, changed_fields,
            )
            skip_count += 1
            continue

        if dry_run:
            # Dry-run is handled by run_dry_run(); this path shouldn't be reached
            continue

        # --- Re-serialize (round-trip preserving) ---
        try:
            new_raw = _reconstruct(new_fm, body)
        except Exception as e:
            log.error("ROLLBACK: %s — serialisation failed: %s", page_path, e)
            rollback_count += 1
            continue

        # --- Governance gate 3: no_downgrade_guard ---
        try:
            guard_result = compare_content(content_file, new_raw)
        except Exception as e:
            log.error("SKIP: %s — no_downgrade_guard check could not run: %s", page_path, e)
            skip_count += 1
            continue

        if guard_result["decision"] == DECISION_BLOCK:
            log.error(
                "REJECT: %s — no_downgrade_guard BLOCK: %s",
                page_path, guard_result["reason"],
            )
            rejected_governance_count += 1
            continue
        if guard_result["decision"] == DECISION_WARN:
            log.warning(
                "%s — no_downgrade_guard WARN: %s (proceeding)",
                page_path, guard_result["reason"],
            )

        # --- Write ---
        try:
            content_file.write_text(new_raw, encoding="utf-8")
        except OSError as e:
            log.error("ROLLBACK: %s — write failed: %s", page_path, e)
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
            verify_fm: Any = _parse_frontmatter(verify_fm_block) or {}

            verification_ok = True
            fields_upd = patch.get("fields_to_update", {})
            writable = _writable_fields_for(page_path)

            if "seoTitle" in writable and fields_upd.get("seoTitle") is not None:
                if verify_fm.get("seoTitle") != fields_upd["seoTitle"]:
                    verification_ok = False
                    log.error("ROLLBACK: %s — seoTitle verification failed", page_path)

            if fields_upd.get("description") is not None:
                if verify_fm.get("description") != fields_upd["description"]:
                    verification_ok = False
                    log.error("ROLLBACK: %s — description verification failed", page_path)

            if fields_upd.get("keywords") is not None:
                if list(verify_fm.get("keywords") or []) != list(fields_upd["keywords"]):
                    verification_ok = False
                    log.error("ROLLBACK: %s — keywords verification failed", page_path)

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
    print(
        f"Apply complete: {applied_count} applied, {rollback_count} rolled back, "
        f"{skip_count} skipped, {rejected_governance_count} rejected (governance)"
    )
    if applied_count > 0:
        print()
        print("Run the following to validate:")
        print("  python scripts/pipeline/commands/content/audit.py changed --json")
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

    if not dry_run and len(patches) > MAX_BATCH_SIZE:
        log.error(
            "REFUSING: %d patches exceeds the %d-file safety cap for a single apply "
            "run (Finding #9 — a bad batch must always be revertable with one git "
            "revert). Use --page or --batch-id to scope a smaller batch.",
            len(patches), MAX_BATCH_SIZE,
        )
        sys.exit(1)

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
