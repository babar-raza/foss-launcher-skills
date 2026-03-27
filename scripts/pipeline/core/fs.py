"""Atomic filesystem operations for the pipeline.

All file mutations that must be safe to retry on failure should go through
atomic_write().  The write-to-tmp + os.replace() pattern ensures that a
crash mid-write leaves the original file intact.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path


def atomic_write(path: Path, content: str, encoding: str = "utf-8") -> None:
    """Write *content* to *path* atomically.

    Writes to ``<path>.tmp`` first, then calls ``os.replace()`` which is
    atomic on POSIX and near-atomic on Windows (no partial-read window).
    Cleans up the temp file if anything goes wrong.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(content, encoding=encoding)
        tmp.replace(path)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def file_hash(path: Path) -> str:
    """Return a fast fingerprint of *path* based on size + mtime_ns.

    Not cryptographically secure — intended for change-detection only
    (e.g. "did this file change since last run?").  Returns a 16-hex-char
    string so it is cheap to store in manifests.
    """
    s = path.stat()
    return hashlib.sha256(
        f"{s.st_size}:{s.st_mtime_ns}".encode()
    ).hexdigest()[:16]
