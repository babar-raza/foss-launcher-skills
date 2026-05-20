# Adapted from aspose.org
#!/usr/bin/env python3
"""migrate_strip_operational_frontmatter.py — MIG-01: Strip operational grade fields.

Removes operational grade fields from .md frontmatter, leaving only the
three canonical grade fields: grade, grade_reasons, graded_content_hash.

All operational data is already preserved in reports/grade_manifest.json.

Usage:
    python migrate_strip_operational_frontmatter.py --inventory
    python migrate_strip_operational_frontmatter.py --dry-run --sample 10
    python migrate_strip_operational_frontmatter.py --apply --batch-size 500

Modes:
    --inventory         Count graded files, enumerate operational fields each has
    --dry-run (default) Show what would change, no disk writes
    --apply             Write stripped frontmatter to disk

Options:
    --sample N            Process only N files (for testing)
    --batch-size N        Files per checkpoint batch (default 500)
    --checkpoint-file P   Path to checkpoint JSON (default reports/mig01_checkpoint.json)
    --content-dir P       Root content directory (default content/)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

import yaml

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE.parent.parent))  # scripts/pipeline/  # scripts/pipeline/

from core.markdown import _FRONTMATTER_WRITER_RE  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Fields that stay in .md frontmatter after migration
CANONICAL_GRADE_FIELDS = frozenset({"grade", "grade_reasons", "graded_content_hash"})

# Fields to remove (operational — now in grade_manifest.json only)
OPERATIONAL_GRADE_FIELDS = frozenset({
    "graded_at",
    "graded_model_sha",
    "graded_evaluators",
    "graded_logic_version",
    "graded_evaluator_versions",
    "graded_enrichment_status",
    "grade_final",
    "grade_stale_reason",
    "grade_stale_targets",
})

ALL_GRADE_FIELDS = CANONICAL_GRADE_FIELDS | OPERATIONAL_GRADE_FIELDS

# Repo root — two levels up from scripts/pipeline/
_REPO_ROOT = _HERE.parents[3]  # repo root

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def find_graded_files(content_dir: Path) -> list[Path]:
    """Return all .md files under content_dir that have a grade: field."""
    graded = []
    for md in sorted(content_dir.rglob("*.md")):
        try:
            text = md.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if re.search(r"^grade:\s", text, re.MULTILINE):
            graded.append(md)
    return graded


def parse_yaml_frontmatter(text: str) -> tuple[dict | None, str, str, str]:
    """Parse YAML frontmatter, returning (fm_dict, open_fence, close_fence, body).

    Returns (None, ...) if no frontmatter found.
    """
    m = _FRONTMATTER_WRITER_RE.match(text)
    if not m:
        return None, "", "", text
    open_fence = m.group(1)
    fm_raw = m.group(2)
    close_fence = m.group(3)
    body = text[m.end():]
    try:
        fm_dict = yaml.safe_load(fm_raw) or {}
    except yaml.YAMLError:
        return None, open_fence, close_fence, body
    return fm_dict, open_fence, close_fence, body


def detect_operational_fields(fm_dict: dict) -> set[str]:
    """Return the set of operational grade fields present in frontmatter."""
    return {k for k in fm_dict if k in OPERATIONAL_GRADE_FIELDS}


def detect_canonical_grade_fields(fm_dict: dict) -> set[str]:
    """Return the set of canonical grade fields present in frontmatter."""
    return {k for k in fm_dict if k in CANONICAL_GRADE_FIELDS}


def strip_operational_fields(text: str) -> tuple[str, set[str], bool]:
    """Strip operational grade fields from frontmatter YAML.

    Uses regex-based line removal to preserve exact formatting of non-grade
    fields (no round-trip through yaml.dump which would reformat everything).

    Returns (new_text, removed_fields, changed).
    """
    m = _FRONTMATTER_WRITER_RE.match(text)
    if not m:
        return text, set(), False

    open_fence = m.group(1)
    fm_raw = m.group(2)
    close_fence = m.group(3)
    body = text[m.end():]

    removed = set()
    new_lines = []
    lines = fm_raw.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        # Check if this line starts an operational field
        field_match = re.match(r"^(\w+):", line)
        if field_match:
            field_name = field_match.group(1)
            if field_name in OPERATIONAL_GRADE_FIELDS:
                removed.add(field_name)
                i += 1
                # Skip continuation lines (indented, part of YAML block value)
                while i < len(lines) and lines[i] and re.match(r"^  ", lines[i]):
                    i += 1
                continue
        new_lines.append(line)
        i += 1

    if not removed:
        return text, set(), False

    new_fm = "\n".join(new_lines)
    # Clean up any double blank lines that result from removal
    while "\n\n\n" in new_fm:
        new_fm = new_fm.replace("\n\n\n", "\n\n")

    new_text = f"{open_fence}{new_fm}{close_fence}{body}"
    return new_text, removed, True


def validate_stripped(original_text: str, new_text: str) -> list[str]:
    """Validate that stripping was correct. Returns list of error strings."""
    errors = []

    # Parse both versions
    orig_fm, _, _, orig_body = parse_yaml_frontmatter(original_text)
    new_fm, _, _, new_body = parse_yaml_frontmatter(new_text)

    if orig_fm is None:
        errors.append("original has no frontmatter")
        return errors
    if new_fm is None:
        errors.append("new text has no frontmatter")
        return errors

    # Check body unchanged
    if orig_body != new_body:
        errors.append("body content changed")

    # Check no operational fields remain
    remaining_ops = {k for k in new_fm if k in OPERATIONAL_GRADE_FIELDS}
    if remaining_ops:
        errors.append(f"operational fields still present: {remaining_ops}")

    # Check canonical fields preserved
    orig_canonical = {k: v for k, v in orig_fm.items() if k in CANONICAL_GRADE_FIELDS}
    new_canonical = {k: v for k, v in new_fm.items() if k in CANONICAL_GRADE_FIELDS}
    if orig_canonical != new_canonical:
        errors.append(f"canonical fields changed: orig={orig_canonical}, new={new_canonical}")

    # Check non-grade fields preserved
    orig_non_grade = {k: v for k, v in orig_fm.items() if k not in ALL_GRADE_FIELDS}
    new_non_grade = {k: v for k, v in new_fm.items() if k not in ALL_GRADE_FIELDS}
    if orig_non_grade != new_non_grade:
        errors.append("non-grade fields changed")

    # Count grade fields in result — should be exactly the canonical ones that were present
    grade_fields_in_new = {k for k in new_fm if k in ALL_GRADE_FIELDS}
    expected = orig_canonical.keys()
    if grade_fields_in_new != set(expected):
        errors.append(
            f"expected grade fields {set(expected)}, got {grade_fields_in_new}"
        )

    return errors


# ---------------------------------------------------------------------------
# Checkpoint management
# ---------------------------------------------------------------------------


def load_checkpoint(path: Path) -> dict:
    """Load checkpoint file, returning dict with completed_files set."""
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            data["completed_files"] = set(data.get("completed_files", []))
            return data
        except (json.JSONDecodeError, KeyError):
            pass
    return {"completed_files": set(), "batch_index": 0}


def save_checkpoint(path: Path, data: dict) -> None:
    """Save checkpoint to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    serializable = {
        "completed_files": sorted(data["completed_files"]),
        "batch_index": data.get("batch_index", 0),
    }
    path.write_text(json.dumps(serializable, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------


def preflight_check(manifest_path: Path, graded_files: list[Path]) -> list[str]:
    """Verify manifest exists and has entries for all graded pages.

    Returns list of error strings (empty = pass).
    """
    errors = []
    if not manifest_path.exists():
        errors.append(f"manifest not found: {manifest_path}")
        return errors

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        errors.append(f"cannot read manifest: {exc}")
        return errors

    if not isinstance(manifest, dict):
        # Manifest might be a list of entries; check structure
        if isinstance(manifest, list):
            manifest_keys = {entry.get("path", "") for entry in manifest if isinstance(entry, dict)}
        else:
            errors.append("manifest is not a dict or list")
            return errors
    else:
        manifest_keys = set(manifest.keys())

    # We only warn about missing entries, don't block the entire migration
    # since the manifest format may vary
    return errors


# ---------------------------------------------------------------------------
# Inventory mode (MD-01)
# ---------------------------------------------------------------------------


def run_inventory(content_dir: Path) -> dict:
    """Produce MD-01 frontmatter inventory report."""
    graded_files = find_graded_files(content_dir)
    field_counts: Counter = Counter()
    files_by_field: dict[str, int] = {}
    canonical_counts: Counter = Counter()

    for fp in graded_files:
        try:
            text = fp.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        fm, _, _, _ = parse_yaml_frontmatter(text)
        if fm is None:
            continue
        ops = detect_operational_fields(fm)
        can = detect_canonical_grade_fields(fm)
        for f in ops:
            field_counts[f] += 1
        for f in can:
            canonical_counts[f] += 1

    report = {
        "total_graded_files": len(graded_files),
        "operational_field_counts": dict(field_counts.most_common()),
        "canonical_field_counts": dict(canonical_counts.most_common()),
    }

    print("\n=== MD-01 Frontmatter Inventory ===")
    print(f"Total graded files: {report['total_graded_files']}")
    print("\nOperational fields (to be removed):")
    for field, count in field_counts.most_common():
        print(f"  {field}: {count} files")
    print("\nCanonical fields (to be preserved):")
    for field, count in canonical_counts.most_common():
        print(f"  {field}: {count} files")
    if not field_counts:
        print("  (no operational fields found — migration may already be complete)")
    print()

    return report


# ---------------------------------------------------------------------------
# Migration mode
# ---------------------------------------------------------------------------


def run_migration(
    content_dir: Path,
    *,
    apply: bool = False,
    sample: int | None = None,
    batch_size: int = 500,
    checkpoint_file: Path | None = None,
    manifest_path: Path | None = None,
) -> dict:
    """Run the operational field stripping migration.

    Returns summary dict with counts.
    """
    if manifest_path is None:
        manifest_path = _REPO_ROOT / "reports" / "grade_manifest.json"
    if checkpoint_file is None:
        checkpoint_file = _REPO_ROOT / "reports" / "mig01_checkpoint.json"

    mode = "APPLY" if apply else "DRY-RUN"
    print(f"\n=== MIG-01 Operational Field Stripping ({mode}) ===")

    # Find graded files
    print("Scanning for graded files...")
    graded_files = find_graded_files(content_dir)
    print(f"Found {len(graded_files)} graded files")

    # Pre-flight: verify manifest
    pf_errors = preflight_check(manifest_path, graded_files)
    if pf_errors:
        print("PRE-FLIGHT FAILED:")
        for e in pf_errors:
            print(f"  - {e}")
        return {"status": "preflight_failed", "errors": pf_errors}

    # Sample mode
    if sample is not None:
        graded_files = graded_files[:sample]
        print(f"Sample mode: processing {len(graded_files)} files")

    # Load checkpoint
    checkpoint = load_checkpoint(checkpoint_file)
    completed = checkpoint["completed_files"]
    skipped_checkpoint = 0

    # Counters
    processed = 0
    stripped = 0
    already_clean = 0
    errors_list = []
    all_removed_fields: Counter = Counter()

    t0 = time.time()

    for batch_start in range(0, len(graded_files), batch_size):
        batch = graded_files[batch_start:batch_start + batch_size]

        for fp in batch:
            fp_str = str(fp)

            # Skip if already done (checkpoint resume)
            if fp_str in completed:
                skipped_checkpoint += 1
                continue

            try:
                text = fp.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                errors_list.append(f"{fp}: read error: {exc}")
                continue

            new_text, removed, changed = strip_operational_fields(text)

            if not changed:
                already_clean += 1
                completed.add(fp_str)
                processed += 1
                continue

            # Validate
            val_errors = validate_stripped(text, new_text)
            if val_errors:
                errors_list.append(f"{fp}: validation errors: {val_errors}")
                continue

            for f in removed:
                all_removed_fields[f] += 1

            if apply:
                try:
                    fp.write_text(new_text, encoding="utf-8")
                except OSError as exc:
                    errors_list.append(f"{fp}: write error: {exc}")
                    continue
                print(f"  STRIPPED {fp} (removed: {', '.join(sorted(removed))})")
            else:
                rel = fp.relative_to(_REPO_ROOT) if fp.is_relative_to(_REPO_ROOT) else fp
                print(f"  WOULD STRIP {rel} (remove: {', '.join(sorted(removed))})")

            stripped += 1
            completed.add(fp_str)
            processed += 1

        # Save checkpoint after each batch (only in apply mode)
        if apply:
            checkpoint["completed_files"] = completed
            checkpoint["batch_index"] = batch_start // batch_size + 1
            save_checkpoint(checkpoint_file, checkpoint)

    elapsed = time.time() - t0

    summary = {
        "status": "ok",
        "mode": mode,
        "total_graded": len(graded_files),
        "processed": processed,
        "stripped": stripped,
        "already_clean": already_clean,
        "skipped_checkpoint": skipped_checkpoint,
        "errors": len(errors_list),
        "fields_removed": dict(all_removed_fields.most_common()),
        "elapsed_seconds": round(elapsed, 2),
    }

    print(f"\n--- Summary ---")
    print(f"Mode: {mode}")
    print(f"Total graded files: {summary['total_graded']}")
    print(f"Processed: {summary['processed']}")
    print(f"Stripped: {summary['stripped']}")
    print(f"Already clean: {summary['already_clean']}")
    print(f"Skipped (checkpoint): {summary['skipped_checkpoint']}")
    print(f"Errors: {summary['errors']}")
    if all_removed_fields:
        print(f"Fields removed:")
        for field, count in all_removed_fields.most_common():
            print(f"  {field}: {count}")
    if errors_list:
        print(f"\nError details:")
        for e in errors_list[:20]:
            print(f"  {e}")
        if len(errors_list) > 20:
            print(f"  ... and {len(errors_list) - 20} more")
    print(f"Elapsed: {summary['elapsed_seconds']}s\n")

    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="MIG-01: Strip operational grade fields from .md frontmatter"
    )
    parser.add_argument(
        "--inventory", action="store_true",
        help="MD-01 inventory mode: count graded files and enumerate fields",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Write changes to disk (default is dry-run)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", default=True,
        help="Show what would change without writing (default)",
    )
    parser.add_argument(
        "--sample", type=int, default=None,
        help="Process only N files (for testing)",
    )
    parser.add_argument(
        "--batch-size", type=int, default=500,
        help="Files per checkpoint batch (default 500)",
    )
    parser.add_argument(
        "--checkpoint-file", type=str, default=None,
        help="Path to checkpoint JSON file",
    )
    parser.add_argument(
        "--content-dir", type=str, default=None,
        help="Root content directory (default: content/)",
    )

    args = parser.parse_args()

    content_dir = Path(args.content_dir) if args.content_dir else _REPO_ROOT / "content"
    if not content_dir.is_dir():
        print(f"ERROR: content directory not found: {content_dir}", file=sys.stderr)
        return 1

    if args.inventory:
        run_inventory(content_dir)
        return 0

    checkpoint_file = (
        Path(args.checkpoint_file) if args.checkpoint_file
        else _REPO_ROOT / "reports" / "mig01_checkpoint.json"
    )

    result = run_migration(
        content_dir,
        apply=args.apply,
        sample=args.sample,
        batch_size=args.batch_size,
        checkpoint_file=checkpoint_file,
    )

    if result.get("status") == "preflight_failed":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
