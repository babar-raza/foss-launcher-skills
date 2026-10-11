"""session_ledger.py — Session-scoped file touch ledger for /commit scoping.

Maintains a per-session manifest at reports/session-state/{session_id}.json
that tracks:
  - Session identity (ID, start time)
  - Dirty files snapshot at session start (to exclude from commit candidates)
  - Every file touched during the session (action, timestamp, skills)

The /commit skill (S-76) reads this ledger to restrict commit candidates to
session-touched files only. Files dirty before the session started are excluded.

Usage (CLI):
  # Initialize a new session (captures dirty-file snapshot)
  python scripts/pipeline/commands/ops/session_ledger.py init
  python scripts/pipeline/commands/ops/session_ledger.py init --session-id 20260409-143022-a7f3

  # Record a file touch
  python scripts/pipeline/commands/ops/session_ledger.py record --file content/docs.aspose.org/en/words/python/foo.md --action created
  python scripts/pipeline/commands/ops/session_ledger.py record --file content/docs.aspose.org/en/words/python/foo.md --action modified --skill S-20

  # List session-touched files
  python scripts/pipeline/commands/ops/session_ledger.py list
  python scripts/pipeline/commands/ops/session_ledger.py list --format json
  python scripts/pipeline/commands/ops/session_ledger.py list --format paths

  # Get current session ID
  python scripts/pipeline/commands/ops/session_ledger.py current

  # Retroactively adopt dirty files into the session (for pre-existing sessions)
  python scripts/pipeline/commands/ops/session_ledger.py adopt --all
  python scripts/pipeline/commands/ops/session_ledger.py adopt --group "content(locale)"
  python scripts/pipeline/commands/ops/session_ledger.py adopt --glob "content/kb.aspose.org/*"
  python scripts/pipeline/commands/ops/session_ledger.py adopt --files path/to/file1.md path/to/file2.md

  # Show all dirty files with group and adoption status
  python scripts/pipeline/commands/ops/session_ledger.py dirty
  python scripts/pipeline/commands/ops/session_ledger.py dirty --format json

  # Show commit candidates (ledger AND git dirty, minus dirty_at_start)
  python scripts/pipeline/commands/ops/session_ledger.py candidates
  python scripts/pipeline/commands/ops/session_ledger.py candidates --format json

  # Classify files into commit groups
  python scripts/pipeline/commands/ops/session_ledger.py groups
  python scripts/pipeline/commands/ops/session_ledger.py groups --format json

Usage (Python import):
  from session_ledger import init_session, record_file, get_candidates, get_current_session_id

Session identity (HARDEN-A2 / ST-021, 2026-07-22; extended 2026-08-01):
  Multiple sessions may be active concurrently. Identity resolution order for every
  operation: explicit --session-id / session_id kwarg > AGENT_SESSION_ID env var >
  CODEX_THREAD_ID env var > CLAUDE_CODE_SESSION_ID env var (honored when that
  manifest exists) > directory scan, via scripts/pipeline/lib/session_identity.py
  (the same module skill_context.py/refresh_run.py/skill_context_attribution.py/
  check_commit_bash_hook.sh already delegate to). If the scan finds MORE THAN ONE
  live active session, the operation fails loudly (exit 3) instead of silently
  picking one — the exact silent-pick that produced the PDF-GO/PDF-NET-REFRESH-001
  provenance corruption. init no longer closes other sessions; close requires
  naming the session explicitly. Manifests older than their stale_after_hours
  (default 8h of no writes) are flipped to status="stale" — excluded from
  resolution, never deleted, reactivated automatically if written to again.

  Production concurrency redesign (2026-08-01), Step 3: init_session's default-id
  generation (when called with no explicit id) now also prefers
  session_identity.resolve() over a fresh random id. This closes a reproduced bug,
  not just an ergonomics gap: without it, a single real session that calls init
  twice without consistently re-supplying an explicit id (the same
  Bash-doesn't-persist-exported-env-vars gap Steps 1-2 fixed for 4 other
  consumers -- e.g. a retried /session-start) silently fragments into two
  unrelated manifests, and the next unqualified call then hits
  AmbiguousSessionError between two ids belonging to the SAME real session. With
  CLAUDE_CODE_SESSION_ID wired into init's default path, the second init call
  resolves to the SAME id as the first and hits the existing F6 guard (loud,
  named ValueError pointing at the live manifest) instead of silently minting a
  second one. Accepted, bounded tradeoff (matching skill_context.py's own
  precedent): sibling subagents of one conversation share CLAUDE_CODE_SESSION_ID,
  so ordinary record_file/adopt calls with no explicit id from a sibling land in
  the SAME manifest as the parent's -- init-time collision is guarded (F6), but
  ongoing merges are not and are by design; any resulting candidate list is still
  surfaced for review by S-76's commit-plan preview before anything stages.

  Stale-open-mission surface (TC-GOV-02-02, REQ-GOV-02, 2026-09-19): every `init`
  -- including each --if-missing fast path the SessionStart hook takes -- ends by
  printing, to stdout, a short block naming open missions with no recent taskcard
  activity (and missions whose ledger is unreadable) with a pointer to
  `mission_authority.py status`. Fail-open (one short line on any failure, never a
  non-zero exit), silent when nothing is stale. See the comment block above
  emit_stale_mission_block() for the constraints it is built around.

Exit codes:
  0  Success
  1  Error (no active session, I/O failure)
  2  No session found
  3  Ambiguous: multiple active sessions and no explicit --session-id
"""
from __future__ import annotations

import argparse
import json
import secrets
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

import session_identity  # noqa: E402
from advisory_lock import FileLock, LockTimeout  # noqa: E402

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent


def _hidden_window_kwargs() -> dict:
    """Suppress the console window git.exe would otherwise flash open.

    Confirmed live (2026-09-25): this module's git subprocess calls opened a
    new, briefly-visible console window on Windows each time -- disruptive
    during an unattended campaign run that calls `current`/`adopt`
    repeatedly. Matches the same fix already applied to git_plumb_commit.py.
    """
    kwargs: dict = {}
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    if hasattr(subprocess, "STARTUPINFO"):
        info = subprocess.STARTUPINFO()
        info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        info.wShowWindow = subprocess.SW_HIDE
        kwargs["startupinfo"] = info
    return kwargs


_REPO_ROOT = _DEFAULT_REPO_ROOT
_SESSION_DIR = _REPO_ROOT / "reports" / "session-state"
_ACTIVE_POINTER = _SESSION_DIR / "ACTIVE"

# DI seam for the session-start stale-mission block (TC-GOV-02-02): a callable
# root -> list of mission_authority._plan_state_report()-shaped rows. None (the
# default) means "read the real plan_state store". Only tests set it, through
# configure(plan_state_rows_fn=...); configure() with no argument resets it.
_PLAN_STATE_ROWS_FN: Callable[[Path], list[dict]] | None = None

_ENV_SESSION_ID = "AGENT_SESSION_ID"
_DEFAULT_STALE_AFTER_HOURS = 8.0
_MANIFEST_LOCK_TIMEOUT = 10.0


class AmbiguousSessionError(Exception):
    """More than one live active session and no explicit session identity given."""

    def __init__(self, candidates: list[str]):
        self.candidates = candidates
        super().__init__(
            "Multiple active sessions — pass --session-id or set "
            f"{_ENV_SESSION_ID}. Candidates: {', '.join(candidates)}"
        )


def configure(
    repo_root: Path | None = None,
    session_dir: Path | None = None,
    plan_state_rows_fn: Callable[[Path], list[dict]] | None = None,
) -> None:
    """Reconfigure module-level paths for testing or alternative layouts.

    - Called with no arguments: resets to built-in defaults.
    - repo_root only: derives session_dir as ``repo_root / "reports" / "session-state"``.
    - Both provided: uses them directly.
    - plan_state_rows_fn: test seam replacing the plan_state row source used by
      the session-start stale-mission block; None (the default) restores the
      real store, so every configure() call resets it.

    ``_ACTIVE_POINTER`` is always recomputed from ``_SESSION_DIR``.
    """
    global _REPO_ROOT, _SESSION_DIR, _ACTIVE_POINTER, _PLAN_STATE_ROWS_FN

    _REPO_ROOT = repo_root if repo_root is not None else _DEFAULT_REPO_ROOT
    _PLAN_STATE_ROWS_FN = plan_state_rows_fn

    if session_dir is not None:
        _SESSION_DIR = session_dir
    else:
        _SESSION_DIR = _REPO_ROOT / "reports" / "session-state"

    _ACTIVE_POINTER = _SESSION_DIR / "ACTIVE"


def _repo_rel(path: Path) -> str:
    """Repo-relative display string; falls back to absolute."""
    try:
        return str(path.relative_to(_REPO_ROOT))
    except ValueError:
        return str(path)


# ---------------------------------------------------------------------------
# Commit group classifier — deterministic, first-match-wins
# ---------------------------------------------------------------------------

# Order matters: more specific prefixes before general ones.
# Locale detection (content/ but not /en/) must come first.
COMMIT_GROUPS: list[tuple[str, str]] = [
    # Locale translations (any content/ path NOT under /en/)
    ("content(locale)", "LOCALE"),
    # English content by site
    ("content(reference)", "content/reference.aspose.org/en/"),
    ("content(products)", "content/products.aspose.org/en/"),
    ("content(blog)", "content/blog.aspose.org/"),
    ("content(kb)", "content/kb.aspose.org/en/"),
    ("content(docs)", "content/docs.aspose.org/en/"),
    # Knowledge artifacts
    ("knowledge", "knowledge/"),
    # Pipeline scripts
    ("fix(pipeline)", "scripts/pipeline/"),
    # CI validators
    ("chore(ci)", "scripts/ci/"),
    # Maintenance scripts
    ("chore(maintenance)", "scripts/maintenance/"),
    # Translator subsystem
    ("chore(translator)", "scripts/translator/"),
    # Generator subsystem
    ("chore(generator)", "scripts/generator/"),
    # SEO tools
    ("chore(seo)", "scripts/seo/"),
    # Gap evaluation
    ("chore(gap-eval)", "scripts/gap-eval/"),
    # Tests
    ("test", "tests/"),
    # Hugo data registry
    ("chore(data)", "data/"),
    # SEO patches
    ("chore(patches)", "patches/"),
]


def _normalize_path(path: str) -> str:
    """Canonical repo-relative path form used for all ledger key comparisons.

    Strips leading/trailing whitespace (including a stray '\\r' -- found live:
    a caller building a newline-separated file list on Windows/Git Bash and
    joining lines with `tr '\\n' ' '` leaves a trailing '\\r' on every token,
    since `tr` only touches the '\\n' half of each CRLF pair) before the
    existing backslash/./ normalization. Without this, `adopt_files()` silently
    writes a '...md\\r'-suffixed key to `touched_files` and never matches the
    clean path in `dirty_at_start` or git's own dirty-file list -- `adopt`
    reports success (the file IS recorded, just under the wrong key) and the
    file then never appears in `candidates`, with no error pointing at the
    real cause. Reproduced and fixed 2026-09-11.
    """
    return path.strip().replace("\\", "/").removeprefix("./")


def classify_file(path: str) -> str:
    """Classify a repo-relative path into a commit group name.

    Returns the group name (e.g. 'content(docs)') or 'chore(misc)' if no
    prefix matches.
    """
    normalized = _normalize_path(path)

    # Special locale detection: content/ path that is NOT English
    if normalized.startswith("content/") and normalized.endswith(".md"):
        # Check if this is a locale file (not under /en/)
        # Blog doesn't use /en/ prefix, so locale detection is different
        if normalized.startswith("content/blog.aspose.org/"):
            pass  # Blog has no locale distinction in path — falls through to site match
        elif "/en/" not in normalized:
            return "content(locale)"

    for group_name, prefix in COMMIT_GROUPS:
        if prefix == "LOCALE":
            continue  # Handled above
        if normalized.startswith(prefix):
            return group_name

    return "chore(misc)"


def group_files(paths: list[str]) -> dict[str, list[str]]:
    """Group a list of repo-relative paths into commit groups.

    Returns a dict mapping group name → sorted list of paths.
    """
    groups: dict[str, list[str]] = {}
    for p in paths:
        g = classify_file(p)
        groups.setdefault(g, []).append(p)
    for v in groups.values():
        v.sort()
    return groups


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def _git_dirty_files() -> list[str]:
    """Return repo-relative paths of all dirty files (modified + untracked)."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "-uall"],
            capture_output=True, text=True, cwd=str(_REPO_ROOT),
            timeout=30, **_hidden_window_kwargs(),
        )
        if result.returncode != 0:
            return []
        paths = []
        for line in result.stdout.splitlines():
            if len(line) < 4:
                continue
            # porcelain format: XY <space> path (or XY <space> path -> newpath)
            raw = line[3:]
            # Handle renames: "old -> new"
            if " -> " in raw:
                raw = raw.split(" -> ", 1)[1]
            paths.append(raw.replace("\\", "/"))
        return sorted(set(paths))
    except (subprocess.SubprocessError, OSError):
        return []


def _git_head_sha() -> str | None:
    """Return the current HEAD commit SHA, or None if it cannot be resolved.

    Stale-file regression guard (2026-08-01, found live: TC-MT018-06's commit
    d2dce37de5 silently reverted an unrelated fix to fetch_aspose_com_targets.py
    committed by another session hours earlier -- byte-exact regression of
    corrected data/aspose_com_targets.json entries back to known-wrong values,
    with the reverting commit's own message never mentioning the file). This
    is the missing reference point: without a recorded baseline, nothing can
    ever ask "has this file changed on main since my session began, and does
    my proposed content actually reflect that change?" -- see
    check_stale_file_regression.py, which consumes this field.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, cwd=str(_REPO_ROOT),
            timeout=30, **_hidden_window_kwargs(),
        )
        if result.returncode != 0:
            return None
        sha = result.stdout.strip()
        return sha or None
    except (subprocess.SubprocessError, OSError):
        return None


# ---------------------------------------------------------------------------
# Session I/O
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _generate_session_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    rand = secrets.token_hex(2)  # 4 hex chars
    return f"{ts}-{rand}"


def _session_path(session_id: str) -> Path:
    return _SESSION_DIR / f"{session_id}.json"


def _save_manifest(path: Path, manifest: dict) -> None:
    """Atomic write of session manifest."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        "w", encoding="utf-8", delete=False, dir=path.parent, suffix=".tmp"
    ) as handle:
        json.dump(manifest, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
        temp_path = Path(handle.name)
    temp_path.replace(path)


def _write_active_pointer(session_id: str) -> None:
    """Write the ACTIVE pointer file atomically."""
    _SESSION_DIR.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        "w", encoding="utf-8", delete=False, dir=_SESSION_DIR, suffix=".tmp"
    ) as handle:
        handle.write(session_id + "\n")
        temp_path = Path(handle.name)
    temp_path.replace(_ACTIVE_POINTER)


def _clear_active_pointer() -> None:
    """Remove the ACTIVE pointer (session closed)."""
    try:
        _ACTIVE_POINTER.unlink()
    except FileNotFoundError:
        pass


def _read_active_pointer() -> str | None:
    """Read session ID from the ACTIVE pointer file, or None."""
    try:
        return _ACTIVE_POINTER.read_text(encoding="utf-8").strip()
    except (FileNotFoundError, OSError):
        return None


def _load_manifest(path: Path) -> dict | None:
    """Load session manifest, returning None if missing or corrupt.

    "Corrupt" includes a file that is valid JSON but not an object (a list,
    string, number...) and one that is not valid UTF-8 (UnicodeDecodeError is a
    ValueError, not a JSONDecodeError). Every caller does `.get(...)` on the
    result, and _sweep_stale() -- the first thing init does, over EVERY manifest
    in the directory -- used to raise AttributeError on one such stray file,
    making `init` exit 1 for every session in the repo (TC-GOV-02-02 stage 3).
    """
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (ValueError, OSError):  # ValueError covers JSONDecodeError + UnicodeDecodeError
        return None
    return data if isinstance(data, dict) else None


def _manifest_lock(path: Path) -> FileLock:
    return FileLock(str(path) + ".lock", timeout=_MANIFEST_LOCK_TIMEOUT)


def _stale_ttl_hours(manifest: dict) -> float:
    try:
        return float(manifest.get("stale_after_hours", _DEFAULT_STALE_AFTER_HOURS))
    except (TypeError, ValueError):
        return _DEFAULT_STALE_AFTER_HOURS


def _sweep_stale() -> list[str]:
    """Flip active manifests with no writes for > stale_after_hours to 'stale'.

    Age is measured from the manifest file's mtime — every record/adopt rewrites
    the manifest, so mtime tracks last activity, not session start. Stale
    manifests are never deleted; they stay inspectable and reactivate on the
    next explicit write. Returns the session ids flipped this sweep.
    """
    flipped: list[str] = []
    if not _SESSION_DIR.exists():
        return flipped
    import time as _time
    now = _time.time()
    for f in _SESSION_DIR.glob("*.json"):
        m = _load_manifest(f)
        if not m or m.get("status") != "active":
            continue
        try:
            age_hours = (now - f.stat().st_mtime) / 3600.0
        except OSError:
            continue
        if age_hours <= _stale_ttl_hours(m):
            continue
        try:
            with _manifest_lock(f):
                # Re-check BOTH status and mtime under the lock (F3): a write that
                # landed between the outer stat and this lock refreshed the mtime —
                # flipping such a just-written session to stale would drop it out
                # of resolution (or silently disambiguate what should be ambiguous).
                m2 = _load_manifest(f)
                try:
                    age_now = (now - f.stat().st_mtime) / 3600.0
                except OSError:
                    continue
                if m2 and m2.get("status") == "active" and age_now > _stale_ttl_hours(m2):
                    m2["status"] = "stale"
                    m2["stale_at"] = _now_iso()
                    _save_manifest(f, m2)
                    flipped.append(m2.get("session_id", f.stem))
        except LockTimeout:
            continue  # another process is mutating it — clearly not abandoned
    return flipped


def _resolve_session(session_id: str | None = None) -> tuple[str, Path] | None:
    """Resolve the session an operation targets (HARDEN-A2; extended Step 3,
    2026-08-01).

    Escalation: explicit session_id > AGENT_SESSION_ID env > CODEX_THREAD_ID
    env > CLAUDE_CODE_SESSION_ID env (via session_identity.resolve(); honored
    when that manifest exists and is not closed) > stale sweep + scan. A scan
    finding exactly one active session uses it (the common single-session
    case, unchanged); zero returns None; two or more raises
    AmbiguousSessionError instead of silently picking one.
    """
    if session_id:
        p = _session_path(session_id)
        m = _load_manifest(p)
        if not m or m.get("status") == "closed":
            return None
        return session_id, p

    env_id = session_identity.resolve()
    if env_id:
        p = _session_path(env_id)
        m = _load_manifest(p)
        if m:
            if m.get("status") == "closed":
                # The env names THIS caller's own, ended session. Falling
                # through to the scan here silently adopted the single other
                # live session's identity (and wrote into ITS manifest) --
                # adversarial finding B2 of the 2026-08-29 stale-guard plan.
                # An ended session must resolve to "no session", never to
                # someone else's.
                return None
            return env_id, p
        # env id has no manifest at all — treat as a hint only, fall through

    if not _SESSION_DIR.exists():
        return None

    _sweep_stale()

    actives: list[tuple[str, Path]] = []
    for f in sorted(_SESSION_DIR.glob("*.json"), reverse=True):
        if f.name.endswith(".tmp"):
            continue
        m = _load_manifest(f)
        if m and m.get("status") == "active":
            actives.append((m.get("session_id", f.stem), f))

    if not actives:
        _clear_active_pointer()
        return None
    if len(actives) == 1:
        # Keep the pointer as an O(1) advisory hint for tooling/diagnostics.
        _write_active_pointer(actives[0][0])
        return actives[0]
    raise AmbiguousSessionError([sid for sid, _ in actives])


def _find_active_session() -> tuple[str, Path] | None:
    """Back-compat wrapper over _resolve_session (no explicit identity)."""
    return _resolve_session(None)


@dataclass(frozen=True)
class SessionContext:
    """Typed, side-effect-free view of 'which session is this?' for callers
    that must not raise, sweep, or write (2026-08-29 stale-guard plan, T3).

    status: "resolved" | "none" | "closed" | "ambiguous" | "no_ledger_dir"
    source: "explicit" | "env" | "scan" | "none"
    """
    status: str
    session_id: "str | None" = None
    manifest_path: "Path | None" = None
    base_sha: "str | None" = None
    source: str = "none"
    candidates: "tuple[str, ...]" = ()


def resolve_context(session_id: "str | None" = None) -> SessionContext:
    """PURE resolver: never runs the stale sweep, never writes the ACTIVE
    pointer, never raises. Liveness is computed from manifest mtime against
    stale_after_hours exactly as _sweep_stale would, but read-only.

    Unlike _resolve_session, an explicit/env identity naming a CLOSED
    manifest reports status="closed" for that identity rather than falling
    anywhere else -- an ended session is never resolved to another live
    session's identity (adversarial finding B2).
    """
    import time as _time

    def _ctx_for(sid: str, source: str) -> SessionContext:
        p = _session_path(sid)
        m = _load_manifest(p)
        if not m:
            return SessionContext(status="none", session_id=sid, source=source)
        if m.get("status") == "closed":
            return SessionContext(status="closed", session_id=sid, manifest_path=p,
                                  base_sha=m.get("base_commit_sha"), source=source)
        return SessionContext(status="resolved", session_id=sid, manifest_path=p,
                              base_sha=m.get("base_commit_sha"), source=source)

    if session_id:
        return _ctx_for(session_id, "explicit")

    env_id = session_identity.resolve()
    if env_id:
        ctx = _ctx_for(env_id, "env")
        if ctx.status != "none":
            return ctx
        # env id has no manifest at all — hint only, fall through to the scan
        # (parity with _resolve_session).

    if not _SESSION_DIR.exists():
        return SessionContext(status="no_ledger_dir")

    now = _time.time()
    live: list[tuple[str, Path, dict]] = []
    for f in sorted(_SESSION_DIR.glob("*.json"), reverse=True):
        if f.name.endswith(".tmp"):
            continue
        m = _load_manifest(f)
        if not m or m.get("status") != "active":
            continue
        try:
            age_hours = (now - f.stat().st_mtime) / 3600.0
        except OSError:
            continue
        if age_hours <= _stale_ttl_hours(m):
            live.append((m.get("session_id", f.stem), f, m))

    if not live:
        return SessionContext(status="none")
    if len(live) == 1:
        sid, p, m = live[0]
        return SessionContext(status="resolved", session_id=sid, manifest_path=p,
                              base_sha=m.get("base_commit_sha"), source="scan")
    return SessionContext(status="ambiguous",
                          candidates=tuple(sid for sid, _p, _m in live))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def init_session(session_id: str | None = None, force: bool = False) -> str:
    """Initialize a new session with dirty-file snapshot.

    HARDEN-A2: no longer closes any other session — a session's manifest is
    mutated only by operations that name it (or resolve to it unambiguously).
    Other live sessions stay active; the caller is told about them by cmd_init.

    F6 guard: re-initializing an id whose manifest is currently ACTIVE would
    silently wipe that session's recorded provenance (empty touched_files) —
    refused with ValueError unless force=True. Ids are passed around in env
    now, so an accidental re-init of a live id is a realistic mistake.

    Returns the session ID.
    """
    if session_id is None:
        # Step 3 (2026-08-01): prefer the caller's resolvable identity over a
        # fresh random id -- closes the self-fragmentation bug described in
        # the module docstring (a single real session calling init twice
        # would otherwise silently mint two unrelated manifests instead of
        # hitting the F6 guard below on the second call).
        session_id = session_identity.resolve() or _generate_session_id()

    path = _session_path(session_id)
    with _manifest_lock(path):
        existing = _load_manifest(path)
        if existing and existing.get("status") == "active" and not force:
            raise ValueError(
                f"session '{session_id}' already has an ACTIVE manifest with "
                f"{len(existing.get('touched_files', {}))} touched files — re-init "
                f"would wipe it. Use force=True (CLI: --force-reinit) if intended."
            )

        dirty = _git_dirty_files()
        manifest = {
            "session_id": session_id,
            "started_at": _now_iso(),
            "stale_after_hours": _DEFAULT_STALE_AFTER_HOURS,
            "dirty_at_start": dirty,
            "base_commit_sha": _git_head_sha(),
            "touched_files": {},
            "status": "active",
        }

        # Ensure reports/ subdirectories exist for governance tools
        for subdir in ("skill-context", "skill-runs", "overrides/pending", "audit"):
            (_REPO_ROOT / "reports" / subdir).mkdir(parents=True, exist_ok=True)

        _save_manifest(path, manifest)
    # Advisory hint only — resolution goes through _resolve_session, never
    # through this pointer alone.
    _write_active_pointer(session_id)
    return session_id


def reopen_session(session_id: str) -> bool:
    """closed -> active (SessionStart resume, 2026-08-30 stale-guard plan T3):
    keeps base_commit_sha and touched_files -- an older base means a wider
    stale-check window, the safe direction. Returns False if no manifest or
    not closed."""
    p = _session_path(session_id)
    with _manifest_lock(p):
        m = _load_manifest(p)
        if not m or m.get("status") != "closed":
            return False
        m["status"] = "active"
        m["reopened_at"] = _now_iso()
        m.pop("closed_at", None)
        _save_manifest(p, m)
    return True


def close_session(session_id: str) -> bool:
    """Close the named session. A session is only ever closed by name —
    there is no 'close whatever is active' operation (HARDEN-A2).

    Returns True if closed, False if the manifest doesn't exist.
    """
    p = _session_path(session_id)
    if _load_manifest(p) is None:
        return False
    with _manifest_lock(p):
        m = _load_manifest(p)
        if m is None:
            return False
        m["status"] = "closed"
        m["closed_at"] = _now_iso()
        _save_manifest(p, m)
    if _read_active_pointer() == session_id:
        _clear_active_pointer()
    return True


def other_active_sessions(exclude_session_id: str | None) -> list[str]:
    """List live (active, post-sweep-eligible) session ids other than the given one."""
    result: list[str] = []
    if not _SESSION_DIR.exists():
        return result
    for f in _SESSION_DIR.glob("*.json"):
        m = _load_manifest(f)
        if not m or m.get("status") != "active":
            continue
        sid = m.get("session_id", f.stem)
        if sid != exclude_session_id:
            result.append(sid)
    return sorted(result)


def files_claimed_by_other_sessions(
    paths: list[str], exclude_session_id: str | None
) -> dict[str, str]:
    """Map each path claimed by ANOTHER active session to that session's id.

    Stale and closed sessions do not claim files. This is the adopt-time guard
    that prevents one session sweeping another live session's in-flight work
    into its own commit (the PDF-*-REFRESH-001 contamination mechanism).
    """
    claimed: dict[str, str] = {}
    if not _SESSION_DIR.exists():
        return claimed
    normalized = {_normalize_path(p) for p in paths}
    for f in _SESSION_DIR.glob("*.json"):
        m = _load_manifest(f)
        if not m or m.get("status") != "active":
            continue
        sid = m.get("session_id", f.stem)
        if sid == exclude_session_id:
            continue
        for touched_path in m.get("touched_files", {}):
            if touched_path in normalized and touched_path not in claimed:
                claimed[touched_path] = sid
    return claimed


def _mutate_manifest(resolved: tuple[str, Path], mutator) -> bool:
    """Locked read-modify-write of one session manifest.

    Reloads under the lock (the resolve-time snapshot may be stale), refuses
    closed manifests, and reactivates a stale manifest being written to —
    staleness is a liveness heuristic, not a tombstone.
    """
    _sid, path = resolved
    with _manifest_lock(path):
        manifest = _load_manifest(path)
        if not manifest or manifest.get("status") == "closed":
            return False
        if manifest.get("status") == "stale":
            manifest["status"] = "active"
            manifest.pop("stale_at", None)
        mutator(manifest)
        _save_manifest(path, manifest)
    return True


def record_file(
    file_path: str,
    action: str = "modified",
    skill: str | None = None,
    session_id: str | None = None,
) -> bool:
    """Record a file touch in the session ledger.

    Args:
        file_path: Repo-relative path (forward slashes).
        action: One of 'created', 'modified', 'deleted', 'renamed'.
        skill: Optional S-{n} skill ID.
        session_id: Explicit session identity (HARDEN-A2); falls back to
            AGENT_SESSION_ID env, then unambiguous scan.

    Returns True if recorded, False if no (or no unambiguous) target session.
    """
    resolved = _resolve_session(session_id)
    if not resolved:
        return False
    return _mutate_manifest(
        resolved,
        lambda m: _apply_touch(m.setdefault("touched_files", {}), file_path, action, skill),
    )


def _apply_touch(touched: dict, file_path: str, action: str, skill: str | None) -> None:
    """Apply one file-touch entry to a touched_files dict (no I/O)."""
    normalized = _normalize_path(file_path)
    if normalized in touched:
        # Update existing entry
        entry = touched[normalized]
        entry["last_touched"] = _now_iso()
        # Upgrade action if more significant (created > modified > renamed > deleted)
        if action == "created" and entry["action"] != "created":
            entry["action"] = action
        elif action == "deleted":
            entry["action"] = "deleted"
        elif action != entry["action"] and entry["action"] not in ("created", "deleted"):
            entry["action"] = action
        if skill and skill not in entry.get("skills", []):
            entry.setdefault("skills", []).append(skill)
    else:
        # New entry
        touched[normalized] = {
            "action": action,
            "first_touched": _now_iso(),
            "last_touched": _now_iso(),
            "skills": [skill] if skill else [],
        }


def record_files(
    file_paths: list[str],
    action: str = "modified",
    skill: str | None = None,
    session_id: str | None = None,
) -> int | None:
    """Record many file touches with a single manifest load/save.

    Added for TC-W3H-009: per-file `record` CLI calls cost ~1-2 s each
    (interpreter + manifest round-trip), which pushed agents toward
    over-broad `adopt --glob`. Batch mode records 1,000 paths in one write.

    Returns the number of files recorded, or None if no target session.
    """
    resolved = _resolve_session(session_id)
    if not resolved:
        return None

    def _apply(manifest: dict) -> None:
        touched = manifest.setdefault("touched_files", {})
        for fp in file_paths:
            _apply_touch(touched, fp, action, skill)

    if not _mutate_manifest(resolved, _apply):
        return None
    return len(file_paths)


def get_current_session_id() -> str | None:
    """Return the current unambiguous session ID, or None."""
    active = _resolve_session(None)
    return active[0] if active else None


def get_touched_files(session_id: str | None = None) -> dict[str, dict]:
    """Return the touched_files dict for the given or resolved session.

    An explicitly named session is readable regardless of status (closed
    sessions stay inspectable); only no-id resolution excludes closed/stale.
    """
    if session_id:
        manifest = _load_manifest(_session_path(session_id))
    else:
        resolved = _resolve_session(None)
        if not resolved:
            return {}
        manifest = _load_manifest(resolved[1])
    if not manifest:
        return {}
    return manifest.get("touched_files", {})


def get_dirty_at_start(session_id: str | None = None) -> list[str]:
    """Return the dirty_at_start list for the given or resolved session.

    Same read semantics as get_touched_files: explicit id reads any status.
    """
    if session_id:
        manifest = _load_manifest(_session_path(session_id))
    else:
        resolved = _resolve_session(None)
        if not resolved:
            return []
        manifest = _load_manifest(resolved[1])
    if not manifest:
        return []
    return manifest.get("dirty_at_start", [])


def get_base_commit_sha(session_id: str | None = None) -> str | None:
    """Return the base_commit_sha recorded at init_session() time for the
    given or resolved session, or None if unavailable (manifest predates
    this field, or HEAD could not be resolved at init time).

    Same read semantics as get_touched_files/get_dirty_at_start: explicit id
    reads any status. Consumed by check_stale_file_regression.py to know
    which commits on a candidate file happened DURING this session (i.e.,
    after its own starting point) and therefore might have been silently
    reverted by this session's proposed content.
    """
    if session_id:
        manifest = _load_manifest(_session_path(session_id))
    else:
        resolved = _resolve_session(None)
        if not resolved:
            return None
        manifest = _load_manifest(resolved[1])
    if not manifest:
        return None
    return manifest.get("base_commit_sha")


def get_candidates(
    session_id: str | None = None,
) -> tuple[list[str], list[str], list[str]]:
    """Compute commit candidates from session ledger.

    Returns (candidates, excluded_dirty_at_start, excluded_not_in_ledger).
      - candidates: files in ledger AND currently dirty
      - excluded_dirty_at_start: dirty files that existed before session
      - excluded_not_in_ledger: dirty files not in ledger (unknown source)
    """
    active = _resolve_session(session_id)
    if not active:
        return [], [], []

    manifest = _load_manifest(active[1])
    if not manifest:
        return [], [], []

    touched = set(manifest.get("touched_files", {}).keys())
    dirty_at_start = set(manifest.get("dirty_at_start", []))
    current_dirty = set(_git_dirty_files())

    candidates = sorted(touched & current_dirty)
    excluded_prior = sorted((current_dirty - touched) & dirty_at_start)
    excluded_unknown = sorted(current_dirty - touched - dirty_at_start)

    return candidates, excluded_prior, excluded_unknown


def is_new_files_only(session_id: str | None = None) -> bool:
    """Check if the session only created new files (no modifications/deletions)."""
    touched = get_touched_files(session_id)
    if not touched:
        return False
    return all(entry.get("action") == "created" for entry in touched.values())


def adopt_files(
    paths: list[str],
    action: str = "modified",
    skill: str | None = None,
    remove_from_dirty_at_start: bool = True,
    session_id: str | None = None,
    confirm_cross_session: bool = False,
    skipped_out: dict[str, str] | None = None,
) -> int:
    """Adopt files into the session ledger retroactively.

    Use this when a session started before the ledger existed, or when files
    were touched outside the normal record flow and need to be claimed.

    HARDEN-A2 cross-session guard: paths already claimed by ANOTHER active
    session are refused (not adopted) unless confirm_cross_session=True.
    Refused paths are reported via skipped_out (path -> claiming session id).
    This is what stops `adopt --all` / broad `adopt --glob` from sweeping a
    concurrent session's in-flight work into this session's commit.

    If remove_from_dirty_at_start is True (default), adopted files are also
    removed from dirty_at_start so they become commit candidates.

    Returns the count of files adopted.
    """
    resolved = _resolve_session(session_id)
    if not resolved:
        return 0
    resolved_sid = resolved[0]

    eligible = list(paths)
    if not confirm_cross_session:
        claimed = files_claimed_by_other_sessions(paths, exclude_session_id=resolved_sid)
        if claimed:
            if skipped_out is not None:
                skipped_out.update(claimed)
            claimed_keys = set(claimed)
            eligible = [
                p for p in paths
                if _normalize_path(p) not in claimed_keys
            ]
    if not eligible:
        return 0

    count_holder = {"count": 0}

    def _apply(manifest: dict) -> None:
        touched = manifest.setdefault("touched_files", {})
        dirty_at_start = manifest.get("dirty_at_start", [])
        for file_path in eligible:
            normalized = _normalize_path(file_path)
            if normalized not in touched:
                touched[normalized] = {
                    "action": action,
                    "first_touched": _now_iso(),
                    "last_touched": _now_iso(),
                    "skills": [skill] if skill else [],
                    "adopted": True,
                }
                count_holder["count"] += 1
            # Also remove from dirty_at_start so it becomes a candidate
            if remove_from_dirty_at_start and normalized in dirty_at_start:
                dirty_at_start.remove(normalized)
        manifest["dirty_at_start"] = dirty_at_start

    if not _mutate_manifest(resolved, _apply):
        return 0
    return count_holder["count"]


def adopt_by_glob(
    pattern: str,
    action: str = "modified",
    skill: str | None = None,
    session_id: str | None = None,
    confirm_cross_session: bool = False,
    skipped_out: dict[str, str] | None = None,
) -> tuple[int, list[str]]:
    """Adopt all currently dirty files matching a glob pattern.

    Returns (count_adopted, list_of_adopted_paths).
    """
    current_dirty = _git_dirty_files()
    import fnmatch
    matched = [p for p in current_dirty if fnmatch.fnmatch(p, pattern)]
    if not matched:
        return 0, []
    count = adopt_files(
        matched, action=action, skill=skill, session_id=session_id,
        confirm_cross_session=confirm_cross_session, skipped_out=skipped_out,
    )
    return count, matched


def adopt_by_group(
    group_name: str,
    action: str = "modified",
    skill: str | None = None,
    session_id: str | None = None,
    confirm_cross_session: bool = False,
    skipped_out: dict[str, str] | None = None,
) -> tuple[int, list[str]]:
    """Adopt all currently dirty files belonging to a commit group.

    Group names match the classifier output: content(docs), content(locale),
    fix(pipeline), etc.

    Returns (count_adopted, list_of_adopted_paths).
    """
    current_dirty = _git_dirty_files()
    matched = [p for p in current_dirty if classify_file(p) == group_name]
    if not matched:
        return 0, []
    count = adopt_files(
        matched, action=action, skill=skill, session_id=session_id,
        confirm_cross_session=confirm_cross_session, skipped_out=skipped_out,
    )
    return count, matched


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Session-start stale-open-mission surface (TC-GOV-02-02, REQ-GOV-02)
#
# mission_authority._plan_state_report() (TC-GOV-02-01/-FIX) knows which open
# missions have gone quiet, but nothing told a NEW session about it: MT066 and
# a dozen others sat open for weeks because nobody thought to run `status`.
# This is the session-start half: cmd_init prints a short block for them.
#
# Constraints this block is built around (each is pinned by a test):
#   - FAIL OPEN. Session start must never break or hang because of it. The
#     emitter catches Exception and prints one short line with the error CLASS
#     only (a message can carry a local path). KeyboardInterrupt/SystemExit are
#     deliberately not caught.
#   - STDOUT, not stderr: the SessionStart hook runs `init ... 2>/dev/null`, so
#     anything on stderr never reaches the agent.
#   - EVERY init path: the hook always passes --if-missing, and cmd_init's
#     --if-missing fast paths (already-active / reactivated / reopened) return
#     BEFORE the print block that only a brand-new session id reaches. A warning
#     placed only in that block would be missing on resume/clear/compact starts,
#     i.e. the normal hook invocation. cmd_init therefore wraps the whole body.
#   - CONCISE: this text lands in every agent session's context.
#   - INDEPENDENT of every other store. The plan_state store is called directly,
#     never through mission_authority.build_liveness_report(), which also bundles
#     the session-state manifests (one valid-JSON-list manifest makes its
#     _session_ledger_report() raise AttributeError), the lock store, and a
#     skill-context subprocess with a 10 second timeout -- any of which would
#     suppress or delay this warning for reasons unrelated to it.
#   - BOTH lists: stale_open_missions AND the missions whose ledger could not be
#     read (plan_state_errors). Those are deliberately not "stale" (their
#     staleness is unknown) but are never silently fine either.
# ---------------------------------------------------------------------------

_STALE_MISSION_MAX_LISTED = 5
_UNREADABLE_MISSION_MAX_LISTED = 3
_MISSION_ID_DISPLAY_MAX = 64
_MISSION_STATUS_COMMAND = (
    "python scripts/pipeline/commands/governance/mission_authority.py status"
)


def _ascii_display(value: object, limit: int) -> str:
    """A bounded, one-line, ASCII-only rendering of `value` (the SessionStart
    output can reach a cp1252 console, and a mission id is free text from yaml)."""
    text = " ".join(str(value).split()).encode("ascii", "backslashreplace").decode("ascii")
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _default_plan_state_rows(root: Path) -> list[dict]:
    """Rows from the real plan_state store, called directly.

    The is-dir pre-check keeps a repo with no reports/plan_state (every test
    repo, a fresh clone) from paying for the import at all. The import is lazy
    so session_ledger's own import cost and failure modes are unchanged.
    """
    if not (root / "reports" / "plan_state").is_dir():
        return []
    pipeline_root = str(_PIPELINE_ROOT)
    if pipeline_root not in sys.path:
        sys.path.append(pipeline_root)  # append, never insert: cannot shadow anything
    from commands.governance import mission_authority  # noqa: E402

    return mission_authority._plan_state_report(root)


def stale_mission_block_lines(
    root: Path | None = None,
    *,
    plan_state_rows_fn: Callable[[Path], list[dict]] | None = None,
) -> list[str]:
    """The lines of the session-start stale-mission block; [] when there is
    nothing to say (a healthy repo prints nothing at all).

    Shape: one header with the count, at most _STALE_MISSION_MAX_LISTED rows
    (id plus days quiet, oldest first, a mission with no activity signal at all
    first of all), one pointer to the full list directly under those rows, and
    one line naming the unreadable-ledger missions (when there are none stale
    that line carries the pointer under it instead). Raises whatever the row
    source raises -- emit_stale_mission_block() is the fail-open caller.
    """
    root = root if root is not None else _REPO_ROOT
    rows_fn = plan_state_rows_fn or _PLAN_STATE_ROWS_FN or _default_plan_state_rows
    rows = [row for row in rows_fn(root) if isinstance(row, dict)]
    stale = [row for row in rows if row.get("stale")]
    unreadable = [row for row in rows if "error" in row]

    def _age(row: dict) -> float | None:
        age = row.get("age_days_since_last_activity")
        if isinstance(age, bool) or not isinstance(age, (int, float)):
            return None
        return float(age)

    def _sort_key(row: dict) -> tuple:
        age = _age(row)
        name = str(row.get("mission_id", "?"))
        return (0, 0.0, name) if age is None else (1, -age, name)

    stale.sort(key=_sort_key)

    lines: list[str] = []
    pointer = f"Full list: {_MISSION_STATUS_COMMAND}"
    if stale:
        lines.append(
            "Stale open missions (informational, no recent taskcard activity): "
            f"{len(stale)}"
        )
        for row in stale[:_STALE_MISSION_MAX_LISTED]:
            name = _ascii_display(row.get("mission_id", "?"), _MISSION_ID_DISPLAY_MAX)
            age = _age(row)
            quiet = "no activity signal" if age is None else f"quiet {int(age)}d"
            lines.append(f"  {name}  {quiet}")
        # "... and N more" counts the STALE rows, so the pointer sits directly under
        # them; the unreadable-ledger line (a different list) comes after it and can
        # never be misread as the thing the pointer's count refers to.
        hidden = len(stale) - _STALE_MISSION_MAX_LISTED
        lead = f"  ... and {hidden} more. " if hidden > 0 else "  "
        lines.append(f"{lead}{pointer}")
    if unreadable:
        names = [
            _ascii_display(row.get("mission_id", "?"), _MISSION_ID_DISPLAY_MAX)
            for row in unreadable
        ]
        shown = ", ".join(names[:_UNREADABLE_MISSION_MAX_LISTED])
        if len(names) > _UNREADABLE_MISSION_MAX_LISTED:
            shown += f", +{len(names) - _UNREADABLE_MISSION_MAX_LISTED} more"
        lines.append(
            f"Mission ledgers unreadable (staleness unknown): {len(unreadable)} - {shown}"
        )
        if not stale:
            lines.append(f"  {pointer}")  # nothing above it to hang the pointer on
    return lines


def emit_stale_mission_block(
    root: Path | None = None,
    *,
    plan_state_rows_fn: Callable[[Path], list[dict]] | None = None,
) -> None:
    """Print the stale-mission block to stdout. FAIL OPEN: never raises an
    Exception; on any failure prints exactly one short line naming the error
    class (never its message) so a broken detector is visible, not silent."""
    try:
        lines = stale_mission_block_lines(root, plan_state_rows_fn=plan_state_rows_fn)
        if lines:
            print("\n".join(lines))
    except Exception as exc:  # noqa: BLE001 -- fail-open by design: never break session start
        try:
            print(f"stale-mission check unavailable: {type(exc).__name__}")
        except Exception:  # noqa: BLE001 -- even a closed stdout must not break init
            pass


def cmd_init(args: argparse.Namespace) -> int:
    """Initialize (or idempotently resume) a session, then surface stale open
    missions. The surface is emitted here, around the whole body, so it runs on
    every path -- including the --if-missing fast paths that return before the
    print block (see the comment block above). It is in a `finally` because the
    list of abandoned missions has nothing to do with the session manifests: a
    failure inside init (an unwritable session dir, a lock timeout) must not
    also suppress it -- and the original error still propagates, unmasked
    (emit_stale_mission_block() never raises an Exception)."""
    try:
        return _cmd_init(args)
    finally:
        emit_stale_mission_block()


def _cmd_init(args: argparse.Namespace) -> int:
    _sweep_stale()
    if getattr(args, "if_missing", False) and args.session_id:
        # SessionStart-hook path (2026-08-30, T3): idempotent by design --
        # active is a no-op, stale reactivates, closed reopens (resume), and
        # only a genuinely missing manifest falls through to a real init.
        p = _session_path(args.session_id)
        m = _load_manifest(p)
        if m:
            status = m.get("status")
            if status == "active":
                print(f"session={args.session_id} base="
                      f"{(m.get('base_commit_sha') or 'none')[:12]} already-active")
                return 0
            if status == "stale":
                _mutate_manifest((args.session_id, p), lambda mm: None)
                print(f"session={args.session_id} base="
                      f"{(m.get('base_commit_sha') or 'none')[:12]} reactivated")
                return 0
            if status == "closed":
                if reopen_session(args.session_id):
                    print(f"session={args.session_id} base="
                          f"{(m.get('base_commit_sha') or 'none')[:12]} reopened")
                    return 0
    try:
        session_id = init_session(args.session_id,
                                  force=bool(getattr(args, "force_reinit", False)))
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    manifest = _load_manifest(_session_path(session_id))
    dirty_count = len(manifest.get("dirty_at_start", [])) if manifest else 0
    print(f"Session initialized: {session_id}")
    print(f"  Manifest: {_repo_rel(_session_path(session_id))}")
    print(f"  Dirty files at start: {dirty_count}")
    if dirty_count > 0 and manifest:
        for p in manifest["dirty_at_start"][:10]:
            print(f"    {p}")
        if dirty_count > 10:
            print(f"    ... and {dirty_count - 10} more")
    others = other_active_sessions(session_id)
    if others:
        print(f"  WARNING: {len(others)} other active session(s): {', '.join(others)}")
        print(f"    This session did NOT close them (HARDEN-A2). Pass --session-id")
        print(f"    {session_id} (or export {_ENV_SESSION_ID}={session_id}) on every")
        print(f"    subsequent call — resolution without it will fail as ambiguous.")
    print(f"  Identity: export {_ENV_SESSION_ID}={session_id}")
    return 0


def cmd_close(args: argparse.Namespace) -> int:
    if close_session(args.session_id):
        print(f"Session closed: {args.session_id}")
        return 0
    print(f"ERROR: no manifest for session '{args.session_id}'.", file=sys.stderr)
    return 2


def cmd_record(args: argparse.Namespace) -> int:
    if args.files_from:
        list_path = Path(args.files_from)
        if not list_path.is_file():
            print(f"ERROR: --files-from list not found: {args.files_from}", file=sys.stderr)
            return 1
        paths = [ln.strip() for ln in list_path.read_text(encoding="utf-8").splitlines()
                 if ln.strip()]
        count = record_files(paths, action=args.action, skill=args.skill,
                             session_id=args.session_id)
        if count is None:
            print("ERROR: no active session. Run 'init' first.", file=sys.stderr)
            return 1
        print(f"Recorded {count} files ({args.action})"
              + (f" [skill: {args.skill}]" if args.skill else ""))
        return 0
    if not args.file:
        print("ERROR: provide --file or --files-from.", file=sys.stderr)
        return 1
    ok = record_file(args.file, action=args.action, skill=args.skill,
                     session_id=args.session_id)
    if not ok:
        print("ERROR: no active session. Run 'init' first.", file=sys.stderr)
        return 1
    print(f"Recorded: {args.file} ({args.action})"
          + (f" [skill: {args.skill}]" if args.skill else ""))
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    touched = get_touched_files(args.session_id)
    if not touched:
        print("No files touched in session.", file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(touched, indent=2, ensure_ascii=False))
    elif args.format == "paths":
        for p in sorted(touched.keys()):
            print(p)
    else:  # text
        for p in sorted(touched.keys()):
            entry = touched[p]
            skills_str = ", ".join(entry.get("skills", [])) or "—"
            print(f"  {entry['action']:10s} {p}  [{skills_str}]")
    return 0


def cmd_current(args: argparse.Namespace) -> int:
    sid = get_current_session_id()
    if not sid:
        print("No active session.", file=sys.stderr)
        return 2
    print(sid)
    return 0


def cmd_candidates(args: argparse.Namespace) -> int:
    candidates, excluded_prior, excluded_unknown = get_candidates(args.session_id)

    if args.format == "json":
        print(json.dumps({
            "candidates": candidates,
            "excluded_dirty_at_start": excluded_prior,
            "excluded_not_in_ledger": excluded_unknown,
        }, indent=2, ensure_ascii=False))
        return 0

    if not candidates:
        print("No commit candidates (ledger is empty or no dirty files match).",
              file=sys.stderr)
        if excluded_prior:
            print(f"\nExcluded (dirty before session): {len(excluded_prior)} files",
                  file=sys.stderr)
        if excluded_unknown:
            print(f"\nExcluded (not in ledger): {len(excluded_unknown)} files",
                  file=sys.stderr)
        return 2

    print(f"Commit candidates ({len(candidates)} files):")
    for p in candidates:
        print(f"  {p}")

    if excluded_prior:
        print(f"\nExcluded (dirty before session): {len(excluded_prior)} files")
        for p in excluded_prior[:5]:
            print(f"  {p}")
        if len(excluded_prior) > 5:
            print(f"  ... and {len(excluded_prior) - 5} more")

    if excluded_unknown:
        print(f"\nExcluded (not in ledger): {len(excluded_unknown)} files")
        for p in excluded_unknown[:5]:
            print(f"  {p}")
        if len(excluded_unknown) > 5:
            print(f"  ... and {len(excluded_unknown) - 5} more")

    return 0


def _log_adopt(adopt_args: list[str], count: int) -> None:
    """Non-fatal session logger entry for adopt operations."""
    try:
        from session_logger import log_invocation
        log_invocation("S-76", "commit/adopt", args=adopt_args + [f"count={count}"])
    except Exception:
        pass  # Non-fatal — logging must not break adoption


def _report_adopt_skipped(skipped: dict[str, str]) -> None:
    if not skipped:
        return
    print(f"REFUSED {len(skipped)} path(s) claimed by other ACTIVE session(s):",
          file=sys.stderr)
    for p, sid in sorted(skipped.items())[:10]:
        print(f"  {p}  [claimed by {sid}]", file=sys.stderr)
    if len(skipped) > 10:
        print(f"  ... and {len(skipped) - 10} more", file=sys.stderr)
    print("Override (audited): re-run with --confirm-cross-session.", file=sys.stderr)


def cmd_adopt(args: argparse.Namespace) -> int:
    active = _resolve_session(args.session_id)
    if not active:
        print("ERROR: no active session. Run 'init' first.", file=sys.stderr)
        return 1
    sid = active[0]
    confirm = bool(getattr(args, "confirm_cross_session", False))
    skipped: dict[str, str] = {}

    if args.all:
        # Adopt all currently dirty files
        dirty = _git_dirty_files()
        if not dirty:
            print("No dirty files to adopt.", file=sys.stderr)
            return 2
        count = adopt_files(dirty, action="modified", skill=args.skill,
                            session_id=sid, confirm_cross_session=confirm,
                            skipped_out=skipped)
        print(f"Adopted {count} files (all dirty)")
        _report_adopt_skipped(skipped)
        _log_adopt(["--all"] + (["--confirm-cross-session"] if confirm else [])
                   + [f"skipped={len(skipped)}"], count)
        return 0

    if args.group:
        count, matched = adopt_by_group(args.group, action="modified", skill=args.skill,
                                        session_id=sid, confirm_cross_session=confirm,
                                        skipped_out=skipped)
        if count == 0 and not skipped:
            print(f"No dirty files match group '{args.group}'.", file=sys.stderr)
            return 2
        print(f"Adopted {count} files in group '{args.group}':")
        for p in matched[:10]:
            print(f"  {p}")
        if len(matched) > 10:
            print(f"  ... and {len(matched) - 10} more")
        _report_adopt_skipped(skipped)
        _log_adopt(["--group", args.group, f"skipped={len(skipped)}"], count)
        return 0

    if args.glob:
        count, matched = adopt_by_glob(args.glob, action="modified", skill=args.skill,
                                       session_id=sid, confirm_cross_session=confirm,
                                       skipped_out=skipped)
        if count == 0 and not skipped:
            print(f"No dirty files match pattern '{args.glob}'.", file=sys.stderr)
            return 2
        print(f"Adopted {count} files matching '{args.glob}':")
        for p in matched[:10]:
            print(f"  {p}")
        if len(matched) > 10:
            print(f"  ... and {len(matched) - 10} more")
        _report_adopt_skipped(skipped)
        _log_adopt(["--glob", args.glob, f"skipped={len(skipped)}"], count)
        return 0

    if args.files:
        count = adopt_files(args.files, action="modified", skill=args.skill,
                            session_id=sid, confirm_cross_session=confirm,
                            skipped_out=skipped)
        print(f"Adopted {count} files")
        _report_adopt_skipped(skipped)
        _log_adopt(["--files"] + args.files[:5] + [f"skipped={len(skipped)}"], count)
        return 0

    print("ERROR: specify --all, --group, --glob, or --files", file=sys.stderr)
    return 1


def cmd_dirty(args: argparse.Namespace) -> int:
    """Show all dirty files grouped by commit group, with adoption status."""
    active = _resolve_session(args.session_id)
    manifest = _load_manifest(active[1]) if active else None
    touched = set(manifest.get("touched_files", {}).keys()) if manifest else set()
    dirty_at_start = set(manifest.get("dirty_at_start", [])) if manifest else set()

    current_dirty = _git_dirty_files()
    if not current_dirty:
        print("Working tree is clean.")
        return 0

    groups = group_files(current_dirty)

    if args.format == "json":
        result = {}
        for g, files in sorted(groups.items()):
            result[g] = [
                {"path": f, "in_ledger": f in touched, "was_dirty_at_start": f in dirty_at_start}
                for f in files
            ]
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    for g in sorted(groups.keys()):
        files = groups[g]
        print(f"\n{g} ({len(files)} files):")
        for f in files:
            marker = ""
            if f in touched:
                marker = " [LEDGER]"
            elif f in dirty_at_start:
                marker = " [PRE-SESSION]"
            else:
                marker = " [UNTRACKED]"
            print(f"  {f}{marker}")
    return 0


def cmd_groups(args: argparse.Namespace) -> int:
    candidates, _, _ = get_candidates(args.session_id)
    if not candidates:
        print("No commit candidates to group.", file=sys.stderr)
        return 2

    groups = group_files(candidates)

    if args.format == "json":
        print(json.dumps(groups, indent=2, ensure_ascii=False))
        return 0

    for group_name in sorted(groups.keys()):
        files = groups[group_name]
        print(f"\n{group_name} ({len(files)} files):")
        for p in files[:10]:
            print(f"  {p}")
        if len(files) > 10:
            print(f"  ... and {len(files) - 10} more")
    return 0


def check_staged(
    staged_paths: list[str], session_id: str | None = None
) -> tuple[list[str], list[str]]:
    """Check staged paths against the session ledger.

    Returns (allowed, blocked) where:
      - allowed: paths that are in the session ledger (touched or adopted)
      - blocked: paths that are NOT in the session ledger
    If no active session exists, returns (staged_paths, []) — no enforcement.
    """
    active = _resolve_session(session_id)
    if not active:
        return staged_paths, []

    manifest = _load_manifest(active[1])
    if not manifest:
        return staged_paths, []

    touched = set(manifest.get("touched_files", {}).keys())
    allowed = []
    blocked = []
    for p in staged_paths:
        normalized = _normalize_path(p)
        if normalized in touched:
            allowed.append(normalized)
        else:
            blocked.append(normalized)
    return allowed, blocked


def cmd_check_staged(args: argparse.Namespace) -> int:
    """Check staged files against session ledger. Exit 0 if all OK, exit 1 if blocked."""
    if sys.stdin.isatty():
        print("Usage: pipe staged paths via stdin, e.g.:", file=sys.stderr)
        print("  git diff --cached --name-only | session_ledger.py check-staged", file=sys.stderr)
        return 1
    staged_paths = [line.strip() for line in sys.stdin if line.strip()]
    if not staged_paths:
        return 0

    allowed, blocked = check_staged(staged_paths, session_id=args.session_id)
    if not blocked:
        return 0

    # Get session info for diagnostic output
    active = _resolve_session(args.session_id)
    sid = active[0] if active else "?"
    manifest = _load_manifest(active[1]) if active else None
    touched_count = len(manifest.get("touched_files", {})) if manifest else 0

    print(f"BLOCKED: {len(blocked)} staged file(s) not found in session ledger.", file=sys.stderr)
    for p in blocked[:10]:
        print(f"  {p}", file=sys.stderr)
    if len(blocked) > 10:
        print(f"  ... and {len(blocked) - 10} more", file=sys.stderr)
    print(f"Session: {sid} (active, {touched_count} touched files)", file=sys.stderr)
    print("Bypass: add '# SKIP-SESSION-CHECK' to commit message.", file=sys.stderr)
    return 1


def inherit_session(
    prior_session_id: str | None = None, session_id: str | None = None
) -> tuple[int, list[str]]:
    """Inherit touched files from a prior (closed) session into the current one.

    If prior_session_id is None, finds the most recently closed session.
    Returns (count_inherited, list_of_inherited_paths).
    """
    active = _resolve_session(session_id)
    if not active:
        return 0, []

    # Find prior session
    if prior_session_id:
        prior_manifest = _load_manifest(_session_path(prior_session_id))
    else:
        # Find most recently closed session (by filename, descending)
        prior_manifest = None
        if _SESSION_DIR.exists():
            for f in sorted(_SESSION_DIR.glob("*.json"), reverse=True):
                if f.name.endswith(".tmp"):
                    continue
                m = _load_manifest(f)
                if m and m.get("status") == "closed" and m.get("touched_files"):
                    prior_manifest = m
                    prior_session_id = m.get("session_id", f.stem)
                    break

    if not prior_manifest or not prior_manifest.get("touched_files"):
        return 0, []

    # Adopt prior session's touched files, preserving original actions.
    # Group by action to minimize manifest writes (one adopt_files call per action).
    prior_touched = prior_manifest["touched_files"]
    by_action: dict[str, list[str]] = {}
    for path, meta in prior_touched.items():
        action = meta.get("action", "modified") if isinstance(meta, dict) else "modified"
        by_action.setdefault(action, []).append(path)
    total = 0
    all_paths: list[str] = []
    for action, paths in sorted(by_action.items()):
        total += adopt_files(paths, action=action, session_id=active[0])
        all_paths.extend(paths)
    all_paths.sort()
    return total, all_paths


def cmd_inherit(args: argparse.Namespace) -> int:
    """Inherit touched files from a prior session into the current one."""
    into_sid = getattr(args, "into", None)
    active = _resolve_session(into_sid)
    if not active:
        print("ERROR: no active session. Run 'init' first.", file=sys.stderr)
        return 1

    # Pre-check: if explicit session ID given, verify it exists before calling inherit
    if args.session_id:
        manifest_check = _load_manifest(_session_path(args.session_id))
        if manifest_check is None:
            print(f"ERROR: session '{args.session_id}' not found "
                  f"(no manifest at {_session_path(args.session_id)}).", file=sys.stderr)
            return 2

    count, paths = inherit_session(args.session_id, session_id=active[0])
    if count == 0 and not paths:
        if args.session_id:
            print(f"No touched files in session '{args.session_id}' to inherit.", file=sys.stderr)
        else:
            print("No prior closed session with touched files found.", file=sys.stderr)
        return 2

    print(f"Inherited {count} files from prior session"
          + (f" '{args.session_id}'" if args.session_id else "") + ":")
    for p in paths[:15]:
        print(f"  {p}")
    if len(paths) > 15:
        print(f"  ... and {len(paths) - 15} more")
    return 0


def cmd_diagnose(args: argparse.Namespace) -> int:
    """Print comprehensive diagnostics for session discovery debugging."""
    print("=== SESSION LEDGER DIAGNOSTICS ===")
    print(f"Repo root:       {_REPO_ROOT}")
    print(f"Session dir:     {_repo_rel(_SESSION_DIR)}"
          f"  [{'EXISTS' if _SESSION_DIR.exists() else 'MISSING'}]")

    # ACTIVE pointer
    pointer_id = _read_active_pointer()
    if pointer_id:
        pointer_manifest = _load_manifest(_session_path(pointer_id))
        if pointer_manifest and pointer_manifest.get("status") == "active":
            print(f"ACTIVE pointer:  {pointer_id}    [VALID]")
        elif pointer_manifest:
            print(f"ACTIVE pointer:  {pointer_id}    [STALE -- status={pointer_manifest.get('status')}]")
        else:
            print(f"ACTIVE pointer:  {pointer_id}    [BROKEN -- manifest not loadable]")
    else:
        print("ACTIVE pointer:  (not set)")

    # Session files — full table with computed (would-be) staleness. Read-only:
    # diagnose never mutates manifests; the sweep runs on real resolutions.
    if _SESSION_DIR.exists():
        import time as _time
        now = _time.time()
        json_files = sorted(_SESSION_DIR.glob("*.json"))
        active_count = 0
        stale_count = 0
        closed_count = 0
        broken_count = 0
        rows: list[str] = []
        for f in json_files:
            m = _load_manifest(f)
            if not m:
                broken_count += 1
                rows.append(f"  {f.stem:28s} BROKEN (manifest not loadable)")
                continue
            status = m.get("status", "?")
            try:
                age_h = (now - f.stat().st_mtime) / 3600.0
            except OSError:
                age_h = 0.0
            touched_count = len(m.get("touched_files", {}))
            if status == "active":
                if age_h > _stale_ttl_hours(m):
                    stale_count += 1
                    label = f"active (STALE — {age_h:.1f}h idle > ttl {_stale_ttl_hours(m):.0f}h)"
                else:
                    active_count += 1
                    label = f"active ({age_h:.1f}h idle)"
            elif status == "stale":
                stale_count += 1
                label = f"stale ({age_h:.1f}h idle)"
            else:
                closed_count += 1
                label = status
            rows.append(f"  {m.get('session_id', f.stem):28s} {label}  [{touched_count} touched]")
        print(f"Session files:   {len(json_files)} total"
              f" ({active_count} live, {stale_count} stale, {closed_count} closed"
              + (f", {broken_count} broken" if broken_count else "") + ")")
        for row in rows:
            print(row)
    else:
        print("Session files:   (directory does not exist)")

    # Live-session resolution preview — computed WITHOUT mutating any manifest
    # (diagnose stays read-only; the real sweep runs on actual operations).
    live: list[str] = []
    if _SESSION_DIR.exists():
        import time as _time
        now = _time.time()
        for f in _SESSION_DIR.glob("*.json"):
            m = _load_manifest(f)
            if not m or m.get("status") != "active":
                continue
            try:
                age_h = (now - f.stat().st_mtime) / 3600.0
            except OSError:
                age_h = 0.0
            if age_h <= _stale_ttl_hours(m):
                live.append(m.get("session_id", f.stem))
    env_id = session_identity.resolve()
    if env_id:
        print(f"Resolved caller identity: {env_id}")
    if len(live) > 1:
        print(f"Resolution:      AMBIGUOUS — {len(live)} live sessions: " + ", ".join(sorted(live)))
        print(f"                 Operations require --session-id or {_ENV_SESSION_ID}.")
    elif len(live) == 1:
        sid = live[0]
        manifest = _load_manifest(_session_path(sid))
        if manifest:
            print(f"Active session:  {sid}")
            print(f"  Started:       {manifest.get('started_at', '?')}")
            print(f"  Dirty at start: {len(manifest.get('dirty_at_start', []))} files")
            print(f"  Touched files: {len(manifest.get('touched_files', {}))}")
            print(f"  Status:        {manifest.get('status', '?')}")
    else:
        print("Active session:  NONE FOUND")

    return 0


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="session_ledger",
        description="Session-scoped file touch ledger for /commit scoping.",
    )
    parser.add_argument(
        "--repo-root", default=None,
        help="Override repo root (testing only -- production always uses the real repo root)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # init
    p_init = sub.add_parser("init", help="Initialize a new session with dirty-file snapshot")
    p_init.add_argument("--session-id", default=None, help="Override session ID (default: auto-generated)")
    p_init.add_argument("--if-missing", action="store_true", dest="if_missing",
                        help="Idempotent init (SessionStart hook): active manifest is a "
                             "no-op, stale reactivates, closed reopens; only a missing "
                             "manifest performs a real init. Requires --session-id. "
                             "Every path (fast or not) still ends with the stale-open-"
                             "mission block, when there is anything to report.")
    p_init.add_argument("--force-reinit", action="store_true", dest="force_reinit",
                        help="Re-init an id whose manifest is ACTIVE (wipes its ledger — audited)")

    # record
    p_rec = sub.add_parser("record", help="Record a file touch")
    p_rec.add_argument("--file", default=None, help="Repo-relative file path")
    p_rec.add_argument("--files-from", default=None, dest="files_from",
                       help="Path to newline-delimited list of files (batch mode, one manifest write)")
    p_rec.add_argument("--action", required=True, choices=["created", "modified", "deleted", "renamed"],
                       help="Type of file operation")
    p_rec.add_argument("--skill", default=None, help="S-{n} skill ID (optional)")
    p_rec.add_argument("--session-id", default=None,
                       help=f"Explicit session identity (default: {_ENV_SESSION_ID} env, then unambiguous scan)")

    # list
    p_list = sub.add_parser("list", help="List session-touched files")
    p_list.add_argument("--session-id", default=None, help="Session ID (default: active session)")
    p_list.add_argument("--format", choices=["text", "paths", "json"], default="text")

    # current
    sub.add_parser("current", help="Print current active session ID")

    # close
    p_close = sub.add_parser("close", help="Close a session BY NAME (HARDEN-A2 — no close-whatever-is-active)")
    p_close.add_argument("--session-id", required=True, help="Session ID to close (must be explicit)")

    # adopt
    p_adopt = sub.add_parser("adopt", help="Retroactively adopt dirty files into the session ledger")
    p_adopt.add_argument("--all", action="store_true", help="Adopt ALL currently dirty files")
    p_adopt.add_argument("--group", default=None,
                         help="Adopt dirty files matching a commit group (e.g. 'content(locale)')")
    p_adopt.add_argument("--glob", default=None,
                         help="Adopt dirty files matching a glob pattern (e.g. 'content/kb.aspose.org/*')")
    p_adopt.add_argument("--files", nargs="*", default=None,
                         help="Adopt specific files by path")
    p_adopt.add_argument("--skill", default=None, help="S-{n} skill ID to attribute (optional)")
    p_adopt.add_argument("--session-id", default=None,
                         help=f"Explicit session identity (default: {_ENV_SESSION_ID} env, then unambiguous scan)")
    p_adopt.add_argument("--confirm-cross-session", action="store_true",
                         dest="confirm_cross_session",
                         help="Adopt even paths claimed by another ACTIVE session (audited override)")

    # dirty
    p_dirty = sub.add_parser("dirty", help="Show all dirty files with group and adoption status")
    p_dirty.add_argument("--format", choices=["text", "json"], default="text")
    p_dirty.add_argument("--session-id", default=None)

    # candidates
    p_cand = sub.add_parser("candidates", help="Show commit candidates (ledger AND git dirty)")
    p_cand.add_argument("--format", choices=["text", "json"], default="text")
    p_cand.add_argument("--session-id", default=None)

    # groups
    p_groups = sub.add_parser("groups", help="Classify candidates into commit groups")
    p_groups.add_argument("--format", choices=["text", "json"], default="text")
    p_groups.add_argument("--session-id", default=None)

    # diagnose
    sub.add_parser("diagnose", help="Print comprehensive session discovery diagnostics (read-only)")

    # check-staged
    p_cs = sub.add_parser("check-staged",
                          help="Check staged paths against session ledger (reads from stdin)")
    p_cs.add_argument("--session-id", default=None)

    # inherit
    p_inherit = sub.add_parser("inherit",
                               help="Inherit touched files from a prior closed session")
    p_inherit.add_argument("--session-id", default=None,
                           help="Specific prior session ID (default: most recent closed)")
    p_inherit.add_argument("--into", default=None,
                           help="Session to inherit INTO (default: env/unambiguous scan)")

    args = parser.parse_args(argv)
    if args.repo_root:
        configure(repo_root=Path(args.repo_root))
    dispatch = {
        "init": cmd_init,
        "record": cmd_record,
        "list": cmd_list,
        "current": cmd_current,
        "close": cmd_close,
        "adopt": cmd_adopt,
        "dirty": cmd_dirty,
        "candidates": cmd_candidates,
        "groups": cmd_groups,
        "diagnose": cmd_diagnose,
        "check-staged": cmd_check_staged,
        "inherit": cmd_inherit,
    }
    try:
        return dispatch[args.command](args)
    except AmbiguousSessionError as exc:
        print(f"AMBIGUOUS: {exc}", file=sys.stderr)
        for sid in exc.candidates:
            print(f"  candidate: {sid}", file=sys.stderr)
        print(f"Fix: pass --session-id <id> or export {_ENV_SESSION_ID}=<id>.",
              file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
