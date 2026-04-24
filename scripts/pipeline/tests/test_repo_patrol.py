"""Tests for repo_patrol.py — confidence scoring, classification, merge, and reports."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

_PIPELINE = Path(__file__).resolve().parents[1]
if str(_PIPELINE) not in sys.path:
    sys.path.insert(0, str(_PIPELINE))

import repo_patrol  # noqa: E402
import update_product_registry as upr  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolated_paths(tmp_path):
    """Point all module-level paths at tmp_path for test isolation."""
    repo_patrol.configure(repo_root=tmp_path)
    upr.configure(repo_root=tmp_path)
    (tmp_path / "data").mkdir(exist_ok=True)
    yield
    repo_patrol.configure()
    upr.configure()


def _ago(days: int) -> str:
    dt = datetime.now(tz=timezone.utc) - timedelta(days=days)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_repo(name, *, description="A FOSS lib", pushed_days=10, archived=False):
    return {
        "name": name,
        "full_name": f"org/{name}",
        "html_url": f"https://github.com/org/{name}",
        "clone_url": f"https://github.com/org/{name}.git",
        "pushed_at": _ago(pushed_days),
        "archived": archived,
        "description": description,
    }


def _registry_entry(family, platform, *, status="launched", active=True, **extra):
    entry = {
        "family": family,
        "platform": platform,
        "repo_name": f"Aspose.{family.upper()}-FOSS-for-{platform.title()}",
        "repo_url": f"https://github.com/org/aspose-{family}-{platform}",
        "clone_url": f"https://github.com/org/aspose-{family}-{platform}.git",
        "active": active,
        "discovered_via": "github",
        "status": status,
    }
    entry.update(extra)
    return entry


# ---------------------------------------------------------------------------
# Confidence scoring
# ---------------------------------------------------------------------------

class TestScoreConfidence:
    def test_high_confidence_new_convention(self):
        repo = _make_repo("Aspose.PDF-FOSS-for-Python")
        score = repo_patrol.score_confidence(repo)
        # description(0.10) + pushed(0.20) + not_archived(0.15) + name_new(0.15) = 0.60
        assert score == pytest.approx(0.60, abs=0.01)

    def test_high_confidence_with_clone(self, tmp_path):
        repo = _make_repo("Aspose.PDF-FOSS-for-Python")
        clone = tmp_path / "clone"
        clone.mkdir()
        (clone / "README.md").write_text("# Hi")
        (clone / "main.py").write_text("print('hi')")
        score = repo_patrol.score_confidence(repo, clone_path=clone)
        # 0.60 (API) + 0.15 (readme) + 0.25 (src) = 1.0
        assert score == pytest.approx(1.0, abs=0.01)

    def test_low_confidence_archived_no_desc(self):
        repo = _make_repo("aspose-foo-bar", description="", pushed_days=200, archived=True)
        score = repo_patrol.score_confidence(repo)
        # no description(0) + old push(0) + archived(0) + legacy name(0.05) = 0.05
        assert score == pytest.approx(0.05, abs=0.01)

    def test_legacy_name_lower_score(self):
        repo = _make_repo("aspose-pdf-python")
        score = repo_patrol.score_confidence(repo)
        # description(0.10) + pushed(0.20) + not_archived(0.15) + name_legacy(0.05) = 0.50
        assert score == pytest.approx(0.50, abs=0.01)

    def test_unrecognised_name_no_name_bonus(self):
        repo = _make_repo("random-repo")
        score = repo_patrol.score_confidence(repo)
        # description(0.10) + pushed(0.20) + not_archived(0.15) + name(0) = 0.45
        assert score == pytest.approx(0.45, abs=0.01)

    def test_no_clone_caps_at_api_only(self):
        repo = _make_repo("Aspose.PDF-FOSS-for-Python")
        score = repo_patrol.score_confidence(repo, clone_path=None)
        assert score <= 0.65  # max without clone signals


class TestIsRecentlyPushed:
    def test_recent(self):
        assert repo_patrol._is_recently_pushed(_ago(10)) is True

    def test_old(self):
        assert repo_patrol._is_recently_pushed(_ago(200)) is False

    def test_custom_threshold(self):
        assert repo_patrol._is_recently_pushed(_ago(50), days=30) is False
        assert repo_patrol._is_recently_pushed(_ago(50), days=60) is True

    def test_empty(self):
        assert repo_patrol._is_recently_pushed("") is False

    def test_invalid(self):
        assert repo_patrol._is_recently_pushed("not-a-date") is False


# ---------------------------------------------------------------------------
# Scan — via mocked org_scanner
# ---------------------------------------------------------------------------

class TestCmdScan:
    def test_new_candidate_discovered(self, tmp_path):
        # Empty registry
        (tmp_path / "data" / "products.json").write_text("[]")
        repos = [_make_repo("Aspose.PDF-FOSS-for-Python")]

        # T3-MOCK: target=org_scanner.scan_orgs reason="HTTP boundary" removal=PERMANENT
        with patch("org_scanner.scan_orgs", return_value=repos):
            report = repo_patrol.cmd_scan(orgs=["test-org"], apply=False)

        assert report["summary"]["new_candidates"] == 1
        assert report["new_candidates"][0]["family"] == "pdf"
        assert report["new_candidates"][0]["action"] == "investigate"
        # Not applied — registry still empty
        reg = json.loads((tmp_path / "data" / "products.json").read_text())
        assert len(reg) == 0

    def test_apply_adds_to_registry(self, tmp_path):
        (tmp_path / "data" / "products.json").write_text("[]")
        repos = [_make_repo("Aspose.PDF-FOSS-for-Python")]

        with patch("org_scanner.scan_orgs", return_value=repos):
            report = repo_patrol.cmd_scan(orgs=["test-org"], apply=True)

        reg = json.loads((tmp_path / "data" / "products.json").read_text())
        assert len(reg) == 1
        assert reg[0]["status"] in ("candidate", "investigating")
        assert reg[0].get("first_seen_at") is not None

    def test_existing_launched_skipped(self, tmp_path):
        reg = [_registry_entry("pdf", "python")]
        (tmp_path / "data" / "products.json").write_text(json.dumps(reg))
        repos = [_make_repo("Aspose.PDF-FOSS-for-Python")]

        with patch("org_scanner.scan_orgs", return_value=repos):
            report = repo_patrol.cmd_scan(orgs=["test-org"])

        assert report["summary"]["new_candidates"] == 0
        assert report["summary"]["skipped"] == 1

    def test_rejected_skipped_without_force(self, tmp_path):
        reg = [_registry_entry("pdf", "python", status="rejected",
                               rejection_reason="placeholder repo")]
        (tmp_path / "data" / "products.json").write_text(json.dumps(reg))
        repos = [_make_repo("Aspose.PDF-FOSS-for-Python")]

        with patch("org_scanner.scan_orgs", return_value=repos):
            report = repo_patrol.cmd_scan(orgs=["test-org"], force=False)

        assert report["summary"]["skipped"] == 1

    def test_unclassifiable_reported(self, tmp_path):
        (tmp_path / "data" / "products.json").write_text("[]")
        repos = [_make_repo("random-unrelated-repo")]

        with patch("org_scanner.scan_orgs", return_value=repos):
            report = repo_patrol.cmd_scan(orgs=["test-org"])

        assert report["summary"]["unclassifiable"] >= 1

    def test_archived_detected(self, tmp_path):
        reg = [_registry_entry("pdf", "python")]
        (tmp_path / "data" / "products.json").write_text(json.dumps(reg))
        repos = [_make_repo("Aspose.PDF-FOSS-for-Python", archived=True)]

        with patch("org_scanner.scan_orgs", return_value=repos):
            report = repo_patrol.cmd_scan(orgs=["test-org"])

        assert report["summary"]["status_changes"] == 1
        assert report["status_changes"][0]["change"] == "newly_archived"

    def test_inactive_detected(self, tmp_path):
        reg = [_registry_entry("pdf", "python")]
        (tmp_path / "data" / "products.json").write_text(json.dumps(reg))
        repos = [_make_repo("Aspose.PDF-FOSS-for-Python", pushed_days=200)]

        with patch("org_scanner.scan_orgs", return_value=repos):
            report = repo_patrol.cmd_scan(orgs=["test-org"])

        assert report["summary"]["status_changes"] == 1
        assert report["status_changes"][0]["change"] == "gone_inactive"

    def test_custom_inactive_days(self, tmp_path):
        reg = [_registry_entry("pdf", "python")]
        (tmp_path / "data" / "products.json").write_text(json.dumps(reg))
        repos = [_make_repo("Aspose.PDF-FOSS-for-Python", pushed_days=50)]

        with patch("org_scanner.scan_orgs", return_value=repos):
            report = repo_patrol.cmd_scan(orgs=["test-org"], inactive_days=30)

        assert report["summary"]["status_changes"] == 1
        assert report["status_changes"][0]["change"] == "gone_inactive"


# ---------------------------------------------------------------------------
# Report files
# ---------------------------------------------------------------------------

class TestReportIO:
    def test_write_and_read_report(self, tmp_path):
        data = {"test": True, "count": 42}
        path = repo_patrol._write_report("test_report.json", data)
        assert path.is_file()
        loaded = repo_patrol._read_report("test_report.json")
        assert loaded == data

    def test_archive_creates_dated_file(self, tmp_path):
        data = {"test": True}
        arch = repo_patrol._archive_report("patrol_report.json", data)
        assert arch.is_file()
        assert "patrol" in arch.name
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        assert today in arch.name

    def test_read_missing_returns_none(self, tmp_path):
        assert repo_patrol._read_report("nonexistent.json") is None


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

class TestCmdReport:
    def test_report_with_no_data(self, tmp_path):
        md = repo_patrol.cmd_report()
        assert "No patrol report found" in md
        assert "No sweep report found" in md
        assert (tmp_path / "reports" / "discovery" / "combined_report.md").is_file()

    def test_report_with_patrol_data(self, tmp_path):
        patrol = {
            "generated_at": "2026-04-23T10:00:00Z",
            "orgs_scanned": ["test-org"],
            "total_repos": 5,
            "registry_applied": False,
            "new_candidates": [{"family": "pdf", "platform": "python", "confidence": 0.85,
                                "action": "launch_candidate", "repo_name": "test"}],
            "status_changes": [],
            "unclassifiable": [],
            "summary": {"new_candidates": 1, "status_changes": 0,
                         "unclassifiable": 0, "skipped": 4},
        }
        repo_patrol._write_report("patrol_report.json", patrol)
        md = repo_patrol.cmd_report()
        assert "pdf" in md
        assert "launch_candidate" in md


# ---------------------------------------------------------------------------
# Merge — field preservation (TC-INFRA-03)
# ---------------------------------------------------------------------------

class TestMergeFieldPreservation:
    def test_preserves_discovery_fields(self):
        existing = [{
            "family": "pdf", "platform": "python",
            "repo_name": "old", "repo_url": "", "clone_url": "",
            "active": True, "discovered_via": "github",
            "status": "candidate", "confidence": 0.85,
            "first_seen_at": "2026-01-01T00:00:00Z",
            "last_scanned_at": "2026-01-01T00:00:00Z",
            "rejection_reason": None,
        }]
        incoming = [{
            "family": "pdf", "platform": "python",
            "repo_name": "Aspose.PDF-FOSS-for-Python",
            "repo_url": "https://new", "clone_url": "https://new.git",
            "active": True, "discovered_via": "github",
        }]
        result = upr._merge(existing, incoming, force=False)
        assert result[0]["status"] == "candidate"
        assert result[0]["confidence"] == 0.85
        assert result[0]["first_seen_at"] == "2026-01-01T00:00:00Z"
        assert result[0]["repo_name"] == "Aspose.PDF-FOSS-for-Python"

    def test_rejected_protected_without_force(self):
        existing = [{
            "family": "pdf", "platform": "python",
            "repo_name": "old", "repo_url": "", "clone_url": "",
            "active": False, "discovered_via": "github",
            "status": "rejected", "rejection_reason": "placeholder repo",
        }]
        incoming = [{
            "family": "pdf", "platform": "python",
            "repo_name": "Aspose.PDF-FOSS-for-Python",
            "repo_url": "https://new", "clone_url": "https://new.git",
            "active": True, "discovered_via": "github",
        }]
        result = upr._merge(existing, incoming, force=False)
        assert result[0]["status"] == "rejected"
        assert result[0]["rejection_reason"] == "placeholder repo"

    def test_rejected_overridden_with_force(self):
        existing = [{
            "family": "pdf", "platform": "python",
            "repo_name": "old", "repo_url": "", "clone_url": "",
            "active": False, "discovered_via": "github",
            "status": "rejected", "rejection_reason": "placeholder repo",
        }]
        incoming = [{
            "family": "pdf", "platform": "python",
            "repo_name": "Aspose.PDF-FOSS-for-Python",
            "repo_url": "https://new", "clone_url": "https://new.git",
            "active": True, "discovered_via": "github",
            "status": "candidate",
        }]
        result = upr._merge(existing, incoming, force=True)
        # With force, incoming status is preserved
        assert result[0]["status"] == "candidate"


# ---------------------------------------------------------------------------
# Sweep — mocked clone cache
# ---------------------------------------------------------------------------

class TestCmdSweep:
    def test_unchanged_product(self, tmp_path):
        reg = [_registry_entry("3d", "python")]
        (tmp_path / "data" / "products.json").write_text(json.dumps(reg))

        # Create knowledge model
        model_dir = tmp_path / "knowledge" / "3d" / "python" / "merged"
        model_dir.mkdir(parents=True)
        (model_dir / "model.yaml").write_text("repo_sha: abc123\n")

        with patch("core.clone_cache.clone_exists", return_value=True), \
             patch("core.clone_cache.update_clone", return_value="abc123"), \
             patch("core.clone_cache.clone_head_sha", return_value="abc123"):
            report = repo_patrol.cmd_sweep()

        assert report["summary"]["unchanged"] == 1
        assert report["summary"]["changed"] == 0

    def test_changed_product(self, tmp_path):
        reg = [_registry_entry("3d", "python")]
        (tmp_path / "data" / "products.json").write_text(json.dumps(reg))

        model_dir = tmp_path / "knowledge" / "3d" / "python" / "merged"
        model_dir.mkdir(parents=True)
        (model_dir / "model.yaml").write_text("repo_sha: abc123\n")

        with patch("core.clone_cache.clone_exists", return_value=True), \
             patch("core.clone_cache.update_clone", return_value="def456"), \
             patch("core.clone_cache.clone_head_sha", return_value="def456"), \
             patch.object(repo_patrol, "_classify_impact", return_value="HIGH"):
            report = repo_patrol.cmd_sweep()

        assert report["summary"]["changed"] == 1
        assert report["changed"][0]["impact"] == "HIGH"

    def test_no_clone_is_fetch_failure(self, tmp_path):
        reg = [_registry_entry("3d", "python")]
        (tmp_path / "data" / "products.json").write_text(json.dumps(reg))

        with patch("core.clone_cache.clone_exists", return_value=False):
            report = repo_patrol.cmd_sweep()

        assert report["summary"]["fetch_failures"] == 1

    def test_only_launched_products_swept(self, tmp_path):
        reg = [
            _registry_entry("3d", "python", status="launched"),
            _registry_entry("pdf", "python", status="candidate"),
        ]
        (tmp_path / "data" / "products.json").write_text(json.dumps(reg))

        with patch("core.clone_cache.clone_exists", return_value=False):
            report = repo_patrol.cmd_sweep()

        # Only the launched product should be swept
        assert report["total_products"] == 1


# ---------------------------------------------------------------------------
# Impact classification
# ---------------------------------------------------------------------------

class TestClassifyImpact:
    def test_no_stored_sha_is_high(self):
        assert repo_patrol._classify_impact("3d", "python", None, "abc") == "HIGH"

    def test_clone_missing_is_medium(self):
        with patch("core.clone_cache.clone_path", return_value=Path("/nonexistent")):
            assert repo_patrol._classify_impact("3d", "python", "old", "new") == "MEDIUM"


# ---------------------------------------------------------------------------
# Stored SHA extraction
# ---------------------------------------------------------------------------

class TestGetStoredSha:
    def test_extracts_sha(self, tmp_path):
        model_dir = tmp_path / "knowledge" / "3d" / "python" / "merged"
        model_dir.mkdir(parents=True)
        (model_dir / "model.yaml").write_text("repo_sha: abc123def\nother: value\n")
        assert repo_patrol._get_stored_sha("3d", "python") == "abc123def"

    def test_missing_model(self, tmp_path):
        assert repo_patrol._get_stored_sha("nonexistent", "platform") is None

    def test_no_sha_line(self, tmp_path):
        model_dir = tmp_path / "knowledge" / "3d" / "python" / "merged"
        model_dir.mkdir(parents=True)
        (model_dir / "model.yaml").write_text("other: value\n")
        assert repo_patrol._get_stored_sha("3d", "python") is None

    def test_quoted_sha(self, tmp_path):
        model_dir = tmp_path / "knowledge" / "3d" / "python" / "merged"
        model_dir.mkdir(parents=True)
        (model_dir / "model.yaml").write_text("repo_sha: 'abc123'\n")
        assert repo_patrol._get_stored_sha("3d", "python") == "abc123"


# ---------------------------------------------------------------------------
# CLI parse
# ---------------------------------------------------------------------------

class TestCLI:
    def test_scan_dry_run_default(self, tmp_path):
        (tmp_path / "data" / "products.json").write_text("[]")
        with patch("org_scanner.scan_orgs", return_value=[]):
            rc = repo_patrol.main(["scan", "--orgs", "test-org"])
        assert rc == 0

    def test_report_subcommand(self, tmp_path):
        rc = repo_patrol.main(["report"])
        assert rc == 0
