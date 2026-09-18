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


def _ok_outcome(org: str = "test-org", repo_count: int = 0) -> dict:
    return {"org": org, "status": "ok", "repo_count": repo_count, "detail": ""}


def _fail_outcome(org: str = "test-org", status: str = "auth_denied") -> dict:
    return {"org": org, "status": status, "repo_count": 0, "detail": "HTTP 403 ..."}


def _scan_ok(repos: list) -> tuple:
    """scan_orgs return shape for a fully successful single-org scan (ST-058)."""
    return repos, [_ok_outcome(repo_count=len(repos))]


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
        with patch("lib.org_scanner.scan_orgs", return_value=_scan_ok(repos)):
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

        with patch("lib.org_scanner.scan_orgs", return_value=_scan_ok(repos)):
            report = repo_patrol.cmd_scan(orgs=["test-org"], apply=True)

        reg = json.loads((tmp_path / "data" / "products.json").read_text())
        assert len(reg) == 1
        assert reg[0]["status"] in ("candidate", "investigating")
        assert reg[0].get("first_seen_at") is not None

    def test_existing_launched_skipped(self, tmp_path):
        reg = [_registry_entry("pdf", "python")]
        (tmp_path / "data" / "products.json").write_text(json.dumps(reg))
        repos = [_make_repo("Aspose.PDF-FOSS-for-Python")]

        with patch("lib.org_scanner.scan_orgs", return_value=_scan_ok(repos)):
            report = repo_patrol.cmd_scan(orgs=["test-org"])

        assert report["summary"]["new_candidates"] == 0
        assert report["summary"]["skipped"] == 1

    def test_rejected_skipped_without_force(self, tmp_path):
        reg = [_registry_entry("pdf", "python", status="rejected",
                               rejection_reason="placeholder repo")]
        (tmp_path / "data" / "products.json").write_text(json.dumps(reg))
        repos = [_make_repo("Aspose.PDF-FOSS-for-Python")]

        with patch("lib.org_scanner.scan_orgs", return_value=_scan_ok(repos)):
            report = repo_patrol.cmd_scan(orgs=["test-org"], force=False)

        assert report["summary"]["skipped"] == 1

    def test_unclassifiable_reported(self, tmp_path):
        (tmp_path / "data" / "products.json").write_text("[]")
        repos = [_make_repo("random-unrelated-repo")]

        with patch("lib.org_scanner.scan_orgs", return_value=_scan_ok(repos)):
            report = repo_patrol.cmd_scan(orgs=["test-org"])

        assert report["summary"]["unclassifiable"] >= 1

    def test_archived_detected(self, tmp_path):
        reg = [_registry_entry("pdf", "python")]
        (tmp_path / "data" / "products.json").write_text(json.dumps(reg))
        repos = [_make_repo("Aspose.PDF-FOSS-for-Python", archived=True)]

        with patch("lib.org_scanner.scan_orgs", return_value=_scan_ok(repos)):
            report = repo_patrol.cmd_scan(orgs=["test-org"])

        assert report["summary"]["status_changes"] == 1
        assert report["status_changes"][0]["change"] == "newly_archived"

    def test_inactive_detected(self, tmp_path):
        reg = [_registry_entry("pdf", "python")]
        (tmp_path / "data" / "products.json").write_text(json.dumps(reg))
        repos = [_make_repo("Aspose.PDF-FOSS-for-Python", pushed_days=200)]

        with patch("lib.org_scanner.scan_orgs", return_value=_scan_ok(repos)):
            report = repo_patrol.cmd_scan(orgs=["test-org"])

        assert report["summary"]["status_changes"] == 1
        assert report["status_changes"][0]["change"] == "gone_inactive"

    def test_custom_inactive_days(self, tmp_path):
        reg = [_registry_entry("pdf", "python")]
        (tmp_path / "data" / "products.json").write_text(json.dumps(reg))
        repos = [_make_repo("Aspose.PDF-FOSS-for-Python", pushed_days=50)]

        with patch("lib.org_scanner.scan_orgs", return_value=_scan_ok(repos)):
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

    def test_no_clone_but_auto_clone_fails_is_fetch_failure(self, tmp_path):
        """MT069-2026-09-16-GHA-MINUTES-REARCHITECTURE (2026-09-18): a missing
        clone now triggers ensure_clone() (auto-clone) before giving up -- this
        pins the genuine-failure path (auto-clone itself fails, e.g. no
        clone_url registered or network unavailable), not the old
        "missing cache is always fatal" behavior this test previously
        asserted (that was the actual root cause of the "PAT gap" this
        workflow's failures were misattributed to for months -- see
        cmd_sweep()'s own updated docstring)."""
        reg = [_registry_entry("3d", "python")]
        (tmp_path / "data" / "products.json").write_text(json.dumps(reg))

        def fake_ensure_clone(family, platform):
            raise RuntimeError("no clone_url registered")

        report = repo_patrol.cmd_sweep(
            clone_exists_fn=lambda family, platform: False,
            ensure_clone_fn=fake_ensure_clone,
        )

        assert report["summary"]["fetch_failures"] == 1
        assert "auto-clone failed" in report["fetch_failures"][0]["error"]

    def test_no_clone_but_auto_clone_succeeds_proceeds_normally(self, tmp_path):
        """The actual fix: a cold/missing clone cache (the real, always-true
        state on a fresh CI checkout) self-heals via ensure_clone() instead of
        failing outright -- confirmed via a live repro this session that
        clone_exists() unconditionally returns False on any fresh checkout,
        with zero token/network dependency in that specific check."""
        reg = [_registry_entry("3d", "python")]
        (tmp_path / "data" / "products.json").write_text(json.dumps(reg))

        model_dir = tmp_path / "knowledge" / "3d" / "python" / "merged"
        model_dir.mkdir(parents=True)
        (model_dir / "model.yaml").write_text("repo_sha: abc123\n")

        ensure_clone_calls = []

        def fake_ensure_clone(family, platform):
            ensure_clone_calls.append((family, platform))

        report = repo_patrol.cmd_sweep(
            clone_exists_fn=lambda family, platform: False,
            ensure_clone_fn=fake_ensure_clone,
            update_clone_fn=lambda family, platform: "abc123",
            clone_head_sha_fn=lambda family, platform: "abc123",
        )

        assert ensure_clone_calls == [("3d", "python")]
        assert report["summary"]["fetch_failures"] == 0
        assert report["summary"]["unchanged"] == 1

    def test_only_launched_products_swept(self, tmp_path):
        reg = [
            _registry_entry("3d", "python", status="launched"),
            _registry_entry("pdf", "python", status="candidate"),
        ]
        (tmp_path / "data" / "products.json").write_text(json.dumps(reg))

        def fake_ensure_clone(family, platform):
            raise RuntimeError("no network in test")

        report = repo_patrol.cmd_sweep(
            clone_exists_fn=lambda family, platform: False,
            ensure_clone_fn=fake_ensure_clone,
        )

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
        # FRESH-001 (2026-08-14): _get_stored_sha() delegates to
        # freshness_guard.resolve_baseline(), whose last-resort fallback samples
        # evidence.model_sha from committed content frontmatter (baseline_resolver's
        # existing _sample_content_model_sha) -- a real, intentional new source the
        # old ad hoc 2-source implementation never had. Its default discover_content_fn
        # is not repo-root-isolated (scans the REAL repo's content/ tree), so a real
        # product like "3d"/"python" would otherwise leak a real committed SHA here;
        # patched out to test the true "nothing resolves at all" floor.
        model_dir = tmp_path / "knowledge" / "3d" / "python" / "merged"
        model_dir.mkdir(parents=True)
        (model_dir / "model.yaml").write_text("other: value\n")
        with patch("baseline_resolver._sample_content_model_sha", return_value=None):
            assert repo_patrol._get_stored_sha("3d", "python") is None

    def test_quoted_sha(self, tmp_path):
        model_dir = tmp_path / "knowledge" / "3d" / "python" / "merged"
        model_dir.mkdir(parents=True)
        (model_dir / "model.yaml").write_text("repo_sha: 'abc123'\n")
        assert repo_patrol._get_stored_sha("3d", "python") == "abc123"


class TestGetStoredShaDualSource:
    """FRESH-001 (2026-08-14): _get_stored_sha() now delegates to
    freshness_guard.resolve_baseline(), which prefers merged/model.yaml (now
    git-tracked, T0/T2, and therefore the canonical writer) over
    data/upstream_baselines.json (now a regenerated, derived projection -- see
    freshness_guard.py's module docstring). This intentionally reverses the
    MT030-2026-08-13 fix's priority: that fix made upstream_baselines.json win
    specifically because model.yaml was NOT durable at the time (gitignored);
    now that it is durable, the projection is the fallback, not the source."""

    def test_model_yaml_takes_priority_over_upstream_baselines_json(self, tmp_path):
        model_dir = tmp_path / "knowledge" / "pdf" / "java" / "merged"
        model_dir.mkdir(parents=True)
        (model_dir / "model.yaml").write_text("repo_sha: current_model_yaml_sha\n")
        (tmp_path / "data").mkdir(exist_ok=True)
        (tmp_path / "data" / "upstream_baselines.json").write_text(
            '{"pdf/java": "stale_projection_sha"}'
        )
        assert repo_patrol._get_stored_sha("pdf", "java") == "current_model_yaml_sha"

    def test_falls_back_to_upstream_baselines_when_model_yaml_absent(self, tmp_path):
        (tmp_path / "data").mkdir(exist_ok=True)
        (tmp_path / "data" / "upstream_baselines.json").write_text(
            '{"pdf/java": "projection_sha"}'
        )
        assert repo_patrol._get_stored_sha("pdf", "java") == "projection_sha"

    def test_falls_back_to_model_yaml_when_product_not_in_baselines(self, tmp_path):
        model_dir = tmp_path / "knowledge" / "pdf" / "java" / "merged"
        model_dir.mkdir(parents=True)
        (model_dir / "model.yaml").write_text("repo_sha: abc123def\n")
        (tmp_path / "data").mkdir(exist_ok=True)
        (tmp_path / "data" / "upstream_baselines.json").write_text(
            '{"other/product": "irrelevant_sha"}'
        )
        assert repo_patrol._get_stored_sha("pdf", "java") == "abc123def"

    def test_falls_back_to_model_yaml_when_baselines_file_missing(self, tmp_path):
        model_dir = tmp_path / "knowledge" / "pdf" / "java" / "merged"
        model_dir.mkdir(parents=True)
        (model_dir / "model.yaml").write_text("repo_sha: abc123def\n")
        assert repo_patrol._get_stored_sha("pdf", "java") == "abc123def"

    def test_falls_back_to_model_yaml_when_baselines_file_corrupt(self, tmp_path):
        model_dir = tmp_path / "knowledge" / "pdf" / "java" / "merged"
        model_dir.mkdir(parents=True)
        (model_dir / "model.yaml").write_text("repo_sha: abc123def\n")
        (tmp_path / "data").mkdir(exist_ok=True)
        (tmp_path / "data" / "upstream_baselines.json").write_text("{not valid json")
        assert repo_patrol._get_stored_sha("pdf", "java") == "abc123def"


# ---------------------------------------------------------------------------
# Scan health + fail-closed write policy (ST-058)
# ---------------------------------------------------------------------------

class TestScanHealth:
    """A failed scan must never be indistinguishable from 'nothing found'."""

    def _report_path(self, tmp_path):
        return tmp_path / "reports" / "discovery" / "patrol_report.json"

    def test_healthy_scan_records_ok(self, tmp_path):
        (tmp_path / "data" / "products.json").write_text("[]")
        repos = [_make_repo("Aspose.3D-FOSS-for-Python")]
        with patch("lib.org_scanner.scan_orgs", return_value=_scan_ok(repos)), \
             patch("lib.org_scanner.preflight"):
            report = repo_patrol.cmd_scan(orgs=["test-org"], token="t", auth_mode="GH_TOKEN")

        health = report["scan_health"]
        assert health["status"] == "ok"
        assert health["orgs_ok"] == 1 and health["orgs_failed"] == 0
        assert health["auth_mode"] == "GH_TOKEN"
        assert self._report_path(tmp_path).is_file()

    def test_total_failure_preserves_last_good_report(self, tmp_path):
        """REGRESSION GATE (ST-058): fail-closed.

        The old code wrote total_repos:0 over the last good report AND archived
        it, which also reset the 7-day staleness clock the session-start advisory
        keys on — the failure silenced its own detector.
        """
        (tmp_path / "data" / "products.json").write_text("[]")
        path = self._report_path(tmp_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        sentinel = '{"generated_at": "2026-01-01T00:00:00+00:00", "total_repos": 33}\n'
        path.write_text(sentinel, encoding="utf-8")

        failures = [_fail_outcome("org-a"), _fail_outcome("org-b")]
        with patch("lib.org_scanner.scan_orgs", return_value=([], failures)), \
             patch("lib.org_scanner.preflight"):
            report = repo_patrol.cmd_scan(orgs=["org-a", "org-b"], token="bad",
                                          auth_mode="GITHUB_TOKEN")

        assert report["scan_health"]["status"] == "failed"
        assert report["report_written"] is False
        # The last trustworthy report is byte-identical.
        assert path.read_text(encoding="utf-8") == sentinel

    def test_total_failure_does_not_apply_to_registry(self, tmp_path):
        registry = tmp_path / "data" / "products.json"
        registry.write_text("[]")
        failures = [_fail_outcome("org-a")]
        with patch("lib.org_scanner.scan_orgs", return_value=([], failures)), \
             patch("lib.org_scanner.preflight"):
            report = repo_patrol.cmd_scan(orgs=["org-a"], token="bad", apply=True)
        assert report["registry_applied"] is False
        assert registry.read_text() == "[]"

    def test_partial_failure_is_degraded_and_still_writes(self, tmp_path):
        (tmp_path / "data" / "products.json").write_text("[]")
        repos = [_make_repo("Aspose.3D-FOSS-for-Python")]
        outcomes = [_ok_outcome("good", 1), _fail_outcome("bad", "network_error")]
        with patch("lib.org_scanner.scan_orgs", return_value=(repos, outcomes)), \
             patch("lib.org_scanner.preflight"):
            report = repo_patrol.cmd_scan(orgs=["good", "bad"], token="t")

        health = report["scan_health"]
        assert health["status"] == "degraded"
        assert health["orgs_ok"] == 1 and health["orgs_failed"] == 1
        assert [f["org"] for f in health["failures"]] == ["bad"]
        assert self._report_path(tmp_path).is_file()   # partial data is still useful

    def test_empty_org_list_is_total_failure_not_a_written_report(self, tmp_path):
        """No org attempted is not the same as no repos found."""
        (tmp_path / "data" / "products.json").write_text("[]")
        with patch("lib.org_scanner.scan_orgs", return_value=([], [])), \
             patch("lib.org_scanner.preflight"):
            report = repo_patrol.cmd_scan(orgs=[], token="t")
        assert report["scan_health"]["status"] == "failed"
        assert report["report_written"] is False
        assert not self._report_path(tmp_path).exists()

    def test_preflight_rejection_fails_before_scanning(self, tmp_path):
        """A refused token costs one request, not one per org."""
        (tmp_path / "data" / "products.json").write_text("[]")
        import lib.org_scanner as osc
        with patch("lib.org_scanner.preflight",
                   side_effect=osc.TokenRejected("HTTP 403 ... 366 days ... GH_TOKEN")), \
             patch("lib.org_scanner.scan_orgs") as mock_scan:
            report = repo_patrol.cmd_scan(orgs=["a", "b", "c"], token="bad",
                                          auth_mode="GITHUB_TOKEN")

        mock_scan.assert_not_called()
        assert report["scan_health"]["status"] == "failed"
        assert report["report_written"] is False


class TestScanExitCodes:
    """Exit-code contract: 0 ok / 1 degraded / 2 total failure."""

    def _run(self, tmp_path, monkeypatch, scan_return):
        (tmp_path / "data" / "products.json").write_text("[]")
        monkeypatch.setenv("GH_TOKEN", "ghp_fake")
        with patch("lib.org_scanner.scan_orgs", return_value=scan_return), \
             patch("lib.org_scanner.preflight"):
            return repo_patrol.main(["scan", "--orgs", "test-org"])

    def test_exit_0_on_healthy(self, tmp_path, monkeypatch):
        assert self._run(tmp_path, monkeypatch, ([], [_ok_outcome()])) == 0

    def test_exit_2_on_total_failure(self, tmp_path, monkeypatch):
        assert self._run(tmp_path, monkeypatch, ([], [_fail_outcome()])) == 2

    def test_exit_1_on_degraded(self, tmp_path, monkeypatch):
        rc = self._run(tmp_path, monkeypatch,
                       ([], [_ok_outcome("good"), _fail_outcome("bad")]))
        assert rc == 1

    def test_allow_degraded_suppresses_exit_1(self, tmp_path, monkeypatch):
        (tmp_path / "data" / "products.json").write_text("[]")
        monkeypatch.setenv("GH_TOKEN", "ghp_fake")
        with patch("lib.org_scanner.scan_orgs",
                   return_value=([], [_ok_outcome("good"), _fail_outcome("bad")])), \
             patch("lib.org_scanner.preflight"):
            rc = repo_patrol.main(["scan", "--orgs", "a,b", "--allow-degraded"])
        assert rc == 0

    def test_exit_2_when_no_credential(self, tmp_path, monkeypatch):
        (tmp_path / "data" / "products.json").write_text("[]")
        monkeypatch.delenv("GH_TOKEN", raising=False)
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        assert repo_patrol.main(["scan", "--orgs", "test-org"]) == 2

    def test_no_auth_flag_scans_unauthenticated(self, tmp_path, monkeypatch):
        (tmp_path / "data" / "products.json").write_text("[]")
        monkeypatch.delenv("GH_TOKEN", raising=False)
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        with patch("lib.org_scanner.scan_orgs", return_value=([], [_ok_outcome()])) as m, \
             patch("lib.org_scanner.preflight"):
            rc = repo_patrol.main(["scan", "--orgs", "test-org", "--no-auth"])
        assert rc == 0
        assert m.call_args.kwargs["token"] is None


# ---------------------------------------------------------------------------
# Discovery health gate (MT021 TC-MT021-01/03)
# ---------------------------------------------------------------------------

def _report(status=None, ok=25, req=25, failures=None, include_health=True):
    r = {
        "generated_at": "2026-08-05T12:00:00+00:00",
        "orgs_scanned": [f"org{i}" for i in range(req)],
        "total_repos": 33,
        "new_candidates": [], "status_changes": [], "unclassifiable": [],
        "summary": {"new_candidates": 0},
    }
    if include_health:
        r["scan_health"] = {"status": status, "orgs_ok": ok, "orgs_requested": req,
                            "auth_mode": "GH_TOKEN", "failures": failures or []}
    return r


class TestGateDecisionLogic:
    """evaluate_gate is a pure function -- decision logic tested without I/O."""

    def test_ok_allows_triage(self):
        v = repo_patrol.evaluate_gate(_report("ok"))
        assert v["exit_code"] == 0 and v["verdict"] == "ok" and v["triage_allowed"] is True

    def test_degraded_allows_triage_but_demands_a_stamp(self):
        v = repo_patrol.evaluate_gate(
            _report("degraded", ok=24, req=25,
                    failures=[{"org": "aspose-zip-foss", "status": "not_found"}]))
        assert v["exit_code"] == 1
        assert v["triage_allowed"] is True
        assert "aspose-zip-foss" in v["provenance_stamp"]
        assert "24/25" in v["provenance_stamp"]
        # The reason must forbid the specific wrong conclusion, not just say "incomplete".
        assert "nothing new" in v["reason"]

    def test_failed_blocks_triage(self):
        v = repo_patrol.evaluate_gate(_report("failed", ok=0, req=25))
        assert v["exit_code"] == 2 and v["triage_allowed"] is False

    def test_absent_scan_health_is_unknown_and_blocked(self):
        """REGRESSION GATE (MT021): a pre-ST-058 report must never read as healthy.

        This is the negative control. Such a report has total_repos > 0 and an empty
        candidate list -- exactly the shape of a healthy scan -- but a partial scan of
        that era looks identical, so nothing in the document can prove health.
        """
        v = repo_patrol.evaluate_gate(_report(include_health=False))
        assert v["exit_code"] == 2
        assert v["status"] == "unknown"
        assert v["triage_allowed"] is False

    def test_missing_report_is_blocked(self):
        v = repo_patrol.evaluate_gate(None)
        assert v["exit_code"] == 2 and v["status"] == "missing"
        assert v["triage_allowed"] is False

    def test_unrecognised_status_fails_closed(self):
        """An unknown future status must block, not fall through to allowed."""
        v = repo_patrol.evaluate_gate(_report("weird-new-status"))
        assert v["exit_code"] == 2 and v["triage_allowed"] is False

    def test_scan_health_wrong_type_is_blocked(self):
        r = _report("ok"); r["scan_health"] = "ok"          # string, not dict
        assert repo_patrol.evaluate_gate(r)["exit_code"] == 2

    def test_no_input_shape_allows_triage_of_an_untrustworthy_report(self):
        """Acceptance criterion, asserted exhaustively over every shape we model."""
        untrustworthy = [
            _report("failed"), _report("weird"), _report(include_health=False), None,
        ]
        for r in untrustworthy:
            assert repo_patrol.evaluate_gate(r)["triage_allowed"] is False


class TestGateCommand:
    def _write(self, tmp_path, report):
        d = tmp_path / "reports" / "discovery"; d.mkdir(parents=True, exist_ok=True)
        (d / "patrol_report.json").write_text(json.dumps(report), encoding="utf-8")
        return d

    def test_exit_codes_end_to_end(self, tmp_path):
        d = self._write(tmp_path, _report("ok"))
        assert repo_patrol.cmd_gate() == 0
        (d / "patrol_report.json").write_text(json.dumps(_report("degraded", ok=1, req=2)), encoding="utf-8")
        assert repo_patrol.cmd_gate() == 1
        (d / "patrol_report.json").write_text(json.dumps(_report("failed", ok=0)), encoding="utf-8")
        assert repo_patrol.cmd_gate() == 2

    def test_missing_report_exits_2(self, tmp_path):
        assert repo_patrol.cmd_gate() == 2

    def test_writes_verdict_artifact(self, tmp_path):
        self._write(tmp_path, _report("degraded", ok=1, req=2,
                                      failures=[{"org": "bad", "status": "network_error"}]))
        repo_patrol.cmd_gate()
        vf = tmp_path / "reports" / "discovery" / "discovery_verdict.yaml"
        assert vf.is_file()
        import yaml
        v = yaml.safe_load(vf.read_text(encoding="utf-8"))["discovery_verdict"]
        assert v["verdict"] == "degraded" and v["exit_code"] == 1
        assert v["failures"][0]["org"] == "bad"

    def test_gate_never_mutates_the_input_report(self, tmp_path):
        d = self._write(tmp_path, _report("degraded", ok=1, req=2))
        before = (d / "patrol_report.json").read_bytes()
        repo_patrol.cmd_gate()
        assert (d / "patrol_report.json").read_bytes() == before

    def test_gate_is_idempotent(self, tmp_path):
        self._write(tmp_path, _report("ok"))
        vf = tmp_path / "reports" / "discovery" / "discovery_verdict.yaml"
        assert repo_patrol.cmd_gate() == 0
        import yaml
        a = yaml.safe_load(vf.read_text(encoding="utf-8"))["discovery_verdict"]
        assert repo_patrol.cmd_gate() == 0
        b = yaml.safe_load(vf.read_text(encoding="utf-8"))["discovery_verdict"]
        a.pop("verdict_at"); b.pop("verdict_at")
        assert a == b

    def test_json_mode(self, tmp_path, capsys):
        self._write(tmp_path, _report("ok"))
        repo_patrol.cmd_gate(as_json=True)
        assert json.loads(capsys.readouterr().out)["verdict"] == "ok"

    def test_cli_routes_gate_subcommand(self, tmp_path):
        self._write(tmp_path, _report("failed", ok=0))
        assert repo_patrol.main(["gate"]) == 2


class TestGateArbitraryReport:
    """--report evaluates any file (TC-MT021-08), without disturbing live state."""

    def _archive(self, tmp_path, name, report):
        h = tmp_path / "reports" / "discovery" / "history"; h.mkdir(parents=True, exist_ok=True)
        p = h / name; p.write_text(json.dumps(report), encoding="utf-8")
        return p

    def test_pre_st058_archive_is_blocked(self, tmp_path):
        """The real-world case: an archive with no scan_health must never read healthy."""
        p = self._archive(tmp_path, "2026-05-15-patrol.json", _report(include_health=False))
        assert repo_patrol.cmd_gate(report_path=p) == 2

    def test_healthy_archive_passes(self, tmp_path):
        p = self._archive(tmp_path, "2026-08-05-patrol.json", _report("ok"))
        assert repo_patrol.cmd_gate(report_path=p) == 0

    def test_nonexistent_path_is_blocked(self, tmp_path):
        assert repo_patrol.cmd_gate(report_path=tmp_path / "nope.json") == 2

    def test_unparseable_report_is_blocked(self, tmp_path):
        p = tmp_path / "broken.json"; p.write_text("{not json", encoding="utf-8")
        assert repo_patrol.cmd_gate(report_path=p) == 2

    def test_inspection_does_not_clobber_the_live_verdict(self, tmp_path):
        """REGRESSION GATE: a read-only inspection must not overwrite operative state.

        The live verdict is what S-95 and session-start consume; letting an archive
        inspection silently replace it would reintroduce exactly the quiet state
        corruption this mission removed.
        """
        d = tmp_path / "reports" / "discovery"; d.mkdir(parents=True, exist_ok=True)
        (d / "patrol_report.json").write_text(json.dumps(_report("ok")), encoding="utf-8")
        assert repo_patrol.cmd_gate() == 0                      # writes the live verdict
        live = (d / "discovery_verdict.yaml").read_bytes()

        arch = self._archive(tmp_path, "old.json", _report(include_health=False))
        assert repo_patrol.cmd_gate(report_path=arch) == 2      # inspection only
        assert (d / "discovery_verdict.yaml").read_bytes() == live

    def test_cli_accepts_report_flag(self, tmp_path):
        p = self._archive(tmp_path, "a.json", _report("degraded", ok=1, req=2))
        assert repo_patrol.main(["gate", "--report", str(p)]) == 1


# ---------------------------------------------------------------------------
# CLI parse
# ---------------------------------------------------------------------------

class TestCLI:
    def test_scan_dry_run_default(self, tmp_path, monkeypatch):
        (tmp_path / "data" / "products.json").write_text("[]")
        monkeypatch.setenv("GH_TOKEN", "ghp_fake")
        with patch("lib.org_scanner.scan_orgs", return_value=([], [_ok_outcome()])), \
             patch("lib.org_scanner.preflight"):
            rc = repo_patrol.main(["scan", "--orgs", "test-org"])
        assert rc == 0

    def test_report_subcommand(self, tmp_path):
        rc = repo_patrol.main(["report"])
        assert rc == 0
