"""Regression tests for override_manager.py's validate-for-path.

Covers a real bug hit twice during GHGL-1: an expired pending token that
happens to also list the target path (e.g. from an older, unrelated change)
must never shadow a separately-created, still-valid token for the same
path, regardless of which one a directory glob returns first.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline" / "commands" / "governance"))

import override_manager  # noqa: E402


def _write_token(pending_dir: Path, name: str, paths: list[str], authorized_at: str) -> None:
    import json

    pending_dir.mkdir(parents=True, exist_ok=True)
    token = {
        "override_id": name,
        "paths": paths,
        "operation": "edit",
        "reason": "test",
        "plan_reference": "",
        "scope_description": "",
        "authorized_at": authorized_at,
        "retroactive": False,
        "consumed_by_commit": None,
    }
    (pending_dir / f"{name}.json").write_text(json.dumps(token), encoding="utf-8")


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def test_expired_token_does_not_shadow_a_valid_one_for_same_path(tmp_path):
    pending = tmp_path / "pending"
    override_manager.configure(pending_dir=pending, archived_dir=tmp_path / "archived")

    now = datetime.now(tz=timezone.utc)
    # "old" sorts before "recent" alphabetically -- reproduces the real
    # glob-order collision this bug hit twice during GHGL-1.
    _write_token(pending, "aaa-old-expired", ["some/path.yml"], _iso(now - timedelta(days=60)))
    _write_token(pending, "zzz-recent-valid", ["some/path.yml"], _iso(now - timedelta(minutes=1)))

    code = override_manager.cmd_validate_for_path(argparse.Namespace(path="some/path.yml"))

    assert code == 0


def test_all_matching_tokens_expired_reports_expired(tmp_path):
    pending = tmp_path / "pending"
    override_manager.configure(pending_dir=pending, archived_dir=tmp_path / "archived")
    now = datetime.now(tz=timezone.utc)
    _write_token(pending, "old-expired", ["some/path.yml"], _iso(now - timedelta(days=60)))

    code = override_manager.cmd_validate_for_path(argparse.Namespace(path="some/path.yml"))

    assert code == 2


def test_no_matching_token_reports_not_found(tmp_path):
    pending = tmp_path / "pending"
    override_manager.configure(pending_dir=pending, archived_dir=tmp_path / "archived")
    now = datetime.now(tz=timezone.utc)
    _write_token(pending, "unrelated", ["other/path.yml"], _iso(now))

    code = override_manager.cmd_validate_for_path(argparse.Namespace(path="some/path.yml"))

    assert code == 2
