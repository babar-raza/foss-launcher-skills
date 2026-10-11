"""Tests for the registry_exclusions.json mechanism shared (duplicated) by
update_product_registry.py (S-68) and repo_patrol.py (S-93).

Closes the gap INV-004 documented: a rejected repo could be silently
reactivated by a routine (non --force) scan because nothing checked prior
resolutions before marking a repo active. See
reports/skill-gaps/2026-07-28-registry-exclusion-mechanism.md.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_PIPELINE = Path(__file__).resolve().parents[1]
if str(_PIPELINE) not in sys.path:
    sys.path.insert(0, str(_PIPELINE))

import update_product_registry as upr  # noqa: E402

# ST-058: scan_orgs returns (repos, outcomes); a reached org yields an "ok" outcome.
_OK = {"org": "test-org", "status": "ok", "repo_count": 1, "detail": ""}
import repo_patrol  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_paths(tmp_path):
    upr.configure(repo_root=tmp_path)
    repo_patrol.configure(repo_root=tmp_path)
    (tmp_path / "data").mkdir(exist_ok=True)
    yield
    upr.configure()
    repo_patrol.configure()


def _write_exclusions(tmp_path, records):
    (tmp_path / "data" / "registry_exclusions.json").write_text(
        json.dumps(records), encoding="utf-8"
    )


def _make_repo(name, *, pushed_days=10, archived=False):
    from datetime import datetime, timezone, timedelta
    dt = datetime.now(tz=timezone.utc) - timedelta(days=pushed_days)
    return {
        "name": name,
        "full_name": f"org/{name}",
        "html_url": f"https://github.com/org/{name}",
        "clone_url": f"https://github.com/org/{name}.git",
        "pushed_at": dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "archived": archived,
        "description": "A FOSS lib",
    }


# ---------------------------------------------------------------------------
# _load_exclusions / _is_excluded — pure function tests (both modules)
# ---------------------------------------------------------------------------

class TestLoadExclusionsBothModules:
    def test_missing_file_returns_empty(self, tmp_path):
        assert upr._load_exclusions() == []
        assert repo_patrol._load_exclusions() == []

    def test_malformed_json_returns_empty(self, tmp_path):
        (tmp_path / "data" / "registry_exclusions.json").write_text("not json", encoding="utf-8")
        assert upr._load_exclusions() == []
        assert repo_patrol._load_exclusions() == []

    def test_valid_file_loads(self, tmp_path):
        _write_exclusions(tmp_path, [{"match": "repo_name", "value": "Foo"}])
        assert upr._load_exclusions() == [{"match": "repo_name", "value": "Foo"}]
        assert repo_patrol._load_exclusions() == [{"match": "repo_name", "value": "Foo"}]


class TestIsExcludedBothModules:
    @pytest.mark.parametrize("mod", [upr, repo_patrol])
    def test_repo_name_match_case_insensitive(self, mod):
        exclusions = [{"match": "repo_name", "value": "Aspose-PDF-FOSS-for-Go-MCP"}]
        assert mod._is_excluded(exclusions, repo_name="aspose-pdf-foss-for-go-mcp") is True

    @pytest.mark.parametrize("mod", [upr, repo_patrol])
    def test_repo_name_no_match(self, mod):
        exclusions = [{"match": "repo_name", "value": "Aspose-PDF-FOSS-for-Go-MCP"}]
        assert mod._is_excluded(exclusions, repo_name="Aspose.PDF-FOSS-for-Go") is False

    @pytest.mark.parametrize("mod", [upr, repo_patrol])
    def test_family_platform_match(self, mod):
        exclusions = [{"match": "family_platform", "family": "cells", "platform": "typescript"}]
        assert mod._is_excluded(exclusions, family="cells", platform="typescript") is True

    @pytest.mark.parametrize("mod", [upr, repo_patrol])
    def test_family_platform_no_match_different_platform(self, mod):
        exclusions = [{"match": "family_platform", "family": "cells", "platform": "typescript"}]
        assert mod._is_excluded(exclusions, family="cells", platform="java") is False

    @pytest.mark.parametrize("mod", [upr, repo_patrol])
    def test_empty_exclusions_never_matches(self, mod):
        assert mod._is_excluded([], repo_name="anything", family="cells", platform="java") is False


# ---------------------------------------------------------------------------
# update_product_registry.py integration — discovery-time skip
# ---------------------------------------------------------------------------

class TestUpdateRegistryDiscoveryTimeSkip:
    def test_excluded_repo_name_never_discovered(self, tmp_path):
        _write_exclusions(tmp_path, [
            {"match": "repo_name", "value": "Aspose-PDF-FOSS-for-Go-MCP"},
        ])
        repo = _make_repo("Aspose-PDF-FOSS-for-Go-MCP")
        with patch("org_scanner.scan_orgs", return_value=([repo], [_OK])):
            products, _ = upr._discover_from_github(["test-org"], token=None)
        assert products == []

    def test_non_excluded_repo_still_discovered(self, tmp_path):
        _write_exclusions(tmp_path, [
            {"match": "repo_name", "value": "Aspose-PDF-FOSS-for-Go-MCP"},
        ])
        repo = _make_repo("Aspose.Cells-FOSS-for-Go")
        with patch("org_scanner.scan_orgs", return_value=([repo], [_OK])):
            products, _ = upr._discover_from_github(["test-org"], token=None)
        assert len(products) == 1
        assert products[0]["family"] == "cells"


# ---------------------------------------------------------------------------
# update_product_registry.py integration — post-merge enforcement (the real
# INV-004 regression guard: an excluded entry can never end up active,
# regardless of what discovery/existing-registry state says).
# ---------------------------------------------------------------------------

class TestEnforceExclusionsDirect:
    def test_forces_active_false_even_when_merge_input_says_true(self):
        """Bypasses the discovery-time skip entirely: proves _enforce_exclusions
        is a real, independent safety net, not just redundant with it. A
        --local-only knowledge_dir discovery (which has no exclusion check of
        its own) or any other future code path could hand _merge() an
        already-active=True entry for an excluded pair; this must still be
        forced inactive.
        """
        exclusions = [{"match": "family_platform", "family": "cells", "platform": "typescript"}]
        merged = [
            {
                "family": "cells", "platform": "typescript",
                "repo_name": "Aspose.Cells-FOSS-for-TypeScript",
                "active": True, "discovered_via": "knowledge_dir",
            },
            {
                "family": "cells", "platform": "java",
                "repo_name": "Aspose.Cells-FOSS-for-Java",
                "active": True, "discovered_via": "github",
            },
        ]
        result = upr._enforce_exclusions(merged, exclusions)
        excluded_entry = next(e for e in result if e["platform"] == "typescript")
        other_entry = next(e for e in result if e["platform"] == "java")
        assert excluded_entry["active"] is False
        assert excluded_entry["excluded"] is True
        assert other_entry["active"] is True
        assert "excluded" not in other_entry


class TestUpdateRegistryPostMergeEnforcement:
    def test_excluded_family_platform_forced_inactive_even_with_force_flag(self, tmp_path):
        """Simulates the exact INV-004 failure mode: cells/typescript already
        active:false in the registry, but a fresh scan reports it as
        recently-pushed/not-archived (i.e. GitHub-side signals look "active"
        again). Without this mechanism, --force (or even the pre-existing
        `not prev.get("active")` branch in _merge for force=False) would
        flip it back to active:true. With the exclusion in place, it must
        stay inactive no matter what.
        """
        _write_exclusions(tmp_path, [
            {"match": "family_platform", "family": "cells", "platform": "typescript"},
        ])
        registry_path = tmp_path / "data" / "products.json"
        registry_path.write_text(json.dumps([
            {
                "family": "cells", "platform": "typescript",
                "repo_name": "Aspose.Cells-FOSS-for-TypeScript",
                "repo_url": "https://github.com/aspose-cells-foss/Aspose.Cells-FOSS-for-TypeScript",
                "clone_url": "https://github.com/aspose-cells-foss/Aspose.Cells-FOSS-for-TypeScript.git",
                "active": False, "discovered_via": "github",
            }
        ]), encoding="utf-8")

        repo = _make_repo("Aspose.Cells-FOSS-for-TypeScript", pushed_days=5, archived=False)
        with patch.object(upr, "REGISTRY_PATH", registry_path), \
             patch("org_scanner.scan_orgs", return_value=([repo], [_OK])):
            rc = upr.main(["--org", "test-org", "--force"])

        assert rc == 0
        result = json.loads(registry_path.read_text(encoding="utf-8"))
        entry = next(e for e in result if e["family"] == "cells" and e["platform"] == "typescript")
        assert entry["active"] is False
        assert entry["excluded"] is True

    def test_excluded_repo_name_never_appears_active_on_dry_run_table(self, tmp_path, capsys):
        _write_exclusions(tmp_path, [
            {"match": "repo_name", "value": "Aspose-PDF-FOSS-for-Go-MCP"},
        ])
        repo = _make_repo("Aspose-PDF-FOSS-for-Go-MCP")
        registry_path = tmp_path / "data" / "products.json"
        with patch.object(upr, "REGISTRY_PATH", registry_path), \
             patch("org_scanner.scan_orgs", return_value=([repo], [_OK])):
            rc = upr.main(["--org", "test-org", "--dry-run"])
        assert rc == 0
        assert not registry_path.exists()
        captured = capsys.readouterr()
        assert "Go-MCP" not in captured.out


# ---------------------------------------------------------------------------
# repo_patrol.py integration — excluded repos never surface in the report
# ---------------------------------------------------------------------------

class TestRepoPatrolExclusion:
    def test_excluded_repo_not_in_unclassifiable_or_candidates(self, tmp_path):
        _write_exclusions(tmp_path, [
            {"match": "repo_name", "value": "Aspose-PDF-FOSS-for-Go-MCP"},
        ])
        repos = [_make_repo("Aspose-PDF-FOSS-for-Go-MCP")]
        with patch("lib.org_scanner.scan_orgs", return_value=(repos, [_OK])):
            report = repo_patrol.cmd_scan(orgs=["test-org"], apply=False)

        assert report["summary"]["unclassifiable"] == 0
        assert report["summary"]["new_candidates"] == 0
        assert report["summary"]["excluded"] == 1
        assert all("Go-MCP" not in u.get("repo_name", "") for u in report["unclassifiable"])

    def test_excluded_family_platform_never_reactivated_via_apply(self, tmp_path):
        _write_exclusions(tmp_path, [
            {"match": "family_platform", "family": "cells", "platform": "typescript"},
        ])
        repos = [_make_repo("Aspose.Cells-FOSS-for-TypeScript")]
        with patch("lib.org_scanner.scan_orgs", return_value=(repos, [_OK])):
            report = repo_patrol.cmd_scan(orgs=["test-org"], apply=True)

        assert report["summary"]["new_candidates"] == 0
        reg_path = tmp_path / "data" / "products.json"
        if reg_path.exists():
            reg = json.loads(reg_path.read_text(encoding="utf-8"))
            assert not any(e["family"] == "cells" and e["platform"] == "typescript" for e in reg)
