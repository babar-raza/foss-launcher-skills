# Adapted from aspose.org
#!/usr/bin/env python3
"""seed_grade_manifest.py — One-time seeding of grade_manifest.json from frontmatter.

ARCH-05: Reads operational grade fields from all graded .md files under
content/ and writes manifest entries so the skip-graded gate (ARCH-02)
can function without reading frontmatter.

Usage:
    .venv/Scripts/python scripts/pipeline/commands/migration/seed_grade_manifest.py [--dry-run]

After seeding, skip-graded gate uses manifest first (ARCH-02).  No .md files
are modified by this script — it is read-only for content files.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE.parent.parent))  # scripts/pipeline/  # scripts/pipeline/
    _LIB_DIR = str(Path(_HERE) / "lib") if isinstance(_HERE, str) else str(_HERE / "lib")
    if _LIB_DIR not in sys.path:
        sys.path.insert(0, _LIB_DIR)

from lib.grade_writer import read_grade, content_hash  # noqa: E402
from lib.grade_manifest import load_manifest, save_manifest  # noqa: E402
from core.markdown import _FRONTMATTER_WRITER_RE as _FM_RE  # noqa: E402


def _discover_graded_files() -> list[Path]:
    """Find all .md files under content/ that have a grade: field."""
    content_root = Path("content")
    if not content_root.exists():
        print(f"ERROR: {content_root} not found", file=sys.stderr)
        return []
    return sorted(content_root.rglob("*.md"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seed grade_manifest.json from existing frontmatter (ARCH-05)."
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Count graded files but do not write manifest")
    parser.add_argument("--manifest-path", default=None,
                        help="Override manifest output path")
    args = parser.parse_args()

    files = _discover_graded_files()
    print(f"Scanning {len(files)} .md files under content/...")

    manifest = load_manifest(args.manifest_path) if not args.dry_run else {}
    seeded = 0
    skipped_no_grade = 0
    errors = 0

    for fp in files:
        stored = read_grade(fp)
        if not stored or not stored.get("grade"):
            skipped_no_grade += 1
            continue

        # Read body and compute content hash
        try:
            text = fp.read_text(encoding="utf-8")
            fm_m = _FM_RE.match(text)
            body = text[fm_m.end():] if fm_m else text
            body_hash = content_hash(body)
        except (OSError, UnicodeDecodeError) as exc:
            print(f"  ERROR reading {fp}: {exc}", file=sys.stderr)
            errors += 1
            continue

        rel_path = str(fp).replace("\\", "/")

        if not args.dry_run:
            manifest[rel_path] = {
                "content_hash": body_hash,
                "grade": stored["grade"],
                "grade_reasons": stored.get("grade_reasons", []),
                "evaluator_versions": stored.get("evaluator_versions", {}),
                "model_sha": stored.get("model_sha", ""),
                "logic_version": stored.get("logic_version", ""),
                "enrichment_status": stored.get("enrichment_status") or "full",
                "graded_evaluators": stored.get("tier", "full"),
                "evaluated_at": "",  # Unknown from frontmatter; will update on next eval
            }
        seeded += 1

    print(f"\nResults:")
    print(f"  Graded files found: {seeded}")
    print(f"  Ungraded files:     {skipped_no_grade}")
    print(f"  Read errors:        {errors}")

    if args.dry_run:
        print(f"\n  DRY RUN — manifest not written")
        return 0

    save_manifest(manifest, args.manifest_path)
    print(f"  Manifest entries:   {len(manifest)}")
    print(f"  Written to:         {args.manifest_path or 'reports/grade_manifest.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())