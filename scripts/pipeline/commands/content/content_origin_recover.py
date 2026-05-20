#!/usr/bin/env python3
"""content_origin_recover.py — Infer content_origin for files with unknown origin.

Two confidence rules (both require grade A or B):
  Rule A: evidence.claims is non-empty AND grade A/B → infer skill-generated
          (strong signal: claims were matched to knowledge model)
  Rule B: evidence.apis is non-empty AND grade A/B → infer skill-generated
          (weaker signal: API tokens verified; covers prose-only pages
           where claims are [] but apis list is populated)

Only files where content_origin is 'unknown' are considered.

Usage:
    python content_origin_recover.py [--apply] [--path PATH]

    --dry-run  (default) Print inferences without writing
    --apply    Write changes to disk
    --path     Directory to scan (default: content/)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE.parent.parent))  # scripts/pipeline/
    _LIB_DIR = str(Path(_HERE) / "lib") if isinstance(_HERE, str) else str(_HERE / "lib")
    if _LIB_DIR not in sys.path:
        sys.path.insert(0, _LIB_DIR)

from provenance import read_provenance, write_provenance  # noqa: E402
from core.markdown import _FRONTMATTER_WRITER_RE as _FRONTMATTER_RE  # noqa: E402

# ---------------------------------------------------------------------------
# Frontmatter parser (partial — reads evidence + grade without round-tripping)
# ---------------------------------------------------------------------------


_HIGH_GRADE = frozenset({"A", "B"})


def _read_frontmatter_fields(filepath: Path) -> dict[str, Any] | None:
    """Parse full frontmatter YAML and return the dict, or None on failure."""
    try:
        text = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    fm = _FRONTMATTER_RE.match(text)
    if not fm:
        return None

    try:
        parsed = yaml.safe_load(fm.group(2))
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    return None


def _qualifies_rule_a(fields: dict[str, Any]) -> bool:
    """Return True when Rule A conditions are both met.

    Rule A: evidence.claims is non-empty AND grade is A or B.
    """
    grade = fields.get("grade", "")
    if grade not in _HIGH_GRADE:
        return False

    evidence = fields.get("evidence")
    if not isinstance(evidence, dict):
        return False

    claims = evidence.get("claims")
    if not claims:
        return False

    # claims must be a non-empty list (or truthy iterable)
    if isinstance(claims, list):
        return len(claims) > 0
    # Scalar truthy value (unusual but defensive)
    return bool(claims)


def _qualifies_rule_b(fields: dict[str, Any]) -> bool:
    """Return True when Rule B conditions are both met.

    Rule B: evidence.apis is non-empty AND grade is A or B.
    Covers prose-only pages where claims are empty but API tokens were verified.
    """
    grade = fields.get("grade", "")
    if grade not in _HIGH_GRADE:
        return False

    evidence = fields.get("evidence")
    if not isinstance(evidence, dict):
        return False

    apis = evidence.get("apis")
    if not apis:
        return False

    if isinstance(apis, list):
        return len(apis) > 0
    return bool(apis)


# Keep backward-compatible alias for external callers / tests
_qualifies_for_skill_generated = _qualifies_rule_a


def process_file(filepath: Path, apply: bool) -> str:
    """Process a single file.

    Returns one of:
      'not-unknown'      content_origin is not 'unknown'
      'no-provenance'    no provenance block
      'no-fields'        frontmatter could not be read
      'no-qualify'       content_origin is unknown but neither Rule A nor Rule B met
      'inferred'         content_origin changed (or would be changed)
      'error'            write failed
    """
    # Read provenance block
    prov = read_provenance(filepath)
    if prov is None:
        return "no-provenance"

    # Skip locale/translated files — they have translation_origin, not content_origin
    if "translation_origin" in prov:
        return "not-unknown"

    content_origin = prov.get("content_origin", "unknown")
    if content_origin != "unknown":
        return "not-unknown"

    # Read full frontmatter to check evidence.claims/apis + grade
    fields = _read_frontmatter_fields(filepath)
    if fields is None:
        return "no-fields"

    if _qualifies_rule_a(fields):
        rule_label = "A"
    elif _qualifies_rule_b(fields):
        rule_label = "B"
    else:
        return "no-qualify"

    # Rule fires
    if apply:
        prov["content_origin"] = "skill-generated"
        try:
            ok = write_provenance(filepath, prov)
            if not ok:
                print(f"  ERROR writing provenance to {filepath}")
                return "error"
        except Exception as exc:
            print(f"  ERROR writing {filepath}: {exc}")
            return "error"
        print(f"  UPDATED  {filepath}  content_origin=skill-generated (rule={rule_label})")
    else:
        print(f"  WOULD UPDATE  {filepath}  content_origin: unknown -> skill-generated (rule={rule_label})")

    return "inferred"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Recover content_origin for files where it is unknown."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Write changes to disk (default: dry-run)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print inferences without writing (default behaviour)",
    )
    parser.add_argument(
        "--path",
        default=None,
        help="Directory to scan (default: content/ relative to repo root)",
    )
    args = parser.parse_args()

    apply = args.apply

    # Resolve scan root
    if args.path:
        scan_root = Path(args.path).resolve()
    else:
        scan_root = (_HERE / ".." / ".." / ".." / ".." / "content").resolve()

    if not scan_root.exists():
        print(f"ERROR: scan path does not exist: {scan_root}", file=sys.stderr)
        sys.exit(1)

    mode_label = "APPLY" if apply else "DRY-RUN"
    print(f"content_origin_recover — mode={mode_label}  root={scan_root}")
    print()

    total = 0
    total_unknown = 0
    qualified = 0
    changed = 0
    errors = 0

    for md_file in sorted(scan_root.rglob("*.md")):
        total += 1
        result = process_file(md_file, apply=apply)

        if result in ("not-unknown", "no-provenance", "no-fields"):
            continue

        if result == "no-qualify":
            total_unknown += 1
        elif result == "inferred":
            total_unknown += 1
            qualified += 1
            changed += 1
        elif result == "error":
            total_unknown += 1
            qualified += 1
            errors += 1

    print()
    print("=" * 60)
    print(f"Files scanned         : {total}")
    print(f"Files with unknown    : {total_unknown}")
    print(f"Qualifying (Rule A)   : {qualified}")
    if apply:
        print(f"Updated               : {changed - errors}")
    else:
        print(f"Would update          : {qualified}  (run --apply to write)")
    print(f"Errors                : {errors}")
    print("=" * 60)
    print()
    print("Rule A: evidence.claims non-empty AND grade in {A, B} -> skill-generated")
    print("Rule B: evidence.apis non-empty AND grade in {A, B} -> skill-generated (prose-only)")

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()