#!/usr/bin/env python3
"""check_evidence_churn.py — Block bulk evidence-only frontmatter rewrites.

Sibling check to check_grade_churn.py, for the `evidence:` frontmatter block
instead of grade fields. Detects commits/PRs where many .md files have changes
confined to the `evidence:` block (model_sha/model_version/claims/apis/
formats/sections re-stamp) with no body content change and no change to any
non-grade top-level frontmatter field. A co-occurring change to the
`grade`/`graded_*`/`grade_reasons` family does NOT disqualify a file from this
classification — those fields are derived from evidence + body content, and
re-grading is a routine, expected side effect of an evidence re-stamp, not an
independent editorial change (2026-07-29, HARDEN-EC-01: found live on a
208-file 3d/java evidence re-stamp where `grade_reasons` wording also shifted,
which silently evaded this guard under the pre-fix all-other-keys-identical
rule even though the body was byte-identical).

Root incident this guards against: commit 643c02f7b8 (TC-SFH-007) re-ran
`attach_evidence.py --force` across 845 pdf/net pages after a
0.1.0-alpha -> 26.6.0 knowledge model jump, re-stamping `evidence.model_sha`
and `evidence.model_version` with zero body changes and zero reconciliation
via S-20 (page-update). `stale_detect`/`EG_STALE` only compare model_sha, so
the re-stamp "cleared" the staleness signal without addressing its cause.
This check catches the commit-shape of that incident directly: N+ files
where the entire diff is confined to `evidence:`.

Unlike grade fields (a fixed set of flat scalar keys), `evidence:` is a
nested structure (scalar fields, list fields, and a `sections:` list of
dicts). Rather than enumerate every nested field with per-line regexes, this
check parses old/new frontmatter as YAML and compares top-level keys plus
body text directly — robust to the variable shape of `sections:` and to
future evidence sub-fields without needing regex maintenance.

Modes:
  --mode staged   Check staged files (pre-commit / S-76 commit skill)
  --mode pr       Check PR diff against base branch (CI)

Thresholds:
  --warn-threshold N   Warn if N+ evidence-only files (default: 5)
  --block-threshold N  Block if N+ evidence-only files (default: 20)

Override:
  The commit message (--commit-msg) or PR body (--pr-body) must contain the
  annotation 'EVIDENCE-RESTAMP: approved by ..., run=<path/to/manifest.json>'
  citing a refresh_run.py manifest that has actually reached at least
  VALIDATING. Hardened 2026-08-22 (mission-plan-the-end-to-end-vast-hejlsberg.md
  Task 22, closes G14): the original bypass accepted ANY text matching
  'EVIDENCE-RESTAMP: approved by', with zero verification that the claimed
  justification was true — a free-text excuse, not evidence. An annotation
  present but missing a run= citation, or citing a path that does not exist
  or whose manifest never reached VALIDATING, is now treated exactly like no
  annotation at all (falls through to the normal warn/block threshold).

Exit codes:
  0 = pass (below threshold, or annotation present with a verified run citation)
  1 = block (above block threshold, no verified annotation)
  2 = error (parse failure)
"""
from __future__ import annotations

import argparse
import re
import json
import subprocess
import sys
from pathlib import Path

import yaml

# The bulk re-stamp annotation that overrides the check
_BULK_ANNOTATION_RE = re.compile(r"EVIDENCE-RESTAMP:\s*approved by", re.IGNORECASE)

# G14 hardening (2026-08-22): the run citation the annotation must additionally
# carry. Matches "run=reports/refresh_runs/{family}/{platform}/{run_id}" —
# deliberately permissive about surrounding punctuation/whitespace, since this
# is free-text a commit message, not a structured field.
_RUN_CITATION_RE = re.compile(r"run=([^\s,]+)")

# A run manifest's `state` must have progressed at least this far for its
# citation to count as real verification, not just "a run was started" — see
# refresh_run.py's NEXT_STATES for the full state machine this mirrors.
_MIN_VERIFIED_STATES = frozenset({"VALIDATING", "READY_TO_COMMIT", "COMMITTED"})

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[3]
_repo_root = _DEFAULT_REPO_ROOT


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Override the repo-root seam for tests; call without arguments to reset."""
    global _repo_root
    _repo_root = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT


def verify_run_citation(run_ref: str) -> "tuple[bool, str]":
    """Verify an EVIDENCE-RESTAMP annotation's run= citation is real.

    ``run_ref`` is expected to be a path to (or ending in) a run directory
    under ``reports/refresh_runs/{family}/{platform}/{run_id}`` -- with or
    without a trailing ``/manifest.json``. Returns (verified, reason); reason
    explains a False result for the check's own diagnostic output.
    """
    ref = run_ref.strip().rstrip("/")
    if ref.endswith("manifest.json"):
        manifest_path = _repo_root / ref
    else:
        manifest_path = _repo_root / ref / "manifest.json"

    if not manifest_path.is_file():
        return False, f"cited run manifest not found: {manifest_path}"

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"cited run manifest unreadable: {exc}"

    state = manifest.get("state")
    if state not in _MIN_VERIFIED_STATES:
        return False, (
            f"cited run's state is {state!r}, must be one of "
            f"{sorted(_MIN_VERIFIED_STATES)} to count as verified evidence"
        )
    return True, f"verified: run reached {state}"


def bypass_is_verified(combined_text: str) -> "tuple[bool, str]":
    """Return (bypass_granted, reason) for an EVIDENCE-RESTAMP annotation.

    An annotation with no run= citation, or one that fails verification, is
    NOT granted a bypass -- it falls through to the normal warn/block
    threshold exactly as if no annotation were present at all (G14).
    """
    if not _BULK_ANNOTATION_RE.search(combined_text):
        return False, "no EVIDENCE-RESTAMP annotation present"

    citation = _RUN_CITATION_RE.search(combined_text)
    if not citation:
        return False, (
            "EVIDENCE-RESTAMP annotation present but has no run= citation -- "
            "treated as unverified, per G14 hardening"
        )

    verified, reason = verify_run_citation(citation.group(1))
    return verified, reason

# Grade fields are DERIVED from evidence + body content, not independent
# editorial decisions — when evidence is re-stamped, grade/grade_reasons
# routinely get recomputed as a side effect even though nothing a human
# would call "content" changed. Treating a co-occurring grade change as
# disqualifying (the pre-fix behavior) meant re-stamps that also happened
# to shift `grade_reasons` wording silently evaded this guard entirely,
# even with a byte-identical body. Mirrors the field list check_grade_churn.py
# already treats as the grade-field family (GUARD-01).
_GRADE_FIELDS: frozenset[str] = frozenset({
    "grade", "graded_at", "graded_model_sha", "graded_evaluators",
    "graded_logic_version", "graded_content_hash", "graded_evaluator_versions",
    "graded_enrichment_status", "grade_final", "grade_stale_reason",
    "grade_stale_targets", "grade_reasons",
})


def _get_changed_md_files(*, mode: str, base_branch: str) -> list[str]:
    """Return list of .md files changed in the staged area or PR."""
    if mode == "staged":
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=M", "--", "content/**/*.md"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
    else:  # pr
        result = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=M",
             f"{base_branch}...HEAD", "--", "content/**/*.md"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
    if result.returncode != 0:
        return []
    return [f for f in result.stdout.strip().splitlines() if f.endswith(".md")]


def _git_show(rev: str, path: str) -> str | None:
    """Return file content at a revision, or None if it doesn't exist there."""
    result = subprocess.run(
        ["git", "show", f"{rev}:{path}"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if result.returncode != 0:
        return None
    return result.stdout


def _split_frontmatter(text: str) -> tuple[str | None, str]:
    """Split a markdown file into (frontmatter_yaml_text, body_text).

    Returns (None, text) if the file has no `---`-delimited frontmatter.
    """
    if not text.startswith("---"):
        return None, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None, text
    return parts[1], parts[2]


def is_evidence_only_change(old_text: str | None, new_text: str | None) -> bool:
    """Return True if the only difference between old/new file content is
    confined to the `evidence:` top-level frontmatter key, with the body and
    every other top-level frontmatter key byte-for-byte unchanged.
    """
    if old_text is None or new_text is None:
        return False
    if old_text == new_text:
        return False  # no diff at all — not a churn candidate

    old_fm, old_body = _split_frontmatter(old_text)
    new_fm, new_body = _split_frontmatter(new_text)

    if old_fm is None or new_fm is None:
        return False  # no parseable frontmatter on one side
    if old_body != new_body:
        return False  # body changed — not evidence-only

    try:
        old_data = yaml.safe_load(old_fm) or {}
        new_data = yaml.safe_load(new_fm) or {}
    except yaml.YAMLError:
        return False

    if not isinstance(old_data, dict) or not isinstance(new_data, dict):
        return False

    old_keys = set(old_data.keys())
    new_keys = set(new_data.keys())
    if old_keys != new_keys:
        return False  # a top-level frontmatter key was added/removed

    for key in old_keys:
        if key == "evidence" or key in _GRADE_FIELDS:
            continue
        if old_data[key] != new_data[key]:
            return False  # some non-evidence, non-grade top-level field changed

    return old_data.get("evidence") != new_data.get("evidence")


def _is_evidence_only_file(path: str, *, mode: str, base_branch: str) -> bool:
    if mode == "staged":
        old_text = _git_show("HEAD", path)
        new_text = _git_show(":0", path)  # staged/index version
        if new_text is None:
            # Fallback for tools where ":0:path" isn't populated as expected
            new_text = _git_show(":", path)
    else:
        old_text = _git_show(base_branch, path)
        new_text = _git_show("HEAD", path)
    return is_evidence_only_change(old_text, new_text)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Block bulk evidence-only frontmatter rewrites."
    )
    parser.add_argument("--mode", choices=["staged", "pr"], default="staged")
    parser.add_argument("--base-branch", default="origin/main",
                        help="Base branch for PR mode (default: origin/main)")
    parser.add_argument("--warn-threshold", type=int, default=5)
    parser.add_argument("--block-threshold", type=int, default=20)
    parser.add_argument("--commit-msg", default="",
                        help="Commit message to check for bulk re-stamp annotation")
    parser.add_argument("--pr-body", default="",
                        help="PR body to check for bulk re-stamp annotation")
    args = parser.parse_args()

    # Check for override annotation -- G14: must cite a verified run, not just
    # matching text (see bypass_is_verified()'s docstring for the full rationale).
    combined_text = args.commit_msg + "\n" + args.pr_body
    granted, reason = bypass_is_verified(combined_text)
    if granted:
        print(f"PASS: EVIDENCE-RESTAMP annotation verified ({reason}) — evidence churn check bypassed.")
        return 0
    if _BULK_ANNOTATION_RE.search(combined_text):
        print(f"NOTE: EVIDENCE-RESTAMP annotation present but not verified ({reason}) "
              f"— falling through to the normal threshold check.")

    # Get changed .md files
    changed_files = _get_changed_md_files(mode=args.mode, base_branch=args.base_branch)
    if not changed_files:
        print("PASS: No modified .md content files.")
        return 0

    # Classify each file
    evidence_only_files = []
    for f in changed_files:
        if _is_evidence_only_file(f, mode=args.mode, base_branch=args.base_branch):
            evidence_only_files.append(f)

    count = len(evidence_only_files)

    if count >= args.block_threshold:
        print(f"BLOCK: {count} .md files have evidence-only frontmatter changes "
              f"(threshold: {args.block_threshold}).", file=sys.stderr)
        print("", file=sys.stderr)
        print("This looks like a bulk evidence re-stamp (e.g. attach_evidence.py --force",
              file=sys.stderr)
        print("after a knowledge model update) with no body content changes. If the", file=sys.stderr)
        print("knowledge model changed materially, run S-84 (refresh-product), which", file=sys.stderr)
        print("reconciles page bodies via S-20 (page-update) before re-stamping evidence.",
              file=sys.stderr)
        print("", file=sys.stderr)
        print("If this bulk re-stamp is intentional and reviewed, add to the commit message,",
              file=sys.stderr)
        print("citing a refresh_run.py run that actually reached VALIDATING or later:",
              file=sys.stderr)
        print(
            "  EVIDENCE-RESTAMP: approved by [name] on [date], reason: [trigger], "
            "run=reports/refresh_runs/{family}/{platform}/{run_id}",
            file=sys.stderr,
        )
        print("", file=sys.stderr)
        print("Evidence-only files:", file=sys.stderr)
        for f in evidence_only_files[:10]:
            print(f"  {f}", file=sys.stderr)
        if count > 10:
            print(f"  ... and {count - 10} more", file=sys.stderr)
        return 1

    if count >= args.warn_threshold:
        print(f"WARN: {count} .md files have evidence-only frontmatter changes "
              f"(warn threshold: {args.warn_threshold}).")
        for f in evidence_only_files[:5]:
            print(f"  {f}")
        if count > 5:
            print(f"  ... and {count - 5} more")
        print("Consider whether body content changes should accompany these evidence updates.")

    total_changed = len(changed_files)
    body_changed = total_changed - count
    print(f"PASS: {total_changed} .md files changed ({body_changed} with body/other changes, "
          f"{count} evidence-only).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
