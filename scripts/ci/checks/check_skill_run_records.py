"""check_skill_run_records.py — CI advisory: validate skill run records against commit declarations.

For each content commit in scope, check whether a skill run record exists and whether
the 'Skills invoked:' field in the commit message matches the record.

This check is ADVISORY (designed to run with continue-on-error: true, per
scripts/ci/hooks/simulate_pr_checks.sh, the only place it is currently invoked --
this repo has no PR-gated CI path in practice; production commits push directly to
main, see AGENTS.md/CLAUDE.md). It warns on mismatches and on commits missing a
'Skills invoked:' field entirely.

A missing 'Skills invoked:' field is reported, not silently skipped: prior to
2026-07-24 this case was silently ignored (`continue` with no output), and its own
comment incorrectly claimed "handled by the existing hook/CI check". There IS a real,
robust check for this on the ordinary `git commit` path (.git/hooks/commit-msg, built
from scripts/commit-msg-skills.sh, TC-GOV-15 -- blocking, with an audited bypass
trail) -- but a commit built via git write-tree/commit-tree/push (a documented
workaround for concurrent-session git-index contention, see CLAUDE.md) never invokes
`git commit`, so commit-msg never fires either. No local git hook CAN fire for that
commit-construction path -- this is fundamental git behavior, not a fixable bug in
any hook script. The only viable safety net is post-hoc: this script (invoked from a
periodic/audit context, e.g. a .supervisor/ post-sprint audit) checking recent
commits, and a *retroactive* skill run record (skill_run_manager.py create
--retroactive, finalized with --commit-sha) being created for each git-plumbed commit
as a required step of that workaround procedure. This script recognizes such records
(see 'RECONCILED' below) even though it cannot find a message-level declaration.

Usage:
    python scripts/ci/checks/check_skill_run_records.py --commits sha1 sha2 ...
    python scripts/ci/checks/check_skill_run_records.py --commits $(git log origin/main...HEAD --format='%H')

Exit codes:
    0  all checked commits either have matching records, no records, or no declaration
       (advisory mode -- see module docstring above for why this isn't yet a hard block)
    1  mismatches found (advisory — warnings emitted but caller may choose to ignore)
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_REPO_ROOT = _DEFAULT_REPO_ROOT
_RUNS_DIR = _REPO_ROOT / "reports" / "skill-runs"


def configure(*, repo_root: "Path | str | None" = None, runs_dir: "Path | str | None" = None) -> None:
    """Override module-level path constants for testing."""
    global _REPO_ROOT, _RUNS_DIR
    _REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    _RUNS_DIR = Path(runs_dir) if runs_dir is not None else _REPO_ROOT / "reports" / "skill-runs"

# Pattern to match "Skills invoked: [S-xx, S-yy]" or "Skills invoked: S-xx, S-yy"
_SKILLS_RE = re.compile(r"skills?\s*invoked[:\s]+\[?([^\]\n]+)\]?", re.IGNORECASE)


def _parse_declared_skills(commit_msg: str) -> list[str] | None:
    """Extract declared skills from a commit message. Returns None if not found."""
    m = _SKILLS_RE.search(commit_msg)
    if not m:
        return None
    raw = m.group(1).strip()
    return [s.strip() for s in raw.split(",") if s.strip()]


def _load_json(path: Path) -> dict | None:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _find_record_for_commit(commit_sha: str) -> dict | None:
    """Find a skill run record linked to the given commit SHA."""
    if not _RUNS_DIR.exists():
        return None
    short = commit_sha[:8]
    for record_file in _RUNS_DIR.glob("*.json"):
        record = _load_json(record_file)
        if not isinstance(record, dict):
            continue
        stored_sha = record.get("commit_sha", "")
        if stored_sha and (stored_sha.startswith(short) or commit_sha.startswith(stored_sha[:8])):
            return record
    return None


def _get_commit_message(sha: str) -> str:
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%B", sha],
            capture_output=True, text=True, cwd=str(_REPO_ROOT)
        )
        return result.stdout
    except (subprocess.SubprocessError, OSError):
        return ""


def _compute_declared_from_record(record: dict) -> set[str]:
    """Get the skills that should be in 'Skills invoked:' from a record."""
    all_skills: list[str] = record.get("skills_invoked", [])
    details: list[dict] = record.get("skill_details", [])
    detail_map: dict[str, str] = {d["skill_id"]: d["invocation_type"] for d in details}

    declared = set()
    for skill in all_skills:
        inv_type = detail_map.get(skill)
        if inv_type is None or inv_type in ("full", "partial"):
            declared.add(skill)
    return declared


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv

    commits: list[str] = []
    i = 0
    while i < len(args):
        if args[i] == "--commits":
            i += 1
            while i < len(args) and not args[i].startswith("--"):
                commits.append(args[i])
                i += 1
        else:
            commits.append(args[i])
            i += 1

    if not commits:
        print("No commits specified.")
        return 0

    mismatches: list[str] = []
    no_record: list[str] = []
    validated: list[str] = []
    no_declaration: list[str] = []
    reconciled: list[str] = []

    for sha in commits:
        msg = _get_commit_message(sha)
        declared = _parse_declared_skills(msg)
        if declared is None:
            # No 'Skills invoked:' field in the commit MESSAGE. .git/hooks/commit-msg
            # (TC-GOV-15) robustly enforces this field for ordinary `git commit`
            # invocations -- but that hook, like every git commit-time hook, never
            # fires for a commit built via git write-tree/commit-tree/push (a
            # workaround this repo's own CLAUDE.md documents for concurrent-session
            # git-index contention). Such a commit reaches here with zero prior
            # message-level validation (MT007 L1-01/L3-01/L3-02).
            #
            # A commit message is immutable once pushed, so the fix is not to
            # rewrite history -- it's to check whether a *retroactive* skill run
            # record was created after the fact (skill_run_manager.py create
            # --retroactive, finalized with --commit-sha). If one exists, this is a
            # properly reconciled git-plumbed commit, not an unaccounted-for one.
            record = _find_record_for_commit(sha)
            if record is not None:
                skills = record.get("skills_invoked", [])
                retro = " (retroactive)" if record.get("retroactive") else ""
                reconciled.append(
                    f"  RECONCILED: {sha[:10]} has no message-level declaration but a "
                    f"skill run record exists{retro}: {sorted(skills)}"
                )
            else:
                no_declaration.append(f"  NO DECLARATION: {sha[:10]} has no 'Skills invoked:' field")
            continue

        record = _find_record_for_commit(sha)
        if record is None:
            no_record.append(f"  NO RECORD: {sha[:10]} declares {declared} but no skill run record found")
            continue

        record_skills = _compute_declared_from_record(record)
        declared_set = set(declared)

        false_positives = declared_set - record_skills
        false_negatives = record_skills - declared_set

        if false_positives or false_negatives:
            lines = [f"  MISMATCH: {sha[:10]}"]
            if false_positives:
                lines.append(f"    Declared but not in record: {sorted(false_positives)}")
            if false_negatives:
                lines.append(f"    In record but not declared: {sorted(false_negatives)}")
            mismatches.append("\n".join(lines))
        else:
            validated.append(f"  OK: {sha[:10]} — declared {sorted(declared_set)}")

    if validated:
        print(f"Commits with validated skill declarations ({len(validated)}):")
        for v in validated:
            print(v)

    if reconciled:
        print(f"\nCommits reconciled via a retroactive skill run record ({len(reconciled)}):")
        for r in reconciled:
            print(r)

    if no_declaration:
        print(f"\nCommits with NO 'Skills invoked:' field ({len(no_declaration)}):")
        for d in no_declaration:
            print(d)
        print("  This repo's governance mandate (AGENTS.md / CLAUDE.md) requires every")
        print("  content commit to go through a skill (S-76 /commit or equivalent), which")
        print("  populates this field. A missing field means either an unskilled commit,")
        print("  or a git-plumbing commit (write-tree/commit-tree/push) that bypassed the")
        print("  commit-time hook chain entirely -- create a retroactive skill run record:")
        print("    python scripts/pipeline/commands/ops/skill_run_manager.py create --skills S-xx --plan '...'")

    if no_record:
        print(f"\nCommits with declarations but no skill run records ({len(no_record)}):")
        for n in no_record:
            print(n)
        print("  Create skill run records before committing to enable validation.")
        print("    python scripts/pipeline/commands/ops/skill_run_manager.py create --skills S-xx --plan '...'")

    if mismatches:
        print(f"\nCommits with MISMATCHED skill declarations ({len(mismatches)}):")
        for m in mismatches:
            print(m)
        print("\n  Check reports/skill-runs/ and correct 'Skills invoked:' in the commit message.")
        print("    Use: python scripts/pipeline/commands/ops/skill_run_manager.py get-declared-skills --run-id <id>")
        return 1

    if no_record:
        # Advisory: no record is a warning, not a hard failure yet
        print("\nWarning: some commits have skill declarations but no run records.")
        print("This is advisory. Create skill run records to enable accuracy validation.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
