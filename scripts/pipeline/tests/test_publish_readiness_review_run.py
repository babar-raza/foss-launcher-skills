"""Tests for publish_readiness_review_run.py (RC-W1-006 / TC-BSA-...-06).

Covers the actual confirmed defect: a page can carry a persisted `grade: A` with no
way to tell whether that grade is current relative to the live EVALUATOR_LOGIC_VERSION
-- and even when it IS current, the S-90 rubric never cross-checks truth-audit /
gap-analysis findings before auto-publishing.
"""
from __future__ import annotations

import json

import pytest

from commands.governance import publish_readiness_review_run as prr
from core.markdown import _FRONTMATTER_WRITER_RE as _FM_RE
from grade_writer import content_hash as _content_hash


@pytest.fixture(autouse=True)
def _reset_configure():
    yield
    prr.configure()


def _page_hash(text: str) -> str:
    m = _FM_RE.match(text)
    body = text[m.end():] if m else text
    return _content_hash(body)


def _write_page(tmp_path, rel_path: str, frontmatter_lines: list[str], body: str = "\nSome body text.\n") -> tuple[str, str]:
    """Write a content page under tmp_path and return (rel_path_posix, page_hash)."""
    fm_block = "\n".join(frontmatter_lines)
    text = f"---\n{fm_block}\n---\n{body}"
    full_path = tmp_path / rel_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(text, encoding="utf-8")
    return rel_path.replace("\\", "/"), _page_hash(text)


def _write_json(path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Unit-level: staleness gate
# ---------------------------------------------------------------------------

class TestGradeStatus:
    def test_no_grade_at_all(self):
        status, detail = prr._grade_status({}, None, "somehash")
        assert status == "NO_GRADE"

    def test_no_manifest_entry_and_no_frontmatter_logic_version(self):
        """Reproduces the real words/python Document.md/Table.md case: grade present,
        graded_logic_version absent from frontmatter (expected under ARCH-04), and no
        entry in the external grade manifest either."""
        fm = {"grade": "A"}
        status, detail = prr._grade_status(fm, None, "somehash")
        assert status == "STALE_NO_MANIFEST_ENTRY"

    def test_manifest_entry_with_stale_logic_version(self):
        fm = {"grade": "A"}
        manifest_entry = {"logic_version": "17", "content_hash": "somehash"}
        status, detail = prr._grade_status(fm, manifest_entry, "somehash")
        assert status == "STALE_LOGIC_VERSION"
        assert "17" in detail

    def test_manifest_entry_fresh_logic_version_but_body_changed(self):
        fm = {"grade": "A"}
        manifest_entry = {"logic_version": prr.CURRENT_LOGIC_VERSION, "content_hash": "old-hash"}
        status, detail = prr._grade_status(fm, manifest_entry, "new-hash")
        assert status == "STALE_CONTENT_HASH"

    def test_manifest_entry_fully_fresh(self):
        fm = {"grade": "A"}
        manifest_entry = {"logic_version": prr.CURRENT_LOGIC_VERSION, "content_hash": "matching-hash"}
        status, detail = prr._grade_status(fm, manifest_entry, "matching-hash")
        assert status == "FRESH"

    def test_legacy_frontmatter_logic_version_fresh(self):
        """Pre-ARCH-04 pages may still carry graded_logic_version directly in
        frontmatter -- trust it without needing the manifest."""
        fm = {
            "grade": "A",
            "graded_logic_version": prr.CURRENT_LOGIC_VERSION,
            "graded_content_hash": "matching-hash",
        }
        status, detail = prr._grade_status(fm, None, "matching-hash")
        assert status == "FRESH"

    def test_legacy_frontmatter_logic_version_stale(self):
        fm = {"grade": "A", "graded_logic_version": "1", "graded_content_hash": "h"}
        status, detail = prr._grade_status(fm, None, "h")
        assert status == "STALE_LOGIC_VERSION"


class TestExtractFailCount:
    def test_no_reasons(self):
        assert prr._extract_fail_count([]) == 0
        assert prr._extract_fail_count(None) == 0

    def test_no_findings_reason(self):
        assert prr._extract_fail_count(["No findings -> grade A"]) == 0

    def test_fail_count_parsed(self):
        reasons = ["2 FAIL finding(s) [type_accuracy×2] -> base grade C"]
        assert prr._extract_fail_count(reasons) == 2

    def test_warn_only_not_counted_as_fail(self):
        reasons = ["3 WARN finding(s) [audit] -> base grade B"]
        assert prr._extract_fail_count(reasons) == 0


class TestManifestLookup:
    def test_relative_key_only(self):
        manifest = {"content/a.md": {"logic_version": "18"}}
        entry = prr._lookup_manifest_entry(manifest, "content/a.md", "/abs/content/a.md")
        assert entry == {"logic_version": "18"}

    def test_absolute_key_only(self):
        manifest = {"/abs/content/a.md": {"logic_version": "18"}}
        entry = prr._lookup_manifest_entry(manifest, "content/a.md", "/abs/content/a.md")
        assert entry == {"logic_version": "18"}

    def test_prefers_nonempty_logic_version(self):
        """Reproduces the real dual-key mess seen live in grade_manifest.json: a
        relative-path key with an empty logic_version and an absolute-path key with a
        real one for the same page."""
        manifest = {
            "content/a.md": {"logic_version": "", "evaluated_at": ""},
            "/abs/content/a.md": {"logic_version": "17", "evaluated_at": "2026-06-06T00:00:00Z"},
        }
        entry = prr._lookup_manifest_entry(manifest, "content/a.md", "/abs/content/a.md")
        assert entry["logic_version"] == "17"

    def test_neither_key_present(self):
        assert prr._lookup_manifest_entry({}, "content/a.md", "/abs/content/a.md") is None


class TestSeverityIsHigh:
    @pytest.mark.parametrize("sev", ["M", "S", "medium", "severe"])
    def test_high(self, sev):
        assert prr._severity_is_high(sev) is True

    @pytest.mark.parametrize("sev", ["low", "L", "", None])
    def test_not_high(self, sev):
        assert prr._severity_is_high(sev) is False


class TestCrossCheck:
    def test_unsupported_verdict_open_is_a_hit(self):
        truth = {"p.md": [{"verdict": "UNSUPPORTED", "severity": "S", "status": "open"}]}
        hits = prr._cross_check("p.md", truth, {})
        assert len(hits) == 1
        assert hits[0]["source"] == "truth-audit"
        assert hits[0]["severe"] is False

    def test_fabricated_is_severe(self):
        truth = {"p.md": [{"verdict": "FABRICATED", "severity": "S", "status": "open"}]}
        hits = prr._cross_check("p.md", truth, {})
        assert hits[0]["severe"] is True

    def test_fixed_status_excluded(self):
        truth = {"p.md": [{"verdict": "UNSUPPORTED", "severity": "S", "status": "fixed"}]}
        assert prr._cross_check("p.md", truth, {}) == []

    def test_low_severity_verified_verdict_excluded(self):
        truth = {"p.md": [{"verdict": "VERIFIED", "severity": "", "status": "open"}]}
        assert prr._cross_check("p.md", truth, {}) == []

    def test_gap_analysis_medium_severity_open_is_a_hit(self):
        gap = {"p.md": [{"type": "wrong-package", "severity": "M", "status": "open"}]}
        hits = prr._cross_check("p.md", {}, gap)
        assert len(hits) == 1
        assert hits[0]["source"] == "gap-analysis"

    def test_gap_analysis_low_severity_excluded(self):
        gap = {"p.md": [{"type": "missing-page", "severity": "low", "status": "open"}]}
        assert prr._cross_check("p.md", {}, gap) == []


# ---------------------------------------------------------------------------
# End-to-end: review_product()
# ---------------------------------------------------------------------------

class TestReviewProductEndToEnd:
    def test_fresh_grade_clean_cross_check_is_publish(self, tmp_path):
        rel, h = _write_page(
            tmp_path,
            "content/reference.aspose.org/en/testfam/testplat/PageA.md",
            [
                "title: PageA",
                "grade: A",
                'grade_reasons:',
                '  - "No findings -> grade A"',
                "evidence:",
                "  apis:",
                "    - SomeClass",
            ],
        )
        manifest = {rel: {
            "logic_version": prr.CURRENT_LOGIC_VERSION,
            "content_hash": h,
            "grade": "A",
            "grade_reasons": ["No findings -> grade A"],
        }}
        _write_json(tmp_path / "reports" / "grade_manifest.json", manifest)

        prr.configure(repo_root=tmp_path)
        report = prr.review_product("testfam", "testplat", dry_run=True)

        assert report.total_pages == 1
        result = report.results[0]
        assert result.grade_status == "FRESH"
        assert result.disposition == "PUBLISH"

    def test_missing_graded_logic_version_never_publishes(self, tmp_path):
        """Reproduces the real defect: words/python Document.md/Table.md carry
        grade: A with NO graded_logic_version anywhere (frontmatter or manifest).
        Must NOT classify PUBLISH regardless of the stored grade letter."""
        rel, h = _write_page(
            tmp_path,
            "content/reference.aspose.org/en/words/python/Document.md",
            [
                "title: Document",
                "grade: A",
                'grade_reasons:',
                '  - "No findings -> grade A"',
            ],
        )
        # No grade_manifest.json at all -- exhaustive-search-confirmed real state.
        prr.configure(repo_root=tmp_path)
        report = prr.review_product("words", "python", dry_run=True)

        assert report.total_pages == 1
        result = report.results[0]
        assert result.grade_status == "STALE_NO_MANIFEST_ENTRY"
        assert result.disposition != "PUBLISH"
        assert result.grade == "A"  # stored grade is still surfaced, just not trusted

    def test_fresh_grade_with_live_unsupported_finding_not_publish(self, tmp_path):
        rel, h = _write_page(
            tmp_path,
            "content/reference.aspose.org/en/testfam/testplat/PageC.md",
            [
                "title: PageC",
                "grade: A",
                'grade_reasons:',
                '  - "No findings -> grade A"',
                "evidence:",
                "  apis:",
                "    - SomeClass",
            ],
        )
        manifest = {rel: {
            "logic_version": prr.CURRENT_LOGIC_VERSION,
            "content_hash": h,
            "grade": "A",
            "grade_reasons": ["No findings -> grade A"],
        }}
        _write_json(tmp_path / "reports" / "grade_manifest.json", manifest)
        _write_json(tmp_path / "reports" / "truth-audit" / "testfam-testplat-20260809.json", {
            "findings": [
                {
                    "id": "F-1",
                    "file": rel,
                    "verdict": "UNSUPPORTED",
                    "severity": "S",
                    "status": "open",
                    "description": "unsupported claim",
                }
            ]
        })

        prr.configure(repo_root=tmp_path)
        report = prr.review_product("testfam", "testplat", dry_run=True)

        assert report.total_pages == 1
        result = report.results[0]
        assert result.grade_status == "FRESH"
        assert result.disposition in ("CONDITIONAL", "BLOCKED")
        assert result.disposition != "PUBLISH"
        assert len(result.cross_check_hits) == 1

    def test_fresh_grade_with_live_fabricated_finding_is_blocked(self, tmp_path):
        rel, h = _write_page(
            tmp_path,
            "content/reference.aspose.org/en/testfam/testplat/PageD.md",
            [
                "title: PageD",
                "grade: A",
                'grade_reasons:',
                '  - "No findings -> grade A"',
                "evidence:",
                "  apis:",
                "    - SomeClass",
            ],
        )
        manifest = {rel: {
            "logic_version": prr.CURRENT_LOGIC_VERSION,
            "content_hash": h,
            "grade": "A",
            "grade_reasons": ["No findings -> grade A"],
        }}
        _write_json(tmp_path / "reports" / "grade_manifest.json", manifest)
        _write_json(tmp_path / "reports" / "truth-audit" / "testfam-testplat-20260809.json", {
            "findings": [
                {"id": "F-1", "file": rel, "verdict": "FABRICATED", "severity": "S", "status": "open"}
            ]
        })

        prr.configure(repo_root=tmp_path)
        report = prr.review_product("testfam", "testplat", dry_run=True)
        result = report.results[0]
        assert result.disposition == "BLOCKED"

    def test_draft_page_is_skipped(self, tmp_path):
        _write_page(
            tmp_path,
            "content/docs.aspose.org/en/testfam/testplat/draft-page.md",
            ["title: Draft", "grade: A", "draft: true"],
        )
        prr.configure(repo_root=tmp_path)
        report = prr.review_product("testfam", "testplat", dry_run=True)
        assert report.total_pages == 1
        assert report.results[0].disposition == "SKIP"

    def test_latest_report_picked_by_name_when_multiple_dated_reports_exist(self, tmp_path):
        rel, h = _write_page(
            tmp_path,
            "content/reference.aspose.org/en/testfam/testplat/PageE.md",
            [
                "title: PageE",
                "grade: A",
                'grade_reasons:',
                '  - "No findings -> grade A"',
                "evidence:",
                "  apis:",
                "    - SomeClass",
            ],
        )
        manifest = {rel: {
            "logic_version": prr.CURRENT_LOGIC_VERSION,
            "content_hash": h,
            "grade": "A",
            "grade_reasons": ["No findings -> grade A"],
        }}
        _write_json(tmp_path / "reports" / "grade_manifest.json", manifest)
        # Older report has a disqualifying finding; newer (higher date) report is clean.
        _write_json(tmp_path / "reports" / "truth-audit" / "testfam-testplat-20260101.json", {
            "findings": [{"id": "F-old", "file": rel, "verdict": "FABRICATED", "severity": "S", "status": "open"}]
        })
        _write_json(tmp_path / "reports" / "truth-audit" / "testfam-testplat-20260809.json", {
            "findings": []
        })

        prr.configure(repo_root=tmp_path)
        report = prr.review_product("testfam", "testplat", dry_run=True)
        assert report.truth_audit_report.endswith("20260809.json")
        assert report.results[0].disposition == "PUBLISH"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

class TestCLI:
    def test_dry_run_does_not_write_manifest(self, tmp_path, capsys):
        _write_page(
            tmp_path,
            "content/reference.aspose.org/en/testfam/testplat/PageF.md",
            ["title: PageF", "grade: A"],
        )
        prr.configure(repo_root=tmp_path)
        rc = prr.main(["testfam", "testplat", "--dry-run"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "PUBLISH READINESS REVIEW" in out
        assert not (tmp_path / "reports" / "publish-review").exists()

    def test_non_dry_run_writes_manifest(self, tmp_path, capsys):
        _write_page(
            tmp_path,
            "content/reference.aspose.org/en/testfam/testplat/PageG.md",
            ["title: PageG", "grade: A"],
        )
        prr.configure(repo_root=tmp_path)
        rc = prr.main(["testfam", "testplat"])
        assert rc == 0
        manifests = list((tmp_path / "reports" / "publish-review").rglob("inspection-manifest.json"))
        assert len(manifests) == 1
        data = json.loads(manifests[0].read_text(encoding="utf-8"))
        assert data["family"] == "testfam"
        assert data["platform"] == "testplat"
        assert data["total_pages"] == 1

    def test_json_format_output(self, tmp_path, capsys):
        _write_page(
            tmp_path,
            "content/reference.aspose.org/en/testfam/testplat/PageH.md",
            ["title: PageH", "grade: A"],
        )
        prr.configure(repo_root=tmp_path)
        rc = prr.main(["testfam", "testplat", "--dry-run", "--format", "json"])
        assert rc == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["family"] == "testfam"
        assert data["total_pages"] == 1
        assert data["pages"][0]["disposition"] != "PUBLISH"  # stale grade, no manifest entry
