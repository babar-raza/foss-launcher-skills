"""Tests for post_refresh_verify.py — progress tracking and verification gate.

Coverage:
- record_step(): step written to progress.json; duplicate steps not added twice
- record_step(): progress.json created on first call
- verify() check 1: model.yaml stale_since=null → passes
- verify() check 1: model.yaml stale_since set → fails
- verify() check 2: orphaned claim IDs → reported as failure
- verify() check 3: stale reference pages (API class absent) → reported
- verify() check 4: stale_detect subprocess (mocked)
- verify() returns (True, []) on all-clean state
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

import post_refresh_verify


# ---------------------------------------------------------------------------
# Path isolation fixture
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate_paths(tmp_path):
    """Redirect all module-level paths to tmp_path for each test.

    REPORTS_ROOT is explicitly set to tmp_path/refresh_state (not
    tmp_path/reports/refresh_state) to match existing test assertions.
    _HERE is set to a non-existent sub-path so stale_detect.py is not
    found by default; override with configure(here=tmp_path) when needed.
    """
    post_refresh_verify.configure(
        repo_root=tmp_path,
        reports_root=tmp_path / "refresh_state",
        here=tmp_path / "_nonexistent_scripts",
    )
    yield
    post_refresh_verify.configure()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_knowledge(tmp_path: Path, family: str, platform: str, **kwargs) -> Path:
    """Write a minimal knowledge tree for testing. Returns merged/ dir."""
    merged = tmp_path / "knowledge" / family / platform / "merged"
    merged.mkdir(parents=True)

    if "stale_since" in kwargs:
        model = {"stale_since": kwargs["stale_since"], "version": "1.0"}
    else:
        model = {"stale_since": None, "version": "1.0"}
    (merged / "model.yaml").write_text(yaml.dump(model), encoding="utf-8")

    claims = kwargs.get("claims", [])
    (merged / "claims.json").write_text(
        json.dumps(claims, indent=2), encoding="utf-8"
    )

    api_surface = kwargs.get("api_surface", [])
    (merged / "api_surface.json").write_text(
        json.dumps(api_surface, indent=2), encoding="utf-8"
    )
    return merged


# ---------------------------------------------------------------------------
# record_step tests
# ---------------------------------------------------------------------------

class TestRecordStep:
    def test_step_written_to_progress_json(self, tmp_path):
        post_refresh_verify.record_step("3d", "python", "knowledge_refresh")

        p = tmp_path / "refresh_state" / "3d" / "python" / "progress.json"
        assert p.exists()
        data = json.loads(p.read_text())
        assert "knowledge_refresh" in data["steps"]

    def test_duplicate_step_not_added_twice(self, tmp_path):
        post_refresh_verify.record_step("3d", "python", "knowledge_refresh")
        post_refresh_verify.record_step("3d", "python", "knowledge_refresh")

        p = tmp_path / "refresh_state" / "3d" / "python" / "progress.json"
        data = json.loads(p.read_text())
        assert data["steps"].count("knowledge_refresh") == 1

    def test_multiple_steps_all_recorded(self, tmp_path):
        post_refresh_verify.record_step("3d", "python", "step_a")
        post_refresh_verify.record_step("3d", "python", "step_b")
        post_refresh_verify.record_step("3d", "python", "step_c")

        p = tmp_path / "refresh_state" / "3d" / "python" / "progress.json"
        data = json.loads(p.read_text())
        assert set(data["steps"]) == {"step_a", "step_b", "step_c"}


# ---------------------------------------------------------------------------
# verify() — check 1: model.yaml stale_since
# ---------------------------------------------------------------------------

class TestVerifyCheckStaleSince:
    def test_stale_since_null_passes(self, tmp_path):
        _setup_knowledge(tmp_path, "3d", "python", stale_since=None)
        passed, failures = post_refresh_verify.verify("3d", "python")
        stale_failures = [f for f in failures if "stale_since" in f]
        assert len(stale_failures) == 0

    def test_stale_since_set_fails(self, tmp_path):
        _setup_knowledge(tmp_path, "3d", "python", stale_since="2026-04-01")
        passed, failures = post_refresh_verify.verify("3d", "python")
        assert any("stale_since" in f for f in failures)


# ---------------------------------------------------------------------------
# verify() — check 2: orphaned claims
# ---------------------------------------------------------------------------

class TestVerifyCheckOrphanedClaims:
    def test_valid_citations_pass(self, tmp_path):
        claims = [{"claim_id": "CL-001"}, {"claim_id": "CL-002"}]
        _setup_knowledge(tmp_path, "3d", "python", claims=claims)

        content_dir = tmp_path / "content" / "docs.aspose.org" / "en" / "3d" / "python"
        content_dir.mkdir(parents=True)
        (content_dir / "page.md").write_text(
            "---\nevidence:\n  claims:\n    - CL-001\n    - CL-002\n---\nbody\n"
        )

        passed, failures = post_refresh_verify.verify("3d", "python")
        orphan_failures = [f for f in failures if "Orphaned" in f]
        assert len(orphan_failures) == 0

    def test_orphaned_claim_reported(self, tmp_path):
        claims = [{"claim_id": "CL-001"}]
        _setup_knowledge(tmp_path, "3d", "python", claims=claims)

        content_dir = tmp_path / "content" / "docs.aspose.org" / "en" / "3d" / "python"
        content_dir.mkdir(parents=True)
        (content_dir / "page.md").write_text(
            "---\nevidence:\n  claims:\n    - CL-999\n---\nbody\n"
        )

        passed, failures = post_refresh_verify.verify("3d", "python")
        assert any("Orphaned" in f for f in failures)


# ---------------------------------------------------------------------------
# verify() — check 4: stale_detect subprocess (mocked)
# ---------------------------------------------------------------------------

class TestVerifyCheckStaleDetect:
    def test_stale_detect_exit_0_passes(self, tmp_path):
        _setup_knowledge(tmp_path, "3d", "python")

        # Create fake stale_detect.py at tmp_path and point _HERE there
        (tmp_path / "stale_detect.py").touch()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"stale_pages": 0})
        post_refresh_verify.configure(
            repo_root=tmp_path,
            reports_root=tmp_path / "refresh_state",
            here=tmp_path,
            subprocess_run=lambda *a, **kw: mock_result,
        )

        passed, failures = post_refresh_verify.verify("3d", "python")

        stale_failures = [f for f in failures if "stale_detect" in f.lower()]
        assert len(stale_failures) == 0

    def test_stale_detect_exit_1_reports_failure(self, tmp_path):
        _setup_knowledge(tmp_path, "3d", "python")

        (tmp_path / "stale_detect.py").touch()
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = json.dumps({"stale_pages": 3, "pages": []})
        post_refresh_verify.configure(
            repo_root=tmp_path,
            reports_root=tmp_path / "refresh_state",
            here=tmp_path,
            subprocess_run=lambda *a, **kw: mock_result,
        )

        passed, failures = post_refresh_verify.verify("3d", "python")

        assert any("stale_detect" in f.lower() for f in failures)


# ---------------------------------------------------------------------------
# verify() — check 9 (RPR-F-03, S-111): triage_confirm Layer 2 scan
#
# Regression context: prior to RPR-F-03, triage_confirm.py had no CLI at all,
# so no gate anywhere in --verify could invoke it. These tests prove Check 9
# actually blocks on triage_confirm reporting stale pages, and correctly
# distinguishes "no knowledge yet" (SKIP) from "ran and found something" (FAIL)
# from "ran clean" (PASS) — mirroring TestVerifyCheckStaleDetect's mock pattern.
# ---------------------------------------------------------------------------

class TestVerifyCheck10FrontmatterOnly:
    """Check 10 (RPR-F-04): frontmatter-only grade regressions among updated pages."""

    def _write_progress(self, tmp_path, pages_updated):
        refresh_dir = tmp_path / "refresh_state" / "pdf" / "net"
        refresh_dir.mkdir(parents=True, exist_ok=True)
        (refresh_dir / "progress.json").write_text(
            json.dumps({"steps": ["page_update"], "pages_updated": pages_updated}),
            encoding="utf-8",
        )

    def test_blocks_on_frontmatter_only_grade_regression(self, tmp_path):
        _setup_knowledge(tmp_path, "pdf", "net")
        self._write_progress(tmp_path, ["content/kb.aspose.org/en/pdf/net/faq.md"])

        fake_violation = [{"path": "content/kb.aspose.org/en/pdf/net/faq.md",
                           "grade_before": "A", "grade_after": "C"}]
        post_refresh_verify.configure(
            repo_root=tmp_path,
            reports_root=tmp_path / "refresh_state",
            detect_grade_regressions=lambda *a, **kw: fake_violation,
        )
        passed, failures = post_refresh_verify.verify("pdf", "net")

        c10 = [f for f in failures if "Check 10" in f]
        assert len(c10) == 1
        assert "A->C" in c10[0]
        assert passed is False

    def test_passes_when_no_regressions(self, tmp_path):
        _setup_knowledge(tmp_path, "pdf", "net")
        self._write_progress(tmp_path, ["content/docs.aspose.org/en/pdf/net/p.md"])
        post_refresh_verify.configure(
            repo_root=tmp_path,
            reports_root=tmp_path / "refresh_state",
            detect_grade_regressions=lambda *a, **kw: [],
        )
        passed, failures = post_refresh_verify.verify("pdf", "net")
        assert not any("Check 10" in f for f in failures)

    def test_skips_when_no_updated_pages(self, tmp_path):
        _setup_knowledge(tmp_path, "pdf", "net")
        self._write_progress(tmp_path, [])
        passed, failures = post_refresh_verify.verify("pdf", "net")
        assert not any("Check 10" in f for f in failures)  # SKIP, not a failure


class TestVerifyCheck11SeoStability:
    """Check 11 (RPR-F-05): undeclared title/H1/slug/canonical changes block."""

    def _write_progress(self, tmp_path, pages_updated):
        refresh_dir = tmp_path / "refresh_state" / "pdf" / "net"
        refresh_dir.mkdir(parents=True, exist_ok=True)
        (refresh_dir / "progress.json").write_text(
            json.dumps({"steps": ["page_update"], "pages_updated": pages_updated}),
            encoding="utf-8",
        )

    def test_blocks_on_undeclared_seo_change(self, tmp_path):
        _setup_knowledge(tmp_path, "pdf", "net")
        self._write_progress(tmp_path, ["content/docs.aspose.org/en/pdf/net/p.md"])
        fake = [{"page": "content/docs.aspose.org/en/pdf/net/p.md",
                 "changed_fields": ["slug"], "before": {"slug": "a"}, "after": {"slug": "b"}}]
        post_refresh_verify.configure(
            repo_root=tmp_path,
            reports_root=tmp_path / "refresh_state",
            detect_seo_violations=lambda *a, **kw: fake,
        )
        passed, failures = post_refresh_verify.verify("pdf", "net")
        c11 = [f for f in failures if "Check 11" in f]
        assert len(c11) == 1
        assert "slug" in c11[0]
        assert passed is False

    def test_passes_when_no_seo_changes(self, tmp_path):
        _setup_knowledge(tmp_path, "pdf", "net")
        self._write_progress(tmp_path, ["content/docs.aspose.org/en/pdf/net/p.md"])
        post_refresh_verify.configure(
            repo_root=tmp_path,
            reports_root=tmp_path / "refresh_state",
            detect_seo_violations=lambda *a, **kw: [],
        )
        passed, failures = post_refresh_verify.verify("pdf", "net")
        assert not any("Check 11" in f for f in failures)

    def test_skips_when_no_updated_pages(self, tmp_path):
        _setup_knowledge(tmp_path, "pdf", "net")
        self._write_progress(tmp_path, [])
        passed, failures = post_refresh_verify.verify("pdf", "net")
        assert not any("Check 11" in f for f in failures)  # SKIP, not a failure


class TestVerifyCheck9TriageConfirm:
    def _configure_with_real_script_path(self, tmp_path, subprocess_run=None):
        """Point triage_confirm_script at a real (touched) file under tmp_path,
        matching Check 9's REPO_ROOT/scripts/pipeline/lib/triage_confirm.py
        construction so is_file() finds it under the test sandbox."""
        script_dir = tmp_path / "scripts" / "pipeline" / "lib"
        script_dir.mkdir(parents=True, exist_ok=True)
        (script_dir / "triage_confirm.py").touch()
        post_refresh_verify.configure(
            repo_root=tmp_path,
            reports_root=tmp_path / "refresh_state",
            here=tmp_path,
            subprocess_run=subprocess_run,
        )

    def test_exit_0_passes(self, tmp_path):
        _setup_knowledge(tmp_path, "3d", "python")
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"stale_count": 0})
        self._configure_with_real_script_path(tmp_path, subprocess_run=lambda *a, **kw: mock_result)

        passed, failures = post_refresh_verify.verify("3d", "python")

        assert not any("Check 9" in f for f in failures)

    def test_exit_1_blocks_with_stale_count(self, tmp_path):
        _setup_knowledge(tmp_path, "3d", "python")
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = json.dumps({"stale_count": 2})
        self._configure_with_real_script_path(tmp_path, subprocess_run=lambda *a, **kw: mock_result)

        passed, failures = post_refresh_verify.verify("3d", "python")

        c9_failures = [f for f in failures if "Check 9" in f]
        assert len(c9_failures) == 1
        assert "2 stale page" in c9_failures[0]

    def test_exit_2_is_skip_not_fail(self, tmp_path):
        """Knowledge-absent (exit 2) must not block — it's a precondition gap,
        not a content-quality failure; distinct from exit 1 (ran, found staleness)."""
        _setup_knowledge(tmp_path, "3d", "python")
        mock_result = MagicMock()
        mock_result.returncode = 2
        mock_result.stdout = ""
        self._configure_with_real_script_path(tmp_path, subprocess_run=lambda *a, **kw: mock_result)

        passed, failures = post_refresh_verify.verify("3d", "python")

        assert not any("Check 9" in f for f in failures)

    def test_script_missing_is_skip(self, tmp_path):
        """If triage_confirm.py genuinely doesn't exist at the resolved path,
        Check 9 must SKIP silently, not error the whole verify() call —
        this is what keeps all 32 pre-existing tests (which redirect _HERE to
        a nonexistent path and don't create scripts/pipeline/lib/) passing
        unmodified after Check 9 was added."""
        _setup_knowledge(tmp_path, "3d", "python")
        post_refresh_verify.configure(
            repo_root=tmp_path,
            reports_root=tmp_path / "refresh_state",
            here=tmp_path,
        )
        # Deliberately do NOT create scripts/pipeline/lib/triage_confirm.py

        passed, failures = post_refresh_verify.verify("3d", "python")
        assert not any("Check 9" in f for f in failures)

    def test_unexpected_exit_code_blocks(self, tmp_path):
        _setup_knowledge(tmp_path, "3d", "python")
        mock_result = MagicMock()
        mock_result.returncode = 3
        mock_result.stdout = ""
        self._configure_with_real_script_path(tmp_path, subprocess_run=lambda *a, **kw: mock_result)

        passed, failures = post_refresh_verify.verify("3d", "python")

        assert any("Check 9" in f and "exit 3" in f for f in failures)


# ---------------------------------------------------------------------------
# verify() — check 3: stale reference pages (API class absent)
# ---------------------------------------------------------------------------

class TestVerifyCheckStaleReferencePages:
    """Check 3: reference pages for API classes absent from api_surface.json."""

    def test_valid_reference_page_passes(self, tmp_path):
        """Reference page for a KNOWN class → no failure. Guard: check actually runs."""
        _setup_knowledge(tmp_path, "3d", "python", api_surface=[{"name": "PdfDocument"}])

        ref_dir = tmp_path / "content" / "reference.aspose.org" / "en" / "3d" / "python"
        ref_dir.mkdir(parents=True)
        (ref_dir / "PdfDocument.md").write_text("---\ntitle: PdfDocument\n---\nbody\n")

        passed, failures = post_refresh_verify.verify("3d", "python")
        assert not any("Reference page for absent" in f for f in failures)

    def test_orphaned_reference_page_reported(self, tmp_path):
        """Reference page whose stem is NOT in api_surface.json → failure reported."""
        _setup_knowledge(tmp_path, "3d", "python", api_surface=[{"name": "PdfDocument"}])

        ref_dir = tmp_path / "content" / "reference.aspose.org" / "en" / "3d" / "python"
        ref_dir.mkdir(parents=True)
        (ref_dir / "OrphanedClass.md").write_text("---\ntitle: OrphanedClass\n---\n")

        passed, failures = post_refresh_verify.verify("3d", "python")
        assert any("Reference page for absent" in f for f in failures)
        assert any("OrphanedClass" in f for f in failures)

    def test_index_page_not_flagged(self, tmp_path):
        """_index.md is explicitly excluded from stale detection."""
        _setup_knowledge(tmp_path, "3d", "python", api_surface=[{"name": "PdfDocument"}])

        ref_dir = tmp_path / "content" / "reference.aspose.org" / "en" / "3d" / "python"
        ref_dir.mkdir(parents=True)
        (ref_dir / "_index.md").write_text("---\ntitle: Reference Index\n---\n")
        (ref_dir / "PdfDocument.md").write_text("---\ntitle: PdfDocument\n---\n")

        passed, failures = post_refresh_verify.verify("3d", "python")
        assert not any("Reference page for absent" in f for f in failures)

    def test_empty_api_surface_skips_check(self, tmp_path):
        """When api_surface.json has no classes, check 3 is silently skipped."""
        _setup_knowledge(tmp_path, "3d", "python", api_surface=[])

        ref_dir = tmp_path / "content" / "reference.aspose.org" / "en" / "3d" / "python"
        ref_dir.mkdir(parents=True)
        (ref_dir / "SomeClass.md").write_text("---\ntitle: SomeClass\n---\n")

        passed, failures = post_refresh_verify.verify("3d", "python")
        assert not any("Reference page for absent" in f for f in failures)


# ---------------------------------------------------------------------------
# Fix E: Check 3b — incorrectly retired pages (healing sprint 2026-04-15)
# ---------------------------------------------------------------------------

class TestCheck3bIncorrectlyRetiredPages:
    """Fix E: check_incorrectly_retired_pages catches draft:true pages for live APIs."""

    def test_catches_retired_page_with_live_api(self, tmp_path):
        """A reference page with draft:true whose class IS in api_surface → FAIL."""
        api_path = tmp_path / "api_surface.json"
        api_path.write_text(json.dumps([
            {"name": "FilterColumn", "methods": [], "properties": []},
            {"name": "Workbook", "methods": [], "properties": []},
        ]), encoding="utf-8")

        ref_root = tmp_path / "ref"
        ref_root.mkdir()
        (ref_root / "FilterColumn.md").write_text(
            "---\ntitle: FilterColumn\ndraft: true\nretired_at: '2026-04-13'\n---\nBody.\n",
            encoding="utf-8",
        )
        (ref_root / "Workbook.md").write_text(
            "---\ntitle: Workbook\nlayout: reference-single\n---\nBody.\n",
            encoding="utf-8",
        )

        passed, failures = post_refresh_verify.check_incorrectly_retired_pages(api_path, ref_root)
        assert not passed, "Should FAIL — FilterColumn is retired but exists in api_surface"
        assert len(failures) == 1
        assert "FilterColumn" in failures[0]

    def test_passes_when_no_incorrectly_retired_pages(self, tmp_path):
        """All draft:true pages are for absent APIs → PASS."""
        api_path = tmp_path / "api_surface.json"
        api_path.write_text(json.dumps([
            {"name": "Workbook", "methods": [], "properties": []},
        ]), encoding="utf-8")

        ref_root = tmp_path / "ref"
        ref_root.mkdir()
        # Retired page for a class NOT in api_surface — correct retirement
        (ref_root / "OldClass.md").write_text(
            "---\ntitle: OldClass\ndraft: true\n---\nBody.\n",
            encoding="utf-8",
        )
        (ref_root / "Workbook.md").write_text(
            "---\ntitle: Workbook\n---\nBody.\n",
            encoding="utf-8",
        )

        passed, failures = post_refresh_verify.check_incorrectly_retired_pages(api_path, ref_root)
        assert passed
        assert len(failures) == 0

    def test_skips_index_page(self, tmp_path):
        """_index.md pages are never flagged even if retired."""
        api_path = tmp_path / "api_surface.json"
        api_path.write_text(json.dumps([{"name": "_index"}]), encoding="utf-8")

        ref_root = tmp_path / "ref"
        ref_root.mkdir()
        (ref_root / "_index.md").write_text(
            "---\ntitle: Index\ndraft: true\n---\nBody.\n",
            encoding="utf-8",
        )

        passed, _ = post_refresh_verify.check_incorrectly_retired_pages(api_path, ref_root)
        assert passed

    def test_empty_api_surface_is_pass(self, tmp_path):
        """No API entries → check is skipped → PASS."""
        api_path = tmp_path / "api_surface.json"
        api_path.write_text("[]", encoding="utf-8")
        ref_root = tmp_path / "ref"
        ref_root.mkdir()

        passed, _ = post_refresh_verify.check_incorrectly_retired_pages(api_path, ref_root)
        assert passed


# ---------------------------------------------------------------------------
# Check 6: check_coverage_completeness
# ---------------------------------------------------------------------------

class TestCheck6CoverageCompleteness:
    """Check 6: page_decisions.json must cover all discovered English pages."""

    def _write_page(self, dir_: Path, name: str) -> Path:
        dir_.mkdir(parents=True, exist_ok=True)
        p = dir_ / name
        p.write_text(f"---\ntitle: {name}\n---\nbody\n", encoding="utf-8")
        return p

    def _write_decisions(self, review_root: Path, family: str, platform: str, paths: list[str]) -> None:
        d = review_root / family / platform
        d.mkdir(parents=True, exist_ok=True)
        pages = {p: {"decision": "EVIDENCE_ONLY", "reason": "test"} for p in paths}
        (d / "page_decisions.json").write_text(
            json.dumps({"family": family, "platform": platform, "pages": pages}),
            encoding="utf-8",
        )

    def test_check6_fail_when_decisions_absent(self, tmp_path):
        """Check 6 FAIL when page_decisions.json does not exist."""
        d = tmp_path / "content" / "docs.aspose.org" / "en" / "cells" / "net"
        self._write_page(d, "page.md")

        passed, failures = post_refresh_verify.check_coverage_completeness(
            "cells", "net", review_root=tmp_path / "review"
        )

        assert not passed
        assert any("page_decisions.json not found" in f for f in failures)

    def test_check6_fail_when_page_missing_from_decisions(self, tmp_path):
        """Check 6 FAIL when a discovered page is absent from page_decisions.json."""
        d = tmp_path / "content" / "docs.aspose.org" / "en" / "cells" / "net"
        self._write_page(d, "page1.md")
        self._write_page(d, "page2.md")

        self._write_decisions(
            tmp_path / "review", "cells", "net",
            ["content/docs.aspose.org/en/cells/net/page1.md"]
        )

        passed, failures = post_refresh_verify.check_coverage_completeness(
            "cells", "net", review_root=tmp_path / "review"
        )

        assert not passed
        assert any("Missing" in f and "page2.md" in f for f in failures)

    def test_check6_pass_with_full_coverage(self, tmp_path):
        """Check 6 PASS when page_decisions.json covers all discovered files."""
        d = tmp_path / "content" / "docs.aspose.org" / "en" / "cells" / "net"
        self._write_page(d, "page1.md")
        self._write_page(d, "page2.md")

        self._write_decisions(
            tmp_path / "review", "cells", "net",
            [
                "content/docs.aspose.org/en/cells/net/page1.md",
                "content/docs.aspose.org/en/cells/net/page2.md",
            ]
        )

        passed, failures = post_refresh_verify.check_coverage_completeness(
            "cells", "net", review_root=tmp_path / "review"
        )

        assert passed
        assert failures == []

    def test_check6_pass_no_content_pages(self, tmp_path):
        """Check 6 PASS when no content pages are discovered (product not generated yet)."""
        passed, failures = post_refresh_verify.check_coverage_completeness(
            "cells", "net", review_root=tmp_path / "review"
        )
        assert passed

    def test_check6_skips_locale_files(self, tmp_path):
        """Check 6 does not require locale (translation) files in page_decisions.json."""
        d = tmp_path / "content" / "docs.aspose.org" / "en" / "cells" / "net"
        self._write_page(d, "page.md")
        (d / "page.fr.md").write_text("---\ntitle: page fr\n---\nbody\n", encoding="utf-8")

        self._write_decisions(
            tmp_path / "review", "cells", "net",
            ["content/docs.aspose.org/en/cells/net/page.md"]
        )

        passed, failures = post_refresh_verify.check_coverage_completeness(
            "cells", "net", review_root=tmp_path / "review"
        )

        assert passed


# ---------------------------------------------------------------------------
# G-12 regression: write_reconciliation reads delta from plan.delta, not sp.delta
# ---------------------------------------------------------------------------

class TestWriteReconciliationDeltaPath:
    """G-12 regression: site_plan.yaml delta lives at plan.delta, not top-level delta."""

    def _write_site_plan(self, plans_dir: Path, pages_to_update: list) -> None:
        import yaml
        site_plan = {
            "plan": {
                "schema_version": 2,
                "plan_version": 2,
                "family": "cells",
                "platform": "net",
                "delta": {
                    "pages_to_add": [],
                    "pages_to_update": pages_to_update,  # strings (actual site_plan format)
                    "pages_to_remove": [],
                    "pages_renamed": [],
                },
            }
        }
        plans_dir.mkdir(parents=True, exist_ok=True)
        (plans_dir / "site_plan.yaml").write_text(yaml.dump(site_plan), encoding="utf-8")

    def _write_progress(self, refresh_dir: Path, steps: list) -> None:
        import json
        refresh_dir.mkdir(parents=True, exist_ok=True)
        (refresh_dir / "progress.json").write_text(
            json.dumps({"steps": steps, "pages_updated": []}), encoding="utf-8"
        )

    def test_reads_planned_from_plan_delta_not_top_level(self, tmp_path):
        """write_reconciliation must read delta from plan.delta (G-12 fix)."""
        import json
        plans_dir = tmp_path / "reports" / "plans" / "cells" / "net"
        refresh_dir = tmp_path / "refresh_state" / "cells" / "net"
        paths = [
            "content/docs.aspose.org/en/cells/net/page1.md",
            "content/docs.aspose.org/en/cells/net/page2.md",
        ]
        self._write_site_plan(plans_dir, paths)
        self._write_progress(refresh_dir, ["page_update"])

        post_refresh_verify.configure(
            repo_root=tmp_path,
            reports_root=tmp_path / "refresh_state",
        )
        try:
            recon_path = post_refresh_verify.write_reconciliation(
                "cells", "net", require_content_steps=False
            )
            recon = json.loads(recon_path.read_text(encoding="utf-8"))
            assert recon["planned"]["pages_to_update"] == 2, (
                "G-12: planned.pages_to_update must be 2, not 0. "
                "write_reconciliation is reading from the wrong YAML key."
            )
        finally:
            post_refresh_verify.configure()

    def test_top_level_delta_key_ignored(self, tmp_path):
        """A top-level 'delta' key in site_plan.yaml must NOT be read (G-12 regression)."""
        import json, yaml
        plans_dir = tmp_path / "reports" / "plans" / "cells" / "net"
        refresh_dir = tmp_path / "refresh_state" / "cells" / "net"
        plans_dir.mkdir(parents=True, exist_ok=True)
        # Write site_plan with delta at the WRONG (old) location — should be ignored
        bad_plan = {
            "delta": {"pages_to_update": [{"path": "content/docs.aspose.org/en/cells/net/p.md"}]},
            "plan": {
                "schema_version": 2,
                "plan_version": 2,
                "family": "cells",
                "platform": "net",
                "delta": {"pages_to_add": [], "pages_to_update": [], "pages_to_remove": [], "pages_renamed": []},
            },
        }
        (plans_dir / "site_plan.yaml").write_text(yaml.dump(bad_plan), encoding="utf-8")
        refresh_dir.mkdir(parents=True, exist_ok=True)
        (refresh_dir / "progress.json").write_text(
            json.dumps({"steps": ["page_update"], "pages_updated": []}), encoding="utf-8"
        )

        post_refresh_verify.configure(
            repo_root=tmp_path,
            reports_root=tmp_path / "refresh_state",
        )
        try:
            recon_path = post_refresh_verify.write_reconciliation(
                "cells", "net", require_content_steps=False
            )
            recon = json.loads(recon_path.read_text(encoding="utf-8"))
            assert recon["planned"]["pages_to_update"] == 0, (
                "Top-level 'delta' key must be ignored; planned must come from plan.delta"
            )
        finally:
            post_refresh_verify.configure()


# ---------------------------------------------------------------------------
# Check 8 (G-16): Tracking-gap and stale-prose detection
# ---------------------------------------------------------------------------

class TestCheck8FilesWithBodyDiffMismatch:
    """Check 8 Case A: files_with_body_diff > 0 but pages_updated=[]. RPR-F-01 promoted
    this from WARN to BLOCK by default (the exact PDF-NET-REFRESH-001 tracking gap);
    --allow-warn demotes it back to WARN."""

    def _write_reconciliation(self, refresh_dir: Path, files_with_body_diff: int,
                              executed_pages_updated: "int | None" = None) -> None:
        """Write a minimal execution_reconciliation.json.

        RPR-J-00: Check 8 Case A now judges reconciliation by its OWN self-consistency
        (executed.pages_updated vs body_changes.files_with_body_diff), not by whether it
        agrees with the separate progress.json. `executed_pages_updated` defaults to
        `files_with_body_diff` (a self-consistent, healthy refresh); pass a smaller value
        to model a genuine internal tracking gap.
        """
        if executed_pages_updated is None:
            executed_pages_updated = files_with_body_diff
        refresh_dir.mkdir(parents=True, exist_ok=True)
        recon = {
            "planned": {"pages_to_update": files_with_body_diff, "pages_to_add": 0, "pages_to_remove": 0},
            "executed": {"pages_updated": executed_pages_updated, "pages_added": 0, "pages_removed": 0},
            "skipped": {"pages_update_skipped": 0},
            "body_changes": {
                "files_with_body_diff": files_with_body_diff,
                "files_metadata_only": 0,
                "metadata_only_files": [],
            },
        }
        (refresh_dir / "execution_reconciliation.json").write_text(
            json.dumps(recon), encoding="utf-8"
        )

    def _write_progress(self, refresh_dir: Path, pages_updated: list) -> None:
        refresh_dir.mkdir(parents=True, exist_ok=True)
        (refresh_dir / "progress.json").write_text(
            json.dumps({"steps": ["page_update"], "pages_updated": pages_updated}),
            encoding="utf-8",
        )

    def test_check8_case_a_blocks_on_real_internal_gap(self, tmp_path):
        """RPR-J-00: Case A blocks when RECONCILIATION ITSELF is inconsistent — more body
        diffs than it recorded as executed page updates (body_diff=3, executed=0). That is
        a genuine tracking gap in the durable-ish record, not a progress.json disagreement."""
        _setup_knowledge(tmp_path, "cells", "net")
        refresh_dir = tmp_path / "refresh_state" / "cells" / "net"
        self._write_reconciliation(refresh_dir, files_with_body_diff=3, executed_pages_updated=0)
        self._write_progress(refresh_dir, pages_updated=[])

        passed, failures = post_refresh_verify.verify("cells", "net")

        c8_failures = [f for f in failures if "Check 8" in f and "Case A" in f]
        assert len(c8_failures) == 1, f"a real internal gap must block; failures: {failures}"
        assert passed is False

    def test_check8_case_a_allow_warn_demotes_to_warn(self, tmp_path):
        """RPR-F-01 opt-out: --allow-warn keeps a real internal gap as WARN-only."""
        _setup_knowledge(tmp_path, "cells", "net")
        refresh_dir = tmp_path / "refresh_state" / "cells" / "net"
        self._write_reconciliation(refresh_dir, files_with_body_diff=3, executed_pages_updated=0)
        self._write_progress(refresh_dir, pages_updated=[])

        passed, failures = post_refresh_verify.verify("cells", "net", allow_warn=True)

        c8_failures = [f for f in failures if "Check 8" in f and "Case A" in f]
        assert len(c8_failures) == 0, f"--allow-warn must demote Case A to WARN; got: {c8_failures}"

    def test_check8_case_a_healthy_pdf_net_36_36_passes(self, tmp_path):
        """ANTI-ARTIFACT FIXTURE (plan §18.5, RPR-J-00). The REAL PDF-NET-REFRESH-001
        v26.7.0 reconciliation was executed=36, body_diff=36, metadata_only=0 — a HEALTHY
        refresh. The old Check 8 wrongly FAILed it because progress.json.pages_updated was []
        (two ephemeral files disagreeing). It must now PASS: reconciliation is self-consistent."""
        _setup_knowledge(tmp_path, "pdf", "net")
        refresh_dir = tmp_path / "refresh_state" / "pdf" / "net"
        self._write_reconciliation(refresh_dir, files_with_body_diff=36, executed_pages_updated=36)
        self._write_progress(refresh_dir, pages_updated=[])  # progress.json lags — must not matter

        passed, failures = post_refresh_verify.verify("pdf", "net")

        c8_failures = [f for f in failures if "Check 8" in f and "Case A" in f]
        assert len(c8_failures) == 0, f"healthy 36/36 refresh must not fail Check 8; got: {c8_failures}"

    def test_check8_case_a_self_consistent_recon_passes_despite_empty_progress(self, tmp_path):
        """RPR-J-00: reconciliation self-consistent (executed >= body_diff) PASSES even when
        progress.json.pages_updated is empty — the progress file is not the authority."""
        _setup_knowledge(tmp_path, "cells", "net")
        refresh_dir = tmp_path / "refresh_state" / "cells" / "net"
        self._write_reconciliation(refresh_dir, files_with_body_diff=3, executed_pages_updated=3)
        self._write_progress(refresh_dir, pages_updated=[])

        passed, failures = post_refresh_verify.verify("cells", "net")

        c8_failures = [f for f in failures if "Check 8" in f]
        assert len(c8_failures) == 0

    def test_check8_case_a_no_warn_when_body_diff_zero(self, tmp_path):
        """Case A: files_with_body_diff == 0 -> PASS regardless of pages_updated."""
        _setup_knowledge(tmp_path, "cells", "net")
        refresh_dir = tmp_path / "refresh_state" / "cells" / "net"
        self._write_reconciliation(refresh_dir, files_with_body_diff=0)
        self._write_progress(refresh_dir, pages_updated=[])

        passed, failures = post_refresh_verify.verify("cells", "net")

        c8_failures = [f for f in failures if "Check 8" in f]
        assert len(c8_failures) == 0

    def test_check8_case_a_unknown_when_no_reconciliation(self, tmp_path):
        """RPR-J-00: reconciliation absent -> UNKNOWN (unverifiable), NOT a failure and NOT a
        silent pass. It never contributes a Check-8 FAILURE."""
        _setup_knowledge(tmp_path, "cells", "net")
        # No reconciliation file written
        unknowns: list = []
        passed, failures = post_refresh_verify.verify("cells", "net", unknowns_out=unknowns)

        c8_failures = [f for f in failures if "Check 8" in f]
        assert len(c8_failures) == 0
        assert any("Case A" in u for u in unknowns), f"absent recon must be UNKNOWN; got {unknowns}"


class TestRPRJ00TriState:
    """RPR-J-00: absent / old-schema / self-contradictory bookkeeping yields UNKNOWN, never a
    fabricated FAIL with a made-up count. Encodes the two documented false blocks."""

    def _delta(self, tmp_path, family, platform, removed):
        merged = tmp_path / "knowledge" / family / platform / "merged"
        merged.mkdir(parents=True, exist_ok=True)
        (merged / "knowledge_delta.json").write_text(
            json.dumps({"removed_claims": [f"CLM-{i}" for i in range(removed)]}), encoding="utf-8")

    def _progress(self, tmp_path, family, platform, obj):
        d = tmp_path / "refresh_state" / family / platform
        d.mkdir(parents=True, exist_ok=True)
        (d / "progress.json").write_text(json.dumps(obj), encoding="utf-8")

    def test_check7_old_schema_progress_is_unknown_not_fail(self, tmp_path):
        """The cells/java false block: a 2026-06-28 progress.json with NO pages_updated key
        must NOT be read as '0 updates'. It is UNKNOWN, never a FAIL with a removed-claim count."""
        _setup_knowledge(tmp_path, "cells", "java")
        self._delta(tmp_path, "cells", "java", removed=1996)
        # old-schema progress.json: has 'steps' but NO 'pages_updated' key at all
        self._progress(tmp_path, "cells", "java",
                       {"status": "done", "steps": ["page_update", "reference_update"]})
        unknowns: list = []
        passed, failures = post_refresh_verify.verify("cells", "java", unknowns_out=unknowns)
        assert not any("Check 7" in f for f in failures), f"old-schema must not FAIL Check 7: {failures}"
        assert any("Check 7" in u and "old_schema" in u for u in unknowns)

    def test_check7_absent_progress_is_unknown_not_fail(self, tmp_path):
        """Fresh clone / CI: no progress.json at all -> Check 7 UNKNOWN, never a fabricated FAIL."""
        _setup_knowledge(tmp_path, "cells", "java")
        self._delta(tmp_path, "cells", "java", removed=1996)
        unknowns: list = []
        passed, failures = post_refresh_verify.verify("cells", "java", unknowns_out=unknowns)
        assert not any("Check 7" in f for f in failures)
        assert any("Check 7" in u for u in unknowns)

    def test_check7_genuine_ran_and_did_nothing_still_blocks(self, tmp_path):
        """Preserve the real signal: current-schema progress records 0 updates AND
        reconciliation confirms no body work AND >50 removed -> still a FAIL."""
        _setup_knowledge(tmp_path, "cells", "java")
        self._delta(tmp_path, "cells", "java", removed=100)
        self._progress(tmp_path, "cells", "java", {"steps": ["page_update"], "pages_updated": []})
        # reconciliation present and shows no body work either
        d = tmp_path / "refresh_state" / "cells" / "java"
        (d / "execution_reconciliation.json").write_text(json.dumps({
            "executed": {"pages_updated": 0}, "body_changes": {"files_with_body_diff": 0}}),
            encoding="utf-8")
        passed, failures = post_refresh_verify.verify("cells", "java")
        assert any("Check 7" in f for f in failures), "genuine ran-and-did-nothing must still block"

    def test_check7_progress_desync_with_recon_work_is_unknown(self, tmp_path):
        """progress.json says 0 but reconciliation records body work -> bookkeeping desync ->
        UNKNOWN, not a FAIL."""
        _setup_knowledge(tmp_path, "3d", "net")
        self._delta(tmp_path, "3d", "net", removed=99)
        self._progress(tmp_path, "3d", "net", {"steps": ["page_update"], "pages_updated": []})
        d = tmp_path / "refresh_state" / "3d" / "net"
        (d / "execution_reconciliation.json").write_text(json.dumps({
            "executed": {"pages_updated": 32}, "body_changes": {"files_with_body_diff": 32}}),
            encoding="utf-8")
        unknowns: list = []
        passed, failures = post_refresh_verify.verify("3d", "net", unknowns_out=unknowns)
        assert not any("Check 7" in f for f in failures)
        assert any("Check 7" in u and "desync" in u for u in unknowns)


class TestCheck8ProseStaleWarn:
    """Check 8 Case B: prose_stale_scan JSON with hits. RPR-F-01 promoted this from
    WARN to BLOCK by default; --allow-warn demotes it back."""

    def _write_prose_stale(self, gap_dir: Path, family: str, platform: str, hits: list) -> None:
        gap_dir.mkdir(parents=True, exist_ok=True)
        report = {"family": family, "platform": platform, "hits": hits}
        (gap_dir / f"{family}-{platform}-prose-stale.json").write_text(
            json.dumps(report), encoding="utf-8"
        )

    def test_check8_case_b_blocks_by_default(self, tmp_path):
        """RPR-F-01: Case B with hits now BLOCKS."""
        _setup_knowledge(tmp_path, "cells", "net")
        gap_dir = tmp_path / "reports" / "gap-analysis"
        self._write_prose_stale(gap_dir, "cells", "net", hits=[
            {"file": "content/docs.aspose.org/en/cells/net/page1.md", "api": "OldMethod"},
            {"file": "content/docs.aspose.org/en/cells/net/page2.md", "api": "OldClass"},
        ])

        passed, failures = post_refresh_verify.verify("cells", "net")

        c8_failures = [f for f in failures if "Check 8" in f and "Case B" in f]
        assert len(c8_failures) == 1, f"Case B must now block; failures: {failures}"
        assert passed is False

    def test_check8_case_b_allow_warn_demotes_to_warn(self, tmp_path):
        _setup_knowledge(tmp_path, "cells", "net")
        gap_dir = tmp_path / "reports" / "gap-analysis"
        self._write_prose_stale(gap_dir, "cells", "net", hits=[
            {"file": "content/docs.aspose.org/en/cells/net/page1.md", "api": "OldMethod"},
        ])

        passed, failures = post_refresh_verify.verify("cells", "net", allow_warn=True)

        c8_failures = [f for f in failures if "Check 8" in f and "Case B" in f]
        assert len(c8_failures) == 0

    def test_check8_case_b_pass_when_hits_empty(self, tmp_path):
        """Case B: prose-stale report exists but hits=[] -> PASS."""
        _setup_knowledge(tmp_path, "cells", "net")
        gap_dir = tmp_path / "reports" / "gap-analysis"
        self._write_prose_stale(gap_dir, "cells", "net", hits=[])

        passed, failures = post_refresh_verify.verify("cells", "net")

        c8_failures = [f for f in failures if "Check 8" in f]
        assert len(c8_failures) == 0

    def test_check8_case_b_skip_when_no_report(self, tmp_path):
        """Case B: no prose-stale report -> SKIP (no failures)."""
        _setup_knowledge(tmp_path, "cells", "net")
        # No prose-stale report written

        passed, failures = post_refresh_verify.verify("cells", "net")

        c8_failures = [f for f in failures if "Check 8" in f]
        assert len(c8_failures) == 0

    def test_check8_both_cases_clean_passes(self, tmp_path):
        """Both Case A and Case B clean -> overall no Check 8 failures."""
        _setup_knowledge(tmp_path, "cells", "net")
        refresh_dir = tmp_path / "refresh_state" / "cells" / "net"
        refresh_dir.mkdir(parents=True, exist_ok=True)
        recon = {
            "planned": {"pages_to_update": 2, "pages_to_add": 0, "pages_to_remove": 0},
            "executed": {"pages_updated": 2, "pages_added": 0, "pages_removed": 0},
            "skipped": {"pages_update_skipped": 0},
            "body_changes": {
                "files_with_body_diff": 2,
                "files_metadata_only": 0,
                "metadata_only_files": [],
            },
        }
        (refresh_dir / "execution_reconciliation.json").write_text(
            json.dumps(recon), encoding="utf-8"
        )
        (refresh_dir / "progress.json").write_text(
            json.dumps({
                "steps": ["page_update"],
                "pages_updated": [
                    "content/docs.aspose.org/en/cells/net/page1.md",
                    "content/docs.aspose.org/en/cells/net/page2.md",
                ],
            }),
            encoding="utf-8",
        )
        # No prose-stale report -> Case B skip

        passed, failures = post_refresh_verify.verify("cells", "net")

        c8_failures = [f for f in failures if "Check 8" in f]
        assert len(c8_failures) == 0
