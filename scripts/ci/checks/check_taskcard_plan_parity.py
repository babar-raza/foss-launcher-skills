#!/usr/bin/env python3
"""check_taskcard_plan_parity.py — RPR-G-04: taskcards.jsonl vs plan-markdown parity.

§2.5 SW-4: dazzling-strolling-shell failed because its task status lived only as
prose (`TC-W11-001.C7: TODO`) that nothing checked, drifting silently for 5+ days
before a silent revert. This check makes "does the plan's prose contradict the
structured task store" a machine-checkable question — the same class of check
`check_skill_command_parity.py` (RPR-G-02) applies to skill mirrors.

Design (deliberate, per SW-4): the structured `taskcards.jsonl` (schema 5f) is the
SOURCE OF TRUTH. The plan markdown may carry an explicit `[STATUS: ...]` tag on a
task card; if it does, that tag must NOT contradict the store's bucket. A task the
markdown leaves untagged is treated as SILENT, not as a contradiction — forcing the
prose to be a complete, always-current status board would itself be the brittle
prose-scanning failure mode this check exists to retire. Silence is fine; lying is not.

  --strict-coverage   Additionally require every store task to carry a markdown tag.
  --execution-authority
                      Declare this plan authoritative for execution; strict coverage
                      becomes mandatory. The in-file marker
                      ``<!-- TASKCARD_EXECUTION_AUTHORITY -->`` has the same effect.

ENFORCEMENT STATUS — read this before assuming it is a gate (ST-030, found by this plan's
own Lane I adversarial review):
  This is an **agent-invoked tool (via S-113 plan-health-watchdog), NOT a CI gate.** It has
  zero references in .github/ or pre-commit, and that is architectural, not an oversight:
  plan documents live in ~/.claude/plans/ — OUTSIDE the repo — so a repo-scoped CI job
  cannot reach the --plan-file it requires. Do not read "check" in the filename as "enforced".
  Known limit of the default mode: because silence is tolerated, a task the markdown never
  tags is never compared. On this mission's own plan that means the default compares 7 of 36
  tasks; --strict-coverage reports the other 26 as untagged. The silence-tolerant default is
  still the right default (forcing the prose to be a complete, always-current status board is
  precisely the brittle prose-scanning failure mode S-113 exists to retire) — but the limit is
  real and is stated here rather than implied away.

Exit codes:
  0 — no contradictions (and, with --strict-coverage, full tag coverage)
  1 — at least one contradiction (or missing tag under --strict-coverage)
  2 — a required input file is missing/unparseable
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# A task card header carries the task id and an optional [STATUS: ...] tag, e.g.
#   **RPR-A-01 — Classify ... [STATUS: PARTIAL — 12/74 ...]**
#
# _TASK_ID below is a FALLBACK ONLY, kept for callers that invoke
# extract_plan_tags() without a pattern (older tests, ad hoc scripts). It used
# to be the only matcher this tool had -- hardcoded to one legacy mission's
# id shape -- which meant this tool silently reported "0 tagged tasks, no
# contradictions" (a false-confidence pass, not an error) against every other
# mission's taskcards.jsonl, since none of them use RPR-[A-Z]-NN ids
# (TC-MEDIA-01, MT023-..., etc. all went unmatched). main() now derives the
# real pattern from the mission's own taskcards.jsonl via
# infer_task_id_pattern() and passes it explicitly -- see there.
_TASK_ID = re.compile(r"\bRPR-[A-Z]-\d{2}\b")
_STATUS_TAG = re.compile(r"\[STATUS:\s*([^\]]+)\]", re.IGNORECASE)
_EXECUTION_AUTHORITY_MARKER = "<!-- TASKCARD_EXECUTION_AUTHORITY -->"

# Buckets — the granularity at which drift actually matters (a DONE-vs-TODO
# contradiction), not the full 15-value enum (comparing freeform prose to a
# 15-value enum would itself be fragile).
DONE, PARTIAL, NOT_STARTED = "DONE", "PARTIAL", "NOT_STARTED"

# schema-5f status enum -> bucket
_STORE_BUCKET = {
    "TODO": NOT_STARTED, "READY": NOT_STARTED,
    "IN_PROGRESS": PARTIAL, "IMPLEMENTED": PARTIAL, "PAUSED": PARTIAL,
    "FOCUSED_VERIFIED": DONE, "INTEGRATION_VERIFIED": DONE,
    "END_TO_END_VERIFIED": DONE, "PILOT_PROVEN": DONE,
    "INDEPENDENTLY_REVIEWED": DONE, "CLOSED": DONE,
    # Non-progress states are excluded from parity (see _EXCLUDED_STORE_STATUSES).
}
_EXCLUDED_STORE_STATUSES = {"SUPERSEDED", "OUT_OF_SCOPE", "REWORK_REQUIRED",
                            "BLOCKED_LOCAL", "BLOCKED_EXTERNAL"}


def infer_task_id_pattern(task_ids) -> re.Pattern:
    """Build a task-id-matching regex from a mission's own observed
    task_id values, instead of a hardcoded prefix.

    Derives each id's prefix (everything up to and including its final
    hyphen before a trailing numeric suffix, e.g. "TC-MEDIA-01" -> "TC-MEDIA-",
    "RPR-A-01" -> "RPR-A-") and matches any id sharing one of those prefixes
    followed by digits -- broad enough to also catch a plan-mentioned id that
    shares the mission's convention but has NO store row yet at all (the
    tagged_but_missing_from_store case this tool exists to catch; restricting
    the pattern to only ALREADY-known exact ids would silently defeat that).
    Ids with no trailing numeric suffix are matched verbatim as a fallback.

    Returns a regex matching nothing (never matches) if task_ids is empty --
    an empty store has no convention to infer, and the caller should not fall
    back to the RPR-only default silently.
    """
    prefixes: set[str] = set()
    literals: set[str] = set()
    for tid in task_ids:
        m = re.match(r"^(.*-)(\d+)$", tid)
        if m:
            prefixes.add(m.group(1))
        else:
            literals.add(tid)
    if not prefixes and not literals:
        return re.compile(r"(?!)")  # matches nothing
    alts = [re.escape(p) + r"\d+" for p in prefixes] + [re.escape(l) for l in literals]
    alts.sort(key=len, reverse=True)  # longer/more-specific prefixes first
    return re.compile(r"\b(?:" + "|".join(alts) + r")\b")

# Phrases in a markdown [STATUS: ...] tag that qualify a "DONE" down to PARTIAL.
_PARTIAL_QUALIFIERS = ("partial", "portion", "still open", "not yet", "⏳",
                       "steps 3-4", "steps 2-4", "step 1")


def markdown_status_bucket(tag_text: str) -> str:
    """Classify a plan markdown [STATUS: ...] tag's free text into a bucket."""
    low = tag_text.lower()
    has_done = "done" in low
    has_partial_qual = any(q in low for q in _PARTIAL_QUALIFIERS)
    if has_done and not has_partial_qual:
        return DONE
    if has_done and has_partial_qual:
        return PARTIAL
    if "partial" in low or "in_progress" in low or "in progress" in low:
        return PARTIAL
    return NOT_STARTED


def store_status_bucket(status: str) -> str | None:
    """Bucket a schema-5f status; None if excluded from parity."""
    if status in _EXCLUDED_STORE_STATUSES:
        return None
    return _STORE_BUCKET.get(status, NOT_STARTED)


def extract_plan_tags(plan_text: str, task_id_pattern: "re.Pattern | None" = None) -> dict[str, str]:
    """task_id -> raw [STATUS: ...] text, for cards that carry an explicit tag.

    A card header is a single line containing a task id; the tag (if any) is on
    the same line. Only the first tag per task id is taken.

    task_id_pattern should normally be built by infer_task_id_pattern() from
    the mission's own taskcards.jsonl (main() does this). Defaults to the
    legacy RPR-only pattern only when omitted, for callers that don't have a
    store loaded yet -- new call sites should always pass an inferred pattern.
    """
    pattern = task_id_pattern if task_id_pattern is not None else _TASK_ID
    tags: dict[str, str] = {}
    for line in plan_text.splitlines():
        ids = pattern.findall(line)
        if not ids:
            continue
        m = _STATUS_TAG.search(line)
        if not m:
            continue
        tid = ids[0]
        if tid not in tags:  # first tag wins (the header line)
            tags[tid] = m.group(1).strip()
    return tags


def load_taskcards(path: Path) -> dict[str, str]:
    """task_id -> status (last-writer-wins, matching append-on-status-change 5f)."""
    store: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        store[obj["task_id"]] = obj["status"]
    return store


def find_contradictions(plan_tags: dict[str, str], store: dict[str, str],
                        *, strict_coverage: bool = False) -> list[dict]:
    """Return parity problems. Silence in the markdown is never a contradiction."""
    problems = []
    # Every markdown-tagged task must exist in the store and not be contradicted.
    for tid, tag_text in sorted(plan_tags.items()):
        if tid not in store:
            problems.append({"task": tid, "kind": "tagged_but_missing_from_store",
                             "detail": f"plan tags {tid} [{tag_text}] but it has no taskcards.jsonl row"})
            continue
        plan_bucket = markdown_status_bucket(tag_text)
        store_bucket = store_status_bucket(store[tid])
        if store_bucket is None:
            continue  # excluded store status
        if plan_bucket != store_bucket:
            problems.append({"task": tid, "kind": "contradiction",
                             "detail": f"plan says {plan_bucket} ([{tag_text}]) but store says "
                                       f"{store_bucket} ({store[tid]})"})
    if strict_coverage:
        for tid in sorted(store):
            if store_status_bucket(store[tid]) is None:
                continue
            if tid not in plan_tags:
                problems.append({"task": tid, "kind": "untagged_under_strict_coverage",
                                 "detail": f"store has {tid} ({store[tid]}) but plan carries no [STATUS] tag"})
    return problems


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Taskcard-store vs plan-markdown parity (RPR-G-04).")
    parser.add_argument("--plan-file", required=True, help="Path to the plan markdown (§7 task cards)")
    parser.add_argument("--taskcards", required=True, help="Path to the mission's taskcards.jsonl")
    parser.add_argument("--strict-coverage", action="store_true",
                        help="Also require every store task to carry a markdown [STATUS] tag")
    parser.add_argument(
        "--execution-authority",
        action="store_true",
        help="Treat the plan as execution authority and require strict task coverage",
    )
    args = parser.parse_args(argv)

    plan_path, store_path = Path(args.plan_file), Path(args.taskcards)
    if not plan_path.is_file():
        print(f"ERROR: plan file not found: {plan_path}", file=sys.stderr)
        return 2
    if not store_path.is_file():
        print(f"ERROR: taskcards file not found: {store_path}", file=sys.stderr)
        return 2
    try:
        plan_text = plan_path.read_text(encoding="utf-8")
        store = load_taskcards(store_path)
        # Derive the id-matching pattern from THIS mission's own task_ids,
        # not a hardcoded convention -- see infer_task_id_pattern().
        task_id_pattern = infer_task_id_pattern(store.keys())
        plan_tags = extract_plan_tags(plan_text, task_id_pattern)
    except (json.JSONDecodeError, KeyError, OSError) as exc:
        print(f"ERROR: could not parse inputs: {exc}", file=sys.stderr)
        return 2

    strict_coverage = (
        args.strict_coverage
        or args.execution_authority
        or _EXECUTION_AUTHORITY_MARKER in plan_text
    )
    problems = find_contradictions(
        plan_tags,
        store,
        strict_coverage=strict_coverage,
    )
    if problems:
        print(f"TASKCARD/PLAN PARITY: {len(problems)} problem(s):")
        for p in problems:
            print(f"  [{p['kind']}] {p['detail']}")
        return 1
    print(f"OK: {len(plan_tags)} tagged task(s) consistent with {len(store)} store row(s); "
          f"no contradictions.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
