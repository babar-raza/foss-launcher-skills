"""check_taskcard_plan_parity.py -- detect a plan markdown's [STATUS: ...]
tags contradicting its taskcards.jsonl store.

Rewritten 2026-08-30 (TASK_BACKLOG.md SYNC-3-remaining) after real
dogfooding against this repo's own plan-hardening-addendum doc found the
prior line-scoped done/not-done-word heuristic threw 8 false positives out
of 10 reported "contradictions" -- it flagged any line merely MENTIONING a
task id near unrelated done/not-done vocabulary (e.g. closeout-criteria
prose describing a future condition), not lines actually claiming a
current status. That first version's own docstring admitted it hadn't
read aspose.org's real check_taskcard_plan_parity.py (RPR-G-04); this
rewrite reads it in full and adopts its actual, already-battle-tested
design: only an explicit `[STATUS: ...]` tag on a taskcard line counts as
a claim. Silence in the markdown is never a contradiction -- the store is
the source of truth, and forcing every line to be a live, accurate status
board would just be a differently-shaped version of the same
brittle-prose-scanning problem this tool exists to retire.

  --strict-coverage   Additionally require every non-excluded store task
                      to carry a markdown [STATUS] tag.

Design difference from source: source keeps a hardcoded legacy `RPR-`
prefix regex as a fallback default for callers that don't pass a pattern.
This repo has no equivalent legacy convention, so this port drops that
fallback entirely -- main() always derives the task-id pattern from the
mission's own taskcards.jsonl via infer_task_id_pattern(); a fake default
would just reintroduce the kind of hardcoded assumption this whole sync
effort exists to remove.

Exit codes:
  0 -- no contradictions (and, with --strict-coverage, full tag coverage)
  1 -- at least one contradiction found (or missing tag under --strict-coverage)
  2 -- required plan file is missing
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_STATUS_TAG = re.compile(r"\[STATUS:\s*([^\]]+)\]", re.IGNORECASE)

# Buckets -- the granularity at which drift actually matters (a DONE-vs-
# NOT_STARTED contradiction), not the full multi-value status enum
# (comparing freeform prose to a many-value enum would itself be fragile).
DONE, PARTIAL, NOT_STARTED = "DONE", "PARTIAL", "NOT_STARTED"

_STORE_BUCKET = {
    "TODO": NOT_STARTED, "READY": NOT_STARTED,
    "IN_PROGRESS": PARTIAL, "IMPLEMENTED": PARTIAL, "PAUSED": PARTIAL,
    "FOCUSED_VERIFIED": DONE, "INTEGRATION_VERIFIED": DONE,
    "END_TO_END_VERIFIED": DONE, "PILOT_PROVEN": DONE,
    "INDEPENDENTLY_REVIEWED": DONE, "CLOSED": DONE,
    # Non-progress states are excluded from parity -- see _EXCLUDED_STORE_STATUSES.
}
_EXCLUDED_STORE_STATUSES = {"SUPERSEDED", "OUT_OF_SCOPE", "REWORK_REQUIRED",
                            "BLOCKED_LOCAL", "BLOCKED_EXTERNAL"}
_PARTIAL_QUALIFIERS = ("partial", "portion", "still open", "not yet")


def infer_task_id_pattern(task_ids) -> "re.Pattern[str]":
    """Build a task-id-matching regex from a mission's own observed
    task_id values, instead of a hardcoded prefix convention.

    Derives each id's prefix (everything up to and including its final
    hyphen before a trailing numeric suffix, e.g. "SYNC-5" -> "SYNC-") and
    matches any id sharing one of those prefixes followed by digits --
    broad enough to also catch a plan-mentioned id that shares the
    mission's convention but has no store row yet at all (the
    tagged_but_missing_from_store case this tool exists to catch;
    restricting the pattern to only already-known exact ids would
    silently defeat that). Ids with no trailing numeric suffix (e.g.
    "SYNC-8-full") are matched verbatim as a literal fallback.

    Returns a regex matching nothing if task_ids is empty -- an empty
    store has no convention to infer, and the caller should not silently
    fall back to matching everything.
    """
    prefixes: "set[str]" = set()
    literals: "set[str]" = set()
    for tid in task_ids:
        m = re.match(r"^(.*-)(\d+)$", tid)
        if m:
            prefixes.add(m.group(1))
        else:
            literals.add(tid)
    if not prefixes and not literals:
        return re.compile(r"(?!)")  # matches nothing
    alts = [re.escape(p) + r"\d+" for p in prefixes] + [re.escape(l) for l in literals]
    alts.sort(key=len, reverse=True)  # longer/more-specific literals first
    return re.compile(r"\b(?:" + "|".join(alts) + r")\b")


def markdown_status_bucket(tag_text: str) -> str:
    """Classify a plan markdown [STATUS: ...] tag's free text into a bucket."""
    low = tag_text.lower()
    has_done = "done" in low or "closed" in low
    has_partial_qual = any(q in low for q in _PARTIAL_QUALIFIERS)
    if has_done and not has_partial_qual:
        return DONE
    if has_done and has_partial_qual:
        return PARTIAL
    if "partial" in low or "in_progress" in low or "in progress" in low or "paused" in low:
        return PARTIAL
    return NOT_STARTED


def store_status_bucket(status: str) -> "str | None":
    """Bucket a taskcard status; None if excluded from parity checking."""
    if status in _EXCLUDED_STORE_STATUSES:
        return None
    return _STORE_BUCKET.get(status, NOT_STARTED)


def extract_plan_tags(plan_text: str, task_id_pattern: "re.Pattern[str]") -> "dict[str, str]":
    """task_id -> raw [STATUS: ...] text, for lines that carry both a known
    task id and an explicit tag on the same line. Only the first tag per
    task id is taken (the header line)."""
    tags: "dict[str, str]" = {}
    for line in plan_text.splitlines():
        ids = task_id_pattern.findall(line)
        if not ids:
            continue
        m = _STATUS_TAG.search(line)
        if not m:
            continue
        tid = ids[0]
        if tid not in tags:
            tags[tid] = m.group(1).strip()
    return tags


def load_taskcards_latest(path: Path) -> "dict[str, dict]":
    """task_id -> latest full row (last-writer-wins), matching
    taskcard_store.py's own read_latest() semantics."""
    if not path.is_file():
        return {}
    latest: "dict[str, dict]" = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        tid = row.get("task_id")
        if tid:
            latest[tid] = row
    return latest


def find_contradictions(plan_tags: "dict[str, str]", taskcards: "dict[str, dict]",
                         *, strict_coverage: bool = False) -> "list[dict]":
    """Return parity problems. Silence in the markdown is never a
    contradiction -- only a tagged line can disagree with the store."""
    problems: "list[dict]" = []
    for tid, tag_text in sorted(plan_tags.items()):
        row = taskcards.get(tid)
        if row is None:
            problems.append({
                "task_id": tid, "kind": "tagged_but_missing_from_store",
                "detail": f"plan tags {tid} [{tag_text}] but it has no taskcards.jsonl row",
            })
            continue
        plan_bucket = markdown_status_bucket(tag_text)
        store_bucket = store_status_bucket(row.get("status", ""))
        if store_bucket is None:
            continue  # excluded store status
        if plan_bucket != store_bucket:
            problems.append({
                "task_id": tid, "kind": "contradiction",
                "detail": f"plan says {plan_bucket} ([{tag_text}]) but store says "
                          f"{store_bucket} ({row.get('status')})",
            })
    if strict_coverage:
        for tid, row in sorted(taskcards.items()):
            if store_status_bucket(row.get("status", "")) is None:
                continue
            if tid not in plan_tags:
                problems.append({
                    "task_id": tid, "kind": "untagged_under_strict_coverage",
                    "detail": f"store has {tid} ({row.get('status')}) but plan carries no [STATUS] tag",
                })
    return problems


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--plan-file", required=True)
    parser.add_argument("--taskcards", required=True)
    parser.add_argument("--strict-coverage", action="store_true",
                        help="Also require every store task to carry a markdown [STATUS] tag")
    args = parser.parse_args(argv)

    plan_path = Path(args.plan_file)
    taskcards_path = Path(args.taskcards)
    if not plan_path.is_file():
        print(f"ERROR: plan file not found: {plan_path}", file=sys.stderr)
        return 2

    taskcards = load_taskcards_latest(taskcards_path)
    if not taskcards:
        print(f"No taskcards found at {taskcards_path} -- mission is untracked (advisory, not blocking).", file=sys.stderr)
        return 0

    plan_text = plan_path.read_text(encoding="utf-8")
    task_id_pattern = infer_task_id_pattern(taskcards.keys())
    plan_tags = extract_plan_tags(plan_text, task_id_pattern)
    problems = find_contradictions(plan_tags, taskcards, strict_coverage=args.strict_coverage)

    if problems:
        print(f"PARITY: {len(problems)} problem(s) found in {plan_path}:")
        for p in problems:
            print(f"  [{p['kind']}] {p['task_id']}: {p['detail']}")
        return 1

    print(f"PASS: {len(plan_tags)} tagged task(s) checked in {plan_path}, consistent with {len(taskcards)} store row(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
