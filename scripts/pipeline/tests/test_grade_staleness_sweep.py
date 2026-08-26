"""Tests for grade_staleness_sweep.py -- Phase C (MT037-2026-08-24-FOSS-
PORTFOLIO-FORENSIC-HEAL blind-spot audit, A-09 repair).

Uses the module's own configure() seam (repo_root, audit_files_fn) rather
than monkeypatching internals directly -- see AGENTS.md 16's tiered
monkeypatch policy. A recording fake stands in for audit_files() (its own
behavior is covered by audit.runner's own test suite); this module's tests
isolate only its own new logic: which manifest entries are eligible, and
what happens to stale/clean/previously-stale pages after a sweep.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_PIPELINE_ROOT = Path(__file__).resolve().parent.parent
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_GOV_DIR = str(_PIPELINE_ROOT / "commands" / "governance")
if _GOV_DIR not in sys.path:
    sys.path.insert(0, _GOV_DIR)

from grade_manifest import write_manifest_entry, load_manifest, mark_stale  # noqa: E402
import grade_staleness_sweep as sweep_mod  # noqa: E402


def _fake_finding(filepath: str, level: str = "FAIL", message: str = "some defect"):
    return SimpleNamespace(level=level, filepath=filepath, line_no=1, message=message, suggestion="")


class _FakeAuditFiles:
    """Records the paths it is called with; returns a fixed findings list."""

    def __init__(self, findings=None):
        self._findings = findings or []
        self.calls: list[list[Path]] = []

    def __call__(self, paths, **kwargs):
        self.calls.append(list(paths))
        return self._findings


@pytest.fixture(autouse=True)
def _isolate_repo_root(tmp_path):
    """Redirect the sweep's notion of repo root to a scratch dir with real
    on-disk stub files (audit_files itself is faked via configure(), but the
    sweep's own candidate-filtering checks real_path.is_file() before
    including a page)."""
    sweep_mod.configure(repo_root=tmp_path)
    yield
    sweep_mod.configure(repo_root=None, audit_files_fn=None)


def _touch(tmp_path: Path, rel: str) -> None:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("stub", encoding="utf-8")


class TestCandidateFiltering:
    def test_only_a_and_b_grades_are_eligible(self, tmp_path):
        mp = tmp_path / "manifest.json"
        for rel, grade in [
            ("content/docs.aspose.org/en/tex/python/a.md", "A"),
            ("content/docs.aspose.org/en/tex/python/b.md", "B"),
            ("content/docs.aspose.org/en/tex/python/c.md", "C"),
            ("content/docs.aspose.org/en/tex/python/f.md", "F"),
        ]:
            _touch(tmp_path, rel)
            write_manifest_entry(rel, content_hash="x" * 32, grade=grade, manifest_path=mp)

        fake = _FakeAuditFiles([])
        sweep_mod.configure(audit_files_fn=fake)
        sweep_mod.sweep(manifest_path=mp)

        checked_paths = {str(p) for p in fake.calls[0]}
        assert any("a.md" in p for p in checked_paths)
        assert any("b.md" in p for p in checked_paths)
        assert not any("c.md" in p for p in checked_paths)
        assert not any("f.md" in p for p in checked_paths)

    def test_family_scoping(self, tmp_path):
        mp = tmp_path / "manifest.json"
        for rel in [
            "content/docs.aspose.org/en/tex/python/a.md",
            "content/docs.aspose.org/en/barcode/python/b.md",
        ]:
            _touch(tmp_path, rel)
            write_manifest_entry(rel, content_hash="x" * 32, grade="A", manifest_path=mp)

        fake = _FakeAuditFiles([])
        sweep_mod.configure(audit_files_fn=fake)
        sweep_mod.sweep(family="tex", manifest_path=mp)

        checked_paths = {str(p) for p in fake.calls[0]}
        assert any("tex" in p for p in checked_paths)
        assert not any("barcode" in p for p in checked_paths)

    def test_missing_file_on_disk_is_skipped(self, tmp_path):
        """A stale manifest entry for a since-deleted page must not crash the sweep."""
        mp = tmp_path / "manifest.json"
        write_manifest_entry("content/docs.aspose.org/en/tex/python/gone.md", content_hash="x" * 32, grade="A", manifest_path=mp)
        # deliberately do NOT touch the file on disk

        fake = _FakeAuditFiles([])
        sweep_mod.configure(audit_files_fn=fake)
        result = sweep_mod.sweep(manifest_path=mp)

        assert fake.calls == []  # zero real candidates -- no wasted work
        assert result["pages_checked"] == 0


class TestStalenessDispatch:
    def test_live_fail_marks_page_stale(self, tmp_path):
        mp = tmp_path / "manifest.json"
        rel = "content/docs.aspose.org/en/tex/python/a.md"
        _touch(tmp_path, rel)
        write_manifest_entry(rel, content_hash="x" * 32, grade="A", manifest_path=mp)

        sweep_mod.configure(audit_files_fn=_FakeAuditFiles([_fake_finding(rel)]))
        result = sweep_mod.sweep(manifest_path=mp)

        assert len(result["newly_flagged_stale"]) == 1
        assert result["newly_flagged_stale"][0]["file"] == rel
        entry = load_manifest(mp)[rel]
        assert entry["stale"] is True
        assert "audit.py FAIL" in entry["stale_reason"]

    def test_clean_page_is_not_flagged(self, tmp_path):
        mp = tmp_path / "manifest.json"
        rel = "content/docs.aspose.org/en/tex/python/a.md"
        _touch(tmp_path, rel)
        write_manifest_entry(rel, content_hash="x" * 32, grade="A", manifest_path=mp)

        sweep_mod.configure(audit_files_fn=_FakeAuditFiles([]))
        result = sweep_mod.sweep(manifest_path=mp)

        assert result["newly_flagged_stale"] == []
        assert result["clean"] == 1
        assert load_manifest(mp)[rel]["stale"] is False

    def test_previously_stale_now_clean_gets_cleared(self, tmp_path):
        mp = tmp_path / "manifest.json"
        rel = "content/docs.aspose.org/en/tex/python/a.md"
        _touch(tmp_path, rel)
        write_manifest_entry(rel, content_hash="x" * 32, grade="A", manifest_path=mp)
        mark_stale(rel, "old reason", manifest_path=mp)

        sweep_mod.configure(audit_files_fn=_FakeAuditFiles([]))
        result = sweep_mod.sweep(manifest_path=mp)

        assert result["cleared_stale"] == [rel]
        assert load_manifest(mp)[rel]["stale"] is False

    def test_dry_run_does_not_write_manifest(self, tmp_path):
        mp = tmp_path / "manifest.json"
        rel = "content/docs.aspose.org/en/tex/python/a.md"
        _touch(tmp_path, rel)
        write_manifest_entry(rel, content_hash="x" * 32, grade="A", manifest_path=mp)

        sweep_mod.configure(audit_files_fn=_FakeAuditFiles([_fake_finding(rel)]))
        result = sweep_mod.sweep(manifest_path=mp, dry_run=True)

        assert len(result["newly_flagged_stale"]) == 1  # reported...
        assert load_manifest(mp)[rel]["stale"] is False  # ...but not written

    def test_no_findings_module_import_never_auto_corrects_grade(self, tmp_path):
        """The sweep must never touch the grade/grade_reasons fields -- only
        stale/stale_reason/stale_marked_at. This is a hard safety property:
        a possibly-buggy check must never silently rewrite a page's grade."""
        mp = tmp_path / "manifest.json"
        rel = "content/docs.aspose.org/en/tex/python/a.md"
        _touch(tmp_path, rel)
        write_manifest_entry(rel, content_hash="x" * 32, grade="A", grade_reasons=["No findings -> grade A"], manifest_path=mp)

        sweep_mod.configure(audit_files_fn=_FakeAuditFiles([_fake_finding(rel)]))
        sweep_mod.sweep(manifest_path=mp)

        entry = load_manifest(mp)[rel]
        assert entry["grade"] == "A"
        assert entry["grade_reasons"] == ["No findings -> grade A"]
