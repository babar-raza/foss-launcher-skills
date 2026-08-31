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
    update_clone(family, platform)  -> str|None  # fetch upstream + return new HEAD sha
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

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


def configure(*, lock_timeout_seconds: Optional[float] = None) -> None:
    """Override external-boundary knobs for tests; call without arguments to reset.

    AGENTS.md 16 (Tiered Monkeypatch Policy): a bare ``monkeypatch.setattr`` on this
    module's private ``_cfg_*`` state is a T2 violation (caught live by
    scripts/pipeline/tests/content_eval's monkeypatch lint, RC-clone-cache-directory-lock,
    2026-08-30) -- this configure() seam is the sanctioned way for a test to shrink the
    real 120s lock-acquisition timeout to something fast, matching the exact
    module-global + configure() + reset pattern readme_refresh_run.py/refresh_run.py
    already use for their own external-boundary knobs.
    """
    global _cfg_clone_lock_timeout_seconds
    _cfg_clone_lock_timeout_seconds = (
        lock_timeout_seconds if lock_timeout_seconds is not None
        else _DEFAULT_CLONE_LOCK_TIMEOUT_SECONDS
    )


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


def update_clone(family: str, platform: str) -> Optional[str]:
    """Fetch the latest commits from upstream and reset the clone to origin/HEAD.

    Uses ``git fetch --depth=1 origin`` to stay shallow (avoids downloading full
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
        return None

    _LOCK_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with FileLock(_clone_lock_path(family, platform), timeout=_cfg_clone_lock_timeout_seconds):
            return _update_clone_locked(family, platform, p)
    except LockTimeout:
        return None


def _update_clone_locked(family: str, platform: str, p: Path) -> Optional[str]:
    """The real fetch+reset body of update_clone(), run only while its FileLock is held."""
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
                return None
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
            return None

        reset = subprocess.run(
            ["git", "reset", "--hard", "origin/HEAD"],
            cwd=str(p),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if reset.returncode != 0:
            return None
    except Exception:
        return None

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
