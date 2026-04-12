"""Tests for update_product_registry.py and org_scanner.py."""
from __future__ import annotations

import sys
import json
import time
import types
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

# Ensure pipeline dir is importable
_PIPELINE = Path(__file__).resolve().parents[1]
if str(_PIPELINE) not in sys.path:
    sys.path.insert(0, str(_PIPELINE))

import update_product_registry as upr  # noqa: E402
import org_scanner  # noqa: E402


# ---------------------------------------------------------------------------
# _classify_repo — pure function tests
# ---------------------------------------------------------------------------

class TestClassifyRepo:
    def test_new_convention_3d_python(self):
        assert upr._classify_repo("Aspose.3D-FOSS-for-Python") == ("3d", "python")

    def test_new_convention_words_net(self):
        assert upr._classify_repo("Aspose.Words-FOSS-for-.NET") == ("words", "net")

    def test_new_convention_java(self):
        assert upr._classify_repo("Aspose.Cells-FOSS-for-Java") == ("cells", "java")

    def test_legacy_convention(self):
        assert upr._classify_repo("aspose-pdf-python") == ("pdf", "python")

    def test_legacy_convention_slides(self):
        assert upr._classify_repo("aspose-slides-java") == ("slides", "java")

    def test_unrecognised_returns_none(self):
        assert upr._classify_repo("some-random-repo") is None

    def test_partial_match_returns_none(self):
        assert upr._classify_repo("Aspose.Words-FOSS") is None

    def test_new_convention_cpp(self):
        assert upr._classify_repo("Aspose.Imaging-FOSS-for-Cpp") == ("imaging", "cpp")


# ---------------------------------------------------------------------------
# _is_recently_pushed — pure function tests
# ---------------------------------------------------------------------------

class TestIsRecentlyPushed:
    def _ago(self, days: int) -> str:
        dt = datetime.now(tz=timezone.utc) - timedelta(days=days)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    def test_recent_push_is_active(self):
        assert upr._is_recently_pushed(self._ago(10)) is True

    def test_old_push_is_inactive(self):
        assert upr._is_recently_pushed(self._ago(200)) is False

    def test_exactly_at_boundary(self):
        # 180 days ago is still within the window (age.days <= 180)
        assert upr._is_recently_pushed(self._ago(180)) is True

    def test_empty_string_returns_false(self):
        assert upr._is_recently_pushed("") is False

    def test_invalid_string_returns_false(self):
        assert upr._is_recently_pushed("not-a-date") is False


# ---------------------------------------------------------------------------
# _merge — pure function tests
# ---------------------------------------------------------------------------

def _entry(family, platform, active=True, via="github", repo_name=None):
    return {
        "family": family,
        "platform": platform,
        "repo_name": repo_name or f"aspose-{family}-{platform}",
        "repo_url": f"https://github.com/aspose-{family}-foss/aspose-{family}-{platform}",
        "clone_url": f"https://github.com/aspose-{family}-foss/aspose-{family}-{platform}.git",
        "active": active,
        "discovered_via": via,
    }


class TestMerge:
    def test_new_entry_added(self):
        result = upr._merge([], [_entry("3d", "python")], force=False)
        assert len(result) == 1
        assert result[0]["family"] == "3d"

    def test_sorted_by_family_then_platform(self):
        incoming = [_entry("words", "python"), _entry("3d", "java"), _entry("3d", "python")]
        result = upr._merge([], incoming, force=False)
        keys = [(e["family"], e["platform"]) for e in result]
        assert keys == sorted(keys)

    def test_github_overwrites_knowledge_dir_urls(self):
        existing = [_entry("pdf", "java", via="knowledge_dir", repo_name="aspose-pdf-java")]
        incoming = [_entry("pdf", "java", via="github", repo_name="Aspose.PDF-FOSS-for-Java")]
        result = upr._merge(existing, incoming, force=False)
        assert result[0]["repo_name"] == "Aspose.PDF-FOSS-for-Java"
        assert result[0]["discovered_via"] == "github"

    def test_force_false_preserves_active_true(self):
        existing = [_entry("pdf", "java", active=True, via="github")]
        incoming = [_entry("pdf", "java", active=False, via="github")]
        result = upr._merge(existing, incoming, force=False)
        # active=True entry should NOT be flipped to False when force=False
        assert result[0]["active"] is True

    def test_force_true_overwrites_active(self):
        existing = [_entry("pdf", "java", active=True, via="github")]
        incoming = [_entry("pdf", "java", active=False, via="github")]
        result = upr._merge(existing, incoming, force=True)
        assert result[0]["active"] is False

    def test_dedup_same_family_platform(self):
        incoming = [_entry("3d", "python"), _entry("3d", "python")]
        result = upr._merge([], incoming, force=False)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# org_scanner._paginate — HTTP 403 retry with mocked requests
# ---------------------------------------------------------------------------

class TestPaginateRateLimit:
    def _make_response(self, status, body, headers=None):
        r = MagicMock()
        r.status_code = status
        r.json.return_value = body
        r.headers = headers or {}
        r.raise_for_status = MagicMock()
        return r

    def test_403_triggers_sleep_and_retry(self):
        rate_resp = self._make_response(
            403, [],
            {"X-RateLimit-Reset": str(int(time.time()) + 5)}
        )
        ok_resp = self._make_response(200, [{"name": "repo1"}], {"Link": ""})
        ok_resp.raise_for_status = MagicMock()

        with patch.object(org_scanner, "requests") as mock_req, \
             patch("org_scanner.time.sleep") as mock_sleep:
            mock_req.get.side_effect = [rate_resp, ok_resp]
            repos = list(org_scanner._paginate("https://api.github.com/orgs/test/repos", {}, None))

        assert mock_sleep.called
        assert repos == [{"name": "repo1"}]

    def test_no_403_no_sleep_between_single_page(self):
        ok_resp = self._make_response(200, [{"name": "r1"}, {"name": "r2"}], {"Link": ""})
        with patch.object(org_scanner, "requests") as mock_req, \
             patch("org_scanner.time.sleep") as mock_sleep:
            mock_req.get.return_value = ok_resp
            repos = list(org_scanner._paginate("https://api.github.com/orgs/test/repos", {}, None))

        mock_sleep.assert_not_called()
        assert len(repos) == 2


# ---------------------------------------------------------------------------
# dry-run mode — no file written
# ---------------------------------------------------------------------------

class TestDryRun:
    def test_dry_run_does_not_write_file(self, tmp_path, capsys):
        registry_path = tmp_path / "products.json"
        # Patch REGISTRY_PATH and KNOWLEDGE_ROOT so no real I/O
        with patch.object(upr, "REGISTRY_PATH", registry_path), \
             patch.object(upr, "KNOWLEDGE_ROOT", tmp_path / "knowledge"), \
             patch("update_product_registry._discover_from_github", return_value=[]):
            rc = upr.main(["--local-only", "--dry-run"])

        assert rc == 0
        assert not registry_path.exists(), "dry-run must not create products.json"
        captured = capsys.readouterr()
        assert "DRY-RUN" in captured.out
