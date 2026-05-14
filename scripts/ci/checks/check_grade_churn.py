#!/usr/bin/env python3
"""Block bulk grade-only frontmatter rewrites."""
from __future__ import annotations

import argparse
import re
import subprocess
import sys

_GRADE_FIELD_RE = re.compile(
    r"^[+-](?:grade|graded_at|graded_model_sha|graded_evaluators|"
    r"graded_logic_version|graded_content_hash|graded_evaluator_versions|"
    r"graded_enrichment_status|grade_final|grade_stale_reason|"
    r"grade_stale_targets|grade_reasons)(?::|[ \t])"
)
_GRADE_CONTINUATION_RE = re.compile(r"^[+-]  (?:-|[^-\s][^:]*)$")
_BULK_ANNOTATION_RE = re.compile(r"BULK-GRADE-MIGRATION:\s*approved by", re.IGNORECASE)


def _get_changed_md_files(*, mode: str, base_branch: str) -> list[str]:
    if mode == "staged":
        cmd = ["git", "diff", "--cached", "--name-only", "--diff-filter=M", "--", "content/**/*.md"]
    else:
        cmd = ["git", "diff", "--name-only", "--diff-filter=M", f"{base_branch}...HEAD", "--", "content/**/*.md"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line.endswith(".md")]


def _is_grade_only_change(path: str, *, mode: str, base_branch: str) -> bool:
    if mode == "staged":
        cmd = ["git", "diff", "--cached", "--unified=0", "--", path]
    else:
        cmd = ["git", "diff", "--unified=0", f"{base_branch}...HEAD", "--", path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return False
    content_lines: list[str] = []
    for line in result.stdout.splitlines():
        if line.startswith(("+++", "---", "@@")):
            continue
        if line.startswith(("+", "-")):
            content_lines.append(line)
    if not content_lines:
        return False
    return all(_GRADE_FIELD_RE.match(line) or _GRADE_CONTINUATION_RE.match(line) for line in content_lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("staged", "pr"), default="staged")
    parser.add_argument("--base-branch", default="origin/main")
    parser.add_argument("--warn-threshold", type=int, default=5)
    parser.add_argument("--block-threshold", type=int, default=20)
    parser.add_argument("--commit-msg", default="")
    parser.add_argument("--pr-body", default="")
    args = parser.parse_args(argv)

    if _BULK_ANNOTATION_RE.search(args.commit_msg + "\n" + args.pr_body):
        print("PASS: BULK-GRADE-MIGRATION annotation found - grade churn check bypassed.")
        return 0

    changed = _get_changed_md_files(mode=args.mode, base_branch=args.base_branch)
    if not changed:
        print("PASS: No modified .md content files.")
        return 0
    grade_only = [path for path in changed if _is_grade_only_change(path, mode=args.mode, base_branch=args.base_branch)]
    count = len(grade_only)
    if count >= args.block_threshold:
        print(f"BLOCK: {count} .md files have grade-only frontmatter changes.", file=sys.stderr)
        for path in grade_only[:10]:
            print(f"  {path}", file=sys.stderr)
        return 1
    if count >= args.warn_threshold:
        print(f"WARN: {count} .md files have grade-only frontmatter changes.")
    print(f"PASS: {len(changed)} .md files changed ({len(changed) - count} with body changes, {count} grade-only).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
