"""checkout_sync.py — scoped, clean-verified sync of the real index (and,
when asked, worktree) after a ref advance (2026-08-29 stale-guard plan, T11;
TC-SG-03 — the RC-1 source fix).

Why this exists (reproduced in a fixture AND measured live 2026-08-29):
this repo's sanctioned commit/merge techniques advance ``refs/heads/<branch>``
without ever updating the real ``.git/index`` or worktree —
``git_plumb_commit.py`` (isolated temp index + ``update-ref``), the documented
object-level ``merge-tree``/``commit-tree`` recipes, and ``reconcile()``. The
result: for every path such a commit touched, the real index keeps the
PRE-commit blob. The very next porcelain ``git commit`` by ANY session — even
one that only staged an unrelated file — commits that stale index and silently
reverts the change, byte-exactly, in a commit whose author never touched the
file (this is the MT018 / 2026-08-07 keywords incident class the stale-file
regression guard exists to catch). At plan time the live repo carried 17 such
residue entries from a single day's plumbed commits.

Safety contract (the invariant, restated from the plan): this module NEVER
stages, unstages, or rewrites any path whose current state is not PROVABLY the
untouched pre-advance state:

- index entry is synced only when its blob OID equals ``old_head:path`` —
  i.e. it is exactly the residue the ref advance manufactured;
- worktree content (mode="index+worktree") is additionally rewritten only when
  the on-disk bytes hash (via git's clean filter, so autocrlf-safe) to
  ``old_head:path`` — i.e. what ``git merge --ff-only`` would have produced;
- anything else is someone's uncommitted work: skipped and reported;
- a held ``index.lock`` aborts the remaining index writes (never wait, never
  steal — another live session owns the index at that instant);
- every operation is idempotent: a second run finds nothing to do.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[3]

_REPO_ROOT = _DEFAULT_REPO_ROOT
_COMMAND_RUNNER: Callable[..., "subprocess.CompletedProcess"] = subprocess.run

_TEXT_KW = dict(text=True, encoding="utf-8", errors="replace")
_CHUNK = 300  # same argv-length discipline as git_plumb_commit._REAL_INDEX_SNAPSHOT_CHUNK_SIZE


def configure(
    *,
    repo_root: "Path | str | None" = None,
    command_runner: "Callable[..., subprocess.CompletedProcess] | None" = None,
) -> None:
    """Test seam. Called with no arguments, resets to defaults."""
    global _REPO_ROOT, _COMMAND_RUNNER
    if repo_root is None and command_runner is None:
        _REPO_ROOT = _DEFAULT_REPO_ROOT
        _COMMAND_RUNNER = subprocess.run
        return
    if repo_root is not None:
        _REPO_ROOT = Path(repo_root)
    if command_runner is not None:
        _COMMAND_RUNNER = command_runner


@dataclass
class SyncReport:
    synced_index: "list[str]" = field(default_factory=list)
    synced_worktree: "list[str]" = field(default_factory=list)
    removed_index: "list[str]" = field(default_factory=list)
    skipped_dirty: "list[str]" = field(default_factory=list)
    skipped_missing: "list[str]" = field(default_factory=list)
    index_locked: bool = False
    errors: "list[str]" = field(default_factory=list)

    @property
    def touched(self) -> int:
        return len(self.synced_index) + len(self.synced_worktree) + len(self.removed_index)

    def summary(self) -> str:
        parts = [f"index synced: {len(self.synced_index)}"]
        if self.synced_worktree:
            parts.append(f"worktree synced: {len(self.synced_worktree)}")
        if self.removed_index:
            parts.append(f"index entries removed: {len(self.removed_index)}")
        if self.skipped_dirty:
            parts.append(f"skipped (not provably untouched): {len(self.skipped_dirty)}")
        if self.skipped_missing:
            parts.append(f"skipped (missing on disk): {len(self.skipped_missing)}")
        if self.index_locked:
            parts.append("ABORTED: index.lock held by another process")
        if self.errors:
            parts.append(f"errors: {len(self.errors)}")
        return "checkout_sync: " + "; ".join(parts)


def _run(args: "list[str]", *, repo_root: Path, input_bytes: "bytes | None" = None,
         ) -> "subprocess.CompletedProcess":
    if input_bytes is not None:
        return _COMMAND_RUNNER(["git", *args], cwd=str(repo_root), capture_output=True,
                               input=input_bytes, text=False)
    return _COMMAND_RUNNER(["git", *args], cwd=str(repo_root), capture_output=True, **_TEXT_KW)


def _changed_paths(old_head: str, new_head: str, *, repo_root: Path) -> "list[str]":
    result = _run(["diff", "--name-only", "-z", old_head, new_head], repo_root=repo_root)
    if result.returncode != 0:
        return []
    return [p for p in (result.stdout or "").split("\0") if p]


def _index_oids(paths: "list[str]", *, repo_root: Path) -> "dict[str, tuple[str, str]]":
    """path -> (mode, oid) for entries currently in the REAL index."""
    out: "dict[str, tuple[str, str]]" = {}
    for i in range(0, len(paths), _CHUNK):
        chunk = paths[i:i + _CHUNK]
        result = _run(["ls-files", "-s", "-z", "--", *chunk], repo_root=repo_root)
        if result.returncode != 0:
            continue
        for entry in (result.stdout or "").split("\0"):
            if not entry.strip():
                continue
            meta, _tab, path = entry.partition("\t")
            fields = meta.split()
            if len(fields) >= 3 and fields[2] == "0":  # skip conflict stages
                out[path] = (fields[0], fields[1])
    return out


def _tree_oids(rev: str, paths: "list[str]", *, repo_root: Path) -> "dict[str, tuple[str, str]]":
    """path -> (mode, oid) at `rev` (blobs only)."""
    out: "dict[str, tuple[str, str]]" = {}
    for i in range(0, len(paths), _CHUNK):
        chunk = paths[i:i + _CHUNK]
        result = _run(["ls-tree", "-r", "-z", rev, "--", *chunk], repo_root=repo_root)
        if result.returncode != 0:
            continue
        for entry in (result.stdout or "").split("\0"):
            if not entry.strip():
                continue
            meta, _tab, path = entry.partition("\t")
            fields = meta.split()
            if len(fields) >= 3 and fields[1] == "blob":
                out[path] = (fields[0], fields[2])
    return out


def _worktree_oids(paths: "list[str]", *, repo_root: Path) -> "dict[str, str | None]":
    """path -> hash-object OID of the on-disk file WITH clean filters applied
    (autocrlf-safe; equals the blob OID git would store on `git add`), or
    None when the file is missing. Binary stdin: --stdin-paths has no -z and
    text-mode stdin would append CRs on Windows (adversarial finding A2)."""
    present = [p for p in paths if (repo_root / p).is_file()]
    out: "dict[str, str | None]" = {p: None for p in paths}
    if not present:
        return out
    stdin_bytes = "\n".join(present).encode("utf-8") + b"\n"
    result = _COMMAND_RUNNER(
        ["git", "hash-object", "--stdin-paths"], cwd=str(repo_root),
        capture_output=True, input=stdin_bytes, text=False,
    )
    if result.returncode != 0:
        return out
    hashes = (result.stdout or b"").decode("utf-8", "replace").split()
    for path, oid in zip(present, hashes):
        out[path] = oid
    return out


def _is_lock_error(stderr: str) -> bool:
    lowered = (stderr or "").lower()
    return "index.lock" in lowered or "unable to create" in lowered and ".lock" in lowered


def sync_after_ref_advance(
    old_head: str,
    new_head: str,
    *,
    paths: "list[str] | None" = None,
    repo_root: "Path | None" = None,
    mode: str = "index",
) -> SyncReport:
    """Sync the real index (and worktree for mode="index+worktree") to
    `new_head` for exactly the paths that changed between `old_head` and
    `new_head` (or the explicit `paths`), each gated on being provably the
    untouched pre-advance state. Never raises; returns a SyncReport."""
    root = Path(repo_root) if repo_root is not None else _REPO_ROOT
    report = SyncReport()

    candidates = paths if paths is not None else _changed_paths(old_head, new_head, repo_root=root)
    candidates = [p.replace("\\", "/") for p in candidates if p]
    if not candidates:
        return report

    old_tree = _tree_oids(old_head, candidates, repo_root=root)
    new_tree = _tree_oids(new_head, candidates, repo_root=root)
    index_now = _index_oids(candidates, repo_root=root)
    wt = _worktree_oids(candidates, repo_root=root) if mode == "index+worktree" else {}

    to_cacheinfo: "list[tuple[str, str, str]]" = []  # (mode, oid, path)
    to_remove: "list[str]" = []
    to_checkout: "list[str]" = []

    for path in candidates:
        old_entry = old_tree.get(path)
        new_entry = new_tree.get(path)
        idx_entry = index_now.get(path)

        idx_is_residue = (
            (idx_entry is not None and old_entry is not None and idx_entry[1] == old_entry[1])
            or (idx_entry is None and old_entry is None)  # path absent both then and now in index
        )
        if not idx_is_residue:
            if idx_entry is not None and new_entry is not None and idx_entry[1] == new_entry[1]:
                continue  # already synced (idempotency)
            report.skipped_dirty.append(path)
            continue

        if mode == "index+worktree":
            wt_oid = wt.get(path)
            wt_is_residue = (
                (old_entry is not None and wt_oid == old_entry[1])
                or (old_entry is None and wt_oid is None)
            )
            if not wt_is_residue:
                report.skipped_dirty.append(path)
                continue
            if new_entry is not None:
                to_checkout.append(path)  # updates index AND worktree
                continue
            # deleted by the advance and untouched locally: remove entry;
            # leave the on-disk file for a human (deletion is DGR-governed).
            if idx_entry is not None:
                to_remove.append(path)
            report.skipped_missing.append(path)
            continue

        # mode == "index": worktree is not touched at all.
        if new_entry is not None:
            # idx_entry may be None only in the (idx None, old None) residue
            # case here -- a brand-new path introduced by the advance, with
            # nothing ever staged locally. Without an entry, the next
            # porcelain commit of the untouched index would DELETE the file
            # (the deletion flavour of the residue class). Adding HEAD's own
            # entry makes index == HEAD: sync, not staging.
            to_cacheinfo.append((new_entry[0], new_entry[1], path))
        elif idx_entry is not None:
            to_remove.append(path)

    # Apply index updates (chunked); a held index.lock aborts the remainder.
    for i in range(0, len(to_cacheinfo), _CHUNK):
        chunk = to_cacheinfo[i:i + _CHUNK]
        # --add: required to CREATE an entry for a path new to the index (the
        # deletion-flavour residue); a no-op qualifier for existing entries.
        args: "list[str]" = ["update-index", "--add"]
        for entry_mode, oid, path in chunk:
            args += ["--cacheinfo", f"{entry_mode},{oid},{path}"]
        result = _run(args, repo_root=root)
        if result.returncode != 0:
            if _is_lock_error(result.stderr):
                report.index_locked = True
                return report
            report.errors.append((result.stderr or "").strip()[:200])
            continue
        report.synced_index.extend(path for _m, _o, path in chunk)

    for i in range(0, len(to_remove), _CHUNK):
        chunk = to_remove[i:i + _CHUNK]
        result = _run(["update-index", "--force-remove", "--", *chunk], repo_root=root)
        if result.returncode != 0:
            if _is_lock_error(result.stderr):
                report.index_locked = True
                return report
            report.errors.append((result.stderr or "").strip()[:200])
            continue
        report.removed_index.extend(chunk)

    for i in range(0, len(to_checkout), _CHUNK):
        chunk = to_checkout[i:i + _CHUNK]
        result = _run(["checkout", new_head, "--", *chunk], repo_root=root)
        if result.returncode != 0:
            if _is_lock_error(result.stderr):
                report.index_locked = True
                return report
            report.errors.append((result.stderr or "").strip()[:200])
            continue
        report.synced_worktree.extend(chunk)

    return report


def residue_report(repo_root: "Path | None" = None, max_entries: int = 200) -> "list[dict]":
    """Read-only: real-index entries that equal the PARENT blob of the last
    commit touching their path — i.e. exactly the stale state a following
    porcelain commit would sweep into history as a byte-exact revert."""
    root = Path(repo_root) if repo_root is not None else _REPO_ROOT
    result = _run(["diff", "--cached", "--name-only", "-z"], repo_root=root)
    if result.returncode != 0:
        return []
    paths = [p for p in (result.stdout or "").split("\0") if p][:max_entries]
    if not paths:
        return []
    index_now = _index_oids(paths, repo_root=root)
    rows: "list[dict]" = []
    for path in paths:
        idx_entry = index_now.get(path)
        if idx_entry is None:
            continue
        last = _run(["log", "-1", "--format=%H", "HEAD", "--", path], repo_root=root)
        last_sha = (last.stdout or "").strip()
        if not last_sha:
            continue
        parent = _run(["rev-parse", "--verify", "-q", f"{last_sha}^:{path}"], repo_root=root)
        parent_oid = (parent.stdout or "").strip()
        if parent_oid and idx_entry[1] == parent_oid:
            rows.append({"path": path, "index_oid": idx_entry[1],
                         "reverts_commit": last_sha})
    return rows
