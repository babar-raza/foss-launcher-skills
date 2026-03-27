"""core/clone_cache.py — Internal FOSS repo clone cache management.

Manages shallow git clones of FOSS source repos used by scout.py.
No dependency on foss-launcher — clones are stored inside this repo at
``runs/.clone_cache/`` and populated on-demand from ``data/products.json``.

Environment override::

    ASPOSE_CLONE_CACHE=/path/to/cache

Set this to point scout.py at an alternate pre-populated cache (CI, shared
NFS, etc.).  When unset, defaults to ``<repo_root>/runs/.clone_cache/``.

Public API::

    cache_root()                    -> Path   # resolved cache directory
    clone_path(family, platform)    -> Path   # expected clone dir
    clone_exists(family, platform)  -> bool   # valid git clone present?
    clone_head_sha(family, platform)-> str|None  # HEAD commit sha
    ensure_clone(family, platform)  -> Path   # ensure clone exists; auto-clone if missing
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Optional

# Three parents up: core/ -> pipeline/ -> scripts/ -> repo_root
_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_CACHE = _REPO_ROOT / "runs" / ".clone_cache"
_PRODUCTS_JSON = _REPO_ROOT / "data" / "products.json"


def cache_root() -> Path:
    """Return the resolved clone cache root directory.

    Respects ``ASPOSE_CLONE_CACHE`` environment variable if set.
    Falls back to ``<repo_root>/runs/.clone_cache/``.
    """
    env = os.environ.get("ASPOSE_CLONE_CACHE")
    if env:
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
            "Either add it via `python scripts/pipeline/update_product_registry.py` "
            "or set ASPOSE_CLONE_CACHE to a pre-populated cache directory."
        )

    p = clone_path(family, platform)
    p.parent.mkdir(parents=True, exist_ok=True)

    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", url, str(p)],
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
