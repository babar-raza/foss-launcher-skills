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
from taskcard_store import TaskcardStore  # noqa: E402

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
        # ValueError covers json.JSONDecodeError AND UnicodeDecodeError (invalid
        # UTF-8 is neither a JSONDecodeError nor an OSError -- it used to escape
        # and crash `status` for every session).
        except (ValueError, OSError) as exc:
            out.append({"session_id": f.stem, "error": _plan_state_error_text(exc)})
            continue
        if not isinstance(data, dict):
            # Valid JSON that is not an object (list/str/number/null/bool): `.get`
            # below used to raise AttributeError out of this whole store. Reported
            # like any other unreadable manifest, so one bad file never hides the rest.
            out.append({
                "session_id": f.stem,
                "error": f"manifest is not a JSON object (got {type(data).__name__})",
            })
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


_STALE_MISSION_THRESHOLD_DAYS = 7

# TC-GOV-02-01-FIX: a `recorded_at` / `_archived_at` more than this far ahead
# of "now" is "clearly future" and carries NO liveness signal. Accepting it
# would let one stray row (a bad writer, a wrong clock, a typo'd year) make an
# abandoned mission look permanently live -- a row ~10 years ahead used to give
# age_days=-3650 and stale=False. The 1-day slack covers ordinary clock skew and
# the worst real source of a legitimately future-looking stamp (a local time
# mislabelled `Z`; the maximum UTC offset is +14h) while bounding any masking
# of a genuinely stale mission to under a day.
_FUTURE_TIMESTAMP_TOLERANCE = datetime.timedelta(days=1)

# Upper bound on the message part of a plan_state error row (it is printed to a
# console and embedded in JSON -- keep it one short line, never a traceback).
_ERROR_TEXT_MAX_CHARS = 200


def _parse_iso_timestamp(value: Any) -> Optional[datetime.datetime]:
    """Parse an ISO-8601 timestamp in this repo's `...Z` idiom -- the exact
    format every `recorded_at`/`_archived_at` field in this codebase uses
    (see taskcard_store.py's `_now_iso()` / taskcard_cli.py's `_parse_iso()`,
    which this mirrors). Returns None for missing/unparseable input rather
    than raising -- this is a read-only liveness report, never a hard gate
    (RC1/RC2 convention already followed by the other 3 stores).

    Anything that is not a `str` is "no signal" and returns None: the schema
    (validate_taskcard_record) checks that `recorded_at` is present, not what
    type it is, so a row with an int/dict/list/bool value is a legal row. That
    includes `datetime` objects -- an UNQUOTED `_archived_at: 2026-09-17T...Z`
    in the archive yaml loads as one -- which are ignored explicitly rather
    than accepted (or, as before, discarded only by an accidental TypeError)."""
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError, OverflowError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt


def _usable_activity_timestamp(
    value: Any, now: datetime.datetime,
) -> Optional[datetime.datetime]:
    """`_parse_iso_timestamp()` plus the future-date rule: None unless `value`
    is a parseable string that is not more than _FUTURE_TIMESTAMP_TOLERANCE
    ahead of `now`. This is the only way a timestamp becomes a liveness signal."""
    dt = _parse_iso_timestamp(value)
    if dt is None or dt - now > _FUTURE_TIMESTAMP_TOLERANCE:
        return None
    return dt


def _plan_state_error_text(exc: BaseException) -> str:
    """`<ErrorClass>: <short message>` -- one line, ASCII-only, bounded. Never a
    traceback. ASCII-escaping matters: a YAML error quotes source text, and a
    non-ASCII character reaching a cp1252 console used to kill `status --json`
    with UnicodeEncodeError."""
    message = " ".join(str(exc).split()).encode("ascii", "backslashreplace").decode("ascii")
    if len(message) > _ERROR_TEXT_MAX_CHARS:
        message = message[: _ERROR_TEXT_MAX_CHARS - 3] + "..."
    return f"{type(exc).__name__}: {message}" if message else type(exc).__name__


def _plan_state_mission_row(
    mission_dir: Path, archive_path: Path, now: datetime.datetime,
) -> Dict[str, Any]:
    """Evaluate ONE mission directory into its report row. Raises on anything
    unreadable or malformed -- the caller (_plan_state_report) turns that into
    an error row for this mission only; nothing in here may leak to the others."""
    data = yaml.safe_load(archive_path.read_text(encoding="utf-8"))
    ma = data.get("mission_authority") if isinstance(data, dict) else None
    if not isinstance(ma, dict):
        raise ValueError("archive must contain a top-level 'mission_authority' mapping")

    # yaml can hand back any type (an unquoted 2026-09-17 is a datetime.date,
    # which json.dumps cannot serialise) -- keep both fields strings.
    mission_id = ma.get("mission_id")
    if not isinstance(mission_id, str) or not mission_id:
        mission_id = mission_dir.name
    archive_status = ma.get("_archive_status")
    if not isinstance(archive_status, str) or not archive_status:
        archive_status = "unknown"

    history = TaskcardStore(mission_id, plan_state_dir=mission_dir).read_history()
    recorded_ats = [
        dt for dt in (
            _usable_activity_timestamp(row.get("recorded_at"), now)
            for row in history if isinstance(row, dict)  # valid JSON != a taskcard row
        )
        if dt is not None
    ]

    if recorded_ats:
        last_activity_at = max(recorded_ats)
        last_activity_source = "taskcards"
    else:
        last_activity_at = _usable_activity_timestamp(ma.get("_archived_at"), now)
        last_activity_source = "archived_at" if last_activity_at is not None else "unknown"

    if last_activity_at is not None:
        # Clamped: a stamp inside the future tolerance is activity "just now".
        age_days: Optional[float] = max(0.0, (now - last_activity_at).total_seconds() / 86400.0)
    else:
        age_days = None

    stale = archive_status == "open" and (
        age_days is None or age_days >= _STALE_MISSION_THRESHOLD_DAYS
    )

    return {
        "mission_id": mission_id,
        "archive_status": archive_status,
        "last_activity_at": (
            last_activity_at.isoformat().replace("+00:00", "Z")
            if last_activity_at is not None else None
        ),
        "last_activity_source": last_activity_source,
        "age_days_since_last_activity": round(age_days, 2) if age_days is not None else None,
        "stale": stale,
    }


def _plan_state_report(
    root: Path, now: Optional[datetime.datetime] = None,
) -> List[Dict[str, Any]]:
    """Read-only summary of every reports/plan_state/{mission_id}/ mission,
    cross-referencing its own taskcards.jsonl activity -- the store
    build_liveness_report() was missing entirely before TC-GOV-02-01: it read
    session-state/skill-context/locks but never plan_state itself, so an
    open-but-abandoned mission (MT066 and >=9 others found live at plan-time,
    per REQ-GOV-02) produced no liveness signal at all. Mirrors cmd_list()'s
    own mission-directory walk rather than introducing a second one.

    For each archived mission directory (any `_archive_status`, not just
    "open" -- same as cmd_list()), reports:
      - mission_id: from the archived snapshot, falling back to the
        directory name (matches cmd_list()'s own fallback; also used when the
        snapshot's mission_id is not a string)
      - archive_status: this mission's `_archive_status` field, or "unknown"
        if absent or not a string (matches cmd_list()'s own default)
      - last_activity_at: max(recorded_at) across every taskcards.jsonl row
        for this mission (via TaskcardStore(...).read_history() -- read-only,
        never touches the write path or CAS guards), or, if the mission has
        never had a single usable taskcard timestamp, this archive's own
        `_archived_at` as a fallback anchor -- a mission opened and then never
        touched at all must not silently produce "no signal" instead of
        "stale".
      - last_activity_source: "taskcards" | "archived_at" | "unknown"
      - age_days_since_last_activity: float days between now and
        last_activity_at (never negative), or None if neither signal is
        available.
      - stale: True only for `_archive_status: open` missions whose
        last_activity_at is at least _STALE_MISSION_THRESHOLD_DAYS days old
        (`>=`: exactly 7 days is stale) OR entirely absent -- absence of any
        liveness signal for an open mission is treated as stale, not silently
        skipped, so this store fails toward surfacing a possibly-abandoned
        mission rather than missing it.

    What counts as a liveness signal (TC-GOV-02-01-FIX): only a `recorded_at`
    (or `_archived_at`) that is a parseable string and not more than
    _FUTURE_TIMESTAMP_TOLERANCE in the future. A non-string value, a
    datetime-typed yaml scalar, garbage, or a clearly-future stamp is "no
    signal" -- skipped individually, so the row's other timestamps still count.
    Naive timestamps are read as UTC. Rows in taskcards.jsonl that are valid
    JSON but not objects are skipped.

    Failure isolation: each mission is evaluated inside its own try/except. A
    mission whose archive or ledger is unreadable or malformed (bad yaml, a
    `mission_authority:` that is not a mapping, invalid UTF-8, an OSError)
    yields `{"mission_id": <dir name>, "error": "<ErrorClass>: <message>"}` --
    no `stale` key, since its staleness is unknowable -- and every other
    mission is still evaluated. One bad mission can never blind the detector
    for the rest; build_liveness_report() lists those ids as `plan_state_errors`.

    `now` is a test seam (tz-aware); production callers omit it.
    """
    plan_state_root = root / "reports" / "plan_state"
    out: List[Dict[str, Any]] = []
    if not plan_state_root.is_dir():
        return out
    if now is None:
        now = datetime.datetime.now(datetime.timezone.utc)
    for mission_dir in sorted(plan_state_root.iterdir()):
        archive_path = mission_dir / "mission_authority.yaml"
        if not archive_path.is_file():
            continue  # not a mission directory (e.g. mission_activation_log.jsonl)
        try:
            out.append(_plan_state_mission_row(mission_dir, archive_path, now))
        except Exception as exc:  # noqa: BLE001 -- isolate: one mission must never blind the rest
            out.append({"mission_id": mission_dir.name, "error": _plan_state_error_text(exc)})
    return out


def build_liveness_report(root: Optional[Path] = None) -> Dict[str, Any]:
    """Aggregate all four liveness stores into one structured, read-only report.

    This is the automated replacement for the manual, undocumented
    cross-checking a mission handoff previously required (see the
    `conflicts_found` field in past root MISSION_AUTHORITY.yaml commits) --
    it does not decide anything, it only reports what each store currently
    shows, so an agent/human can make an informed handoff decision instead
    of hand-grepping reports/session-state/ and reports/skill-context/.

    `plan_state` (TC-GOV-02-01) is the 4th store, added to close REQ-GOV-02:
    every mission with `_archive_status: open` and zero taskcards.jsonl
    activity for >=7 days now surfaces here as `stale_open_missions`,
    without a human having to think to check.

    `plan_state_errors` (TC-GOV-02-01-FIX) lists the missions that could not be
    evaluated at all (their `plan_state` row carries `error`, not `stale`). They
    are deliberately NOT in `stale_open_missions` -- their staleness is unknown,
    not established -- but they are never silently fine either: consumers must
    surface this list next to the stale one.
    """
    root = root or repo_root()
    plan_state_rows = _plan_state_report(root)
    return {
        "sessions": _session_ledger_report(root),
        "skill_context": _skill_context_report(root),
        "locks": _lock_report(root),
        "plan_state": plan_state_rows,
        "stale_open_missions": [
            row["mission_id"] for row in plan_state_rows if row.get("stale")
        ],
        "plan_state_errors": [
            row["mission_id"] for row in plan_state_rows if "error" in row
        ],
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

    stale_open_missions = report["stale_open_missions"]
    print(f"Stale open missions (>= {_STALE_MISSION_THRESHOLD_DAYS}d no taskcard activity): "
          f"{len(stale_open_missions)}")
    for row in report["plan_state"]:
        if row.get("stale"):
            print(f"  {row['mission_id']}: last_activity={row.get('last_activity_at')} "
                  f"({row.get('last_activity_source')}), "
                  f"age={row.get('age_days_since_last_activity')}d")

    # An errored mission is never silently fine: its staleness is unknown, so it
    # is not in the stale list above -- but it is counted and named here.
    plan_state_errors = report["plan_state_errors"]
    print(f"Unreadable plan_state missions (staleness UNKNOWN, not evaluated): "
          f"{len(plan_state_errors)}")
    for row in report["plan_state"]:
        if "error" in row:
            print(f"  {row['mission_id']}: {row['error']}")

    return 0


ACTIVATION_LOG_NAME = "mission_activation_log.jsonl"
_MIN_FORCE_REASON_LEN = 15

# TC-GOV-03-01 (REQ-GOV-03): a --force takeover must record what happens to
# the incumbent's remaining work, not just why the takeover is justified --
# the reason string alone (validated only for length) never captured this,
# which is the exact mechanism that left MT066 (and >=9 other missions, per
# TC-GOV-02-01's live liveness run) dangling open with no disposition.
_DISPOSITION_LITERAL_VALUES = {"will-close-after-current-task"}
_DISPOSITION_PREFIXES = ("parking-with-reason:", "handing-off-to:")


def _validate_disposition(disposition: Optional[str]) -> Optional[str]:
    """Return an error message if `disposition` is missing or malformed for a
    --force takeover, else None (valid). Accepted shapes:
      - the literal 'will-close-after-current-task'
      - 'parking-with-reason:<text>' with non-empty <text>
      - 'handing-off-to:<mission-id>' with non-empty <mission-id>
    A bare prefix with no real text after it is the same "narrative filler"
    failure mode the reason-length check already guards against one layer up.
    """
    if disposition is None or not disposition.strip():
        return (
            "ERROR: --force requires --disposition (what happens to the incumbent's "
            "remaining work) -- one of 'will-close-after-current-task', "
            "'parking-with-reason:<text>', or 'handing-off-to:<mission-id>'. A reason "
            "string alone no longer records this."
        )
    disposition = disposition.strip()
    if disposition in _DISPOSITION_LITERAL_VALUES:
        return None
    for prefix in _DISPOSITION_PREFIXES:
        if disposition.startswith(prefix):
            if disposition[len(prefix):].strip():
                return None
            return (
                f"ERROR: --disposition {disposition!r} is missing required text after "
                f"'{prefix}'."
            )
    return (
        f"ERROR: --disposition {disposition!r} is not a recognized shape. Use "
        "'will-close-after-current-task', 'parking-with-reason:<text>', or "
        "'handing-off-to:<mission-id>'."
    )


def _activation_log_path(root: Optional[Path] = None) -> Path:
    return (root or repo_root()) / "reports" / "plan_state" / ACTIVATION_LOG_NAME


def _append_activation_log(entry: Dict[str, Any], root: Optional[Path] = None) -> None:
    path = _activation_log_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = dict(entry)
    entry.setdefault(
        "logged_at", datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _incumbent_snapshot(mission_id: str, root: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Read a mission's archived snapshot, or None if it doesn't exist / is unreadable."""
    path = plan_state_dir(mission_id, root) / "mission_authority.yaml"
    if not path.is_file():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data.get("mission_authority")
    except Exception:  # noqa: BLE001
        return None


def cmd_activate(args: argparse.Namespace) -> int:
    """H1: the one sanctioned pre-flight gate for taking over the root
    MISSION_AUTHORITY.yaml slot (docs/workflows -- see
    reports/skill-gaps/2026-09-11-imaging-net-pipeline-hardening-prerequisites.md).

    Must run BEFORE hand-editing the root file to a new mission's narrative:
    it reads the CURRENT (pre-edit) root content to identify the incumbent,
    so it cannot recover the incumbent's identity after the edit already
    happened. It never writes MISSION_AUTHORITY.yaml itself -- narrative
    content stays human/agent-authored, per this module's existing design
    (see module docstring); this command only decides whether proceeding to
    edit it is currently sanctioned, and durably logs that decision.

    Same-mission-id resumption (args.mission_id already matches the root
    file's current mission_id) is an ungated fast path with zero liveness
    checks by design -- this is what a same-session-later-day resume needs
    (this mission's own 2026-09-11 situation), and what a naive lock-shaped
    design would have wrongly blocked.

    A genuine takeover of a DIFFERENT incumbent is refused if that
    incumbent's own archived snapshot is both `_archive_status: open` and
    `mission_locked: true`, unless --force is given with a real (non-empty,
    minimum-length) reason -- an unvalidated free-text reason would just
    reproduce the "schema-checked but never semantically enforced" defect
    (`mission_locked` itself, per this module's own history) that this
    command exists to close one layer up.

    TC-GOV-03-01 (REQ-GOV-03): --force also requires --disposition, recording
    what happens to the incumbent's remaining work (see
    _validate_disposition()) -- the reason string alone justified WHY a
    takeover happened but never recorded what became of the incumbent's own
    unfinished taskcards, which is the exact mechanism that left MT066 (and
    >=9 other missions) dangling open with no disposition. Persisted as an
    additive field on the existing _append_activation_log() entry. Does not
    apply to the same-mission-id resumption fast path above, which never
    reaches this validation at all.
    """
    root = Path(args.root) if args.root else None
    root_path = root_mission_authority_path(root)

    current_id: Optional[str] = None
    if root_path.is_file():
        try:
            current_ma = read_root_mission_authority(root)
            current_id = current_ma.get("mission_id")
        except (FileNotFoundError, ValueError) as exc:
            print(
                f"WARNING: could not read current root MISSION_AUTHORITY.yaml ({exc}); "
                "treating as no incumbent."
            )

    if current_id is None:
        _append_activation_log(
            {
                "mission_id": args.mission_id,
                "previous_mission_id": None,
                "action": "initial",
                "session_id": args.session_id,
            },
            root,
        )
        print(
            f"No incumbent found at the root slot -- {args.mission_id!r} may proceed "
            "(edit MISSION_AUTHORITY.yaml, then run `open`)."
        )
        return 0

    if current_id == args.mission_id:
        _append_activation_log(
            {
                "mission_id": args.mission_id,
                "previous_mission_id": current_id,
                "action": "resume",
                "session_id": args.session_id,
            },
            root,
        )
        print(
            f"Resuming {args.mission_id!r} -- already the root slot's current mission; "
            "no takeover check needed."
        )
        return 0

    incumbent = _incumbent_snapshot(current_id, root)
    incumbent_locked_open = bool(
        incumbent is not None
        and incumbent.get("_archive_status") == "open"
        and incumbent.get("mission_locked") is True
    )

    if incumbent_locked_open and not args.force:
        print(
            f"ERROR: root slot is held by {current_id!r}, which is mission_locked: true and "
            f"_archive_status: open (still active by every signal this repo tracks). Refusing "
            f"to let {args.mission_id!r} take over without --force \"<reason>\". Root file "
            "untouched. Run `mission_authority.py status` to see what else is live, or resolve "
            f"{current_id!r} (close it) first."
        )
        return 1

    disposition: Optional[str] = None
    if args.force:
        reason = args.force.strip()
        if len(reason) < _MIN_FORCE_REASON_LEN:
            print(
                f"ERROR: --force reason is too short ({len(reason)} chars, need >= "
                f"{_MIN_FORCE_REASON_LEN}) to be a real justification, not narrative filler. "
                "Cite a report/taskcard/plan path."
            )
            return 1

        disposition_error = _validate_disposition(getattr(args, "disposition", None))
        if disposition_error:
            print(disposition_error)
            return 1
        disposition = args.disposition.strip()

    _append_activation_log(
        {
            "mission_id": args.mission_id,
            "previous_mission_id": current_id,
            "action": "takeover",
            "incumbent_locked_open": incumbent_locked_open,
            "force_reason": args.force.strip() if args.force else None,
            "disposition": disposition,
            "session_id": args.session_id,
        },
        root,
    )
    print(
        f"{args.mission_id!r} may take over the root slot from {current_id!r} "
        f"({'forced over a locked/open incumbent' if incumbent_locked_open else 'incumbent not locked/open'}). "
        "Edit MISSION_AUTHORITY.yaml to the new mission's content, then run `open`."
    )
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
    mission_id_ledger.py's module docstring).

    Extracts every "MT\\d+" token from the row's first cell, not just a bare
    "MT034" -- found live 2026-09-11 (ST-194 independent verification) that a
    prior version of this function's regex required the number to be
    IMMEDIATELY followed by the closing pipe, silently dropping any row whose
    first cell carries trailing text (e.g. "MT034 (+ Phase 2)", "MT015
    (dependency)") or names more than one number in one cell (e.g.
    "MT043/MT044") -- the exact same false-green failure shape as the
    bare-vs-dated-slug bug this docstring already describes, just a second,
    independently-discovered instance of it in the same function. Scoped to
    the first cell only (not the whole line) so a Notes-column mention of an
    unrelated number elsewhere in the row (e.g. "restored by MT056" in a
    DIFFERENT row's notes) is never picked up."""
    doc_path = root / "docs" / "readme-refresh" / "plan-system-forensic-reconciliation.md"
    if not doc_path.is_file():
        return []
    cell_re = re.compile(r"^\|\s*([^|]+?)\s*\|")
    number_re = re.compile(r"MT(\d+)")
    numbers: List[int] = []
    for line in doc_path.read_text(encoding="utf-8").splitlines():
        m = cell_re.match(line)
        if not m:
            continue
        first_cell = m.group(1)
        if not first_cell.upper().startswith("MT"):
            continue
        numbers.extend(int(n) for n in number_re.findall(first_cell))
    return numbers


# Historical off-the-books mission numbers with NO full dated-slug id anywhere
# in the repo (no plans/missions/*.md file, no reports/plan_state/ dir, no
# MISSION_AUTHORITY.yaml entry) -- invisible to every source above AND to the
# Track B table. Found live 2026-09-11 while investigating the MT041-067
# duplicate-numbered-mission finding: MT021's second, real instance
# ("Discovery health gate enforcement", commit a30d6a0ae9) exists only as a
# bare "MT021" mention in that commit message and in
# reports/skill-gaps/2026-08-05-discovery-health-gate-enforcement.md's own
# title line -- there is no real dated-slug id to record, so (like Track B) a
# labeled placeholder is seeded instead of one.
#
# Deliberately a hard-coded list, not a generic content scanner: a scan of
# reports/skill-gaps/*.md for any "MT\d+" mention was tried and rejected
# while building this fix -- most hits there are narrative references to
# missions that already have a real id recorded elsewhere (MT013, MT015,
# MT018, MT020, MT022, MT029, MT033, MT037, MT064, ...), and seeding a
# placeholder for every mention would fabricate false "collisions" against
# those already-correctly-recorded missions. Extend this list by hand, citing
# the source, if another genuinely off-the-books case like this is found.
#
# Each entry's citation file is checked to exist under `root` before it is
# seeded (mirroring every other source function's root-relative disk read) --
# this keeps the list from unconditionally polluting an unrelated tmp_path
# test fixture that never created that evidence file.
_KNOWN_OFF_THE_BOOKS_MISSIONS: List[Tuple[int, str, str]] = [
    # (number, placeholder_id, citation_path_relative_to_root)
    (21, "MT021-2026-08-05-DISCOVERY-HEALTH-GATE-ENFORCEMENT-OFF-THE-BOOKS-PLACEHOLDER",
     "reports/skill-gaps/2026-08-05-discovery-health-gate-enforcement.md"),
]


def _known_off_the_books_missions(root: Path) -> List[Tuple[int, str]]:
    """Filter _KNOWN_OFF_THE_BOOKS_MISSIONS to entries whose citation file
    actually exists under `root` -- so this list only ever seeds something
    into a repo that genuinely has the cited evidence on disk."""
    return [
        (number, placeholder_id)
        for number, placeholder_id, citation in _KNOWN_OFF_THE_BOOKS_MISSIONS
        if (root / citation).is_file()
    ]


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
    #
    # Seed unconditionally: ledger.seed() is already idempotent per exact
    # mission_id (has_id() check), which is sufficient to avoid double-
    # reserving this number. A prior version of this loop additionally
    # skipped seeding whenever ANY entry (from any track) already claimed the
    # number -- that avoided a redundant reservation, but it also meant a
    # genuine main-vs-Track-B collision (a real main-track mission and a real
    # Track-B mission independently claiming the same number) was silently
    # swallowed instead of disclosed -- the opposite of what this ledger
    # exists to guarantee. Confirmed live 2026-09-11: MT038/MT039 each have a
    # real Track-B mission that this skip condition alone was hiding; MT034's
    # own Track-B collision needed BOTH this fix and the _track_b_numbers()
    # regex fix above (its row is "MT034 (+ Phase 2)", which the old regex
    # never even captured as a candidate number in the first place).
    for number in _track_b_numbers(root):
        placeholder_id = f"MT{number:03d}-README-REFRESH-TRACK-B-PLACEHOLDER"
        result = ledger.seed(number=number, mission_id=placeholder_id, track="readme-refresh", source="track-b-table-scan")
        if result is None:
            already_present += 1
        else:
            seeded += 1

    # Known off-the-books collisions (Mechanism 3) -- see
    # _KNOWN_OFF_THE_BOOKS_MISSIONS's own docstring for why this is a small,
    # explicit, cited list rather than a generic content scanner.
    for number, placeholder_id in _known_off_the_books_missions(root):
        result = ledger.seed(number=number, mission_id=placeholder_id, track="main", source="off-the-books-backfill")
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

    p_activate = sub.add_parser(
        "activate",
        help="H1: pre-flight consent gate for taking over the root MISSION_AUTHORITY.yaml slot. "
             "Run BEFORE hand-editing the root file. Same-mission-id resumption is an ungated "
             "fast path; a takeover of a locked+open incumbent requires --force with a real reason.",
    )
    p_activate.add_argument("--mission-id", required=True)
    p_activate.add_argument(
        "--force", default=None, metavar="REASON",
        help="Required to take over a mission_locked:true, _archive_status:open incumbent.",
    )
    p_activate.add_argument(
        "--disposition", default=None, metavar="DISPOSITION",
        help="Required with --force: what happens to the incumbent's remaining work. One "
             "of 'will-close-after-current-task', 'parking-with-reason:<text>', or "
             "'handing-off-to:<mission-id>'.",
    )
    p_activate.add_argument(
        "--session-id", default=os.environ.get("AGENT_SESSION_ID"),
        help="Recorded in the activation log (default: $AGENT_SESSION_ID)",
    )
    p_activate.set_defaults(func=cmd_activate)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
