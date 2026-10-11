"""Tests for content_coverage_audit.py — cumulative, delta-independent
detection of api_surface.json classes with no reference page.

Found live 2026-08-24 (mission-plan-the-end-to-end-vast-hejlsberg.md,
deep-reassessment pass): knowledge_delta.json is cycle-scoped, so a real
knowledge advance whose content generation was skipped for one cycle becomes
invisible to every later cycle's delta. This detector performs a direct,
cumulative comparison instead, reusing batch_reference.py's own dry-run
(the single source of truth for "what would batch_reference actually
generate") rather than re-implementing candidate-selection logic.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

PIPELINE_DIR = Path(__file__).resolve().parent.parent
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))
DIAG_DIR = PIPELINE_DIR / "commands" / "diagnostics"
if str(DIAG_DIR) not in sys.path:
    sys.path.insert(0, str(DIAG_DIR))

# Qualified import, matching content_coverage_audit.py's own
# "from commands.content import batch_reference" -- a bare "import
# batch_reference" here would resolve to a SEPARATE module object with its
# own KNOWLEDGE_ROOT/CONTENT_ROOT globals, so configure() calls made through
# it would never actually affect what content_coverage_audit.scan_product()
# sees (the exact module-identity collision found and fixed in Task 16).
from commands.content import batch_reference as _br
import content_coverage_audit as cca


@pytest.fixture(autouse=True)
def reset_batch_reference_config():
    yield
    _br.configure()


def _write_fixture(tmp_path: Path, entries: list[dict], existing_pages: list[str]) -> None:
    merged = tmp_path / "knowledge" / "fake" / "python" / "merged"
    merged.mkdir(parents=True)
    (merged / "api_surface.json").write_text(json.dumps(entries), encoding="utf-8")
    (merged / "model.yaml").write_text(
        yaml.safe_dump({"stale_since": None, "version": "1.0.0", "repo_sha": "test-fixture-sha"}),
    )
    page_dir = tmp_path / "content" / "reference.aspose.org" / "en" / "fake" / "python"
    page_dir.mkdir(parents=True)
    for name in existing_pages:
        (page_dir / f"{name}.md").write_text(
            f"---\nauto_updatable: true\n---\n# {name}\n", encoding="utf-8"
        )
    _br.configure(repo_root=tmp_path)


class TestScanProduct:
    def test_missing_pages_reported_by_name(self, tmp_path):
        entries = [
            {"name": "Alpha", "kind": "class_definition", "methods": [], "properties": []},
            {"name": "Beta", "kind": "class_definition", "methods": [], "properties": []},
            {"name": "Gamma", "kind": "class_definition", "methods": [], "properties": []},
        ]
        _write_fixture(tmp_path, entries, existing_pages=["Alpha"])

        report = cca.scan_product("fake", "python")

        assert report["missing_page_count"] == 2
        assert report["existing_page_count"] == 1
        assert report["total_candidates"] == 3
        assert sorted(report["missing_classes"]) == ["Beta", "Gamma"]

    def test_full_coverage_reports_zero_missing(self, tmp_path):
        entries = [
            {"name": "Alpha", "kind": "class_definition", "methods": [], "properties": []},
        ]
        _write_fixture(tmp_path, entries, existing_pages=["Alpha"])

        report = cca.scan_product("fake", "python")

        assert report["missing_page_count"] == 0
        assert report["missing_classes"] == []

    def test_never_writes_content(self, tmp_path):
        """The audit is detection-only -- batch_reference.run() must be
        called with dry_run=True, never generating a real page."""
        entries = [
            {"name": "Alpha", "kind": "class_definition", "methods": [], "properties": []},
        ]
        _write_fixture(tmp_path, entries, existing_pages=[])

        cca.scan_product("fake", "python")

        page_dir = tmp_path / "content" / "reference.aspose.org" / "en" / "fake" / "python"
        assert not (page_dir / "Alpha.md").exists()

    def test_delta_independent_finds_gap_even_with_empty_knowledge_delta(self, tmp_path):
        """The core regression this detector exists to close: a class fully
        present in api_surface.json but missing a page must be found
        regardless of what knowledge_delta.json says (or whether it exists
        at all) -- unlike page_impact_assess.py/semantic_diff.py, which are
        delta-scoped by design."""
        entries = [
            {"name": "OldNewsClass", "kind": "class_definition", "methods": [], "properties": []},
        ]
        _write_fixture(tmp_path, entries, existing_pages=[])
        # No knowledge_delta.json written at all -- simulates the exact
        # real-world scenario found live: the class was added in an EARLIER
        # cycle whose delta has since rotated to .prev.json or been
        # overwritten by a later, unrelated (empty) delta.
        merged = tmp_path / "knowledge" / "fake" / "python" / "merged"
        assert not (merged / "knowledge_delta.json").exists()

        report = cca.scan_product("fake", "python")
        assert report["missing_classes"] == ["OldNewsClass"]


class TestWriteReport:
    def test_report_written_to_expected_path(self, tmp_path):
        entries = [{"name": "Alpha", "kind": "class_definition", "methods": [], "properties": []}]
        _write_fixture(tmp_path, entries, existing_pages=[])
        report = cca.scan_product("fake", "python")

        report_root = tmp_path / "reports" / "content_coverage"
        path = cca.write_report(report, report_root=report_root)

        assert path == report_root / "fake-python.json"
        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert loaded["missing_classes"] == ["Alpha"]


class TestCLI:
    def test_cli_exit_code_reflects_missing_pages(self, tmp_path, monkeypatch):
        entries = [{"name": "Alpha", "kind": "class_definition", "methods": [], "properties": []}]
        _write_fixture(tmp_path, entries, existing_pages=[])
        monkeypatch.chdir(tmp_path)

        exit_code = cca.main(["fake", "python", "--json"])
        assert exit_code == 1

    def test_cli_exit_code_zero_when_fully_covered(self, tmp_path, monkeypatch):
        entries = [{"name": "Alpha", "kind": "class_definition", "methods": [], "properties": []}]
        _write_fixture(tmp_path, entries, existing_pages=["Alpha"])
        monkeypatch.chdir(tmp_path)

        exit_code = cca.main(["fake", "python", "--json"])
        assert exit_code == 0
