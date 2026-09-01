#!/usr/bin/env python3
"""mission_authority.py — durable multi-mission archive for MISSION_AUTHORITY.yaml.

Root-level MISSION_AUTHORITY.yaml is a single mutable "current mission"
projection with zero tooling behind it (confirmed: no script anywhere
referenced it before this one) — it gets overwritten per mission, and only
`git log -p` recovers prior missions. Meanwhile reports/plan_state/{mission_id}/
already holds a durable taskcards.jsonl per mission, for 6 missions at once.

This script closes that gap without replacing the root file's role: the root
file stays the human-authored "current mission" narrative (mission_summary,
in_scope_outcomes, etc. remain hand-written prose — a script must not
fabricate mission narrative). What this script adds:

  open --mission-id X   validate the root file's required fields, confirm its
                        mission_id matches X, and archive an immutable
                        snapshot to reports/plan_state/X/mission_authority.yaml
                        (status: open)
  list                  scan reports/plan_state/*/mission_authority.yaml and
                        print every known mission with its status
  close --mission-id X  mark mission X's archived snapshot status: closed
  status [--json]       read-only liveness aggregator across session_ledger,
                        skill_context, and advisory-lock state (RC1/RC2
                        hardening, 2026-07-31) -- the automated replacement
                        for the manual, undocumented investigation a mission
                        handoff previously required to answer "is anything
                        else really in progress?" (see the hand-typed
                        conflicts_found field in past root-file commits).
                        Read-only: never mutates, never gates `open` today.

Required fields (concordance table, docs/governance/planning-methodology.md):
mission_id, mission_summary, governing_plan_path, in_scope_outcomes,
out_of_scope_items, mandatory_acceptance_criteria, mission_locked.

Usage:
    python scripts/pipeline/commands/governance/mission_authority.py open --mission-id X
    python scripts/pipeline/commands/governance/mission_authority.py list
    python scripts/pipeline/commands/governance/mission_authority.py close --mission-id X
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

_LIB_DIR = str(Path(__file__).resolve().parents[2] / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from advisory_lock import _pid_alive  # noqa: E402
from mission_id_ledger import MissionIdLedger  # noqa: E402

# Matches the numeric MT0NN track only (ST-157 fix scope) -- e.g.
# "MT018-2026-08-01-PACKAGE-IDENTITY-COVERAGE" -> number 18. Free-text slug
# mission ids (e.g. "backlink-governance-redesign") never match and are
# deliberately left out of ledger coverage -- see mission_id_ledger.py's
# module docstring for why.
_MT_ID_RE = re.compile(r"^(MT(\d+))-")


class MissionIdCollisionError(Exception):
    """Raised when archive_mission() would overwrite an existing archive at
    the same mission_id whose content genuinely differs (ST-157 hardening:
    archive_mission() previously overwrote silently, with no diff check --
    the exact storage-layer manifestation of a mission-id collision)."""


REQUIRED_FIELDS = [
    "mission_id",
    "mission_summary",
    "governing_plan_path",
    "in_scope_outcomes",
    "out_of_scope_items",
    "mandatory_acceptance_criteria",
    "mission_locked",
]


def repo_root() -> Path:
    # scripts/pipeline/commands/governance/mission_authority.py -> repo root is 4 up
    return Path(__file__).resolve().parents[4]


def root_mission_authority_path(root: Optional[Path] = None) -> Path:
    return (root or repo_root()) / "MISSION_AUTHORITY.yaml"


def plan_state_dir(mission_id: str, root: Optional[Path] = None) -> Path:
    return (root or repo_root()) / "reports" / "plan_state" / mission_id


def read_root_mission_authority(root: Optional[Path] = None) -> Dict[str, Any]:
    path = root_mission_authority_path(root)
    if not path.is_file():
        raise FileNotFoundError(f"MISSION_AUTHORITY.yaml not found at {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "mission_authority" not in data:
        raise ValueError("MISSION_AUTHORITY.yaml must have a top-level 'mission_authority' key")
    return data["mission_authority"]


def validate_mission_authority(ma: Dict[str, Any]) -> List[str]:
    """Return a list of validation errors (empty list = valid)."""
    errors = []
    for field in REQUIRED_FIELDS:
        if field not in ma:
            errors.append(f"missing required field: {field}")
    for list_field in ("in_scope_outcomes", "out_of_scope_items", "mandatory_acceptance_criteria"):
        if list_field in ma and not isinstance(ma[list_field], list):
            errors.append(f"field must be a list: {list_field}")
    if "mission_locked" in ma and not isinstance(ma["mission_locked"], bool):
        errors.append("field must be a boolean: mission_locked")
    return errors


def archive_mission(
    mission_id: str,
    ma: Dict[str, Any],
    status: str,
    root: Optional[Path] = None,
) -> Path:
    """Write the durable per-mission snapshot. status is 'open' or 'closed'.

    Raises MissionIdCollisionError if a snapshot already exists at this
    mission_id whose content (ignoring the archive-status/timestamp fields
    every re-archive legitimately changes) differs from what's being written
    now -- previously this silently overwrote, which is the storage-layer
    reason a mission-id collision was invisible even after the fact.
    """
    out_dir = plan_state_dir(mission_id, root)
    out_path = out_dir / "mission_authority.yaml"
    if out_path.is_file():
        try:
            existing = yaml.safe_load(out_path.read_text(encoding="utf-8"))["mission_authority"]
        except Exception:  # noqa: BLE001
            existing = None
        if existing is not None:
            ignore_keys = {"_archive_status", "_archived_at", "_closed_at"}
            existing_cmp = {k: v for k, v in existing.items() if k not in ignore_keys}
            new_cmp = {k: v for k, v in ma.items() if k not in ignore_keys}
            if existing_cmp != new_cmp:
                raise MissionIdCollisionError(
                    f"archive_mission({mission_id!r}) refused: an existing archive at "
                    f"{out_path} has different content than what's being written now -- "
                    "this mission_id is already in use by different mission content. "
                    "Choose a different id (see mission_authority.py allocate)."
                )
    out_dir.mkdir(parents=True, exist_ok=True)

    snapshot = dict(ma)
    snapshot["_archive_status"] = status
    snapshot["_archived_at"] = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    out_path.write_text(
        yaml.safe_dump({"mission_authority": snapshot}, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return out_path


def cmd_open(args: argparse.Namespace) -> int:
    root = Path(args.root) if args.root else None
    try:
        ma = read_root_mission_authority(root)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 1

    errors = validate_mission_authority(ma)
    if errors:
        print("ERROR: MISSION_AUTHORITY.yaml failed validation:")
        for e in errors:
            print(f"  - {e}")
        return 1

    if ma.get("mission_id") != args.mission_id:
        print(
            f"ERROR: root MISSION_AUTHORITY.yaml mission_id is "
            f"{ma.get('mission_id')!r}, not {args.mission_id!r}. "
            "The root file must already contain this mission's contract "
            "before it can be archived — this script does not author the "
            "mission narrative."
        )
        return 1

    try:
        out_path = archive_mission(args.mission_id, ma, status="open", root=root)
    except MissionIdCollisionError as exc:
        print(f"ERROR: {exc}")
        return 1
    print(f"Archived mission {args.mission_id!r} (status: open) -> {out_path}")
    return 0


def cmd_close(args: argparse.Namespace) -> int:
    root = Path(args.root) if args.root else None
    archive_path = plan_state_dir(args.mission_id, root) / "mission_authority.yaml"
    if not archive_path.is_file():
        print(f"ERROR: no archived mission found for {args.mission_id!r} at {archive_path}")
        return 1

    data = yaml.safe_load(archive_path.read_text(encoding="utf-8"))
    ma = data["mission_authority"]
    ma["_archive_status"] = "closed"
    ma["_closed_at"] = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    archive_path.write_text(
        yaml.safe_dump({"mission_authority": ma}, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    print(f"Mission {args.mission_id!r} marked closed -> {archive_path}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    root = Path(args.root) if args.root else repo_root()
    plan_state_root = root / "reports" / "plan_state"
    if not plan_state_root.is_dir():
        print("No missions archived yet.")
        return 0

    rows = []
    for mission_dir in sorted(plan_state_root.iterdir()):
        archive_path = mission_dir / "mission_authority.yaml"
        if not archive_path.is_file():
            continue
        try:
            data = yaml.safe_load(archive_path.read_text(encoding="utf-8"))
            ma = data["mission_authority"]
        except Exception as exc:  # noqa: BLE001
            rows.append((mission_dir.name, "UNREADABLE", str(exc)))
            continue
        status = ma.get("_archive_status", "unknown")
        rows.append((ma.get("mission_id", mission_dir.name), status, ma.get("mission_summary", "")[:80]))

    if not rows:
        print("No missions archived yet.")
        return 0

    for mission_id, status, summary in rows:
        print(f"[{status:>6}] {mission_id} - {summary}")

    # ST-157: ledger-coverage cross-check. Flags any MT0NN-shaped mission id
    # this archive knows about that never went through `allocate`/`seed-ledger`
    # -- a bypass of the sanctioned minting path. Non-numeric slug ids are out
    # of scope (see mission_id_ledger.py) and never flagged.
    ledger = MissionIdLedger(repo_root=root)
    ledger_ids = {e.get("mission_id") for e in ledger.history()}
    uncovered = sorted(
        mission_id for mission_id, _status, _summary in rows
        if _MT_ID_RE.match(mission_id) and mission_id not in ledger_ids
    )
    if uncovered:
        print(f"\nLEDGER COVERAGE WARNING: {len(uncovered)} MT0NN-shaped mission id(s) "
              f"not found in {ledger.path} -- minted outside `allocate`/`seed-ledger`:")
        for mission_id in uncovered:
            print(f"  - {mission_id}")
    return 0


def _session_ledger_report(root: Path) -> List[Dict[str, Any]]:
    """Read-only summary of every reports/session-state/*.json manifest.

    Never invokes session_ledger.py's sweep/resolution machinery -- reads the
    raw files and reports their on-disk `status` field plus mtime-derived
    age, exactly as pass-1/pass-2 of this investigation did by hand. Age is
    informational only; session_ledger.py's own TTL logic is the source of
    truth for whether a manifest is actually stale.
    """
    session_dir = root / "reports" / "session-state"
    out: List[Dict[str, Any]] = []
    if not session_dir.is_dir():
        return out
    now = datetime.datetime.now(datetime.timezone.utc).timestamp()
    for f in sorted(session_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            out.append({"session_id": f.stem, "error": str(exc)})
            continue
        try:
            age_hours = round((now - f.stat().st_mtime) / 3600.0, 2)
        except OSError:
            age_hours = None
        out.append({
            "session_id": data.get("session_id", f.stem),
            "status": data.get("status", "?"),
            "age_hours_since_last_write": age_hours,
        })
    return out


def _skill_context_report(root: Path) -> Dict[str, Any]:
    """Read-only summary via `skill_context.py status --json` (RC1/RC2
    hardening, 2026-07-31) -- never touches the mutating loaders directly."""
    script = Path(__file__).resolve().parent / "skill_context.py"
    if not script.is_file():
        return {"error": f"skill_context.py not found at {script}"}
    full_env = dict(os.environ)
    full_env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
    try:
        result = subprocess.run(
            [sys.executable, str(script), "status", "--json", "--root", str(root)],
            cwd=str(root), capture_output=True, text=True, timeout=10, env=full_env,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        return {"error": str(exc)}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"error": f"unparseable output: {result.stdout!r} {result.stderr!r}"}


def _lock_report(root: Path) -> List[Dict[str, Any]]:
    """Read-only summary of every reports/locks/**/*.lock file.

    Re-checks PID liveness live via advisory_lock._pid_alive() rather than
    trusting mtime alone -- this is the one store of the three that CAN
    verify liveness, so the aggregator uses that capability instead of
    just reporting age like the other two.
    """
    locks_dir = root / "reports" / "locks"
    out: List[Dict[str, Any]] = []
    if not locks_dir.is_dir():
        return out
    now = datetime.datetime.now(datetime.timezone.utc).timestamp()
    for f in sorted(locks_dir.rglob("*.lock")):
        try:
            raw = f.read_text(encoding="utf-8").strip()
        except OSError as exc:
            out.append({"path": str(f.relative_to(root)), "error": str(exc)})
            continue
        entry: Dict[str, Any] = {"path": str(f.relative_to(root)).replace("\\", "/")}
        # advisory_lock.py's format: "{pid}:{timestamp}"
        parts = raw.split(":", 1)
        pid_str = parts[0] if parts else ""
        if pid_str.isdigit():
            pid = int(pid_str)
            alive = _pid_alive(pid)
            entry["pid"] = pid
            entry["liveness"] = "alive" if alive is True else ("dead" if alive is False else "indeterminate")
        else:
            entry["liveness"] = "unrecognized_format"
        try:
            entry["age_hours"] = round((now - f.stat().st_mtime) / 3600.0, 2)
        except OSError:
            entry["age_hours"] = None
        out.append(entry)
    return out


def build_liveness_report(root: Optional[Path] = None) -> Dict[str, Any]:
    """Aggregate all three liveness stores into one structured, read-only report.

    This is the automated replacement for the manual, undocumented
    cross-checking a mission handoff previously required (see the
    `conflicts_found` field in past root MISSION_AUTHORITY.yaml commits) --
    it does not decide anything, it only reports what each store currently
    shows, so an agent/human can make an informed handoff decision instead
    of hand-grepping reports/session-state/ and reports/skill-context/.
    """
    root = root or repo_root()
    return {
        "sessions": _session_ledger_report(root),
        "skill_context": _skill_context_report(root),
        "locks": _lock_report(root),
    }


def cmd_status(args: argparse.Namespace) -> int:
    """Print the aggregated liveness report. Read-only; always exits 0."""
    root = Path(args.root) if args.root else None
    report = build_liveness_report(root)

    if getattr(args, "json", False):
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    sessions = report["sessions"]
    active_sessions = [s for s in sessions if s.get("status") == "active"]
    print(f"Sessions: {len(sessions)} total, {len(active_sessions)} status=active")
    for s in sessions:
        if "error" in s:
            print(f"  {s['session_id']}: UNREADABLE ({s['error']})")
        else:
            print(f"  {s['session_id']}: status={s['status']} "
                  f"age={s['age_hours_since_last_write']}h since last write")

    sc = report["skill_context"]
    if "error" in sc:
        print(f"Skill context: ERROR ({sc['error']})")
    else:
        legacy = sc.get("legacy")
        print(f"Skill context (legacy): "
              f"{legacy['skill_id'] + (' [STALE]' if legacy['would_be_stale'] else ' [live]') if legacy else 'none'}")
        for sid, d in sorted(sc.get("sessions", {}).items()):
            flag = "STALE" if d.get("would_be_stale") else "live"
            print(f"  session {sid}: {d.get('skill_id')} [{flag}] age={d.get('age')}")

    locks = report["locks"]
    print(f"Locks: {len(locks)} file(s) under reports/locks/")
    for lk in locks:
        if "error" in lk:
            print(f"  {lk['path']}: UNREADABLE ({lk['error']})")
        else:
            print(f"  {lk['path']}: liveness={lk['liveness']} age={lk['age_hours']}h")

    return 0


def dedupe_missions_by_id(commit_mission_pairs: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    """Collapse consecutive (sha, mission_id) pairs sharing the same mission_id,
    keeping only the LAST sha of each run — commit count is not mission count
    (a mission can be amended across several commits without its mission_id
    changing). `commit_mission_pairs` must be in chronological (oldest-first)
    order. Returns one (sha, mission_id) pair per distinct mission, in the
    order each mission first appeared.
    """
    if not commit_mission_pairs:
        return []

    result: List[Tuple[str, str]] = []
    current_id = None
    last_sha_for_current = None
    for sha, mission_id in commit_mission_pairs:
        if mission_id != current_id:
            if current_id is not None:
                result.append((last_sha_for_current, current_id))
            current_id = mission_id
        last_sha_for_current = sha
    result.append((last_sha_for_current, current_id))
    return result


def cmd_backfill(args: argparse.Namespace) -> int:
    """One-time backfill: reconstruct reports/plan_state/{mission_id}/mission_authority.yaml
    for every mission_id ever recorded in MISSION_AUTHORITY.yaml's git history.
    The mission matching the CURRENT working-tree root file is marked open;
    every other reconstructed mission is closed.
    """
    root = Path(args.root) if args.root else repo_root()

    log_result = subprocess.run(
        ["git", "log", "--format=%H", "--follow", "--", "MISSION_AUTHORITY.yaml"],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=True,
    )
    shas = [line.strip() for line in log_result.stdout.splitlines() if line.strip()]
    shas.reverse()  # git log is newest-first; we need chronological (oldest-first)

    pairs: List[Tuple[str, str]] = []
    for sha in shas:
        show_result = subprocess.run(
            ["git", "show", f"{sha}:MISSION_AUTHORITY.yaml"],
            cwd=str(root),
            capture_output=True,
            text=True,
        )
        if show_result.returncode != 0:
            continue
        try:
            data = yaml.safe_load(show_result.stdout)
            mission_id = data["mission_authority"]["mission_id"]
        except Exception:  # noqa: BLE001
            continue
        pairs.append((sha, mission_id))

    deduped = dedupe_missions_by_id(pairs)

    try:
        current_ma = read_root_mission_authority(root)
        current_mission_id = current_ma.get("mission_id")
    except (FileNotFoundError, ValueError):
        current_mission_id = None

    archived = []
    for sha, mission_id in deduped:
        show_result = subprocess.run(
            ["git", "show", f"{sha}:MISSION_AUTHORITY.yaml"],
            cwd=str(root),
            capture_output=True,
            text=True,
        )
        data = yaml.safe_load(show_result.stdout)
        ma = data["mission_authority"]
        status = "open" if mission_id == current_mission_id else "closed"
        out_path = archive_mission(mission_id, ma, status=status, root=root)
        archived.append((mission_id, status, out_path))

    for mission_id, status, out_path in archived:
        print(f"Backfilled {mission_id!r} (status: {status}) -> {out_path}")
    return 0


# ---------------------------------------------------------------------------
# ST-157: mission-id ledger seed + allocate
# ---------------------------------------------------------------------------

def _git_history_mission_ids(root: Path) -> List[str]:
    """Every mission_id ever recorded in MISSION_AUTHORITY.yaml's git history
    (Track A). Reuses the same walk cmd_backfill already performs."""
    try:
        log_result = subprocess.run(
            ["git", "log", "--format=%H", "--follow", "--", "MISSION_AUTHORITY.yaml"],
            cwd=str(root), capture_output=True, text=True, encoding="utf-8", errors="replace", check=True,
        )
    except (subprocess.SubprocessError, OSError):
        return []
    shas = [line.strip() for line in log_result.stdout.splitlines() if line.strip()]
    ids: List[str] = []
    for sha in shas:
        show_result = subprocess.run(
            ["git", "show", f"{sha}:MISSION_AUTHORITY.yaml"],
            cwd=str(root), capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if show_result.returncode != 0:
            continue
        try:
            mission_id = yaml.safe_load(show_result.stdout)["mission_authority"]["mission_id"]
        except Exception:  # noqa: BLE001
            continue
        if isinstance(mission_id, str):
            ids.append(mission_id)
    return ids


def _local_plan_state_mission_ids(root: Path) -> List[str]:
    """Every mission_id with a LOCAL reports/plan_state/{mission_id}/ directory,
    scanned directly off disk rather than via git history.

    Reads the DIRECTORY NAME, not any file inside it: plan_state_dir() defines
    the directory as named exactly after the mission_id by construction, so
    this is authoritative regardless of what (if anything) is inside --
    deliberately NOT parsing mission_authority.yaml content, after a live
    2026-09-01 check found several real, currently-open missions whose
    reports/plan_state/{id}/ directory has no mission_authority.yaml at all
    (MT018-2026-08-01-PACKAGE-IDENTITY-COVERAGE: only taskcards.jsonl;
    MT038-2026-08-27-CI-HARDENING: only planning_evidence.md) or only a
    mission_authority.DRAFT.yaml (MT039-2026-08-28-PRODUCT-LAUNCH-REFRESH-EXECUTION)
    -- a content-parsing scan silently dropped all three. This is also the
    fix for the more general backfill gap: a mission can be hand-authored
    straight into this directory without ever touching the root
    MISSION_AUTHORITY.yaml (done deliberately when the root slot is occupied --
    see readme-refresh-trackb-and-followon-2026-09-01's own conflicts_found for
    a same-day example), so such a mission's id never appears in the root
    file's git history either. reports/plan_state/ is gitignored (local-only),
    so this source's completeness is bounded by what exists on THIS machine at
    seed time -- disclosed, not silently assumed complete.
    """
    plan_state_root = root / "reports" / "plan_state"
    if not plan_state_root.is_dir():
        return []
    return [d.name for d in sorted(plan_state_root.iterdir()) if d.is_dir()]


def _plans_missions_mission_ids(root: Path) -> List[str]:
    """Every mission id named by a file under plans/missions/*.md -- in
    practice the single richest source (covers missions whose
    reports/plan_state/ archive was never written at all, e.g. MT018's own
    GOVERNANCE-EVIDENCE-TRUST-FORENSICS half, confirmed live 2026-09-01 to
    have neither a mission_authority.yaml NOR a reports/plan_state/ directory
    -- only this file records it)."""
    missions_dir = root / "plans" / "missions"
    if not missions_dir.is_dir():
        return []
    return [p.stem for p in sorted(missions_dir.glob("*.md"))]


def _track_b_numbers(root: Path) -> List[int]:
    """Every MT0NN NUMBER referenced in /readme-refresh's own, entirely
    separate incident table (Track B) --
    docs/readme-refresh/plan-system-forensic-reconciliation.md.

    Returns bare numbers, not full mission_id strings: the table's own first
    column is just "MT021", never a full "MT021-YYYY-MM-DD-SLUG" id (confirmed
    live 2026-09-01 -- an earlier version of this function tried to feed that
    bare string straight to _MT_ID_RE, which requires a trailing hyphen and
    rejected every single one, silently dropping all 32 rows into the generic
    "non-numeric skipped" bucket with no error -- a false-green result: the
    output looked clean but every Track B number was actually unprotected).
    The caller synthesizes a placeholder id per number -- the goal here is
    reserving the NUMBER against future re-allocation, not reconstructing
    Track B's full historical mission narrative (out of scope; see
    mission_id_ledger.py's module docstring)."""
    doc_path = root / "docs" / "readme-refresh" / "plan-system-forensic-reconciliation.md"
    if not doc_path.is_file():
        return []
    row_re = re.compile(r"^\|\s*MT(\d+)\s*\|")
    numbers: List[int] = []
    for line in doc_path.read_text(encoding="utf-8").splitlines():
        m = row_re.match(line)
        if m:
            numbers.append(int(m.group(1)))
    return numbers


def cmd_seed_ledger(args: argparse.Namespace) -> int:
    """One-time (idempotent, safe to re-run) backfill of the mission-id
    ledger from every known source, BEFORE `allocate` is used for the first
    live mission -- otherwise the first allocate() call could re-mint an
    already-used number that simply hadn't been seeded yet."""
    root = Path(args.root) if args.root else repo_root()
    ledger = MissionIdLedger(repo_root=root)

    sources = [
        ("git-history-backfill", "main", _git_history_mission_ids(root)),
        ("local-plan-state-scan", "main", _local_plan_state_mission_ids(root)),
        ("plans-missions-scan", "main", _plans_missions_mission_ids(root)),
    ]

    seeded = 0
    already_present = 0
    non_numeric_skipped = 0
    for source, track, ids in sources:
        for mission_id in ids:
            m = _MT_ID_RE.match(mission_id)
            if not m:
                non_numeric_skipped += 1
                continue
            number = int(m.group(2))
            result = ledger.seed(number=number, mission_id=mission_id, track=track, source=source)
            if result is None:
                already_present += 1
            else:
                seeded += 1

    # Track B's table only ever gives a bare number (no full dated-slug id),
    # so it's handled separately from the _MT_ID_RE-shaped sources above --
    # reserve the NUMBER via a clearly-labeled placeholder id, so a future
    # allocate() can never re-mint it, without fabricating a fake historical
    # mission narrative this repo has no real record of.
    for number in _track_b_numbers(root):
        placeholder_id = f"MT{number:03d}-README-REFRESH-TRACK-B-PLACEHOLDER"
        # A real, already-recorded id for this number (from any source above)
        # takes precedence -- only reserve the placeholder if genuinely nothing
        # else already claims this number.
        if any(e.get("number") == number for e in ledger.history()):
            already_present += 1
            continue
        result = ledger.seed(number=number, mission_id=placeholder_id, track="readme-refresh", source="track-b-table-scan")
        if result is None:
            already_present += 1
        else:
            seeded += 1

    print(f"Seeded {seeded} new entr{'y' if seeded == 1 else 'ies'}, "
          f"{already_present} already present (idempotent no-op), "
          f"{non_numeric_skipped} non-numeric ids skipped (out of scope).")
    print(f"Ledger highest_number() is now: {ledger.highest_number()}")
    print(f"Ledger path: {ledger.path}")
    return 0


def cmd_allocate(args: argparse.Namespace) -> int:
    """Mint a new, collision-free numeric mission id. The ONLY sanctioned
    way to get a new MT0NN id -- never hand-pick one."""
    root = Path(args.root) if args.root else repo_root()
    ledger = MissionIdLedger(repo_root=root)
    mission_id = ledger.allocate(
        track=args.track, slug=args.slug, date=args.date, session_id=os.environ.get("AGENT_SESSION_ID"),
    )
    print(mission_id)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=None, help="Repo root override (for tests)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_open = sub.add_parser("open", help="Validate + archive the current root MISSION_AUTHORITY.yaml")
    p_open.add_argument("--mission-id", required=True)
    p_open.set_defaults(func=cmd_open)

    p_close = sub.add_parser("close", help="Mark an archived mission closed")
    p_close.add_argument("--mission-id", required=True)
    p_close.set_defaults(func=cmd_close)

    p_list = sub.add_parser("list", help="List all archived missions")
    p_list.set_defaults(func=cmd_list)

    p_backfill = sub.add_parser(
        "backfill",
        help="One-time: reconstruct archives for every mission in MISSION_AUTHORITY.yaml's git history",
    )
    p_backfill.set_defaults(func=cmd_backfill)

    p_status = sub.add_parser(
        "status",
        help="Read-only liveness aggregator (sessions, skill-context, locks) -- "
             "replaces manual conflicts_found investigation for mission handoffs",
    )
    p_status.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    p_status.set_defaults(func=cmd_status)

    p_seed = sub.add_parser(
        "seed-ledger",
        help="ST-157: one-time, idempotent backfill of the mission-id ledger from "
             "git history + local reports/plan_state/ + the readme-refresh Track B table. "
             "Run once, and verify its output, before the first live 'allocate' call.",
    )
    p_seed.set_defaults(func=cmd_seed_ledger)

    p_allocate = sub.add_parser(
        "allocate",
        help="ST-157: mint a new, collision-free numeric mission id. The only "
             "sanctioned way to get a new MT0NN id.",
    )
    p_allocate.add_argument("--track", required=True, help="e.g. 'main' or 'readme-refresh'")
    p_allocate.add_argument("--slug", required=True, help="Descriptive UPPER-CASE slug, e.g. EXAMPLE-MISSION")
    p_allocate.add_argument("--date", default=None, help="YYYY-MM-DD, defaults to today (UTC)")
    p_allocate.set_defaults(func=cmd_allocate)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
