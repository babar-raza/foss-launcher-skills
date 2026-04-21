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
from unittest.mock import MagicMock, patch

import pytest
import yaml

import post_refresh_verify


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
    def test_step_written_to_progress_json(self, tmp_path, monkeypatch):
        monkeypatch.setattr(post_refresh_verify, "REPORTS_ROOT", tmp_path / "refresh_state")

        post_refresh_verify.record_step("3d", "python", "knowledge_refresh")

        p = tmp_path / "refresh_state" / "3d" / "python" / "progress.json"
        assert p.exists()
        data = json.loads(p.read_text())
        assert "knowledge_refresh" in data["steps"]

    def test_duplicate_step_not_added_twice(self, tmp_path, monkeypatch):
        monkeypatch.setattr(post_refresh_verify, "REPORTS_ROOT", tmp_path / "refresh_state")

        post_refresh_verify.record_step("3d", "python", "knowledge_refresh")
        post_refresh_verify.record_step("3d", "python", "knowledge_refresh")

        p = tmp_path / "refresh_state" / "3d" / "python" / "progress.json"
        data = json.loads(p.read_text())
        assert data["steps"].count("knowledge_refresh") == 1

    def test_multiple_steps_all_recorded(self, tmp_path, monkeypatch):
        monkeypatch.setattr(post_refresh_verify, "REPORTS_ROOT", tmp_path / "refresh_state")

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
    def test_stale_since_null_passes(self, tmp_path, monkeypatch):
        monkeypatch.setattr(post_refresh_verify, "KNOWLEDGE_ROOT", tmp_path / "knowledge")
        monkeypatch.setattr(post_refresh_verify, "CONTENT_ROOT", tmp_path / "content")
        _setup_knowledge(tmp_path, "3d", "python", stale_since=None)

        with patch.object(post_refresh_verify, "_HERE", tmp_path / "nonexistent_scripts"):
            passed, failures = post_refresh_verify.verify("3d", "python")

        stale_failures = [f for f in failures if "stale_since" in f]
        assert len(stale_failures) == 0

    def test_stale_since_set_fails(self, tmp_path, monkeypatch):
        monkeypatch.setattr(post_refresh_verify, "KNOWLEDGE_ROOT", tmp_path / "knowledge")
        monkeypatch.setattr(post_refresh_verify, "CONTENT_ROOT", tmp_path / "content")
        _setup_knowledge(tmp_path, "3d", "python", stale_since="2026-04-01")

        with patch.object(post_refresh_verify, "_HERE", tmp_path / "nonexistent_scripts"):
            passed, failures = post_refresh_verify.verify("3d", "python")

        assert any("stale_since" in f for f in failures)


# ---------------------------------------------------------------------------
# verify() — check 2: orphaned claims
# ---------------------------------------------------------------------------

class TestVerifyCheckOrphanedClaims:
    def test_valid_citations_pass(self, tmp_path, monkeypatch):
        monkeypatch.setattr(post_refresh_verify, "KNOWLEDGE_ROOT", tmp_path / "knowledge")
        monkeypatch.setattr(post_refresh_verify, "CONTENT_ROOT", tmp_path / "content")
        monkeypatch.setattr(post_refresh_verify, "REPO_ROOT", tmp_path)

        claims = [{"claim_id": "CL-001"}, {"claim_id": "CL-002"}]
        _setup_knowledge(tmp_path, "3d", "python", claims=claims)

        # Write a content page that cites valid claim IDs
        content_dir = tmp_path / "content" / "docs.aspose.org" / "en" / "3d" / "python"
        content_dir.mkdir(parents=True)
        (content_dir / "page.md").write_text(
            "---\nevidence:\n  claims:\n    - CL-001\n    - CL-002\n---\nbody\n"
        )

        with patch.object(post_refresh_verify, "_HERE", tmp_path / "nonexistent_scripts"):
            passed, failures = post_refresh_verify.verify("3d", "python")

        orphan_failures = [f for f in failures if "Orphaned" in f]
        assert len(orphan_failures) == 0

    def test_orphaned_claim_reported(self, tmp_path, monkeypatch):
        monkeypatch.setattr(post_refresh_verify, "KNOWLEDGE_ROOT", tmp_path / "knowledge")
        monkeypatch.setattr(post_refresh_verify, "CONTENT_ROOT", tmp_path / "content")
        monkeypatch.setattr(post_refresh_verify, "REPO_ROOT", tmp_path)

        claims = [{"claim_id": "CL-001"}]
        _setup_knowledge(tmp_path, "3d", "python", claims=claims)

        content_dir = tmp_path / "content" / "docs.aspose.org" / "en" / "3d" / "python"
        content_dir.mkdir(parents=True)
        # Cites CL-999 which doesn't exist
        (content_dir / "page.md").write_text(
            "---\nevidence:\n  claims:\n    - CL-999\n---\nbody\n"
        )

        with patch.object(post_refresh_verify, "_HERE", tmp_path / "nonexistent_scripts"):
            passed, failures = post_refresh_verify.verify("3d", "python")

        assert any("Orphaned" in f for f in failures)


# ---------------------------------------------------------------------------
# verify() — check 4: stale_detect subprocess (mocked)
# ---------------------------------------------------------------------------

class TestVerifyCheckStaleDetect:
    def test_stale_detect_exit_0_passes(self, tmp_path, monkeypatch):
        monkeypatch.setattr(post_refresh_verify, "KNOWLEDGE_ROOT", tmp_path / "knowledge")
        monkeypatch.setattr(post_refresh_verify, "CONTENT_ROOT", tmp_path / "content")
        _setup_knowledge(tmp_path, "3d", "python")

        # Create fake stale_detect.py so it's found
        stale_detect = tmp_path / "stale_detect.py"
        stale_detect.touch()
        monkeypatch.setattr(post_refresh_verify, "_HERE", tmp_path)

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"stale_pages": 0})

        with patch("post_refresh_verify.subprocess.run", return_value=mock_result):
            passed, failures = post_refresh_verify.verify("3d", "python")

        stale_failures = [f for f in failures if "stale_detect" in f.lower()]
        assert len(stale_failures) == 0

    def test_stale_detect_exit_1_reports_failure(self, tmp_path, monkeypatch):
        monkeypatch.setattr(post_refresh_verify, "KNOWLEDGE_ROOT", tmp_path / "knowledge")
        monkeypatch.setattr(post_refresh_verify, "CONTENT_ROOT", tmp_path / "content")
        _setup_knowledge(tmp_path, "3d", "python")

        stale_detect = tmp_path / "stale_detect.py"
        stale_detect.touch()
        monkeypatch.setattr(post_refresh_verify, "_HERE", tmp_path)

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = json.dumps({"stale_pages": 3, "pages": []})

        with patch("post_refresh_verify.subprocess.run", return_value=mock_result):
            passed, failures = post_refresh_verify.verify("3d", "python")

        assert any("stale_detect" in f.lower() for f in failures)


# ---------------------------------------------------------------------------
# verify() — check 3: stale reference pages (API class absent)
# ---------------------------------------------------------------------------

class TestVerifyCheckStaleReferencePages:
    """Check 3: reference pages for API classes absent from api_surface.json."""

    def test_valid_reference_page_passes(self, tmp_path, monkeypatch):
        """Reference page for a KNOWN class → no failure. Guard: check actually runs."""
        monkeypatch.setattr(post_refresh_verify, "KNOWLEDGE_ROOT", tmp_path / "knowledge")
        monkeypatch.setattr(post_refresh_verify, "CONTENT_ROOT", tmp_path / "content")
        monkeypatch.setattr(post_refresh_verify, "REPO_ROOT", tmp_path)

        _setup_knowledge(tmp_path, "3d", "python",
                         api_surface=[{"name": "PdfDocument"}])

        # Must create ref_dir so ref_root.is_dir() is True (otherwise check silently skips)
        ref_dir = tmp_path / "content" / "reference.aspose.org" / "en" / "3d" / "python"
        ref_dir.mkdir(parents=True)
        (ref_dir / "PdfDocument.md").write_text("---\ntitle: PdfDocument\n---\nbody\n")

        with patch.object(post_refresh_verify, "_HERE", tmp_path / "nonexistent"):
            passed, failures = post_refresh_verify.verify("3d", "python")

        assert not any("Reference page for absent" in f for f in failures)

    def test_orphaned_reference_page_reported(self, tmp_path, monkeypatch):
        """Reference page whose stem is NOT in api_surface.json → failure reported."""
        monkeypatch.setattr(post_refresh_verify, "KNOWLEDGE_ROOT", tmp_path / "knowledge")
        monkeypatch.setattr(post_refresh_verify, "CONTENT_ROOT", tmp_path / "content")
        monkeypatch.setattr(post_refresh_verify, "REPO_ROOT", tmp_path)

        # Non-empty api_surface so valid_api_names ≠ {} (guard passes)
        _setup_knowledge(tmp_path, "3d", "python",
                         api_surface=[{"name": "PdfDocument"}])

        ref_dir = tmp_path / "content" / "reference.aspose.org" / "en" / "3d" / "python"
        ref_dir.mkdir(parents=True)
        # stem "OrphanedClass" → not in {"pdfdocument"} → stale
        (ref_dir / "OrphanedClass.md").write_text("---\ntitle: OrphanedClass\n---\n")

        with patch.object(post_refresh_verify, "_HERE", tmp_path / "nonexistent"):
            passed, failures = post_refresh_verify.verify("3d", "python")

        assert any("Reference page for absent" in f for f in failures)
        assert any("OrphanedClass" in f for f in failures)

    def test_index_page_not_flagged(self, tmp_path, monkeypatch):
        """_index.md is explicitly excluded from stale detection."""
        monkeypatch.setattr(post_refresh_verify, "KNOWLEDGE_ROOT", tmp_path / "knowledge")
        monkeypatch.setattr(post_refresh_verify, "CONTENT_ROOT", tmp_path / "content")
        monkeypatch.setattr(post_refresh_verify, "REPO_ROOT", tmp_path)

        _setup_knowledge(tmp_path, "3d", "python",
                         api_surface=[{"name": "PdfDocument"}])

        ref_dir = tmp_path / "content" / "reference.aspose.org" / "en" / "3d" / "python"
        ref_dir.mkdir(parents=True)
        (ref_dir / "_index.md").write_text("---\ntitle: Reference Index\n---\n")
        (ref_dir / "PdfDocument.md").write_text("---\ntitle: PdfDocument\n---\n")

        with patch.object(post_refresh_verify, "_HERE", tmp_path / "nonexistent"):
            passed, failures = post_refresh_verify.verify("3d", "python")

        assert not any("Reference page for absent" in f for f in failures)

    def test_empty_api_surface_skips_check(self, tmp_path, monkeypatch):
        """When api_surface.json has no classes, check 3 is silently skipped.
        Documents the guard: valid_api_names must be non-empty for check to run."""
        monkeypatch.setattr(post_refresh_verify, "KNOWLEDGE_ROOT", tmp_path / "knowledge")
        monkeypatch.setattr(post_refresh_verify, "CONTENT_ROOT", tmp_path / "content")
        monkeypatch.setattr(post_refresh_verify, "REPO_ROOT", tmp_path)

        # Empty api_surface → valid_api_names = set() → guard short-circuits
        _setup_knowledge(tmp_path, "3d", "python", api_surface=[])

        ref_dir = tmp_path / "content" / "reference.aspose.org" / "en" / "3d" / "python"
        ref_dir.mkdir(parents=True)
        (ref_dir / "SomeClass.md").write_text("---\ntitle: SomeClass\n---\n")

        with patch.object(post_refresh_verify, "_HERE", tmp_path / "nonexistent"):
            passed, failures = post_refresh_verify.verify("3d", "python")

        # No "Reference page for absent" failures — check was skipped
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

    def test_check6_fail_when_decisions_absent(self, tmp_path, monkeypatch):
        """Check 6 FAIL when page_decisions.json does not exist."""
        monkeypatch.setattr(post_refresh_verify, "CONTENT_ROOT", tmp_path / "content")
        monkeypatch.setattr(post_refresh_verify, "REPO_ROOT", tmp_path)

        # Create a content page so there's something to check
        d = tmp_path / "content" / "docs.aspose.org" / "en" / "cells" / "net"
        self._write_page(d, "page.md")

        passed, failures = post_refresh_verify.check_coverage_completeness(
            "cells", "net", review_root=tmp_path / "review"
        )

        assert not passed
        assert any("page_decisions.json not found" in f for f in failures)

    def test_check6_fail_when_page_missing_from_decisions(self, tmp_path, monkeypatch):
        """Check 6 FAIL when a discovered page is absent from page_decisions.json."""
        monkeypatch.setattr(post_refresh_verify, "CONTENT_ROOT", tmp_path / "content")
        monkeypatch.setattr(post_refresh_verify, "REPO_ROOT", tmp_path)

        d = tmp_path / "content" / "docs.aspose.org" / "en" / "cells" / "net"
        self._write_page(d, "page1.md")
        self._write_page(d, "page2.md")  # this one won't be in decisions

        # Only record page1 — page2 is missing
        self._write_decisions(
            tmp_path / "review", "cells", "net",
            ["content/docs.aspose.org/en/cells/net/page1.md"]
        )

        passed, failures = post_refresh_verify.check_coverage_completeness(
            "cells", "net", review_root=tmp_path / "review"
        )

        assert not passed
        assert any("Missing" in f and "page2.md" in f for f in failures)

    def test_check6_pass_with_full_coverage(self, tmp_path, monkeypatch):
        """Check 6 PASS when page_decisions.json covers all discovered files."""
        monkeypatch.setattr(post_refresh_verify, "CONTENT_ROOT", tmp_path / "content")
        monkeypatch.setattr(post_refresh_verify, "REPO_ROOT", tmp_path)

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

    def test_check6_pass_no_content_pages(self, tmp_path, monkeypatch):
        """Check 6 PASS when no content pages are discovered (product not generated yet)."""
        monkeypatch.setattr(post_refresh_verify, "CONTENT_ROOT", tmp_path / "content")
        monkeypatch.setattr(post_refresh_verify, "REPO_ROOT", tmp_path)

        # No content pages exist; decisions file also absent — should pass (no content to cover)
        passed, failures = post_refresh_verify.check_coverage_completeness(
            "cells", "net", review_root=tmp_path / "review"
        )

        assert passed

    def test_check6_skips_locale_files(self, tmp_path, monkeypatch):
        """Check 6 does not require locale (translation) files in page_decisions.json."""
        monkeypatch.setattr(post_refresh_verify, "CONTENT_ROOT", tmp_path / "content")
        monkeypatch.setattr(post_refresh_verify, "REPO_ROOT", tmp_path)

        d = tmp_path / "content" / "docs.aspose.org" / "en" / "cells" / "net"
        self._write_page(d, "page.md")
        # Locale file — must be excluded from coverage requirement
        (d / "page.fr.md").write_text("---\ntitle: page fr\n---\nbody\n", encoding="utf-8")

        self._write_decisions(
            tmp_path / "review", "cells", "net",
            ["content/docs.aspose.org/en/cells/net/page.md"]  # only English file
        )

        passed, failures = post_refresh_verify.check_coverage_completeness(
            "cells", "net", review_root=tmp_path / "review"
        )

        assert passed
