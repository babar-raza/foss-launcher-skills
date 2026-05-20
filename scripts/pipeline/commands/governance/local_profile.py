# Adapted from aspose.org
"""local_profile.py — Local governance profile reader.

Reads .local/governance.json to determine the local governance mode.
CI environments always return "strict" regardless of profile contents.
Missing, expired, or malformed profiles also return "strict".

This module does NOT integrate with any hooks — it is infrastructure only.
Hook integration is deferred to a future sprint.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

_SCHEMA_VERSION = 1
_PROFILE_REL = ".local/governance.json"


def is_ci() -> bool:
    """Return True if running in a CI environment."""
    return os.environ.get("CI", "").lower() in ("true", "1") or \
           os.environ.get("GITHUB_ACTIONS", "").lower() in ("true", "1")


def validate_profile(data: dict) -> bool:
    """Validate profile schema and expiry. Returns True if valid."""
    if not isinstance(data, dict):
        return False
    if data.get("schema_version") != _SCHEMA_VERSION:
        return False
    required = ("profile", "operator", "created_at", "expires_at")
    if not all(k in data for k in required):
        return False
    try:
        expires = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
        if expires < datetime.now(tz=timezone.utc):
            return False
    except (ValueError, TypeError, AttributeError):
        return False
    return True


def load_profile(repo_root: Path) -> dict:
    """Load local governance profile. Returns strict defaults on any failure or CI."""
    strict = {"profile": "strict"}
    if is_ci():
        return strict
    profile_path = repo_root / _PROFILE_REL
    if not profile_path.exists():
        return strict
    try:
        with profile_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return strict
    if not validate_profile(data):
        return strict
    return data


def get_mode(repo_root: Path) -> str:
    """Return the governance mode string for the local environment."""
    profile = load_profile(repo_root)
    return profile.get("profile", "strict")
