"""core/clone_cache.py — Internal FOSS repo clone cache management.

Manages shallow git clones of FOSS source repos used by scout.py.
No dependency on foss-launcher — clones are stored inside this repo at
``runs/.clone_cache/`` and populated on-demand from ``data/products.json``.

Environment override::

    ASPOSE_CLONE_CACHE=/path/to/cache

Set this to point scout.py at an alternate pre-populated cache (CI, shared
NFS, etc.).  When unset, defaults to ``<repo_root>/runs/.clone_cache/``.

Public API::

    cache_root()                    -> Path      # resolved cache directory
    clone_path(family, platform)    -> Path      # expected clone dir
    clone_exists(family, platform)  -> bool      # valid git clone present?
    clone_head_sha(family, platform)-> str|None  # HEAD commit sha
    ensure_clone(family, platform)  -> Path      # ensure clone exists; auto-clone if missing
    update_clone(family, platform, strict=False) -> str|None  # fetch upstream + return new HEAD sha
    ensure_baseline_reachable(family, platform, sha) -> bool  # deepen shallow clone until sha is an ancestor of HEAD
    ensure_baseline_reachable_at(repo_path, sha)    -> bool   # same, addressed by clone directory
    probe_baseline_reachability[_at](...)           -> str    # memoized tri-state: REACHABLE / ORPHANED / UNKNOWN
    checkout_pinned(family, platform, sha)          -> str    # detached checkout of an exact sha (no reset)

MT074 B1 (shallow-clone baseline reachability): clones are ``--depth 2``, so a
baseline SHA older than the two fetched commits is NOT an ancestor of HEAD even
though it is a perfectly healthy upstream commit; ``merge-base --is-ancestor``
then wrongly reports it orphaned. ``ensure_baseline_reachable`` deepens the
clone progressively (never ``--unshallow`` by default) until the SHA is an
ancestor or the steps are exhausted; only a SHA that stays unreachable after
that is genuinely orphaned (force-push / history rewrite).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Optional, Sequence

# Three parents up: core/ -> pipeline/ -> scripts/ -> repo_root
_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_CACHE = _REPO_ROOT / "runs" / ".clone_cache"
_PRODUCTS_JSON = _REPO_ROOT / "data" / "products.json"

# sibling-import guard, matching core/knowledge.py's own established pattern.
_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
_LIB_DIR = str(_HERE / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from advisory_lock import FileLock, LockTimeout  # noqa: E402

_LOCK_DIR = _REPO_ROOT / "reports" / "locks" / "clone_cache"
_DEFAULT_CLONE_LOCK_TIMEOUT_SECONDS = 120.0
_cfg_clone_lock_timeout_seconds = _DEFAULT_CLONE_LOCK_TIMEOUT_SECONDS


def configure(
    *,
    lock_timeout_seconds: Optional[float] = None,
    max_deepen_fetches: Optional[int] = None,
    unknown_retry_seconds: Optional[float] = None,
    fetch_timeout_seconds: Optional[float] = None,
) -> None:
    """Override external-boundary knobs for tests; call without arguments to reset.

    Every knob not passed falls back to its default, and every call also clears the
    reachability-probe memo and fetch counter (MT074 B1), so a test never inherits another
    test's verdicts.

    AGENTS.md 16 (Tiered Monkeypatch Policy): a bare ``monkeypatch.setattr`` on this
    module's private ``_cfg_*`` state is a T2 violation (caught live by
    scripts/pipeline/tests/content_eval's monkeypatch lint, RC-clone-cache-directory-lock,
    2026-08-30) -- this configure() seam is the sanctioned way for a test to shrink the
    real 120s lock-acquisition timeout to something fast, matching the exact
    module-global + configure() + reset pattern readme_refresh_run.py/refresh_run.py
    already use for their own external-boundary knobs.
    """
    global _cfg_clone_lock_timeout_seconds, _cfg_max_deepen_fetches
    global _cfg_unknown_retry_seconds, _cfg_fetch_timeout_seconds
    _cfg_clone_lock_timeout_seconds = (
        lock_timeout_seconds if lock_timeout_seconds is not None
        else _DEFAULT_CLONE_LOCK_TIMEOUT_SECONDS
    )
    _cfg_max_deepen_fetches = (
        max_deepen_fetches if max_deepen_fetches is not None else DEFAULT_MAX_DEEPEN_FETCHES
    )
    _cfg_unknown_retry_seconds = (
        unknown_retry_seconds if unknown_retry_seconds is not None else DEFAULT_UNKNOWN_RETRY_SECONDS
    )
    _cfg_fetch_timeout_seconds = (
        fetch_timeout_seconds if fetch_timeout_seconds is not None else DEFAULT_FETCH_TIMEOUT_SECONDS
    )
    reset_deepen_state()


def _clone_lock_path(family: str, platform: str) -> Path:
    return _LOCK_DIR / f"{family}-{platform}.lock"


def cache_root() -> Path:
    """Return the resolved clone cache root directory.

    Respects ``ASPOSE_CLONE_CACHE`` environment variable if set.
    Falls back to ``<repo_root>/runs/.clone_cache/``.

    Raises ``ValueError`` if ``ASPOSE_CLONE_CACHE`` contains an obsolete
    ``foss-launcher`` path — that location is permanently retired.
    """
    env = os.environ.get("ASPOSE_CLONE_CACHE")
    if env:
        env_lower = env.lower().replace("\\", "/")
        if "foss-launcher" in env_lower or "foss_launcher" in env_lower:  # HISTORICAL_OBSOLETE_FOSS_LAUNCHER_REFERENCE
            raise ValueError(
                f"ASPOSE_CLONE_CACHE points to an obsolete foss-launcher path: {env!r}\n"
                "The foss-launcher clone cache location is permanently retired.\n"  # HISTORICAL_OBSOLETE_FOSS_LAUNCHER_REFERENCE
                "Canonical clone cache: runs/.clone_cache/ inside the aspose.org repo\n"
                "Unset ASPOSE_CLONE_CACHE or set it to the correct path."
            )
        return Path(env).resolve()
    resolved = _DEFAULT_CACHE.resolve()
    return resolved


def clone_path(family: str, platform: str) -> Path:
    """Return the expected clone directory for a product.

    Does not check whether the directory exists.
    """
    return cache_root() / f"aspose_{family}_{platform}"


def clone_exists(family: str, platform: str) -> bool:
    """Return True if a valid git clone exists for this product."""
    p = clone_path(family, platform)
    return p.is_dir() and (p / ".git").is_dir()


def clone_head_sha(family: str, platform: str) -> Optional[str]:
    """Return the HEAD commit sha of the clone, or None if clone is missing."""
    p = clone_path(family, platform)
    if not p.is_dir():
        return None
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(p),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def ensure_clone(family: str, platform: str) -> Path:
    """Ensure a clone exists for the given product; auto-clone from GitHub if missing.

    Returns the clone path on success.  Raises ``RuntimeError`` if the clone
    cannot be created (no ``clone_url`` in ``data/products.json``, git failure,
    or network unavailable).

    Idempotent — safe to call repeatedly; skips cloning if clone already exists.
    """
    if clone_exists(family, platform):
        return clone_path(family, platform)

    url = _get_clone_url(family, platform)
    if not url:
        raise RuntimeError(
            f"No clone_url found in data/products.json for {family}/{platform}. "
            "Either add it via `python scripts/pipeline/commands/ops/update_product_registry.py` "
            "or set ASPOSE_CLONE_CACHE to a pre-populated cache directory."
        )

    p = clone_path(family, platform)
    p.parent.mkdir(parents=True, exist_ok=True)

    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "2", url, str(p)],
            capture_output=False,
            timeout=300,
        )
    except Exception as exc:
        raise RuntimeError(
            f"git clone failed for {family}/{platform}: {exc}"
        ) from exc

    if result.returncode != 0:
        raise RuntimeError(
            f"git clone exited {result.returncode} for {family}/{platform} "
            f"(url: {url})"
        )

    return p


# ---------------------------------------------------------------------------
# MT074 B1: baseline reachability on shallow clones + pinned checkout
#
# NETWORK CONTRACT (precise): the ONLY network-touching functions in this block are
# ``probe_baseline_reachability`` / ``probe_baseline_reachability_at`` (and the bool wrappers
# ``ensure_baseline_reachable``, ``ensure_baseline_reachable_at``, ``deepen_until_ancestor``) and
# ``checkout_pinned`` (fetches a missing commit only). The probe touches the network ONLY when
# the clone is shallow AND the sha is not already an ancestor of HEAD; it is memoized per
# process, capped per process, and reports an inability to finish as UNKNOWN -- never as
# ORPHANED. ``is_shallow_repo`` and every other helper are local-only.
# ---------------------------------------------------------------------------

DEFAULT_DEEPEN_STEPS: "tuple[int, ...]" = (10, 50, 250, 1000)
_SHA_RE = re.compile(r"^[0-9a-fA-F]{7,64}$")

# Tri-state reachability verdict. ORPHANED is definitive (a completed deepen, or a full clone,
# still has no path to the sha); UNKNOWN means "could not finish" (network/lock/timeout/cap/
# guard/any error) and must never be reported to a user as an orphan.
REACHABLE = "reachable"
ORPHANED = "orphaned"
UNKNOWN = "unknown"

DEFAULT_MAX_DEEPEN_FETCHES = 12          # total network fetches the probe may spend per process
DEFAULT_UNKNOWN_RETRY_SECONDS = 300.0    # an UNKNOWN verdict is re-probed at most this often
DEFAULT_FETCH_TIMEOUT_SECONDS = 60.0     # per git fetch
_LOCAL_GIT_TIMEOUT_SECONDS = 30.0
_cfg_max_deepen_fetches = DEFAULT_MAX_DEEPEN_FETCHES
_cfg_unknown_retry_seconds = DEFAULT_UNKNOWN_RETRY_SECONDS
_cfg_fetch_timeout_seconds = DEFAULT_FETCH_TIMEOUT_SECONDS

# (resolved clone path, lowercase sha) -> (state, monotonic timestamp); per process.
_probe_memo: "dict[tuple[str, str], tuple[str, float]]" = {}
_deepen_fetches_used = 0

GitRunner = Callable[[Sequence[str], Path], "subprocess.CompletedProcess"]


def reset_deepen_state() -> None:
    """Forget every memoized reachability verdict and the per-process fetch counter."""
    global _deepen_fetches_used
    _probe_memo.clear()
    _deepen_fetches_used = 0


def _default_runner(args: Sequence[str], cwd: Path) -> "subprocess.CompletedProcess":
    """Run one git command in ``cwd``; the production ``runner`` for this module's helpers."""
    timeout = _cfg_fetch_timeout_seconds if "fetch" in list(args) else _LOCAL_GIT_TIMEOUT_SECONDS
    return subprocess.run(
        list(args), cwd=str(cwd), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout,
    )


def _rc(runner: GitRunner, args: Sequence[str], cwd: Path) -> "Optional[int]":
    """Return the exit code of ``args``, or None when the command could not run (timeout/OSError/...)."""
    try:
        return runner(args, cwd).returncode
    except Exception:
        return None


def _run_ok(runner: GitRunner, args: Sequence[str], cwd: Path) -> bool:
    """True iff ``runner`` ran ``args`` and the command exited 0 (never raises)."""
    return _rc(runner, args, cwd) == 0


def _is_ancestor(runner: GitRunner, repo: Path, sha: str) -> bool:
    return _run_ok(runner, ["git", "merge-base", "--is-ancestor", sha, "HEAD"], repo)


def _object_exists(runner: GitRunner, repo: Path, sha: str) -> bool:
    return _run_ok(runner, ["git", "cat-file", "-e", f"{sha}^{{commit}}"], repo)


def _valid_sha(sha: object) -> bool:
    return isinstance(sha, str) and bool(_SHA_RE.match(sha))


def _shallow_state(runner: GitRunner, repo: Path) -> "Optional[bool]":
    """True/False when git answers ``--is-shallow-repository``; None when it cannot be determined."""
    try:
        result = runner(["git", "rev-parse", "--is-shallow-repository"], repo)
    except Exception:
        return None
    if result.returncode != 0:
        return None
    return (result.stdout or "").strip() == "true"


def is_shallow_repo(repo_path: "Path | str", *, runner: Optional[GitRunner] = None) -> bool:
    """True iff the git repo at ``repo_path`` is a shallow clone (False on any git error). Local-only."""
    return _shallow_state(runner or _default_runner, Path(repo_path)) is True


def _toplevel_is(runner: GitRunner, repo: Path) -> bool:
    """True iff git's toplevel for ``repo`` IS ``repo`` -- never operate on a parent repository."""
    try:
        result = runner(["git", "rev-parse", "--show-toplevel"], repo)
        if result.returncode != 0:
            return False
        return Path((result.stdout or "").strip()).resolve() == repo.resolve()
    except Exception:
        return False


def deepen_until_ancestor_state(
    repo_path: "Path | str",
    sha: str,
    *,
    deepen_steps: "Sequence[int]" = DEFAULT_DEEPEN_STEPS,
    runner: Optional[GitRunner] = None,
) -> str:
    """Uncached, lock-free core: REACHABLE / ORPHANED / UNKNOWN for ``sha`` against HEAD.

    CONTRACT:
      * ancestor already -> REACHABLE, no network.
      * invalid sha (not 7-64 hex) -> ORPHANED, git not run.
      * NOT shallow and not an ancestor -> ORPHANED, NO network (nothing to deepen; a full
        clone is never fetched into, so its history is never truncated).
      * shallow: refuses (UNKNOWN) unless git's toplevel is ``repo_path`` itself, so a
        path-only caller can never fetch into a parent repository. Otherwise fetch the sha
        (best effort: a refusal is tolerated, a timeout/OSError is UNKNOWN), then
        ``git fetch --deepen=<n>`` per step. A non-zero/timeout deepen fetch, git failing to
        run, or the per-process fetch cap (``max_deepen_fetches``) is UNKNOWN. ORPHANED only
        after every step COMPLETED and the sha is still not an ancestor.
      * never ``--unshallow``; never raises.
    """
    global _deepen_fetches_used
    run = runner or _default_runner
    repo = Path(repo_path)
    if not _valid_sha(sha):
        return ORPHANED
    rc = _rc(run, ["git", "merge-base", "--is-ancestor", sha, "HEAD"], repo)
    if rc == 0:
        return REACHABLE
    if rc is None:
        return UNKNOWN
    shallow = _shallow_state(run, repo)
    if shallow is None:
        return UNKNOWN
    if not shallow:
        return ORPHANED
    if not _toplevel_is(run, repo):
        return UNKNOWN

    def _spend() -> bool:
        global _deepen_fetches_used
        if _deepen_fetches_used >= _cfg_max_deepen_fetches:
            return False
        _deepen_fetches_used += 1
        return True

    if not _spend():
        return UNKNOWN
    fetch_rc = _rc(run, ["git", "fetch", "--depth=2", "origin", sha], repo)
    if fetch_rc is None:
        return UNKNOWN  # timeout / cannot run: do not claim anything
    if _is_ancestor(run, repo, sha):
        return REACHABLE
    for n in deepen_steps:
        now_shallow = _shallow_state(run, repo)
        if now_shallow is None:
            return UNKNOWN
        if not now_shallow:
            break  # full history already present: nothing left to deepen
        if not _spend():
            return UNKNOWN
        if _rc(run, ["git", "fetch", f"--deepen={int(n)}", "origin"], repo) != 0:
            return UNKNOWN  # incomplete deepen is NOT evidence of an orphan
        if _is_ancestor(run, repo, sha):
            return REACHABLE
    return ORPHANED


def _memo_key(repo: Path, sha: str) -> "tuple[str, str]":
    try:
        return (str(repo.resolve()), sha.lower())
    except OSError:
        return (str(repo), sha.lower())


def _invalidate_probe_memo(repo: "Path | str") -> None:
    """Drop memoized verdicts for ``repo`` (its HEAD moved, so old answers may be stale)."""
    try:
        target = str(Path(repo).resolve())
    except OSError:
        target = str(repo)
    for key in [k for k in _probe_memo if k[0] == target]:
        _probe_memo.pop(key, None)


def probe_baseline_reachability(
    repo_path: "Path | str",
    sha: str,
    *,
    deepen_steps: "Sequence[int]" = DEFAULT_DEEPEN_STEPS,
    runner: Optional[GitRunner] = None,
    clock: "Optional[Callable[[], float]]" = None,
    lock_key: "Optional[tuple[str, str]]" = None,
) -> str:
    """Memoized tri-state verdict (REACHABLE / ORPHANED / UNKNOWN) for ``sha`` in ``repo_path``.

    Verdicts are memoized per process by (clone path, sha) -- negative and UNKNOWN verdicts
    included, so a repeated probe makes ZERO git calls. An UNKNOWN verdict is re-probed at most
    once per ``unknown_retry_seconds``; REACHABLE/ORPHANED are kept until the clone's HEAD is
    moved by ``update_clone`` / ``checkout_pinned`` (which invalidate the memo).
    ``lock_key=(family, platform)`` serializes the probe on that product's clone lock; a busy
    lock is UNKNOWN (and not memoized). Network use: see the block comment above.
    """
    repo = Path(repo_path)
    now = (clock or time.monotonic)
    if not _valid_sha(sha):
        return ORPHANED
    key = _memo_key(repo, sha)
    hit = _probe_memo.get(key)
    if hit is not None:
        state, stamp = hit
        if state != UNKNOWN or (now() - stamp) < _cfg_unknown_retry_seconds:
            return state

    def _do() -> str:
        return deepen_until_ancestor_state(repo, sha, deepen_steps=deepen_steps, runner=runner)

    try:
        if lock_key is not None:
            _LOCK_DIR.mkdir(parents=True, exist_ok=True)
            with FileLock(_clone_lock_path(*lock_key), timeout=_cfg_clone_lock_timeout_seconds):
                state = _do()
        else:
            state = _do()
    except LockTimeout:
        return UNKNOWN
    except Exception:
        return UNKNOWN
    _probe_memo[key] = (state, now())
    return state


def _lock_key_for_path(repo: Path) -> "Optional[tuple[str, str]]":
    """(family, platform) when ``repo`` is a product clone directly under ``cache_root()``."""
    try:
        if repo.resolve().parent != cache_root() or not repo.name.startswith("aspose_"):
            return None
    except (OSError, ValueError):
        return None
    parts = repo.name.removeprefix("aspose_").split("_", 1)
    return (parts[0], parts[1]) if len(parts) == 2 and all(parts) else None


def probe_baseline_reachability_at(
    repo_path: "Path | str",
    sha: str,
    *,
    deepen_steps: "Sequence[int]" = DEFAULT_DEEPEN_STEPS,
    runner: Optional[GitRunner] = None,
    clock: "Optional[Callable[[], float]]" = None,
) -> str:
    """``probe_baseline_reachability`` addressed by directory (reuses the product clone lock
    when ``repo_path`` is a clone under ``cache_root()``, else no lock)."""
    repo = Path(repo_path)
    return probe_baseline_reachability(
        repo, sha, deepen_steps=deepen_steps, runner=runner, clock=clock,
        lock_key=_lock_key_for_path(repo),
    )


def deepen_until_ancestor(
    repo_path: "Path | str",
    sha: str,
    *,
    deepen_steps: "Sequence[int]" = DEFAULT_DEEPEN_STEPS,
    runner: Optional[GitRunner] = None,
) -> bool:
    """Bool form of ``deepen_until_ancestor_state``: True only for REACHABLE (UNKNOWN -> False)."""
    return deepen_until_ancestor_state(
        repo_path, sha, deepen_steps=deepen_steps, runner=runner,
    ) == REACHABLE


def ensure_baseline_reachable(
    family: str,
    platform: str,
    sha: str,
    *,
    deepen_steps: "Sequence[int]" = DEFAULT_DEEPEN_STEPS,
    runner: Optional[GitRunner] = None,
) -> bool:
    """True iff ``sha`` is (or, after a bounded deepen of a SHALLOW clone, becomes) an ancestor
    of the product clone's HEAD. False for ORPHANED *and* UNKNOWN or a missing clone -- callers
    that must tell those apart use ``probe_baseline_reachability_at``. A full clone is never
    fetched into. Serialized per product on the FileLock ``update_clone`` uses.
    """
    if not clone_exists(family, platform):
        return False
    return probe_baseline_reachability(
        clone_path(family, platform), sha, deepen_steps=deepen_steps, runner=runner,
        lock_key=(family, platform),
    ) == REACHABLE


def ensure_baseline_reachable_at(
    repo_path: "Path | str",
    sha: str,
    *,
    deepen_steps: "Sequence[int]" = DEFAULT_DEEPEN_STEPS,
    runner: Optional[GitRunner] = None,
) -> bool:
    """Bool form of ``probe_baseline_reachability_at`` (True only for REACHABLE)."""
    return probe_baseline_reachability_at(
        repo_path, sha, deepen_steps=deepen_steps, runner=runner,
    ) == REACHABLE


def checkout_pinned(
    family: str,
    platform: str,
    sha: str,
    *,
    runner: Optional[GitRunner] = None,
) -> str:
    """Detached checkout of exactly ``sha`` inside the product clone; returns the full sha.

    Fetches the sha only when its commit object is not already present (the one network call),
    then runs ``git checkout --detach <sha>`` -- deliberately NOT ``git reset`` (no ref is
    moved, no local work is discarded; git itself refuses if a checkout would overwrite local
    changes). NOTE: this DETACHES the clone's HEAD, including when the caller is a check-only
    refresh; a later ``update_clone`` re-attaches by resetting to origin/HEAD. Refuses (raises)
    unless git's toplevel is the clone directory itself, so a path-only mistake can never
    detach a parent repository. Every failure -- missing clone, malformed/unfetchable sha,
    git timeout or OSError, checkout failure, HEAD != the pin afterwards -- is a
    ``RuntimeError``. Serialized on the product clone lock.
    """
    run = runner or _default_runner
    if not _valid_sha(sha):
        raise RuntimeError(f"checkout_pinned: {sha!r} is not a valid commit sha")
    if not clone_exists(family, platform):
        raise RuntimeError(f"checkout_pinned: no clone for {family}/{platform}")
    repo = clone_path(family, platform)

    def _git(args: "Sequence[str]") -> "subprocess.CompletedProcess":
        try:
            return run(args, repo)
        except Exception as exc:  # TimeoutExpired, OSError, ...
            raise RuntimeError(f"checkout_pinned: git {args[1]} could not run: {exc}") from exc

    _LOCK_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with FileLock(_clone_lock_path(family, platform), timeout=_cfg_clone_lock_timeout_seconds):
            if not _toplevel_is(run, repo):
                raise RuntimeError(
                    f"checkout_pinned: git toplevel is not the clone directory {repo} -- refusing"
                )
            if not _object_exists(run, repo, sha):
                if _rc(run, ["git", "fetch", "--depth=2", "origin", sha], repo) != 0:
                    raise RuntimeError(
                        f"checkout_pinned: commit {sha[:10]} is not in the clone and could not be fetched"
                    )
            resolved = _git(["git", "rev-parse", "--verify", f"{sha}^{{commit}}"])
            if resolved.returncode != 0:
                raise RuntimeError(f"checkout_pinned: {sha[:10]} does not resolve to a commit")
            full = (resolved.stdout or "").strip()
            co = _git(["git", "checkout", "--detach", full])
            if co.returncode != 0:
                raise RuntimeError(
                    f"checkout_pinned: git checkout --detach {full[:10]} failed: "
                    f"{(co.stderr or '').strip()[:200]}"
                )
            head = _git(["git", "rev-parse", "HEAD"])
            if head.returncode != 0 or (head.stdout or "").strip() != full:
                raise RuntimeError(f"checkout_pinned: HEAD is not {full[:10]} after checkout")
            _invalidate_probe_memo(repo)
            return full
    except LockTimeout as exc:
        raise RuntimeError(f"checkout_pinned: clone lock busy for {family}/{platform}") from exc


def update_clone(family: str, platform: str, strict: bool = False) -> Optional[str]:
    """Fetch the latest commits from upstream and reset the clone to origin/HEAD.

    ``strict=True`` (MT074 B1, opt-in): instead of degrading to ``None`` on a missing
    clone, lock timeout, safety-guard refusal, fetch failure or reset failure,
    raise ``RuntimeError`` -- for callers that must not silently proceed on a stale
    HEAD. The default (``strict=False``) is unchanged: never raises, ``None`` means
    "could not refresh".

    Uses ``git fetch --depth=2 origin`` to stay shallow (avoids downloading full
    history) then a hard reset to advance the local HEAD to origin/HEAD.

    Returns the new HEAD commit SHA on success, or ``None`` if the fetch fails
    (clone missing, network unavailable, or git error).  Never raises — callers
    can treat ``None`` as "could not refresh; use existing clone".

    RC-clone-cache-directory-lock (readme-refresh-hardening-and-regen-2026-08-30):
    at least 5 independent call sites (repo_patrol.py, enrich.py, promote.py,
    mechanism_sweep.py, typescript_api_completeness.py) can invoke this for the
    SAME family/platform concurrently -- nothing serialized the fetch+reset
    sequence against a second caller doing the identical thing to the same
    directory at the same time, a real interleaving hazard (a reset mid-fetch,
    or two resets racing against different fetched refs) confirmed structurally
    possible by direct code read, not previously guarded anywhere in this
    function or any caller. A FileLock scoped per family/platform, matching the
    exact pattern readme_refresh_run.py's own `_product_guard` already uses for
    the identical class of problem, serializes this specific critical section
    without changing this function's contract (still never raises to the
    caller; a lock timeout degrades to the same `None` "could not refresh"
    return every other failure mode already produces).
    """
    p = clone_path(family, platform)
    if not clone_exists(family, platform):
        if strict:
            raise RuntimeError(f"update_clone(strict): no clone for {family}/{platform}")
        return None

    _LOCK_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with FileLock(_clone_lock_path(family, platform), timeout=_cfg_clone_lock_timeout_seconds):
            return _update_clone_locked(family, platform, p, strict=strict)
    except LockTimeout:
        if strict:
            raise RuntimeError(
                f"update_clone(strict): clone lock busy for {family}/{platform}"
            ) from None
        return None


def _update_clone_locked(
    family: str, platform: str, p: Path, strict: bool = False,
) -> Optional[str]:
    """The real fetch+reset body of update_clone(), run only while its FileLock is held.

    With ``strict=True`` every failure path raises ``RuntimeError`` instead of returning None.
    """
    # Safety guard: verify git will operate on the clone, not a parent repo.
    try:
        toplevel = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(p), capture_output=True, text=True, timeout=5,
        )
        if toplevel.returncode == 0:
            resolved_top = Path(toplevel.stdout.strip()).resolve()
            if resolved_top != p.resolve():
                import logging
                logging.getLogger(__name__).error(
                    "update_clone safety guard: git toplevel %s != clone path %s — refusing to reset",
                    resolved_top, p.resolve(),
                )
                if strict:
                    raise RuntimeError(
                        f"update_clone(strict): git toplevel {resolved_top} != clone path {p.resolve()}"
                    )
                return None
    except RuntimeError:
        raise
    except Exception:
        pass  # If the check fails, proceed cautiously

    try:
        fetch = subprocess.run(
            ["git", "fetch", "--depth=2", "origin"],
            cwd=str(p),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if fetch.returncode != 0:
            if strict:
                raise RuntimeError(
                    f"update_clone(strict): git fetch failed for {family}/{platform}: "
                    f"{(fetch.stderr or '').strip()[:200]}"
                )
            return None

        reset = subprocess.run(
            ["git", "reset", "--hard", "origin/HEAD"],
            cwd=str(p),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if reset.returncode != 0:
            if strict:
                raise RuntimeError(
                    f"update_clone(strict): git reset failed for {family}/{platform}: "
                    f"{(reset.stderr or '').strip()[:200]}"
                )
            return None
    except RuntimeError:
        raise
    except Exception as exc:
        if strict:
            raise RuntimeError(f"update_clone(strict): {exc}") from exc
        return None

    _invalidate_probe_memo(p)  # HEAD moved: earlier reachability verdicts may be stale
    return clone_head_sha(family, platform)


def _get_clone_url(family: str, platform: str) -> Optional[str]:
    """Look up clone_url from data/products.json for the given product."""
    if not _PRODUCTS_JSON.is_file():
        return None
    try:
        products = json.loads(_PRODUCTS_JSON.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    for entry in products:
        if entry.get("family") == family and entry.get("platform") == platform:
            return entry.get("clone_url") or None
    return None


if __name__ == "__main__":
    import sys

    def _usage() -> None:
        print("Usage: python clone_cache.py resolve <family> <platform>", file=sys.stderr)
        print("       Prints the absolute clone path, auto-cloning if missing.", file=sys.stderr)
        print("       Respects ASPOSE_CLONE_CACHE env var.", file=sys.stderr)
        sys.exit(1)

    if len(sys.argv) != 4 or sys.argv[1] != "resolve":
        _usage()

    _, _, fam, plat = sys.argv
    try:
        path = ensure_clone(fam, plat)
        print(path)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
