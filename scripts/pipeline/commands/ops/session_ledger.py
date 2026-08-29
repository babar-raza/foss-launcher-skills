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
  python scripts/pipeline/session_ledger.py init
  python scripts/pipeline/session_ledger.py init --session-id 20260409-143022-a7f3

  # Record a file touch
  python scripts/pipeline/session_ledger.py record --file content/docs.aspose.org/en/words/python/foo.md --action created
  python scripts/pipeline/session_ledger.py record --file content/docs.aspose.org/en/words/python/foo.md --action modified --skill S-20

  # List session-touched files
  python scripts/pipeline/session_ledger.py list
  python scripts/pipeline/session_ledger.py list --format json
  python scripts/pipeline/session_ledger.py list --format paths

  # Get current session ID
  python scripts/pipeline/session_ledger.py current

  # Retroactively adopt dirty files into the session (for pre-existing sessions)
  python scripts/pipeline/session_ledger.py adopt --all
  python scripts/pipeline/session_ledger.py adopt --group "content(locale)"
  python scripts/pipeline/session_ledger.py adopt --glob "content/kb.aspose.org/*"
  python scripts/pipeline/session_ledger.py adopt --files path/to/file1.md path/to/file2.md

  # Show all dirty files with group and adoption status
  python scripts/pipeline/session_ledger.py dirty
  python scripts/pipeline/session_ledger.py dirty --format json

  # Show commit candidates (ledger AND git dirty, minus dirty_at_start)
  python scripts/pipeline/session_ledger.py candidates
  python scripts/pipeline/session_ledger.py candidates --format json

  # Classify files into commit groups
  python scripts/pipeline/session_ledger.py groups
  python scripts/pipeline/session_ledger.py groups --format json

Usage (Python import):
  from session_ledger import init_session, record_file, get_candidates, get_current_session_id

Exit codes:
  0  Success
  1  Error (no active session, I/O failure)
  2  No session found
"""
from __future__ import annotations

import argparse
import json
import secrets
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# 2026-08-29 sync: additive, informational caller identity (agent-harness
# identity via env vars -- see session_identity.py's own docstring for why
# this is deliberately NOT wired into this module's session-ID GENERATION,
# only recorded alongside it).
_LIB_DIR = _DEFAULT_REPO_ROOT / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))
try:
    import session_identity
except ImportError:  # pragma: no cover - defensive, must never break session_ledger
    session_identity = None

_REPO_ROOT = _DEFAULT_REPO_ROOT
_SESSION_DIR = _REPO_ROOT / "reports" / "session-state"
_ACTIVE_POINTER = _SESSION_DIR / "ACTIVE"


def configure(
    repo_root: Path | None = None,
    session_dir: Path | None = None,
) -> None:
    """Reconfigure module-level paths for testing or alternative layouts.

    - Called with no arguments: resets to built-in defaults.
    - repo_root only: derives session_dir as ``repo_root / "reports" / "session-state"``.
    - Both provided: uses them directly.

    ``_ACTIVE_POINTER`` is always recomputed from ``_SESSION_DIR``.
    """
    global _REPO_ROOT, _SESSION_DIR, _ACTIVE_POINTER

    _REPO_ROOT = repo_root if repo_root is not None else _DEFAULT_REPO_ROOT

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


def classify_file(path: str) -> str:
    """Classify a repo-relative path into a commit group name.

    Returns the group name (e.g. 'content(docs)') or 'chore(misc)' if no
    prefix matches.
    """
    normalized = path.replace("\\", "/").lstrip("./")

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
            timeout=30,
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
    """Load session manifest, returning None if missing or corrupt."""
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _find_active_session() -> tuple[str, Path] | None:
    """Find the most recent active session manifest.

    Priority order:
    1. ACTIVE pointer file (O(1) — written by init_session)
    2. Directory scan fallback (O(N) — safety net)
    """
    # Fast path: ACTIVE pointer file
    pointer_id = _read_active_pointer()
    if pointer_id:
        p = _session_path(pointer_id)
        m = _load_manifest(p)
        if m and m.get("status") == "active":
            return pointer_id, p
        # Pointer is stale — clean it up
        _clear_active_pointer()

    if not _SESSION_DIR.exists():
        return None

    # Slow fallback: scan all manifests by filename (lexicographic = chronological)
    for f in sorted(_SESSION_DIR.glob("*.json"), reverse=True):
        if f.name.endswith(".tmp"):
            continue
        m = _load_manifest(f)
        if m and m.get("status") == "active":
            sid = m.get("session_id", f.stem)
            # Repair: write ACTIVE pointer so next lookup is O(1)
            _write_active_pointer(sid)
            return sid, f

    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def init_session(session_id: str | None = None) -> str:
    """Initialize a new session with dirty-file snapshot.

    Returns the session ID.
    """
    if session_id is None:
        session_id = _generate_session_id()

    # Deactivate any prior active session
    prior = _find_active_session()
    if prior:
        _, prior_path = prior
        prior_manifest = _load_manifest(prior_path)
        if prior_manifest:
            prior_manifest["status"] = "closed"
            prior_manifest["closed_at"] = _now_iso()
            _save_manifest(prior_path, prior_manifest)
    _clear_active_pointer()

    dirty = _git_dirty_files()
    caller_identity = None
    if session_identity is not None:
        try:
            caller_identity = session_identity.resolve_sanitized()
        except Exception:  # pragma: no cover - identity resolution must never break init
            caller_identity = None
    manifest = {
        "session_id": session_id,
        "started_at": _now_iso(),
        "dirty_at_start": dirty,
        "touched_files": {},
        "status": "active",
        "caller_identity": caller_identity,
    }

    path = _session_path(session_id)
    _save_manifest(path, manifest)
    _write_active_pointer(session_id)
    return session_id


def record_file(
    file_path: str,
    action: str = "modified",
    skill: str | None = None,
) -> bool:
    """Record a file touch in the current session ledger.

    Args:
        file_path: Repo-relative path (forward slashes).
        action: One of 'created', 'modified', 'deleted', 'renamed'.
        skill: Optional S-{n} skill ID.

    Returns True if recorded, False if no active session.
    """
    active = _find_active_session()
    if not active:
        return False

    session_id, manifest_path = active
    manifest = _load_manifest(manifest_path)
    if not manifest:
        return False

    normalized = file_path.replace("\\", "/").lstrip("./")
    touched = manifest.setdefault("touched_files", {})

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
        entry = {
            "action": action,
            "first_touched": _now_iso(),
            "last_touched": _now_iso(),
            "skills": [skill] if skill else [],
        }
        touched[normalized] = entry

    _save_manifest(manifest_path, manifest)
    return True


def get_current_session_id() -> str | None:
    """Return the current active session ID, or None."""
    active = _find_active_session()
    return active[0] if active else None


def get_touched_files(session_id: str | None = None) -> dict[str, dict]:
    """Return the touched_files dict for the given or active session."""
    if session_id:
        manifest = _load_manifest(_session_path(session_id))
    else:
        active = _find_active_session()
        if not active:
            return {}
        manifest = _load_manifest(active[1])

    if not manifest:
        return {}
    return manifest.get("touched_files", {})


def get_dirty_at_start(session_id: str | None = None) -> list[str]:
    """Return the dirty_at_start list for the given or active session."""
    if session_id:
        manifest = _load_manifest(_session_path(session_id))
    else:
        active = _find_active_session()
        if not active:
            return []
        manifest = _load_manifest(active[1])

    if not manifest:
        return []
    return manifest.get("dirty_at_start", [])


def get_candidates() -> tuple[list[str], list[str], list[str]]:
    """Compute commit candidates from session ledger.

    Returns (candidates, excluded_dirty_at_start, excluded_not_in_ledger).
      - candidates: files in ledger AND currently dirty
      - excluded_dirty_at_start: dirty files that existed before session
      - excluded_not_in_ledger: dirty files not in ledger (unknown source)
    """
    active = _find_active_session()
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
) -> int:
    """Adopt files into the current session ledger retroactively.

    Use this when a session started before the ledger existed, or when files
    were touched outside the normal record flow and need to be claimed.

    If remove_from_dirty_at_start is True (default), adopted files are also
    removed from dirty_at_start so they become commit candidates.

    Returns the count of files adopted.
    """
    active = _find_active_session()
    if not active:
        return 0

    session_id, manifest_path = active
    manifest = _load_manifest(manifest_path)
    if not manifest:
        return 0

    touched = manifest.setdefault("touched_files", {})
    dirty_at_start = manifest.get("dirty_at_start", [])
    count = 0

    for file_path in paths:
        normalized = file_path.replace("\\", "/").lstrip("./")
        if normalized not in touched:
            touched[normalized] = {
                "action": action,
                "first_touched": _now_iso(),
                "last_touched": _now_iso(),
                "skills": [skill] if skill else [],
                "adopted": True,
            }
            count += 1
        # Also remove from dirty_at_start so it becomes a candidate
        if remove_from_dirty_at_start and normalized in dirty_at_start:
            dirty_at_start.remove(normalized)

    manifest["dirty_at_start"] = dirty_at_start
    _save_manifest(manifest_path, manifest)
    return count


def adopt_by_glob(pattern: str, action: str = "modified", skill: str | None = None) -> tuple[int, list[str]]:
    """Adopt all currently dirty files matching a glob pattern.

    Returns (count_adopted, list_of_adopted_paths).
    """
    current_dirty = _git_dirty_files()
    import fnmatch
    matched = [p for p in current_dirty if fnmatch.fnmatch(p, pattern)]
    if not matched:
        return 0, []
    count = adopt_files(matched, action=action, skill=skill)
    return count, matched


def adopt_by_group(group_name: str, action: str = "modified", skill: str | None = None) -> tuple[int, list[str]]:
    """Adopt all currently dirty files belonging to a commit group.

    Group names match the classifier output: content(docs), content(locale),
    fix(pipeline), etc.

    Returns (count_adopted, list_of_adopted_paths).
    """
    current_dirty = _git_dirty_files()
    matched = [p for p in current_dirty if classify_file(p) == group_name]
    if not matched:
        return 0, []
    count = adopt_files(matched, action=action, skill=skill)
    return count, matched


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

def cmd_init(args: argparse.Namespace) -> int:
    # Capture prior session info before init closes it
    prior = _find_active_session()
    prior_id = None
    prior_touched_count = 0
    if prior:
        prior_id = prior[0]
        prior_manifest = _load_manifest(prior[1])
        if prior_manifest:
            prior_touched_count = len(prior_manifest.get("touched_files", {}))

    session_id = init_session(args.session_id)
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
    if prior_id:
        print(f"  Prior session closed: {prior_id} ({prior_touched_count} touched files)")
        if prior_touched_count > 0:
            print(f"    -> Run 'inherit' to carry forward prior session's work")
    return 0


def cmd_record(args: argparse.Namespace) -> int:
    ok = record_file(args.file, action=args.action, skill=args.skill)
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
    candidates, excluded_prior, excluded_unknown = get_candidates()

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


def cmd_adopt(args: argparse.Namespace) -> int:
    active = _find_active_session()
    if not active:
        print("ERROR: no active session. Run 'init' first.", file=sys.stderr)
        return 1

    if args.all:
        # Adopt all currently dirty files
        dirty = _git_dirty_files()
        if not dirty:
            print("No dirty files to adopt.", file=sys.stderr)
            return 2
        count = adopt_files(dirty, action="modified", skill=args.skill)
        print(f"Adopted {count} files (all dirty)")
        _log_adopt(["--all"], count)
        return 0

    if args.group:
        count, matched = adopt_by_group(args.group, action="modified", skill=args.skill)
        if count == 0:
            print(f"No dirty files match group '{args.group}'.", file=sys.stderr)
            return 2
        print(f"Adopted {count} files in group '{args.group}':")
        for p in matched[:10]:
            print(f"  {p}")
        if len(matched) > 10:
            print(f"  ... and {len(matched) - 10} more")
        _log_adopt(["--group", args.group], count)
        return 0

    if args.glob:
        count, matched = adopt_by_glob(args.glob, action="modified", skill=args.skill)
        if count == 0:
            print(f"No dirty files match pattern '{args.glob}'.", file=sys.stderr)
            return 2
        print(f"Adopted {count} files matching '{args.glob}':")
        for p in matched[:10]:
            print(f"  {p}")
        if len(matched) > 10:
            print(f"  ... and {len(matched) - 10} more")
        _log_adopt(["--glob", args.glob], count)
        return 0

    if args.files:
        count = adopt_files(args.files, action="modified", skill=args.skill)
        print(f"Adopted {count} files")
        _log_adopt(["--files"] + args.files[:5], count)
        return 0

    print("ERROR: specify --all, --group, --glob, or --files", file=sys.stderr)
    return 1


def cmd_dirty(args: argparse.Namespace) -> int:
    """Show all dirty files grouped by commit group, with adoption status."""
    active = _find_active_session()
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
    candidates, _, _ = get_candidates()
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


def check_staged(staged_paths: list[str]) -> tuple[list[str], list[str]]:
    """Check staged paths against the session ledger.

    Returns (allowed, blocked) where:
      - allowed: paths that are in the session ledger (touched or adopted)
      - blocked: paths that are NOT in the session ledger
    If no active session exists, returns (staged_paths, []) — no enforcement.
    """
    active = _find_active_session()
    if not active:
        return staged_paths, []

    manifest = _load_manifest(active[1])
    if not manifest:
        return staged_paths, []

    touched = set(manifest.get("touched_files", {}).keys())
    allowed = []
    blocked = []
    for p in staged_paths:
        normalized = p.replace("\\", "/").lstrip("./")
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

    allowed, blocked = check_staged(staged_paths)
    if not blocked:
        return 0

    # Get session info for diagnostic output
    active = _find_active_session()
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


def inherit_session(prior_session_id: str | None = None) -> tuple[int, list[str]]:
    """Inherit touched files from a prior (closed) session into the current one.

    If prior_session_id is None, finds the most recently closed session.
    Returns (count_inherited, list_of_inherited_paths).
    """
    active = _find_active_session()
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
        total += adopt_files(paths, action=action)
        all_paths.extend(paths)
    all_paths.sort()
    return total, all_paths


def cmd_inherit(args: argparse.Namespace) -> int:
    """Inherit touched files from a prior session into the current one."""
    active = _find_active_session()
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

    count, paths = inherit_session(args.session_id)
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

    # Session files
    if _SESSION_DIR.exists():
        json_files = list(_SESSION_DIR.glob("*.json"))
        active_count = 0
        closed_count = 0
        broken_count = 0
        for f in json_files:
            m = _load_manifest(f)
            if not m:
                broken_count += 1
            elif m.get("status") == "active":
                active_count += 1
            else:
                closed_count += 1
        print(f"Session files:   {len(json_files)} total"
              f" ({active_count} active, {closed_count} closed"
              + (f", {broken_count} broken" if broken_count else "") + ")")
    else:
        print("Session files:   (directory does not exist)")

    # Active session details
    active = _find_active_session()
    if active:
        sid, path = active
        manifest = _load_manifest(path)
        if manifest:
            dirty_count = len(manifest.get("dirty_at_start", []))
            touched_count = len(manifest.get("touched_files", {}))
            print(f"Active session:  {sid}")
            print(f"  Started:       {manifest.get('started_at', '?')}")
            print(f"  Dirty at start: {dirty_count} files")
            print(f"  Touched files: {touched_count}")
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
    sub = parser.add_subparsers(dest="command", required=True)

    # init
    p_init = sub.add_parser("init", help="Initialize a new session with dirty-file snapshot")
    p_init.add_argument("--session-id", default=None, help="Override session ID (default: auto-generated)")

    # record
    p_rec = sub.add_parser("record", help="Record a file touch")
    p_rec.add_argument("--file", required=True, help="Repo-relative file path")
    p_rec.add_argument("--action", required=True, choices=["created", "modified", "deleted", "renamed"],
                       help="Type of file operation")
    p_rec.add_argument("--skill", default=None, help="S-{n} skill ID (optional)")

    # list
    p_list = sub.add_parser("list", help="List session-touched files")
    p_list.add_argument("--session-id", default=None, help="Session ID (default: active session)")
    p_list.add_argument("--format", choices=["text", "paths", "json"], default="text")

    # current
    sub.add_parser("current", help="Print current active session ID")

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

    # dirty
    p_dirty = sub.add_parser("dirty", help="Show all dirty files with group and adoption status")
    p_dirty.add_argument("--format", choices=["text", "json"], default="text")

    # candidates
    p_cand = sub.add_parser("candidates", help="Show commit candidates (ledger AND git dirty)")
    p_cand.add_argument("--format", choices=["text", "json"], default="text")

    # groups
    p_groups = sub.add_parser("groups", help="Classify candidates into commit groups")
    p_groups.add_argument("--format", choices=["text", "json"], default="text")

    # diagnose
    sub.add_parser("diagnose", help="Print comprehensive session discovery diagnostics")

    # check-staged
    sub.add_parser("check-staged",
                   help="Check staged paths against session ledger (reads from stdin)")

    # inherit
    p_inherit = sub.add_parser("inherit",
                               help="Inherit touched files from a prior closed session")
    p_inherit.add_argument("--session-id", default=None,
                           help="Specific prior session ID (default: most recent closed)")

    args = parser.parse_args(argv)
    dispatch = {
        "init": cmd_init,
        "record": cmd_record,
        "list": cmd_list,
        "current": cmd_current,
        "adopt": cmd_adopt,
        "dirty": cmd_dirty,
        "candidates": cmd_candidates,
        "groups": cmd_groups,
        "diagnose": cmd_diagnose,
        "check-staged": cmd_check_staged,
        "inherit": cmd_inherit,
    }
    return dispatch[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
