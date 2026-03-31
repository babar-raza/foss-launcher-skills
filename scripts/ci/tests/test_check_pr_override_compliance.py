"""Unit tests for check_pr_override_compliance.py using temp directories."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_CI_ROOT = Path(__file__).resolve().parent.parent
_PIPELINE_ROOT = _CI_ROOT.parent / "pipeline"
for _p in (str(_CI_ROOT), str(_PIPELINE_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import check_pr_override_compliance  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _patch_dirs(monkeypatch, archived_dir: Path, legacy_dir: Path) -> None:
    monkeypatch.setattr(check_pr_override_compliance, "ARCHIVE_DIR", archived_dir)
    monkeypatch.setattr(check_pr_override_compliance, "LEGACY_ARCHIVE_DIR", legacy_dir)


def _write_token(archive_dir: Path, token_id: str, paths: list[str]) -> None:
    archive_dir.mkdir(parents=True, exist_ok=True)
    token = {"override_id": token_id, "paths": paths, "declared_by": "human"}
    (archive_dir / f"{token_id}.json").write_text(json.dumps(token), encoding="utf-8")


# ---------------------------------------------------------------------------
# TestNoFiles
# ---------------------------------------------------------------------------

class TestNoFiles:
    def test_empty_file_list_exits_0(self, tmp_path, monkeypatch):
        _patch_dirs(monkeypatch, tmp_path / "archived", tmp_path / "legacy")
        monkeypatch.setattr(check_pr_override_compliance, "check_path", lambda p: ("ALLOW", "ok"))
        assert check_pr_override_compliance.main([]) == 0


# ---------------------------------------------------------------------------
# TestAllowedPaths
# ---------------------------------------------------------------------------

class TestAllowedPaths:
    def test_allowed_path_exits_0_no_token_needed(self, tmp_path, monkeypatch):
        _patch_dirs(monkeypatch, tmp_path / "archived", tmp_path / "legacy")
        monkeypatch.setattr(
            check_pr_override_compliance, "check_path", lambda p: ("ALLOW", "allowed")
        )
        rc = check_pr_override_compliance.main(["content/docs.aspose.org/en/test/test.md"])
        assert rc == 0


# ---------------------------------------------------------------------------
# TestForbiddenWithNoToken
# ---------------------------------------------------------------------------

class TestForbiddenWithNoToken:
    def test_forbidden_path_without_token_exits_1(self, tmp_path, monkeypatch):
        archived = tmp_path / "archived"
        archived.mkdir()
        _patch_dirs(monkeypatch, archived, tmp_path / "legacy")
        monkeypatch.setattr(
            check_pr_override_compliance, "check_path", lambda p: ("DENY", "forbidden path")
        )
        rc = check_pr_override_compliance.main(["themes/some-template.html"])
        assert rc == 1


# ---------------------------------------------------------------------------
# TestForbiddenWithArchivedToken
# ---------------------------------------------------------------------------

class TestForbiddenWithArchivedToken:
    def test_forbidden_path_with_archived_token_exits_0(self, tmp_path, monkeypatch):
        archived = tmp_path / "archived"
        _write_token(archived, "token-001", ["themes/some-template.html"])
        _patch_dirs(monkeypatch, archived, tmp_path / "legacy")
        monkeypatch.setattr(
            check_pr_override_compliance, "check_path", lambda p: ("DENY", "forbidden path")
        )
        rc = check_pr_override_compliance.main(["themes/some-template.html"])
        assert rc == 0

    def test_legacy_archive_token_also_satisfies(self, tmp_path, monkeypatch):
        """Tokens in the legacy archive directory are also accepted."""
        legacy = tmp_path / "legacy"
        _write_token(legacy, "legacy-token-001", ["AGENTS.md"])
        _patch_dirs(monkeypatch, tmp_path / "archived", legacy)
        monkeypatch.setattr(
            check_pr_override_compliance, "check_path", lambda p: ("DENY", "forbidden path")
        )
        rc = check_pr_override_compliance.main(["AGENTS.md"])
        assert rc == 0
