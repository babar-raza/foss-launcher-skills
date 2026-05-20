# Adapted from aspose.org
"""CI helper: verify that modified content files have grades in frontmatter.

Usage:
    python scripts/pipeline/commands/governance/check_grade_presence.py --scope modified file1.md file2.md
    python scripts/pipeline/commands/governance/check_grade_presence.py --scope all
    python scripts/pipeline/commands/governance/check_grade_presence.py --scope modified --allow-new file1.md
"""
import argparse
import sys
from pathlib import Path

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]  # commands/governance/ -> commands/ -> pipeline/
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from grade_writer import read_grade  # noqa: E402
# Inline LOCALE_RE (foss does not have content_discovery)
import re as _re_mod  # noqa: E402
LOCALE_RE = _re_mod.compile(r"\.(?:ar|bg|ca|cs|da|de|el|es|et|fa|fi|fr|he|hi|hr|hu|id|it|ja|ko|lt|lv|ms|nl|no|pl|pt|ro|ru|sk|sl|sr|sv|th|tr|uk|vi|zh)\.md$")


def _is_english_content(path: Path) -> bool:
    """Return True if the file is English content (not a translation)."""
    return path.suffix == ".md" and not LOCALE_RE.search(path.name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_grade_presence",
        description="Verify that content files have grades in frontmatter.",
    )
    parser.add_argument("files", nargs="*", help="Files to check (for --scope modified)")
    parser.add_argument("--scope", choices=["modified", "all"], default="modified",
                        help="Check only modified files or all discoverable files")
    parser.add_argument("--allow-new", action="store_true",
                        help="Allow newly created files to be ungraded (transitional)")
    args = parser.parse_args(argv)

    if args.scope == "all":
        # foss stub: content discovery not available
        raise ImportError(
            "content_discovery not available in foss. "
            "Use --scope modified with explicit file list instead of --scope all."
        )
        files = []
        for family, platform in sorted(discover_products()):
            files.extend(discover_content(family, platform))
    else:
        files = [Path(f) for f in args.files if _is_english_content(Path(f))]

    missing = []
    for f in files:
        p = Path(f)
        if not p.exists():
            continue
        if not _is_english_content(p):
            continue
        result = read_grade(p)
        if not result:
            missing.append(str(p))

    if missing:
        print(f"GRADE PRESENCE: {len(missing)} file(s) missing grades:", file=sys.stderr)
        for m in missing[:20]:
            print(f"  {m}", file=sys.stderr)
        if len(missing) > 20:
            print(f"  ... and {len(missing) - 20} more", file=sys.stderr)

        if args.allow_new:
            print("(--allow-new active, exiting with warning only)", file=sys.stderr)
            return 0
        return 1

    print(f"All {len(files)} file(s) have grades.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())