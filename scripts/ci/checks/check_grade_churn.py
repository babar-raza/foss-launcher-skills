#!/usr/bin/env python3
"""check_grade_churn.py — Block bulk grade-only frontmatter rewrites.

GUARD-01 (pre-commit) + GUARD-02 (CI) enforcement for the grading system
remediation plan.  Detects commits/PRs where many .md files have changes
confined to grade frontmatter fields with no body content changes.

Modes:
  --mode staged   Check staged files (pre-commit / S-76 commit skill)
  --mode pr       Check PR diff against base branch (CI)

Thresholds:
  --warn-threshold N   Warn if N+ grade-only files (default: 5)
  --block-threshold N  Block if N+ grade-only files (default: 20)

Override:
  If the commit message (--commit-msg) or PR body (--pr-body) contains
  the annotation 'BULK-GRADE-MIGRATION: approved by', the check passes
  regardless of file count.

Exit codes:
  0 = pass (below threshold or annotation present)
  1 = block (above block threshold, no annotation)
  2 = error (parse failure)

Reference: curried-pondering-music.md §16.5 GUARD-01, GUARD-02
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# Grade frontmatter field patterns — matches +/- diff lines for grade fields
_GRADE_FIELD_RE = re.compile(
    r"^[+-](?:grade|graded_at|graded_model_sha|graded_evaluators|"
    r"graded_logic_version|graded_content_hash|graded_evaluator_versions|"
    r"graded_enrichment_status|grade_final|grade_stale_reason|"
    r"grade_stale_targets|grade_reasons)(?::|[ \t])"
)

# Continuation lines for YAML lists/maps (indented with 2+ spaces under a grade field).
# Only match pure list items (lines starting with "  -") or indented scalar values that
# do NOT contain a colon (which would make them a new field assignment).
# This prevents false-positives when evidence.claims / evidence.apis lines change —
# those are indented but are NOT grade fields and should not be classified as grade-only.
_GRADE_CONTINUATION_RE = re.compile(r"^[+-]  (?:-|[^-\s][^:]*)$")

# The bulk migration annotation that overrides the check
_BULK_ANNOTATION_RE = re.compile(r"BULK-GRADE-MIGRATION:\s*approved by", re.IGNORECASE)


def _get_changed_md_files(*, mode: str, base_branch: str) -> list[str]:
    """Return list of .md files changed in the staged area or PR."""
    if mode == "staged":
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=M", "--", "content/**/*.md"],
            capture_output=True, text=True,
        )
    else:  # pr
        result = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=M",
             f"{base_branch}...HEAD", "--", "content/**/*.md"],
            capture_output=True, text=True,
        )
    if result.returncode != 0:
        return []
    return [f for f in result.stdout.strip().splitlines() if f.endswith(".md")]


def _is_grade_only_change(path: str, *, mode: str, base_branch: str) -> bool:
    """Return True if all diff lines for this file are grade frontmatter fields."""
    if mode == "staged":
        result = subprocess.run(
            ["git", "diff", "--cached", "--unified=0", "--", path],
            capture_output=True, text=True,
        )
    else:
        result = subprocess.run(
            ["git", "diff", "--unified=0", f"{base_branch}...HEAD", "--", path],
            capture_output=True, text=True,
        )
    if result.returncode != 0:
        return False

    content_lines = []
    for line in result.stdout.splitlines():
        # Skip unified diff headers
        if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
            continue
        if line.startswith("+") or line.startswith("-"):
            content_lines.append(line)

    if not content_lines:
        return False  # No diff — not grade-only

    for line in content_lines:
        if not _GRADE_FIELD_RE.match(line) and not _GRADE_CONTINUATION_RE.match(line):
            return False  # Non-grade line found — not grade-only

    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Block bulk grade-only frontmatter rewrites (GUARD-01/GUARD-02)."
    )
    parser.add_argument("--mode", choices=["staged", "pr"], default="staged")
    parser.add_argument("--base-branch", default="origin/main",
                        help="Base branch for PR mode (default: origin/main)")
    parser.add_argument("--warn-threshold", type=int, default=5)
    parser.add_argument("--block-threshold", type=int, default=20)
    parser.add_argument("--commit-msg", default="",
                        help="Commit message to check for bulk migration annotation")
    parser.add_argument("--pr-body", default="",
                        help="PR body to check for bulk migration annotation")
    args = parser.parse_args()

    # Check for override annotation
    combined_text = args.commit_msg + "\n" + args.pr_body
    if _BULK_ANNOTATION_RE.search(combined_text):
        print("PASS: BULK-GRADE-MIGRATION annotation found — grade churn check bypassed.")
        return 0

    # Get changed .md files
    changed_files = _get_changed_md_files(mode=args.mode, base_branch=args.base_branch)
    if not changed_files:
        print("PASS: No modified .md content files.")
        return 0

    # Classify each file
    grade_only_files = []
    for f in changed_files:
        if _is_grade_only_change(f, mode=args.mode, base_branch=args.base_branch):
            grade_only_files.append(f)

    count = len(grade_only_files)

    if count >= args.block_threshold:
        print(f"BLOCK: {count} .md files have grade-only frontmatter changes "
              f"(threshold: {args.block_threshold}).", file=sys.stderr)
        print("", file=sys.stderr)
        print("This looks like a bulk grade rewrite without body content changes.", file=sys.stderr)
        print("If this is intentional, add to the commit message:", file=sys.stderr)
        print("  BULK-GRADE-MIGRATION: approved by [name] on [date], reason: [trigger]", file=sys.stderr)
        print("", file=sys.stderr)
        print("Grade-only files:", file=sys.stderr)
        for f in grade_only_files[:10]:
            print(f"  {f}", file=sys.stderr)
        if count > 10:
            print(f"  ... and {count - 10} more", file=sys.stderr)
        return 1

    if count >= args.warn_threshold:
        print(f"WARN: {count} .md files have grade-only frontmatter changes "
              f"(warn threshold: {args.warn_threshold}).")
        for f in grade_only_files[:5]:
            print(f"  {f}")
        if count > 5:
            print(f"  ... and {count - 5} more")
        print("Consider whether body content changes should accompany these grade updates.")

    total_changed = len(changed_files)
    body_changed = total_changed - count
    print(f"PASS: {total_changed} .md files changed ({body_changed} with body changes, "
          f"{count} grade-only).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
