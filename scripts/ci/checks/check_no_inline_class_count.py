#!/usr/bin/env python3
"""check_no_inline_class_count.py — Flag new inline class-counting formulas.

MT067-2026-09-10, TC-13. The class-count consistency defect (see
docs/reference/knowledge-stats.md) existed for months because nothing enforced
PIPELINE.md's own "3+ scripts need the same function -> extract to lib/" rule: four
scripts independently reimplemented "how many classes does this product have," under
the same field name, with different definitions, and nothing noticed. lib/class_stats.py
now provides the single shared implementation -- this check is what keeps a fifth
inline formula from being added by someone who doesn't know it exists.

Heuristic, not a parser: matches source lines resembling the two formulas that caused
the original defect (a function/non-function kind filter, or a name-based dedup set)
outside lib/class_stats.py itself and its test. False positives are expected and
acceptable -- this runs advisory-only (see --advisory below) for that reason.

Usage:
    python scripts/ci/checks/check_no_inline_class_count.py
    python scripts/ci/checks/check_no_inline_class_count.py --advisory

Exit codes:
    0 — no suspicious formulas found (or --advisory was passed)
    1 — suspicious formula(s) found and --advisory was not passed
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PIPELINE_ROOT = REPO_ROOT / "scripts" / "pipeline"

# Files allowed to contain these patterns — the shared implementation and its test.
_ALLOWLIST = {
    PIPELINE_ROOT / "lib" / "class_stats.py",
    PIPELINE_ROOT / "tests" / "test_class_stats.py",
}

# Signature substrings of the original 4+ independently-reimplemented formulas
# (see docs/reference/knowledge-stats.md for the full history of what each one was).
_SUSPICIOUS_PATTERNS = [
    re.compile(r'!=\s*["\']function["\']'),
    re.compile(r'\bdef\s+_?is_public_api_entry\s*\('),
]


def check() -> list[str]:
    """Return list of "path:line: snippet" strings for suspicious lines."""
    violations = []
    for path in sorted(PIPELINE_ROOT.rglob("*.py")):
        if path in _ALLOWLIST:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for pattern in _SUSPICIOUS_PATTERNS:
                if pattern.search(line):
                    rel = path.relative_to(REPO_ROOT)
                    violations.append(f"{rel}:{lineno}: {line.strip()}")
                    break
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--advisory", action="store_true",
                        help="Report issues but always exit 0 (WARN-mode rollout)")
    args = parser.parse_args()

    violations = check()
    if violations:
        label = "WARN" if args.advisory else "FAIL"
        print(f"{label}: {len(violations)} line(s) resemble an inline class-counting "
              f"formula outside lib/class_stats.py:", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        print("\nIf this is really a new class-count computation, use "
              "lib.class_stats.compute_class_stats() instead of reimplementing it. "
              "If this is a false positive (e.g. an unrelated function/non-function "
              "filter), no action needed -- this check is advisory.", file=sys.stderr)
        if args.advisory:
            print("\n(advisory mode — exit 0)")
            return 0
        return 1

    print("OK: no inline class-counting formulas found outside lib/class_stats.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
