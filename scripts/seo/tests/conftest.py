"""Shared fixtures for scripts/seo/tests.

SEO-MAPURL-CASE-INSENSITIVE-RESOLVE (F2): map_url.py used to call
Path.exists() directly on dynamically-built candidates. That looks correct on
this repo's Windows/NTFS dev checkouts (case-insensitive at the OS level) but
silently fails the identical lookup on the case-sensitive Linux CI runner --
a lowercase URL-derived candidate like "saveformat.md" never matches a real
"SaveFormat.md" file there. `case_sensitive_exists` lets a test prove the OLD
behavior actually fails under case-sensitive semantics without needing a
Linux runner to demonstrate it on.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture
def case_sensitive_exists():
    def _check(path: Path) -> bool:
        """True only if path's exact name (byte-for-byte) is in its parent's
        real directory listing -- simulates a case-sensitive filesystem's
        exists() semantics regardless of the host OS's own case folding."""
        parent = path.parent
        if not parent.is_dir():
            return False
        try:
            return path.name in os.listdir(parent)
        except OSError:
            return False
    return _check
