# Adapted from aspose.org
"""CI helper: detect grade downgrades in modified content files.

Compares the grade on origin/main vs the working-tree version for each
modified file. Uses the no_downgrade_guard decision matrix.

EC-04 / C-17: Reads grade from the external manifest first (if available),
falling back to frontmatter on origin/main.  The manifest may have a more
current operational grade than stale frontmatter (due to WP-01 write policy).

Usage:
    python scripts/pipeline/commands/governance/check_grade_downgrade.py file1.md file2.md
    python scripts/pipeline/commands/governance/check_grade_downgrade.py --strict file1.md
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]  # commands/governance/ -> commands/ -> pipeline/
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from grade_writer import read_grade  # noqa: E402
# Inline LOCALE_RE (foss does not have content_discovery)
import re as _re_mod
LOCALE_RE = _re_mod.compile(r"\.(?:ar|bg|ca|cs|da|de|el|es|et|fa|fi|fr|he|hi|hr|hu|id|it|ja|ko|lt|lv|ms|nl|no|pl|pt|ro|ru|sk|sl|sr|sv|th|tr|uk|vi|zh)\.md$")
from no_downgrade_guard import _decision, DECISION_BLOCK, DECISION_WARN  # noqa: E402  # same directory

_MANIFEST_PATH = "reports/grade_manifest.json"


def _load_manifest_from_main() -> dict:
    """Load grade_manifest.json from origin/main (if it exists)."""
    try:
        content = subprocess.check_output(
            ["git", "show", f"origin/main:{_MANIFEST_PATH}"],
            stderr=subprocess.DEVNULL,
            encoding="utf-8",
        )
        return json.loads(content)
    except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError):
        return {}


def _load_manifest_from_disk() -> dict:
    """Load grade_manifest.json from working tree (fallback for local runs)."""
    p = Path(_MANIFEST_PATH)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _grade_from_manifest(filepath: str, manifest: dict) -> str | None:
    """Read grade from the manifest for a given filepath."""
    key = filepath.replace("\\", "/")
    entry = manifest.get(key)
    if entry and entry.get("grade"):
        return entry["grade"]
    return None


def _grade_from_main(filepath: str) -> str | None:
    """Read the grade from the origin/main version of a file."""
    try:
        content = subprocess.check_output(
            ["git", "show", f"origin/main:{filepath}"],
            stderr=subprocess.DEVNULL,
            encoding="utf-8",
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None  # New file or git not available

    # Write to temp file so read_grade can parse it
    with tempfile.NamedTemporaryFile(
        suffix=".md", mode="w", encoding="utf-8", delete=False
    ) as f:
        f.write(content)
        tmp = Path(f.name)
    try:
        result = read_grade(tmp)
        return result["grade"] if result else None
    finally:
        tmp.unlink(missing_ok=True)


def _is_english_content(path: Path) -> bool:
    return path.suffix == ".md" and not LOCALE_RE.search(path.name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_grade_downgrade",
        description="Detect grade downgrades in modified content files.",
    )
    parser.add_argument("files", nargs="+", help="Modified .md files to check")
    parser.add_argument("--strict", action="store_true",
                        help="WARNs also fail CI (not just BLOCKs)")
    parser.add_argument("--allow-regrade", action="store_true",
                        help="Allow downgrades if graded_model_sha changed")
    args = parser.parse_args(argv)

    # --allow-regrade: skip all downgrade checks (used for rubric/evaluator changes)
    if args.allow_regrade:
        total = len(args.files)
        print(f"Grade downgrade check skipped (--allow-regrade, {total} file(s)).")
        return 0

    # EC-04 / C-17: Load manifest — try origin/main first, fall back to disk
    manifest = _load_manifest_from_main() or _load_manifest_from_disk()
    manifest_hits = 0

    blocks = []
    warns = []

    for filepath in args.files:
        p = Path(filepath)
        if not _is_english_content(p):
            continue
        if not p.exists():
            continue

        # EC-04: Manifest-first grade lookup, frontmatter fallback
        old_grade = _grade_from_manifest(filepath, manifest)
        if old_grade:
            manifest_hits += 1
        else:
            old_grade = _grade_from_main(filepath)
        if old_grade is None:
            continue  # New file — no prior grade to protect

        new_result = read_grade(p)
        new_grade = new_result["grade"] if new_result else None
        if new_grade is None:
            # Grade was removed — treat as grade F proposed
            new_grade = "F"

        decision = _decision(old_grade, new_grade, target_exists=True)
        if decision == DECISION_BLOCK:
            blocks.append((filepath, old_grade, new_grade))
        elif decision == DECISION_WARN:
            warns.append((filepath, old_grade, new_grade))

    if blocks:
        print(f"BLOCKED: {len(blocks)} grade downgrade(s):", file=sys.stderr)
        for f, old, new in blocks:
            print(f"  {f}: {old} → {new}", file=sys.stderr)

    if warns:
        print(f"WARN: {len(warns)} grade degradation(s):", file=sys.stderr)
        for f, old, new in warns:
            print(f"  {f}: {old} → {new}", file=sys.stderr)

    if blocks:
        return 2
    if args.strict and warns:
        return 1

    total = len(args.files)
    source = f"{manifest_hits} from manifest" if manifest_hits else "frontmatter only"
    print(f"Grade downgrade check passed ({total} file(s) checked, {source}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())