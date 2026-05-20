# Adapted from aspose.org
"""CI helper: detect grade frontmatter anomalies in content files.

Checks for:
- Duplicate graded_evaluators: keys
- Duplicate top-level grade: keys
- Non-consecutive orphaned grade keys (separated by non-grade keys)
- Invalid grade values (not A/B/C/D/F)
- Incomplete grade blocks (grade: present but graded_at: missing)

Usage:
    python scripts/pipeline/commands/governance/check_grade_integrity.py --files f1.md f2.md
    python scripts/pipeline/commands/governance/check_grade_integrity.py          # scan all content/**/*.md
    python scripts/pipeline/commands/governance/check_grade_integrity.py --json   # machine-readable
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent.parent.parent  # commands/governance/ -> commands/ -> pipeline/ -> scripts/ -> repo

_GRADE_KEYS = {"grade", "graded_at", "graded_model_sha", "graded_evaluators"}
_VALID_GRADES = {"A", "B", "C", "D", "F"}
_FM_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)


def _extract_frontmatter(text: str) -> str | None:
    """Return raw frontmatter text between --- delimiters, or None."""
    m = _FM_RE.match(text)
    return m.group(1) if m else None


def _check_file(path: Path) -> list[dict]:
    """Return anomaly dicts for a single markdown file."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    fm = _extract_frontmatter(text)
    if fm is None:
        return []

    issues: list[dict] = []
    lines = fm.split("\n")

    # Parse top-level keys and their positions
    top_keys: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        if ":" in line and not line.startswith((" ", "\t", "#")):
            key = line.split(":")[0].strip()
            top_keys.append((i, key))

    grade_positions = [(i, k) for i, k in top_keys if k in _GRADE_KEYS]

    # Check 1: Duplicate grade-related keys
    counts = Counter(k for _, k in grade_positions)
    for key, n in counts.items():
        if n > 1:
            issues.append({"file": str(path), "check": "duplicate_key",
                           "detail": f"'{key}' appears {n} times"})

    # Check 2: Non-consecutive grade keys (separated by non-grade keys)
    for j in range(len(grade_positions) - 1):
        pos1, k1 = grade_positions[j]
        pos2, k2 = grade_positions[j + 1]
        gap = [k for idx, k in top_keys if pos1 < idx < pos2 and k not in _GRADE_KEYS]
        if gap:
            issues.append({"file": str(path), "check": "non_consecutive",
                           "detail": f"'{k1}' and '{k2}' separated by: {', '.join(gap)}"})

    # Check 3: Invalid grade values
    for idx, key in grade_positions:
        if key == "grade":
            val = lines[idx].split(":", 1)[1].strip().strip("'\"")
            # Strip inline YAML comments (e.g. grade: A # written by evaluator)
            if " #" in val:
                val = val[:val.index(" #")].strip().strip("'\"")
            if val and val not in _VALID_GRADES:
                issues.append({"file": str(path), "check": "invalid_grade",
                               "detail": f"grade value '{val}' not in {_VALID_GRADES}"})

    # Check 4: Incomplete grade block (grade without graded_at or graded_evaluators)
    present = {k for _, k in grade_positions}
    if "grade" in present:
        for required in ("graded_at", "graded_evaluators"):
            if required not in present:
                issues.append({"file": str(path), "check": "incomplete_block",
                               "detail": f"'grade' present but '{required}' missing"})

    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check grade frontmatter integrity.")
    parser.add_argument("--files", nargs="+", metavar="FILE", help="Specific files to check")
    parser.add_argument("--json", action="store_true", help="Machine-readable JSON output")
    args = parser.parse_args(argv)

    if args.files:
        targets = [Path(f) for f in args.files if Path(f).suffix == ".md"]
    else:
        targets = sorted((_REPO_ROOT / "content").rglob("*.md"))

    all_issues: list[dict] = []
    for p in targets:
        if p.is_file():
            all_issues.extend(_check_file(p))

    if args.json:
        print(json.dumps({"files_checked": len(targets), "anomaly_count": len(all_issues),
                           "issues": all_issues}, indent=2))
    elif all_issues:
        affected = sorted({i["file"] for i in all_issues})
        print(f"GRADE INTEGRITY: {len(all_issues)} anomaly(s) across {len(affected)} file(s) "
              f"({len(targets)} checked)", file=sys.stderr)
        for issue in all_issues[:30]:
            print(f"  [{issue['check']}] {issue['file']}: {issue['detail']}", file=sys.stderr)
        if len(all_issues) > 30:
            print(f"  ... and {len(all_issues) - 30} more", file=sys.stderr)
    else:
        print(f"GRADE INTEGRITY: PASS ({len(targets)} files checked)", file=sys.stderr)

    return 1 if all_issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
