"""SEO-SCHEMA-A-WORKFLOW-UPDATE: automated pre-merge safety gates for the
weekly Schema A keyword refresh workflow's auto-merge exception.

This exception is scoped exclusively to seo-keyword-refresh.yml's own PRs
(see the governing plan's Mission Contract) and is conditioned entirely on
these gates passing. Run AFTER validate.py (schema integrity -- gate 1) and
BEFORE any auto-merge decision:
  2. Diff is scoped exclusively to keywords/*.json (no other path changed).
  3. Every changed entry has only {pageTitle, sourcePath, keywords} keys
     (catches the 2026-03-27 contamination shape -- stray tags/pluginDescriptions).
  4. No family's entry count decreases vs the base ref.

Exits 0 only if every gate passes; exits 1 and prints exactly which gate(s)
failed otherwise. A failing exit means the caller must leave the PR open for
human review, not auto-merge it -- never a partial pass.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]

_ALLOWED_ENTRY_KEYS = {"pageTitle", "sourcePath", "keywords"}


def _git(args, repo_root):
    return subprocess.run(
        ["git", *args], cwd=repo_root, capture_output=True, text=True, check=True,
    )


def _changed_files(base_ref, repo_root):
    result = _git(["diff", "--name-only", f"{base_ref}...HEAD"], repo_root)
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _load_at_ref(ref, rel_path, repo_root):
    result = subprocess.run(
        ["git", "show", f"{ref}:{rel_path}"],
        cwd=repo_root, capture_output=True, text=True,
    )
    if result.returncode != 0:
        return []  # file didn't exist at that ref -- treat as a new, empty file
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def check_scope(changed_files):
    """Gate 2: every changed path is keywords/*.json."""
    offenders = [f for f in changed_files if not (f.startswith("keywords/") and f.endswith(".json"))]
    return (not offenders), offenders


def check_entry_shape(changed_files, repo_root):
    """Gate 3: every changed entry has only the 3 allowed keys."""
    violations = []
    for rel_path in changed_files:
        payload = _load_at_ref("HEAD", rel_path, repo_root)
        if payload is None:
            violations.append(f"{rel_path}: invalid JSON")
            continue
        for i, entry in enumerate(payload):
            if not isinstance(entry, dict):
                violations.append(f"{rel_path}[{i}]: not an object")
                continue
            extra = set(entry.keys()) - _ALLOWED_ENTRY_KEYS
            if extra:
                violations.append(f"{rel_path}[{i}]: unexpected keys {sorted(extra)}")
    return (not violations), violations


def check_no_entry_count_regression(changed_files, base_ref, repo_root):
    """Gate 4: no family's entry count may decrease vs base_ref."""
    regressions = []
    for rel_path in changed_files:
        before = _load_at_ref(base_ref, rel_path, repo_root)
        after = _load_at_ref("HEAD", rel_path, repo_root)
        if before is None or after is None:
            continue  # shape violations already caught by check_entry_shape
        if len(after) < len(before):
            regressions.append(f"{rel_path}: {len(before)} -> {len(after)} entries")
    return (not regressions), regressions


def run_checks(base_ref, repo_root=None):
    repo_root = repo_root or _REPO_ROOT
    changed = _changed_files(base_ref, repo_root)
    if not changed:
        return True, ["No changed files vs base ref -- nothing to gate, trivially passes."]

    messages = []
    all_passed = True

    scope_ok, offenders = check_scope(changed)
    if not scope_ok:
        all_passed = False
        messages.append(f"GATE 2 FAILED (scope): non-keywords/*.json path(s) changed: {offenders}")
    else:
        messages.append("GATE 2 passed: diff scoped exclusively to keywords/*.json")

    # Gates 3/4 only meaningful for files that passed the scope gate.
    scoped_changed = [f for f in changed if f.startswith("keywords/") and f.endswith(".json")]

    shape_ok, shape_violations = check_entry_shape(scoped_changed, repo_root)
    if not shape_ok:
        all_passed = False
        messages.append(f"GATE 3 FAILED (entry shape): {shape_violations}")
    else:
        messages.append("GATE 3 passed: every changed entry has only pageTitle/sourcePath/keywords")

    count_ok, regressions = check_no_entry_count_regression(scoped_changed, base_ref, repo_root)
    if not count_ok:
        all_passed = False
        messages.append(f"GATE 4 FAILED (entry count regression): {regressions}")
    else:
        messages.append("GATE 4 passed: no family's entry count decreased")

    return all_passed, messages


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-ref", default="origin/main", help="Ref to diff against (default: origin/main)")
    args = parser.parse_args()

    passed, messages = run_checks(args.base_ref)
    for m in messages:
        print(m)
    if not passed:
        print("\nRESULT: one or more auto-merge safety gates FAILED -- leave PR open for human review.")
        sys.exit(1)
    print("\nRESULT: all auto-merge safety gates passed.")
    sys.exit(0)
