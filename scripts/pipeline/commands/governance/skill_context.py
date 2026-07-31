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
_CODEX_SESSION_ID = "CODEX_THREAD_ID"
_CLAUDE_CODE_SESSION_ID = "CLAUDE_CODE_SESSION_ID"

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent  # commands/governance/ -> commands/ -> pipeline/ -> scripts/ -> repo
_REPO_ROOT = _DEFAULT_REPO_ROOT
_CONTEXT_DIR = _REPO_ROOT / "reports" / "skill-context"
_ACTIVE_FILE = _CONTEXT_DIR / "ACTIVE.json"
_HISTORY_DIR = _CONTEXT_DIR / "history"
# RPR-G-03 (§2.5 SW-1) + HARDEN-A2: per-session context directory. A session id
# comes from --session-id, AGENT_SESSION_ID, or CODEX_THREAD_ID, giving each
# session its own file so concurrent
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


def _effective_activity_dt(record: dict) -> "datetime | None":
    """Return the timestamp staleness should be measured from.

    Prefers ``last_touched_at`` (heartbeat, RC1/RC2 hardening 2026-07-31 —
    bumped by ``cmd_check`` on every in-scope hit) over ``started_at``, so a
    context still being actively worked never expires mid-task just because
    it began more than one TTL ago, and a context that has gone genuinely
    quiet is detected from its last real activity, not diluted by how long
    ago it happened to begin. Records written before this field existed have
    none — falling back to ``started_at`` keeps them working exactly as
    before (additive, no migration needed). Returns ``None`` if neither
    timestamp parses.
    """
    for key in ("last_touched_at", "started_at"):
        raw = record.get(key, "")
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            continue
    return None


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
    activity_dt = _effective_activity_dt(record)
    if activity_dt is None:
        # Unparseable timestamps — treat as stale
        _archive_stale(record)
        return None

    # Check TTL for gap-approved contexts
    if record.get("context_type") == "gap_approved":
        ttl = _GAP_TTL
    else:
        ttl = _MAX_CONTEXT_AGE

    if _now() - activity_dt > ttl:
        _archive_stale(record)
        return None

    return record


def _touch_active_heartbeat() -> None:
    """Bump ACTIVE.json's last_touched_at (best-effort; a lost race is harmless
    since the next check simply doesn't extend the TTL that one time).

    Genuinely best-effort (independent verification pass, 2026-07-31, caught
    this): a failure here (lock contention, disk error) must never propagate
    out of cmd_check's in-scope return path and turn an ALLOW into a BLOCK --
    the whole point of this heartbeat is to reduce false blocks, not add a
    new way to cause one.
    """
    try:
        with _legacy_lock():
            if not _ACTIVE_FILE.exists():
                return
            try:
                record = json.loads(_ACTIVE_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return
            record["last_touched_at"] = _now().isoformat().replace("+00:00", "Z")
            _save_active(record)
    except Exception:
        pass


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


def _archive(record: dict, status: str = "completed", *, remove_active: bool = True,
             superseded_by: "dict | None" = None) -> "Path":
    """Move a context record to history.

    remove_active=False is used when archiving a PER-SESSION context (RPR-G-03): that
    record does not live in the legacy ACTIVE.json, so removing ACTIVE.json would destroy
    an unrelated session's live context. The caller unlinks its own session file instead.

    superseded_by (TC-MT007-02, backlog G-41): when a re-begin under the SAME session_id
    hands off to a DIFFERENT skill (the S-72 evidence-repair -> S-73 manual-edit pattern,
    forced by check_content_edit_hook.sh/check_s73_edit_scope.py recognizing only an
    active S-73 context for content/ writes), the archived record gets an explicit
    forward pointer to the record that superseded it -- {"skill_id", "started_at"} is
    enough to locate the exact history file later (history filenames are
    "{timestamp}-{skill_id}.json"). This is additive: existing records/consumers with no
    superseded_by key are unaffected. Returns the path the record was written to, so a
    caller can build the matching reverse pointer (handoff_from) on the new record.
    """
    _HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    record["ended_at"] = _now().isoformat().replace("+00:00", "Z")
    record["end_status"] = status
    if superseded_by is not None:
        record["superseded_by"] = {
            "skill_id": superseded_by.get("skill_id"),
            "started_at": superseded_by.get("started_at"),
            "session_id": superseded_by.get("session_id"),
        }
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
    return out


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
    """Return the stable caller identity.

    Precedence is explicit ``--session-id`` > ``AGENT_SESSION_ID`` >
    ``CODEX_THREAD_ID`` > ``CLAUDE_CODE_SESSION_ID``. Codex supplies its env
    var for every thread, so treating it as a stable identity prevents Codex
    callers from silently falling back to the shared legacy ``ACTIVE.json``.

    ``CLAUDE_CODE_SESSION_ID`` (RC1/RC2 hardening, 2026-07-31) is the harness's
    own per-conversation identifier — inherited into every tool-call subprocess
    automatically, unlike ``AGENT_SESSION_ID``/``--session-id`` which the caller
    must remember to re-supply on every single call (this harness's Bash tool
    does not persist shell state across invocations). It is a LAST-RESORT
    fallback, not a replacement for explicit identity: it is shared by a
    conversation with any subagents it spawns (verified empirically), so
    parallel subagents from one conversation are not distinguished from each
    other by this tier alone — a pre-existing limitation (they already shared
    the single legacy ``ACTIVE.json`` before this change), not a new one. What
    it does fix is the common case this repo actually hit in production: two
    genuinely independent, separately-initiated sessions/conversations, which
    the harness assigns *different* ``CLAUDE_CODE_SESSION_ID`` values, so the
    scope-overlap conflict check now correctly compares two distinct
    identities instead of both silently falling to the legacy path (where a
    conflict is only ever "any different skill", not scope-aware) or, in an
    earlier unsafe design that was tried and reverted, both resolving to one
    shared *mutable* file that either process could legitimately believe was
    its own. Other callers retain the legacy path only when none of the four
    sources resolves to anything.
    """
    value = (
        explicit
        or os.environ.get(_ENV_SESSION_ID, "").strip()
        or os.environ.get(_CODEX_SESSION_ID, "").strip()
        or os.environ.get(_CLAUDE_CODE_SESSION_ID, "").strip()
        or None
    )
    if value:
        return "".join(c if (c.isalnum() or c in "-_") else "-" for c in value)[:64]
    return None


def _session_context_path(session_id: str) -> Path:
    return _ACTIVE_DIR / f"{session_id}.json"


def _record_is_stale(record: dict) -> bool:
    activity_dt = _effective_activity_dt(record)
    if activity_dt is None:
        return True
    ttl = _GAP_TTL if record.get("context_type") == "gap_approved" else _MAX_CONTEXT_AGE
    return _now() - activity_dt > ttl


def _touch_session_heartbeat(session_id: str) -> None:
    """Bump a per-session context's last_touched_at (best-effort — see
    _touch_active_heartbeat; no lock needed, only the owning session's own
    `check`/`begin` calls ever write to this session's own file).

    Genuinely best-effort (independent verification pass, 2026-07-31): any
    failure here must never propagate out of cmd_check's in-scope return
    path and turn an ALLOW into a BLOCK.
    """
    try:
        p = _session_context_path(session_id)
        try:
            record = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        record["last_touched_at"] = _now().isoformat().replace("+00:00", "Z")
        _save_session_context(session_id, record)
    except Exception:
        pass


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
        record = {
            "skill_id": args.skill,
            "context_type": "skill",
            "scope_patterns": scope,
            "started_at": _now().isoformat().replace("+00:00", "Z"),
            "session_id": session_id,
        }
        if prior:
            # Re-begin within the SAME session replaces its own context (not a conflict).
            # TC-MT007-02 (G-41): when this re-begin is a genuine skill CHANGE (e.g. S-72
            # evidence-repair handing off to S-73 manual-edit to satisfy the Edit-tool write
            # gate), record a bidirectional link -- the archived record points forward to
            # this new one (superseded_by), and this new record points back (handoff_from) --
            # so a single S-72 invocation's provenance is traceable end-to-end even though it
            # spans two skill-context records under the same session_id. A same-skill re-arm
            # (the ordinary "scope re-arms before every edit" loop) is not a handoff and gets
            # no handoff_from field, to avoid noise on the overwhelmingly common case.
            if prior.get("skill_id") != args.skill:
                record["handoff_from"] = {
                    "skill_id": prior.get("skill_id"),
                    "started_at": prior.get("started_at"),
                }
                _archive(prior, status="superseded_same_session", remove_active=False,
                          superseded_by=record)
            else:
                _archive(prior, status="superseded_same_session", remove_active=False)
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
            _touch_session_heartbeat(session_id)
            return 0
        print(f"File {args.file} is outside session {session_id} skill "
              f"{record.get('skill_id')} scope.", file=sys.stderr)
        return 1

    # ---- Legacy path first (unchanged) ----
    active = _load_active()
    if active and _file_in_scope(args.file, active.get("scope_patterns", [])):
        _touch_active_heartbeat()
        return 0

    # Additionally honor any live per-session context that covers this file.
    for sid, record in _load_session_contexts().items():
        if _file_in_scope(args.file, record.get("scope_patterns", [])):
            _touch_session_heartbeat(sid)
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


def _describe_record(record: dict) -> dict:
    """Compute display fields for one context record without mutating anything."""
    activity_dt = _effective_activity_dt(record)
    ttl = _GAP_TTL if record.get("context_type") == "gap_approved" else _MAX_CONTEXT_AGE
    if activity_dt is None:
        age_desc = "unknown (unparseable timestamp)"
        stale = True
    else:
        age = _now() - activity_dt
        age_desc = f"{age.total_seconds() / 60:.1f}m"
        stale = age > ttl
    return {
        "skill_id": record.get("skill_id", "unknown"),
        "context_type": record.get("context_type", "skill"),
        "scope_patterns": record.get("scope_patterns", []),
        "started_at": record.get("started_at"),
        "last_touched_at": record.get("last_touched_at"),
        "age": age_desc,
        "would_be_stale": stale,
    }


def cmd_status(args: argparse.Namespace) -> int:
    """Report every skill-context record (legacy + all per-session) with its
    computed staleness, WITHOUT mutating or archiving anything.

    RC1/RC2 hardening (2026-07-31): _load_active()/_load_session_contexts()
    archive-and-delete a stale record as a side effect of being read, so
    diagnosing a live incident by calling them can destroy the evidence
    needed to diagnose it. This command reads the raw files directly instead.
    Always exits 0 -- it is a report, not a gate.

    --root lets an external aggregator (mission_authority.py's liveness
    report) point this subcommand at a different repo root -- e.g. a tmp_path
    test fixture -- without affecting the module's default path resolution
    used by every other subcommand.
    """
    root = getattr(args, "root", None)
    if root:
        configure(repo_root=root)
    as_json = getattr(args, "json", False)
    report: dict = {"legacy": None, "sessions": {}}

    if _ACTIVE_FILE.exists():
        try:
            raw = json.loads(_ACTIVE_FILE.read_text(encoding="utf-8"))
            report["legacy"] = _describe_record(raw)
        except (json.JSONDecodeError, OSError) as exc:
            report["legacy"] = {"error": f"unreadable: {exc}"}

    if _ACTIVE_DIR.exists():
        for p in sorted(_ACTIVE_DIR.glob("*.json")):
            try:
                raw = json.loads(p.read_text(encoding="utf-8"))
                report["sessions"][p.stem] = _describe_record(raw)
            except (json.JSONDecodeError, OSError) as exc:
                report["sessions"][p.stem] = {"error": f"unreadable: {exc}"}

    if as_json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    if not report["legacy"] and not report["sessions"]:
        print("No skill-context records on disk (legacy or per-session).")
        return 0

    if report["legacy"]:
        d = report["legacy"]
        if "error" in d:
            print(f"Legacy ACTIVE.json: {d['error']}")
        else:
            flag = "STALE (would self-expire on next real read)" if d["would_be_stale"] else "live"
            print(f"Legacy ACTIVE.json: {d['skill_id']} ({d['context_type']}) "
                  f"scope={d['scope_patterns']} age={d['age']} [{flag}]")

    for sid, d in sorted(report["sessions"].items()):
        if "error" in d:
            print(f"Session {sid}: {d['error']}")
            continue
        flag = "STALE (would self-expire on next real read)" if d["would_be_stale"] else "live"
        print(f"Session {sid}: {d['skill_id']} ({d['context_type']}) "
              f"scope={d['scope_patterns']} age={d['age']} [{flag}]")

    return 0


def _load_history_records() -> list[dict]:
    """Load every history/*.json record, tolerating unreadable/corrupt files."""
    records = []
    if not _HISTORY_DIR.exists():
        return records
    for path in sorted(_HISTORY_DIR.glob("*.json")):
        try:
            records.append(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    return records


def _find_history_record(records: list[dict], skill_id: "str | None",
                          started_at: "str | None") -> "dict | None":
    for r in records:
        if r.get("skill_id") == skill_id and r.get("started_at") == started_at:
            return r
    return None


def trace_handoff_chain(session_id: str) -> list[dict]:
    """Return every history record for `session_id`, in chronological order,
    plus any record a handoff_from/superseded_by pointer resolves to even if
    that record was filed under a DIFFERENT session_id (the pointer is a
    (skill_id, started_at) reference, not a session_id match, so it still
    resolves correctly even in that less-common case).

    TC-MT007-02 (backlog G-41): makes a multi-skill handoff (e.g. S-72
    evidence-repair -> S-73 manual-edit) traceable end-to-end from either
    direction, not just structurally linkable by an operator willing to grep
    two JSON files by hand.
    """
    records = _load_history_records()
    chain = [r for r in records if r.get("session_id") == session_id]

    seen_keys = {(r.get("skill_id"), r.get("started_at")) for r in chain}
    changed = True
    while changed:
        changed = False
        for r in list(chain):
            for pointer_key in ("handoff_from", "superseded_by"):
                pointer = r.get(pointer_key)
                if not pointer:
                    continue
                key = (pointer.get("skill_id"), pointer.get("started_at"))
                if key in seen_keys:
                    continue
                resolved = _find_history_record(records, *key)
                if resolved is not None:
                    chain.append(resolved)
                    seen_keys.add(key)
                    changed = True

    chain.sort(key=lambda r: r.get("started_at", ""))
    return chain


def cmd_trace(args: argparse.Namespace) -> int:
    """Print the full skill-context handoff chain for a session_id.

    Exit 0 with output if any records were found for the session, 1 if none.
    """
    chain = trace_handoff_chain(args.session_id)
    if not chain:
        print(f"No skill-context history records found for session {args.session_id!r}.",
              file=sys.stderr)
        return 1
    print(f"Handoff chain for session {args.session_id!r} ({len(chain)} record(s)):")
    for i, r in enumerate(chain):
        handoff_note = ""
        if r.get("handoff_from"):
            hf = r["handoff_from"]
            handoff_note = f"  <- handoff from {hf.get('skill_id')} (started {hf.get('started_at')})"
        supersede_note = ""
        if r.get("superseded_by"):
            sb = r["superseded_by"]
            supersede_note = f"  -> superseded by {sb.get('skill_id')} (started {sb.get('started_at')})"
        print(f"  [{i}] {r.get('skill_id')}: {r.get('started_at')} -> "
              f"{r.get('ended_at', '(active)')} [{r.get('end_status', 'active')}]"
              f"{handoff_note}{supersede_note}")
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
                           help="Session identity (default: AGENT_SESSION_ID, then CODEX_THREAD_ID, then legacy)")

    # status (RC1/RC2 hardening 2026-07-31: read-only, never mutates)
    p_status = sub.add_parser(
        "status", help="Report every context (legacy + per-session) with computed staleness; never mutates")
    p_status.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    p_status.add_argument("--root", default=None,
                          help="Repo root override (for tests / external aggregators)")

    # gap
    p_gap = sub.add_parser("gap", help="Create gap-approved temporary context")
    p_gap.add_argument("--task", required=True, help="Description of the gap work")
    p_gap.add_argument("--report", required=True, help="Path to the gap escalation report")
    p_gap.add_argument("--scope", default="*",
                       help="Comma-separated glob patterns for allowed file paths")
    p_gap.add_argument("--session-id", dest="session_id", default=None,
                       help="Session identity (default: AGENT_SESSION_ID, then CODEX_THREAD_ID, then legacy)")

    # trace (TC-MT007-02 / backlog G-41)
    p_trace = sub.add_parser(
        "trace", help="Print the full skill-context handoff chain for a session_id")
    p_trace.add_argument("--session-id", dest="session_id", required=True,
                         help="Session identifier to trace (e.g. evidence-repair-docs-a)")

    args = parser.parse_args(argv)
    dispatch = {
        "begin": cmd_begin,
        "end": cmd_end,
        "check": cmd_check,
        "current": cmd_current,
        "status": cmd_status,
        "gap": cmd_gap,
        "trace": cmd_trace,
    }
    return dispatch[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
