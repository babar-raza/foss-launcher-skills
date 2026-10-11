"""SEO-SCHEMA-A-WORKFLOW-UPDATE: automated pre-merge safety gates for the
weekly Schema A keyword refresh workflow's auto-merge exception.

This exception is scoped exclusively to seo-keyword-refresh.yml's own PRs
(see the governing plan's Mission Contract) and is conditioned entirely on
these gates passing. Run AFTER validate.py (schema integrity -- gate 1) and
BEFORE any auto-merge decision:
  2. Diff is scoped exclusively to keywords/*.json (no other path changed).
  3. Every changed entry has only {pageTitle, sourcePath, keywords,
     title_ready_variants, schema_version} keys (catches the 2026-03-27
     contamination shape -- stray tags/pluginDescriptions -- while accepting
     SEO-SCHEMA-A-DUAL-FIELD-GENERATION's two new, optional, additive keys),
     AND every title_ready_variants value stays within the generation
     prompt's own <=6-word bound (SEO-DUAL-FIELD-VARIANT-LENGTH-GATE-
     RESOLVER-1 -- values were never checked before, only keys).
  4. No family's entry count decreases vs the base ref.
  5. Change-budget guard (Contract G, SEO-CHANGE-BUDGET-GUARD): the number of
     entries actually changed (added or modified, by sourcePath) in each
     touched keywords/{family}.json is within change_budget.py's static caps
     and (once that family's warm-up completes) its rolling-baseline anomaly
     check for mechanism="schema_a_refresh". This gate only CHECKS the
     proposed volume -- it deliberately never calls change_budget.record_run()
     itself, since this script may be invoked more than once against the same
     candidate diff (e.g. a CI rerun) and recording here would double-count a
     single real merge into the rolling baseline; recording actual volume is
     the responsibility of whatever step observes the real, merged outcome.

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

try:
    from seo.pipeline import change_budget  # noqa: E402
except ImportError:
    if str(_REPO_ROOT / "scripts" / "seo") not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT / "scripts" / "seo"))
    from pipeline import change_budget  # type: ignore  # noqa: E402

# title_ready_variants/schema_version (SEO-SCHEMA-A-DUAL-FIELD-GENERATION,
# Finding #57 Section J): additive, optional keys the weekly refresh may now
# emit on a freshly-generated/replaced entry. Accepting them here is the
# other half of that change -- without it, the very next scheduled Schema A
# refresh PR that touches any regenerated entry would fail Gate 3 and lose
# its auto-merge eligibility.
_ALLOWED_ENTRY_KEYS = {"pageTitle", "sourcePath", "keywords", "title_ready_variants", "schema_version"}

# Must match validate.py's own _MAX_TITLE_READY_VARIANT_WORDS and
# get_keywords.py's own _MAX_VARIANT_WORDS. Gate 3 previously checked only
# entry-level KEYS, never the title_ready_variants VALUES -- confirmed live
# to have let a real refresh PR (#81) merge 254 variants across
# keywords/{cells,slides}.json that exceed this bound (up to 8 words),
# because validate.py's own drop-and-flag behavior (Gate 1) never fails the
# process (it is a report generator, not a hard gate) and nothing else
# checked variant length at merge time (SEO-DUAL-FIELD-VARIANT-LENGTH-GATE-
# RESOLVER-1).
_MAX_TITLE_READY_VARIANT_WORDS = 6

# SEO-SCHEMA-A-WORKFLOW-UPDATE Migration Plan v2: the one-time platform-label
# migration persists its resumable progress in this single extra file. Gate 2
# allows exactly this path alongside keywords/*.json -- not a broader glob --
# so a run that touches anything else still fails the gate.
_MIGRATION_STATE_FILE_PATH = "data/seo_schema_a_migration_state.json"


def _git(args, repo_root):
    return subprocess.run(
        ["git", *args], cwd=repo_root, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=True,
    )


def _changed_files(base_ref, repo_root):
    result = _git(["diff", "--name-only", f"{base_ref}...HEAD"], repo_root)
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _load_at_ref(ref, rel_path, repo_root):
    result = subprocess.run(
        ["git", "show", f"{ref}:{rel_path}"],
        cwd=repo_root, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    if result.returncode != 0:
        return []  # file didn't exist at that ref -- treat as a new, empty file
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def check_scope(changed_files):
    """Gate 2: every changed path is keywords/*.json, or exactly the
    migration state file (_MIGRATION_STATE_FILE_PATH)."""
    offenders = [
        f for f in changed_files
        if not (f.startswith("keywords/") and f.endswith(".json"))
        and f != _MIGRATION_STATE_FILE_PATH
    ]
    return (not offenders), offenders


def check_entry_shape(changed_files, repo_root):
    """Gate 3: every changed entry has only the 5 allowed keys, and every
    title_ready_variants value stays within the generation prompt's own
    stated word limit (SEO-DUAL-FIELD-VARIANT-LENGTH-GATE-RESOLVER-1 --
    previously checked keys only, never values, letting a real refresh PR
    merge 254 over-length variants)."""
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
            variants = entry.get("title_ready_variants")
            if isinstance(variants, dict):
                for phrase, variant in variants.items():
                    if isinstance(variant, str) and len(variant.split()) > _MAX_TITLE_READY_VARIANT_WORDS:
                        violations.append(
                            f"{rel_path}[{i}]: title_ready_variants[{phrase!r}] exceeds "
                            f"{_MAX_TITLE_READY_VARIANT_WORDS} words ({len(variant.split())})"
                        )
    return (not violations), violations


def _index_by_source_path(entries):
    idx = {}
    for e in entries:
        if isinstance(e, dict) and e.get("sourcePath"):
            idx[e["sourcePath"]] = e
    return idx


def _count_changed_entries(before, after):
    """Entries in `after` that are new (sourcePath not in `before`) or whose
    content differs from the matching `before` entry. This -- not the raw
    entry count -- is the Schema A refresh's real "proposed change volume":
    a regenerated entry with the same sourcePath still counts as a change
    even though Gate 4 sees no count regression."""
    before_idx = _index_by_source_path(before)
    changed = 0
    for entry in after:
        if not isinstance(entry, dict):
            continue
        sp = entry.get("sourcePath")
        if sp is None or sp not in before_idx or before_idx[sp] != entry:
            changed += 1
    return changed


def check_change_budget(changed_files, base_ref, repo_root):
    """Gate 5: per-family change-budget check (Contract G). See module
    docstring for why this never calls record_run()."""
    budgets = change_budget.load_budgets()
    violations = []
    for rel_path in changed_files:
        family = Path(rel_path).stem
        before = _load_at_ref(base_ref, rel_path, repo_root) or []
        after = _load_at_ref("HEAD", rel_path, repo_root) or []
        if not isinstance(before, list) or not isinstance(after, list):
            continue  # shape violations already caught by check_entry_shape
        changed_count = _count_changed_entries(before, after)
        volume = change_budget.ProposedChangeVolume(
            total_items=changed_count, items_by_scope={family: changed_count},
        )
        verdict = change_budget.check_budget(family, "schema_a_refresh", volume, budgets=budgets)
        if not verdict.allowed:
            detail = verdict.static_cap_violations or verdict.anomaly_status
            violations.append(f"{rel_path} (family={family}, changed_entries={changed_count}): {verdict.reason} -- {detail}")
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
        messages.append(
            f"GATE 2 FAILED (scope): path(s) outside keywords/*.json and "
            f"{_MIGRATION_STATE_FILE_PATH} changed: {offenders}"
        )
    else:
        messages.append(
            f"GATE 2 passed: diff scoped exclusively to keywords/*.json "
            f"(and/or {_MIGRATION_STATE_FILE_PATH})"
        )

    # Gates 3/4 only meaningful for files that passed the scope gate.
    scoped_changed = [f for f in changed if f.startswith("keywords/") and f.endswith(".json")]

    shape_ok, shape_violations = check_entry_shape(scoped_changed, repo_root)
    if not shape_ok:
        all_passed = False
        messages.append(f"GATE 3 FAILED (entry shape): {shape_violations}")
    else:
        messages.append(
            "GATE 3 passed: every changed entry has only pageTitle/sourcePath/keywords "
            "(+ optional title_ready_variants/schema_version)"
        )

    count_ok, regressions = check_no_entry_count_regression(scoped_changed, base_ref, repo_root)
    if not count_ok:
        all_passed = False
        messages.append(f"GATE 4 FAILED (entry count regression): {regressions}")
    else:
        messages.append("GATE 4 passed: no family's entry count decreased")

    budget_ok, budget_violations = check_change_budget(scoped_changed, base_ref, repo_root)
    if not budget_ok:
        all_passed = False
        messages.append(f"GATE 5 FAILED (change-budget guard): {budget_violations}")
    else:
        messages.append("GATE 5 passed: change-budget guard (static caps + anomaly check)")

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
