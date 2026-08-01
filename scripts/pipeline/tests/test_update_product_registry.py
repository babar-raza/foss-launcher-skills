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

        # T3-MOCK: target=requests reason="HTTP boundary call to GitHub API" removal=PERMANENT
        with patch.object(org_scanner, "requests") as mock_req, \
             patch("org_scanner.time.sleep") as mock_sleep:
            mock_req.get.side_effect = [rate_resp, ok_resp]
            repos = list(org_scanner._paginate("https://api.github.com/orgs/test/repos", {}, None))

        assert mock_sleep.called
        assert repos == [{"name": "repo1"}]

    def test_no_403_no_sleep_between_single_page(self):
        ok_resp = self._make_response(200, [{"name": "r1"}, {"name": "r2"}], {"Link": ""})
        # T3-MOCK: target=requests reason="HTTP boundary call to GitHub API" removal=PERMANENT
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
        # Use configure() for KNOWLEDGE_ROOT; patch REGISTRY_PATH and stub discovery
        upr.configure(repo_root=tmp_path)
        with patch.object(upr, "REGISTRY_PATH", registry_path), \
             patch("update_product_registry._discover_from_github", return_value=[]):
            rc = upr.main(["--local-only", "--dry-run"])

        assert rc == 0
        assert not registry_path.exists(), "dry-run must not create products.json"
        captured = capsys.readouterr()
        assert "DRY-RUN" in captured.out


# ---------------------------------------------------------------------------
# --reconcile: blog_content signal distinguishes below-threshold skip from a
# genuinely missing/lost blog section (site_planner.py plan_blog() threshold)
# ---------------------------------------------------------------------------

class TestReconcileBlogSignal:
    @pytest.fixture(autouse=True)
    def _reset_repo_root(self):
        yield
        upr.configure(repo_root=None)

    def _write_site_plan(self, tmp_path, family, platform, justified):
        plan_dir = tmp_path / "reports" / "plans" / family / platform
        plan_dir.mkdir(parents=True, exist_ok=True)
        (plan_dir / "site_plan.yaml").write_text(
            "plan:\n"
            "  sections:\n"
            "    blog:\n"
            f"      justified: {str(justified).lower()}\n"
            "      page_count: 0\n"
            "      pages: []\n",
            encoding="utf-8",
        )

    def test_blog_skipped_when_below_threshold_and_no_content(self, tmp_path):
        upr.configure(repo_root=tmp_path)
        self._write_site_plan(tmp_path, "cells", "go", justified=False)
        entry = {"family": "cells", "platform": "go"}
        signals = dict(upr._check_signals(entry))
        assert signals["blog_content"] == "SKIPPED"

    def test_blog_missing_when_justified_but_no_content(self, tmp_path):
        # Regression guard for the real G-06 class: a product whose blog WAS
        # justified but has no content on disk must still fail loudly.
        upr.configure(repo_root=tmp_path)
        self._write_site_plan(tmp_path, "cells", "cpp", justified=True)
        entry = {"family": "cells", "platform": "cpp"}
        signals = dict(upr._check_signals(entry))
        assert signals["blog_content"] == "MISSING"

    def test_blog_missing_when_site_plan_absent(self, tmp_path):
        # No site_plan.yaml at all -> unknown, fail conservative (not SKIPPED).
        upr.configure(repo_root=tmp_path)
        entry = {"family": "words", "platform": "net"}
        signals = dict(upr._check_signals(entry))
        assert signals["blog_content"] == "MISSING"

    def test_blog_ok_when_content_dir_exists(self, tmp_path):
        upr.configure(repo_root=tmp_path)
        self._write_site_plan(tmp_path, "pdf", "go", justified=True)
        blog_dir = tmp_path / "content" / "blog.aspose.org" / "pdf" / "go"
        blog_dir.mkdir(parents=True)
        entry = {"family": "pdf", "platform": "go"}
        signals = dict(upr._check_signals(entry))
        assert signals["blog_content"] == "OK"

    def _make_fully_ok_product(self, tmp_path, family, platform, *, blog_justified):
        """Build a real on-disk fixture where every signal except (maybe) blog
        resolves OK, exercising _run_reconcile end-to-end with no mocking."""
        model_dir = tmp_path / "knowledge" / family / platform / "merged"
        model_dir.mkdir(parents=True, exist_ok=True)
        (model_dir / "model.yaml").write_text("stale_since: null\n", encoding="utf-8")
        self._write_site_plan(tmp_path, family, platform, justified=blog_justified)
        for site in ("docs.aspose.org", "kb.aspose.org", "reference.aspose.org"):
            (tmp_path / "content" / site / "en" / family / platform).mkdir(parents=True, exist_ok=True)
        # MT015 signal 8: package_registry must also resolve OK for a fixture
        # genuinely meant to be "fully OK" across every signal.
        (tmp_path / "data").mkdir(parents=True, exist_ok=True)
        (tmp_path / "data" / "package_registry.json").write_text(
            json.dumps({family: {platform: {"verification": {"published": True}}}}),
            encoding="utf-8",
        )

    def test_run_reconcile_skipped_does_not_fail(self, tmp_path, capsys):
        upr.configure(repo_root=tmp_path)
        self._make_fully_ok_product(tmp_path, "cells", "go", blog_justified=False)
        entry = {"family": "cells", "platform": "go"}

        rc = upr._run_reconcile([entry])

        assert rc == 0
        captured = capsys.readouterr()
        assert "skipped (below blog threshold)" in captured.out

    def test_run_reconcile_missing_fails(self, tmp_path):
        upr.configure(repo_root=tmp_path)
        # Regression guard for the real G-06 class: everything else OK, but
        # blog was justified and the directory is genuinely absent.
        self._make_fully_ok_product(tmp_path, "cells", "cpp", blog_justified=True)
        entry = {"family": "cells", "platform": "cpp"}

        rc = upr._run_reconcile([entry])

        assert rc == 1


# ---------------------------------------------------------------------------
# --reconcile: package_registry signal (MT015) -- "launched but
# package-unverified" is exactly the discrepancy this signal exists to
# surface. The inverse ("published but content still says unpublished") is
# a content-text concern handled by the audit gate (TC-MT015-05), not here.
# ---------------------------------------------------------------------------

class TestReconcilePackageRegistrySignal:
    @pytest.fixture(autouse=True)
    def _reset_repo_root(self):
        yield
        upr.configure(repo_root=None)

    def _write_site_plan(self, tmp_path, family, platform, justified):
        plan_dir = tmp_path / "reports" / "plans" / family / platform
        plan_dir.mkdir(parents=True, exist_ok=True)
        (plan_dir / "site_plan.yaml").write_text(
            "plan:\n"
            "  sections:\n"
            "    blog:\n"
            f"      justified: {str(justified).lower()}\n"
            "      page_count: 0\n"
            "      pages: []\n",
            encoding="utf-8",
        )

    def _write_package_registry(self, tmp_path, data):
        (tmp_path / "data").mkdir(parents=True, exist_ok=True)
        (tmp_path / "data" / "package_registry.json").write_text(json.dumps(data), encoding="utf-8")

    def test_missing_when_no_package_registry_file_at_all(self, tmp_path):
        upr.configure(repo_root=tmp_path)
        entry = {"family": "words", "platform": "net"}
        signals = dict(upr._check_signals(entry))
        assert signals["package_registry"] == "MISSING"

    def test_missing_when_family_platform_not_in_package_registry(self, tmp_path):
        upr.configure(repo_root=tmp_path)
        self._write_package_registry(tmp_path, {"cells": {"java": {"verification": {"published": True}}}})
        entry = {"family": "words", "platform": "net"}
        signals = dict(upr._check_signals(entry))
        assert signals["package_registry"] == "MISSING"

    def test_unverified_when_entry_exists_but_not_yet_published(self, tmp_path):
        """A tracked-but-unpublished entry (e.g. words/net today) is a normal,
        valid state -- not a defect -- so it must not fail reconcile."""
        upr.configure(repo_root=tmp_path)
        self._write_package_registry(tmp_path, {"words": {"net": {"verification": {"published": False}}}})
        entry = {"family": "words", "platform": "net"}
        signals = dict(upr._check_signals(entry))
        assert signals["package_registry"] == "UNVERIFIED"

    def test_ok_when_entry_exists_and_published(self, tmp_path):
        upr.configure(repo_root=tmp_path)
        self._write_package_registry(tmp_path, {"slides": {"java": {"verification": {"published": True}}}})
        entry = {"family": "slides", "platform": "java"}
        signals = dict(upr._check_signals(entry))
        assert signals["package_registry"] == "OK"

    def test_na_for_platform_with_no_tracked_registry_type(self, tmp_path):
        upr.configure(repo_root=tmp_path)
        entry = {"family": "cells", "platform": "some-unmapped-platform"}
        signals = dict(upr._check_signals(entry))
        assert signals["package_registry"] == "N/A"

    def test_reconcile_passes_with_unverified_package_registry_signal(self, tmp_path):
        """UNVERIFIED must not flip _run_reconcile's exit code -- it is not a failure."""
        upr.configure(repo_root=tmp_path)
        model_dir = tmp_path / "knowledge" / "words" / "net" / "merged"
        model_dir.mkdir(parents=True, exist_ok=True)
        (model_dir / "model.yaml").write_text("stale_since: null\n", encoding="utf-8")
        self._write_site_plan(tmp_path, "words", "net", justified=True)
        for site in ("docs.aspose.org", "kb.aspose.org", "reference.aspose.org"):
            (tmp_path / "content" / site / "en" / "words" / "net").mkdir(parents=True, exist_ok=True)
        (tmp_path / "content" / "blog.aspose.org" / "words" / "net").mkdir(parents=True, exist_ok=True)
        # Tracked but explicitly not-yet-published -- a normal state, matching
        # words/net's real current status.
        self._write_package_registry(tmp_path, {"words": {"net": {"verification": {"published": False}}}})
        entry = {"family": "words", "platform": "net"}

        rc = upr._run_reconcile([entry])

        assert rc == 0

    def test_reconcile_fails_when_package_registry_missing(self, tmp_path):
        """Everything else OK, but no package_registry entry at all -> MISSING -> fail."""
        upr.configure(repo_root=tmp_path)
        model_dir = tmp_path / "knowledge" / "words" / "net" / "merged"
        model_dir.mkdir(parents=True, exist_ok=True)
        (model_dir / "model.yaml").write_text("stale_since: null\n", encoding="utf-8")
        self._write_site_plan(tmp_path, "words", "net", justified=True)
        for site in ("docs.aspose.org", "kb.aspose.org", "reference.aspose.org"):
            (tmp_path / "content" / site / "en" / "words" / "net").mkdir(parents=True, exist_ok=True)
        (tmp_path / "content" / "blog.aspose.org" / "words" / "net").mkdir(parents=True, exist_ok=True)
        # Deliberately no data/package_registry.json written at all.
        entry = {"family": "words", "platform": "net"}

        rc = upr._run_reconcile([entry])

        assert rc == 1
