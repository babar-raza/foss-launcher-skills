"""Standalone clone-cache path resolver and shallow clone helper.

This mirrors the practical aspose.org clone-cache API while keeping the cache
inside this standalone repository by default.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Optional

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_CACHE = _REPO_ROOT / "runs" / ".clone_cache"
_PRODUCTS_JSON = _REPO_ROOT / "data" / "products.json"


def cache_root() -> Path:
    """Return the clone-cache root, honoring ASPOSE_CLONE_CACHE when set."""
    env = os.environ.get("ASPOSE_CLONE_CACHE")
    if env:
        normalized = env.lower().replace("\\", "/")
        if "foss-launcher" in normalized or "foss_launcher" in normalized:
            raise ValueError(
                f"ASPOSE_CLONE_CACHE points to an obsolete foss-launcher path: {env!r}. "
                "Use runs/.clone_cache inside this repo or a non-obsolete explicit cache root."
            )
        return Path(env).resolve()
    return _DEFAULT_CACHE.resolve()


def clone_path(family: str, platform: str) -> Path:
    """Return the expected flat clone directory for a product."""
    return cache_root() / f"aspose_{family}_{platform}"


def clone_exists(family: str, platform: str) -> bool:
    """Return True when the expected clone directory contains a .git directory."""
    path = clone_path(family, platform)
    return path.is_dir() and (path / ".git").is_dir()


def clone_head_sha(family: str, platform: str) -> Optional[str]:
    """Return the HEAD SHA for an existing clone, or None when unavailable."""
    path = clone_path(family, platform)
    if not path.is_dir():
        return None
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(path),
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def ensure_clone(family: str, platform: str) -> Path:
    """Return an existing clone or create one from data/products.json clone_url."""
    if clone_exists(family, platform):
        return clone_path(family, platform)

    clone_url = _get_clone_url(family, platform)
    if not clone_url:
        raise RuntimeError(
            f"No clone_url found in data/products.json for {family}/{platform}. "
            "Set ASPOSE_CLONE_CACHE to a pre-populated cache or add a product registry entry."
        )

    path = clone_path(family, platform)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", clone_url, str(path)],
            capture_output=False,
            timeout=300,
        )
    except Exception as exc:
        raise RuntimeError(f"git clone failed for {family}/{platform}: {exc}") from exc

    if result.returncode != 0:
        raise RuntimeError(f"git clone exited {result.returncode} for {family}/{platform} ({clone_url})")
    return path


def update_clone(family: str, platform: str) -> Optional[str]:
    """Fetch and hard-reset an existing shallow clone to origin/HEAD."""
    path = clone_path(family, platform)
    if not clone_exists(family, platform):
        return None

    try:
        toplevel = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(path),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if toplevel.returncode == 0 and Path(toplevel.stdout.strip()).resolve() != path.resolve():
            return None

        fetch = subprocess.run(
            ["git", "fetch", "--depth=1", "origin"],
            cwd=str(path),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if fetch.returncode != 0:
            return None

        reset = subprocess.run(
            ["git", "reset", "--hard", "origin/HEAD"],
            cwd=str(path),
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
    if not _PRODUCTS_JSON.is_file():
        return None
    try:
        products = json.loads(_PRODUCTS_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    for entry in products:
        if entry.get("family") == family and entry.get("platform") == platform:
            return entry.get("clone_url") or None
    return None


def _usage() -> int:
    print("Usage: python clone_cache.py resolve <family> <platform>", file=os.sys.stderr)
    print("       Prints the absolute clone path, auto-cloning if missing.", file=os.sys.stderr)
    print("       Respects ASPOSE_CLONE_CACHE env var.", file=os.sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    argv = list(os.sys.argv[1:] if argv is None else argv)
    if len(argv) != 3 or argv[0] != "resolve":
        return _usage()
    _, family, platform = argv
    try:
        print(ensure_clone(family, platform))
    except (RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=os.sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
