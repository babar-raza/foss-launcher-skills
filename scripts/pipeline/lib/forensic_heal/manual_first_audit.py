"""CONTRACT: unaided-first enforcement for S-122 (blind-spot-audit), Wave 2 of
MISSION MT025-2026-08-08-FORENSIC-BLIND-SPOT-HEAL-SKILLS.

Purpose: make "review the cloned FOSS repos and generated content before touching any
system tooling" an AUDITED property of a run, not merely a requested one. Without this, an
agent could run the real evaluators first, then write "unaided" findings that conveniently
match, and the resulting blind-spot matrix would be scientifically meaningless.

Two independent, machine-checkable layers (L1, structural ordering, already lives in
blind_spot_audit_run.py's PHASE_CONTRACTS window check):

  L2 — skill-invocation ledger audit. Reads every record under
       reports/skill-context/history/*.json (shape: {skill_id, scope_patterns, started_at,
       ended_at, end_status}) and reports/skill-runs/*.json (shape: {run_id,
       skills_invoked: [...], started_at, completed_at, ...}) and flags any record whose
       start time falls inside the unaided window AND whose skill_id (or any entry of
       skills_invoked) is in SYSTEM_TOOLING_SKILL_IDS.
  L3 — artifact-mtime forensics. Census SYSTEM_ARTIFACT_ROOTS at window-open, re-census at
       seal time, and flag anything new or touched. Two granularities: FULL (every file,
       for the smaller reports/* roots) and SHALLOW (per-subtree max-mtime at a bounded
       depth, for the much larger runs/ and knowledge/ trees -- walking every file under a
       real clone cache on every seal() call would be needlessly slow, and this repo's own
       governance already treats runs/.clone_cache/ as read-only, so legitimate activity
       there during an unaided window should not occur at all).

Neither layer alone is sufficient: L2 only catches invocations that went through
skill_context.py's begin/end (or the older skill_run_manager.py ledger); L3 is the backstop
for anything that bypassed both. A missing or unreadable ledger is treated as UNPROVABLE,
never as a silent pass -- see evaluate_unaided_first()'s docstring.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Every skill that reads/compares/extracts/grades/governs content or knowledge -- letting
# any of these run inside the unaided window (even S-34 repo-scout, which merely extracts
# API surface) defeats the point of an UNAIDED reading pass. Kept as a flat, explicit set
# rather than derived from docs/registries/skills.md so that an accidental registry
# reformat can never silently shrink this set.
SYSTEM_TOOLING_SKILL_IDS: "frozenset[str]" = frozenset({
    "S-23", "S-32", "S-34", "S-38", "S-40", "S-41", "S-42", "S-43", "S-45", "S-46",
    "S-51", "S-67", "S-81", "S-85", "S-87", "S-89", "S-90", "S-92", "S-93", "S-94",
    "S-99", "S-112",
})

# reports/* roots small enough to census every file. Excludes reports/blind_spot_audit/
# itself (this run's own evidence) and reports/skill-context, reports/skill-runs, and
# reports/locks (read BY the ledger audit, not written by system tooling this gate cares
# about).
_FULL_CENSUS_ROOTS: "tuple[str, ...]" = (
    "reports/audit", "reports/audits", "reports/content_eval", "reports/eval-run",
    "reports/gap-eval", "reports/gap-analysis", "reports/truth-audit",
    "reports/publish-review", "reports/system-heal", "reports/sprint",
)
# Large trees: census per-subtree max-mtime at a bounded depth instead of per-file.
_SHALLOW_CENSUS_ROOTS: "tuple[str, ...]" = ("runs", "knowledge")
_DEFAULT_CENSUS_DEPTH = 3

_LEDGER_GLOBS: "tuple[str, ...]" = (
    "reports/skill-context/history/*.json",
    "reports/skill-runs/*.json",
)


def _iter_files(root: Path) -> "list[Path]":
    if not root.is_dir():
        return []
    out = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if ".git" in p.parts:
            continue
        out.append(p)
    return out


def census_artifacts(repo_root: "Path | str", *, census_depth: int = _DEFAULT_CENSUS_DEPTH) -> dict:
    """Snapshot mtimes of every SYSTEM_ARTIFACT_ROOTS location. Returns
    {"full": {relpath: mtime_float}, "shallow": {subtree_relpath: max_mtime_float}}.
    Missing roots are simply absent from the result (not an error -- a fresh repo may not
    have reports/gap-eval/ yet, for instance)."""
    repo_root = Path(repo_root)
    full: "dict[str, float]" = {}
    for rel_root in _FULL_CENSUS_ROOTS:
        root = repo_root / rel_root
        for f in _iter_files(root):
            full[f.relative_to(repo_root).as_posix()] = f.stat().st_mtime

    shallow: "dict[str, float]" = {}
    for rel_root in _SHALLOW_CENSUS_ROOTS:
        root = repo_root / rel_root
        if not root.is_dir():
            continue
        for subtree in _subtrees_at_depth(root, census_depth):
            files = _iter_files(subtree)
            max_mtime = max((f.stat().st_mtime for f in files), default=subtree.stat().st_mtime)
            shallow[subtree.relative_to(repo_root).as_posix()] = max_mtime
        # Also cover files directly at/above the depth cutoff (e.g. runs/ itself).
        direct_files = [f for f in root.iterdir() if f.is_file()]
        if direct_files:
            max_mtime = max(f.stat().st_mtime for f in direct_files)
            shallow[root.relative_to(repo_root).as_posix()] = max_mtime

    return {"full": full, "shallow": shallow}


def _subtrees_at_depth(root: Path, depth: int) -> "list[Path]":
    """Return every directory exactly `depth` levels below root (or leaf directories
    shallower than that, so nothing is silently skipped for a sparse tree)."""
    if depth <= 0:
        return [root]
    frontier = [root]
    result: "list[Path]" = []
    for _ in range(depth):
        next_frontier: "list[Path]" = []
        for d in frontier:
            try:
                children = [c for c in d.iterdir() if c.is_dir() and c.name != ".git"]
            except OSError:
                children = []
            if not children:
                result.append(d)
            else:
                next_frontier.extend(children)
        frontier = next_frontier
    result.extend(frontier)
    return result


def diff_census(before: dict, after: dict) -> "list[dict]":
    """Compare two census_artifacts() snapshots. Returns a list of violation dicts:
    {"layer": "L3", "kind": "new_file"|"modified_file"|"new_subtree"|"touched_subtree",
     "path": relpath, "detail": ...}."""
    violations: "list[dict]" = []

    before_full = before.get("full", {})
    after_full = after.get("full", {})
    for path, mtime in after_full.items():
        if path not in before_full:
            violations.append({
                "layer": "L3", "kind": "new_file", "path": path,
                "detail": f"file appeared during the unaided window (mtime {mtime})",
            })
        elif mtime > before_full[path]:
            violations.append({
                "layer": "L3", "kind": "modified_file", "path": path,
                "detail": f"mtime advanced during the unaided window ({before_full[path]} -> {mtime})",
            })

    before_shallow = before.get("shallow", {})
    after_shallow = after.get("shallow", {})
    for path, mtime in after_shallow.items():
        if path not in before_shallow:
            violations.append({
                "layer": "L3", "kind": "new_subtree", "path": path,
                "detail": f"subtree appeared during the unaided window (max mtime {mtime})",
            })
        elif mtime > before_shallow[path]:
            violations.append({
                "layer": "L3", "kind": "touched_subtree", "path": path,
                "detail": f"subtree max-mtime advanced during the unaided window ({before_shallow[path]} -> {mtime})",
            })

    return violations


def _parse_iso(value: "str | None") -> "datetime | None":
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def audit_ledger(
    repo_root: "Path | str", *, window_start: str, window_end: str,
) -> "tuple[list[dict], bool]":
    """Scan the skill-invocation ledgers for any system-tooling skill started inside
    [window_start, window_end]. Returns (violations, ledger_readable). ledger_readable is
    False only if BOTH ledger directories are entirely absent/unreadable -- a real run
    where nothing has ever invoked a skill (fresh clone) is legitimately empty-but-readable,
    not UNPROVABLE."""
    repo_root = Path(repo_root)
    start_dt = _parse_iso(window_start)
    end_dt = _parse_iso(window_end)
    violations: "list[dict]" = []
    any_dir_present = False

    for glob in _LEDGER_GLOBS:
        parts = glob.split("/")
        dir_path = repo_root.joinpath(*parts[:-1])
        pattern = parts[-1]
        if not dir_path.is_dir():
            continue
        any_dir_present = True
        for f in sorted(dir_path.glob(pattern)):
            try:
                record = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                # A torn/unreadable individual record is itself suspicious inside an
                # active audit window -- treat as UNPROVABLE input, not as "no violation".
                violations.append({
                    "layer": "L2", "kind": "unreadable_ledger_record", "path": str(f),
                    "detail": "record could not be parsed during ledger audit",
                })
                continue

            started = _parse_iso(record.get("started_at"))
            if started is None or start_dt is None or end_dt is None:
                continue
            if not (start_dt <= started <= end_dt):
                continue

            skill_ids = set()
            if record.get("skill_id"):
                skill_ids.add(record["skill_id"])
            for sid in record.get("skills_invoked", []) or []:
                skill_ids.add(sid)

            hit = skill_ids & SYSTEM_TOOLING_SKILL_IDS
            if hit:
                violations.append({
                    "layer": "L2", "kind": "system_skill_in_window", "path": str(f),
                    "skill_ids": sorted(hit), "started_at": record.get("started_at"),
                    "detail": f"system-tooling skill(s) {sorted(hit)} invoked inside the unaided window",
                })

    return violations, any_dir_present


def evaluate_unaided_first(
    repo_root: "Path | str", *, window_start: str, window_end: str, before_census: dict,
) -> dict:
    """Combine L2 + L3 into one verdict.

    Returns {"verdict": "UNAIDED_FIRST_CLEAN" | "VIOLATED" | "UNPROVABLE",
             "violations": [...], "ledger_readable": bool}.

    UNPROVABLE (not CLEAN) whenever the ledger could not be read at all -- an unreadable
    ledger is not evidence of a clean run, it is an absence of evidence, and this gate
    treats absence of evidence as a violation-adjacent state rather than a pass. Real
    violations (from either layer) always win over UNPROVABLE when both are present, since
    a proven violation is a stronger, more specific claim.
    """
    repo_root = Path(repo_root)
    after_census = census_artifacts(repo_root)
    l3_violations = diff_census(before_census, after_census)
    l2_violations, ledger_readable = audit_ledger(
        repo_root, window_start=window_start, window_end=window_end,
    )
    violations = l2_violations + l3_violations

    if violations:
        verdict = "VIOLATED"
    elif not ledger_readable:
        verdict = "UNPROVABLE"
    else:
        verdict = "UNAIDED_FIRST_CLEAN"

    return {
        "verdict": verdict,
        "violations": violations,
        "ledger_readable": ledger_readable,
        "after_census": after_census,
    }
