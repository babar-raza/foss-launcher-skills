"""skill_context.py — Active-skill state machine for governance enforcement.

Tracks which skill is currently active via a marker file at
``reports/skill-context/ACTIVE.json``.  PreToolUse hooks read this marker
to verify that governed file edits happen inside a skill context.

Usage:
  # Start a skill context (typically at the top of a skill's Steps)
  python scripts/pipeline/commands/governance/skill_context.py begin \\
    --skill S-20 --scope "content/docs.aspose.org/en/words/python/*"

  # Check whether a file is within the active scope
  python scripts/pipeline/commands/governance/skill_context.py check --file <path>

  # Print the current active skill (exit 2 if none)
  python scripts/pipeline/commands/governance/skill_context.py current

  # End the skill context
  python scripts/pipeline/commands/governance/skill_context.py end --skill S-20 --status completed

  # Create a gap-approved temporary context (30-min TTL)
  python scripts/pipeline/commands/governance/skill_context.py gap \\
    --task "description" --report reports/skill-gaps/2026-04-16-foo.md

Exit codes:
  0  success / file in scope
  1  failure / file out of scope / validation error
  2  no active context
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile

_LIB_DIR = str(Path(__file__).resolve().parents[2] / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from path_utils import repo_rel
from advisory_lock import FileLock

_ENV_SESSION_ID = "AGENT_SESSION_ID"

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent  # commands/governance/ -> commands/ -> pipeline/ -> scripts/ -> repo
_REPO_ROOT = _DEFAULT_REPO_ROOT
_CONTEXT_DIR = _REPO_ROOT / "reports" / "skill-context"
_ACTIVE_FILE = _CONTEXT_DIR / "ACTIVE.json"
_HISTORY_DIR = _CONTEXT_DIR / "history"
# RPR-G-03 (§2.5 SW-1) + HARDEN-A2: per-session context directory. A session id
# comes from --session-id or the AGENT_SESSION_ID env var (the default path for
# any properly-started session), giving each session its own file so concurrent
# sessions never clobber a single global ACTIVE.json. Callers with NO identity at
# all fall back to the legacy single-file path — now fail-closed: a live context
# for a different skill is a named conflict (exit 3), never a silent supersede.
_ACTIVE_DIR = _CONTEXT_DIR / "active"


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Override module-level path constants for testing."""
    global _REPO_ROOT, _CONTEXT_DIR, _ACTIVE_FILE, _HISTORY_DIR, _ACTIVE_DIR
    _REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    _CONTEXT_DIR = _REPO_ROOT / "reports" / "skill-context"
    _ACTIVE_FILE = _CONTEXT_DIR / "ACTIVE.json"
    _HISTORY_DIR = _CONTEXT_DIR / "history"
    _ACTIVE_DIR = _CONTEXT_DIR / "active"

# Stale-context guard: auto-expire after this duration
_MAX_CONTEXT_AGE = timedelta(hours=2)
_GAP_TTL = timedelta(minutes=30)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _load_active() -> dict | None:
    """Load ACTIVE.json if it exists and is not stale. Returns None if absent or expired."""
    if not _ACTIVE_FILE.exists():
        return None
    try:
        with open(_ACTIVE_FILE, encoding="utf-8") as f:
            record = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    # Check staleness
    started = record.get("started_at", "")
    try:
        start_dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        # Unparseable timestamp — treat as stale
        _archive_stale(record)
        return None

    # Check TTL for gap-approved contexts
    if record.get("context_type") == "gap_approved":
        ttl = _GAP_TTL
    else:
        ttl = _MAX_CONTEXT_AGE

    if _now() - start_dt > ttl:
        _archive_stale(record)
        return None

    return record


def _legacy_lock() -> FileLock:
    """Lock guarding the legacy single-file ACTIVE.json read-modify-write
    (HARDEN-A2 — this was a plain unlocked load/decide/save before)."""
    return FileLock(str(_ACTIVE_FILE) + ".lock", timeout=10.0)


def _save_active(record: dict) -> None:
    _CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", delete=False,
                            dir=_CONTEXT_DIR, suffix=".tmp") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)
        f.write("\n")
        temp_path = Path(f.name)
    temp_path.replace(_ACTIVE_FILE)


def _archive(record: dict, status: str = "completed", *, remove_active: bool = True) -> None:
    """Move a context record to history.

    remove_active=False is used when archiving a PER-SESSION context (RPR-G-03): that
    record does not live in the legacy ACTIVE.json, so removing ACTIVE.json would destroy
    an unrelated session's live context. The caller unlinks its own session file instead.
    """
    _HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    record["ended_at"] = _now().isoformat().replace("+00:00", "Z")
    record["end_status"] = status
    ts = _now().strftime("%Y%m%d-%H%M%S")
    skill = record.get("skill_id", "unknown")
    out = _HISTORY_DIR / f"{ts}-{skill}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)
        f.write("\n")
    if remove_active and _ACTIVE_FILE.exists():
        # F4 guard: only unlink ACTIVE.json if it still holds the record being
        # archived. An un-locked reader (check/current) archiving a stale record
        # could otherwise delete a fresh context a locked begin just wrote.
        try:
            current = json.loads(_ACTIVE_FILE.read_text(encoding="utf-8"))
            matches = (current.get("skill_id") == record.get("skill_id")
                       and current.get("started_at") == record.get("started_at"))
        except (json.JSONDecodeError, OSError):
            matches = True  # unreadable/corrupt — removing it is the safe outcome
        if matches:
            _ACTIVE_FILE.unlink()


def _archive_stale(record: dict) -> None:
    """Archive a stale context (expired TTL)."""
    _archive(record, status="stale_expired")


def _normalize_path(p: str) -> str:
    """Normalize a path to forward-slash repo-relative form."""
    p = p.replace("\\", "/")
    # Strip absolute prefix if present
    try:
        rel = str(Path(p).resolve().relative_to(_REPO_ROOT.resolve()))
        return rel.replace("\\", "/")
    except (ValueError, OSError):
        return p


def _file_in_scope(file_path: str, scope_patterns: list[str]) -> bool:
    """Check if a file matches any scope pattern (glob-style)."""
    normalized = _normalize_path(file_path)
    for pattern in scope_patterns:
        if fnmatch.fnmatch(normalized, pattern):
            return True
    return False


# ---------------------------------------------------------------------------
# RPR-G-03: optimistic-concurrency-control primitives (per-session contexts)
# ---------------------------------------------------------------------------

def _patterns_overlap(a: str, b: str) -> bool:
    """True if two scope glob patterns could match a common path.

    `*` (scope-everything) overlaps anything. Otherwise two patterns overlap if one
    matches the other as a literal (a concrete path in one scope matched by the other's
    glob), or they are identical. This is deliberately conservative: it errs toward
    declaring an overlap, because a false "conflict" is a safe stop while a missed overlap
    is exactly the silent-clobber this fixes.
    """
    if a == "*" or b == "*":
        return True
    if a == b:
        return True
    return fnmatch.fnmatch(a, b) or fnmatch.fnmatch(b, a)


def scope_overlap(scope_a: list[str], scope_b: list[str]) -> bool:
    """True if any pattern in scope_a overlaps any pattern in scope_b."""
    return any(_patterns_overlap(pa, pb) for pa in scope_a for pb in scope_b)


def _derive_session_id(explicit: "str | None") -> "str | None":
    """Return the session id: explicit arg, else AGENT_SESSION_ID env, else None.

    HARDEN-A2 flips RPR-G-03 from opt-in to default: any session that exports
    AGENT_SESSION_ID (the convention session-start now documents) gets per-session
    context isolation automatically — no flag needed. A stable id must come from
    the caller because begin/end and the edit hook run in separate processes and
    cannot share a PID. With neither arg nor env, the caller uses the legacy
    global ACTIVE.json path (backward compatible, now fail-closed on conflicts).
    """
    value = explicit or os.environ.get(_ENV_SESSION_ID, "").strip() or None
    if value:
        return "".join(c if (c.isalnum() or c in "-_") else "-" for c in value)[:64]
    return None


def _session_context_path(session_id: str) -> Path:
    return _ACTIVE_DIR / f"{session_id}.json"


def _record_is_stale(record: dict) -> bool:
    started = record.get("started_at", "")
    try:
        start_dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return True
    ttl = _GAP_TTL if record.get("context_type") == "gap_approved" else _MAX_CONTEXT_AGE
    return _now() - start_dt > ttl


def _load_session_contexts(exclude: "str | None" = None) -> dict:
    """Return {session_id: record} for every non-stale per-session context.

    Stale files self-expire (archived) here, reusing the same TTL as the legacy path.
    """
    out: dict = {}
    if not _ACTIVE_DIR.exists():
        return out
    for p in sorted(_ACTIVE_DIR.glob("*.json")):
        sid = p.stem
        if exclude is not None and sid == exclude:
            continue
        try:
            record = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if _record_is_stale(record):
            # remove_active=False: this record lives in its own session file, NOT in the
            # legacy ACTIVE.json — archiving it must never delete another session's context.
            _archive(record, status="stale_expired", remove_active=False)
            try:
                p.unlink()
            except OSError:
                pass
            continue
        out[sid] = record
    return out


def _save_session_context(session_id: str, record: dict) -> None:
    _ACTIVE_DIR.mkdir(parents=True, exist_ok=True)
    with open(_session_context_path(session_id), "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)
        f.write("\n")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_begin(args: argparse.Namespace) -> int:
    """Start a new skill context."""
    # DAR prerequisite gate — enforced by default (SR-04).
    # Use --skip-dar for bootstrap/recovery only.
    skip_dar = getattr(args, "skip_dar", False)
    if not skip_dar:
        dar_script = _REPO_ROOT / "scripts" / "pipeline" / "commands" / "governance" / "check_dar_prerequisites.py"
        if dar_script.exists():
            result = subprocess.run(
                [sys.executable, str(dar_script), "--skill", args.skill],
                capture_output=False,
            )
            if result.returncode == 1:
                print(
                    f"DAR gate blocked: skill {args.skill} prerequisites not satisfied. "
                    "Run required upstream skills first.",
                    file=sys.stderr,
                )
                return 1
        else:
            print(
                f"WARN: check_dar_prerequisites.py not found at {dar_script} -- skipping DAR check",
                file=sys.stderr,
            )

    scope = [s.strip() for s in args.scope.split(",") if s.strip()] if args.scope else ["*"]
    session_id = _derive_session_id(getattr(args, "session_id", None))

    # RPR-G-03 (§2.5 SW-1): per-session OCC path. Opt-in via --session-id so every existing
    # caller keeps the legacy behavior byte-for-byte. Instead of silently superseding whatever
    # context happens to be active, a scope OVERLAP with another live session is a named,
    # blocking conflict; non-overlapping sessions coexist.
    if session_id:
        others = _load_session_contexts(exclude=session_id)
        for other_sid, other in others.items():
            if scope_overlap(scope, other.get("scope_patterns", ["*"])):
                print(
                    f"CONFLICT: session {other_sid!r} (skill {other.get('skill_id')}) already holds an "
                    f"active context whose scope overlaps {scope}. Refusing to supersede it silently.\n"
                    f"  Their scope: {other.get('scope_patterns')}\n"
                    f"  Your scope:  {scope}\n"
                    f"Wait for that session to end, or narrow your scope so the two do not overlap.",
                    file=sys.stderr,
                )
                return 3
        prior = _load_session_contexts().get(session_id)
        if prior:
            # Re-begin within the SAME session replaces its own context (not a conflict).
            _archive(prior, status="superseded_same_session", remove_active=False)
        record = {
            "skill_id": args.skill,
            "context_type": "skill",
            "scope_patterns": scope,
            "started_at": _now().isoformat().replace("+00:00", "Z"),
            "session_id": session_id,
        }
        _save_session_context(session_id, record)
        coexisting = sorted(others)
        suffix = f"; coexisting sessions: {coexisting}" if coexisting else ""
        print(f"Skill context started: {args.skill} (scope: {scope}; session: {session_id}{suffix})")
        return 0

    # ---- Legacy single-context path (no --session-id and no AGENT_SESSION_ID) ----
    # HARDEN-A2: the old behavior silently superseded whatever live context existed
    # — the exact clobber that let one session end/overwrite another's governance
    # state. Now: a live context for a DIFFERENT skill is a named conflict (exit 3).
    # A live context for the SAME skill is superseded (the standard re-begin loop —
    # scope re-arms before every edit — is single-session and must keep working).
    # The whole load/decide/save is under the legacy lock (was unlocked before).
    with _legacy_lock():
        existing = _load_active()
        if existing and existing.get("skill_id") != args.skill:
            print(
                f"CONFLICT: a live context for {existing.get('skill_id')} "
                f"(scope: {existing.get('scope_patterns')}) already exists and this begin "
                f"({args.skill}) has no session identity. Refusing to supersede it silently.\n"
                f"Fix: export {_ENV_SESSION_ID}=<your-session-id> (or pass --session-id) so "
                f"contexts are per-session, or end the other context first.",
                file=sys.stderr,
            )
            return 3
        if existing:
            _archive(existing, status="superseded_same_skill")

        record = {
            "skill_id": args.skill,
            "context_type": "skill",
            "scope_patterns": scope,
            "started_at": _now().isoformat().replace("+00:00", "Z"),
        }
        _save_active(record)
    print(f"Skill context started: {args.skill} (scope: {scope})")
    return 0


def cmd_end(args: argparse.Namespace) -> int:
    """End the active skill context."""
    session_id = _derive_session_id(getattr(args, "session_id", None))

    # RPR-G-03: a session ends its OWN context only — it can no longer end (or be ended by)
    # an unrelated concurrent session's context, which is the other half of the SW-1 race.
    if session_id:
        record = _load_session_contexts().get(session_id)
        if not record:
            print(f"WARNING: No active skill context to end for session {session_id}.", file=sys.stderr)
            return 0
        if record.get("skill_id") != args.skill:
            print(f"WARNING: Session {session_id} holds {record.get('skill_id')}, not {args.skill}. "
                  f"Ending anyway.", file=sys.stderr)
        _archive(record, status=args.status, remove_active=False)
        try:
            _session_context_path(session_id).unlink()
        except OSError:
            pass
        print(f"Skill context ended: {args.skill} ({args.status}; session: {session_id})")
        return 0

    # ---- Legacy single-context path (now under the legacy lock) ----
    with _legacy_lock():
        active = _load_active()
        if not active:
            print("WARNING: No active skill context to end.", file=sys.stderr)
            return 0

        if active.get("skill_id") != args.skill:
            print(f"WARNING: Active skill is {active.get('skill_id')}, not {args.skill}. Ending anyway.",
                  file=sys.stderr)

        _archive(active, status=args.status)
    print(f"Skill context ended: {args.skill} ({args.status})")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    """Check if a file is within the active skill context scope. Exit 0=in scope, 1=out, 2=no context.

    RPR-G-03: when --session-id is supplied, only THAT session's context is consulted
    (true per-session isolation). Without it, the legacy ACTIVE.json is checked first —
    byte-identical to prior behavior — and per-session contexts are consulted only as an
    additional allow source, so a session using the OCC path is not wrongly blocked by a
    hook that does not know its id. With no session files present, behavior is unchanged.
    """
    session_id = _derive_session_id(getattr(args, "session_id", None))
    if session_id:
        record = _load_session_contexts().get(session_id)
        if not record:
            print(f"No active skill context for session {session_id}.", file=sys.stderr)
            return 2
        if _file_in_scope(args.file, record.get("scope_patterns", [])):
            return 0
        print(f"File {args.file} is outside session {session_id} skill "
              f"{record.get('skill_id')} scope.", file=sys.stderr)
        return 1

    # ---- Legacy path first (unchanged) ----
    active = _load_active()
    if active and _file_in_scope(args.file, active.get("scope_patterns", [])):
        return 0

    # Additionally honor any live per-session context that covers this file.
    for sid, record in _load_session_contexts().items():
        if _file_in_scope(args.file, record.get("scope_patterns", [])):
            return 0

    if not active:
        print("No active skill context.", file=sys.stderr)
        return 2
    print(f"File {args.file} is outside active skill {active.get('skill_id')} scope.", file=sys.stderr)
    return 1


def cmd_current(args: argparse.Namespace) -> int:
    """Print current active skill ID. Exit 2 if no active context.

    Session-aware (HARDEN-A2): with an explicit --session-id or AGENT_SESSION_ID
    env, reports THAT session's context; otherwise the legacy ACTIVE.json.
    """
    session_id = _derive_session_id(getattr(args, "session_id", None))
    if session_id:
        record = _load_session_contexts().get(session_id)
        if not record:
            return 2
        print(f"{record.get('skill_id', 'unknown')} ({record.get('context_type', 'skill')})")
        return 0

    active = _load_active()
    if not active:
        return 2

    skill = active.get("skill_id", "unknown")
    ctx_type = active.get("context_type", "skill")
    print(f"{skill} ({ctx_type})")
    return 0


def cmd_gap(args: argparse.Namespace) -> int:
    """Create a temporary gap-approved context with 30-min TTL."""
    if not args.report:
        print("ERROR: --report is required for gap-approved contexts.", file=sys.stderr)
        return 1

    # Verify the gap report exists
    report_path = Path(args.report)
    if not report_path.exists():
        # Try repo-relative
        report_path = _REPO_ROOT / args.report
    if not report_path.exists():
        print(f"ERROR: Gap report not found: {args.report}", file=sys.stderr)
        return 1

    scope = [s.strip() for s in args.scope.split(",") if s.strip()] if args.scope else ["*"]

    record = {
        "skill_id": "GAP-APPROVED",
        "context_type": "gap_approved",
        "task": args.task,
        "gap_report": str(report_path),
        "scope_patterns": scope,
        "started_at": _now().isoformat().replace("+00:00", "Z"),
        "ttl_minutes": 30,
    }

    # F5: gap contexts follow the same identity/conflict rules as begin — the
    # old path silently superseded ANY live context (the exact clobber class A2
    # eliminated on begin), and ignored session identity entirely.
    session_id = _derive_session_id(getattr(args, "session_id", None))
    if session_id:
        others = _load_session_contexts(exclude=session_id)
        for other_sid, other in others.items():
            if scope_overlap(scope, other.get("scope_patterns", ["*"])):
                print(
                    f"CONFLICT: session {other_sid!r} (skill {other.get('skill_id')}) holds a live "
                    f"context overlapping this gap scope {scope}. Refusing to supersede it.",
                    file=sys.stderr,
                )
                return 3
        prior = _load_session_contexts().get(session_id)
        if prior:
            _archive(prior, status="superseded_by_gap", remove_active=False)
        record["session_id"] = session_id
        _save_session_context(session_id, record)
        print(f"Gap-approved context started (30-min TTL; session: {session_id}): {args.task}")
        print(f"  Report: {args.report}")
        return 0

    with _legacy_lock():
        existing = _load_active()
        if existing and existing.get("skill_id") not in (None, "GAP-APPROVED"):
            print(
                f"CONFLICT: a live context for {existing.get('skill_id')} exists and this gap "
                f"request has no session identity. Refusing to supersede it silently.\n"
                f"Fix: export {_ENV_SESSION_ID}=<your-session-id> (or pass --session-id), or "
                f"end the other context first.",
                file=sys.stderr,
            )
            return 3
        if existing:
            _archive(existing, status="superseded_by_gap")
        _save_active(record)
    print(f"Gap-approved context started (30-min TTL): {args.task}")
    print(f"  Report: {args.report}")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="skill_context",
        description="Active-skill state machine for governance enforcement.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # begin
    p_begin = sub.add_parser("begin", help="Start a skill context")
    p_begin.add_argument("--skill", required=True, help="Skill ID (e.g. S-20)")
    p_begin.add_argument("--scope", default="*",
                         help="Comma-separated glob patterns for allowed file paths")
    p_begin.add_argument("--skip-dar", action="store_true", dest="skip_dar",
                         help="Skip DAR prerequisite check (bootstrap/recovery only)")
    # Backwards compatibility: --check-dar is a no-op (DAR is now the default)
    p_begin.add_argument("--check-dar", action="store_true", dest="check_dar_legacy",
                         help=argparse.SUPPRESS)
    # RPR-G-03: opt-in per-session OCC. Omit for legacy single-ACTIVE.json behavior.
    p_begin.add_argument("--session-id", dest="session_id", default=None,
                         help="Stable session identifier. When set, this session gets its own "
                              "context file and an overlapping-scope begin by another live "
                              "session is a named conflict (exit 3) instead of a silent supersede.")

    # end
    p_end = sub.add_parser("end", help="End the active skill context")
    p_end.add_argument("--skill", required=True, help="Skill ID to end")
    p_end.add_argument("--status", default="completed",
                       choices=["completed", "failed", "aborted"],
                       help="How the skill ended")
    p_end.add_argument("--session-id", dest="session_id", default=None,
                       help="End only this session's context (RPR-G-03)")

    # check
    p_check = sub.add_parser("check", help="Check if a file is in active scope")
    p_check.add_argument("--file", required=True, help="File path to check")
    p_check.add_argument("--session-id", dest="session_id", default=None,
                         help="Check only this session's context (RPR-G-03)")

    # current
    p_current = sub.add_parser("current", help="Print current active skill ID")
    p_current.add_argument("--session-id", dest="session_id", default=None,
                           help="Report this session's context (default: AGENT_SESSION_ID env, then legacy)")

    # gap
    p_gap = sub.add_parser("gap", help="Create gap-approved temporary context")
    p_gap.add_argument("--task", required=True, help="Description of the gap work")
    p_gap.add_argument("--report", required=True, help="Path to the gap escalation report")
    p_gap.add_argument("--scope", default="*",
                       help="Comma-separated glob patterns for allowed file paths")
    p_gap.add_argument("--session-id", dest="session_id", default=None,
                       help="Session identity (default: AGENT_SESSION_ID env, then legacy path)")

    args = parser.parse_args(argv)
    dispatch = {
        "begin": cmd_begin,
        "end": cmd_end,
        "check": cmd_check,
        "current": cmd_current,
        "gap": cmd_gap,
    }
    return dispatch[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())