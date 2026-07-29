"""Tests for legacy refresh-artifact forensic containment."""
from __future__ import annotations

import json

import migrate_schema_version as msv


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


class TestDiscoverProducts:
    def test_finds_products_from_any_artifact_kind(self, tmp_path):
        _write(tmp_path / "reports" / "refresh_state" / "pdf" / "net" / "progress.json", {})
        _write(tmp_path / "reports" / "refresh_review" / "cells" / "java" / "page_decisions.json", {})
        products = msv._discover_products(tmp_path)
        assert set(products) == {("pdf", "net"), ("cells", "java")}

    def test_empty_repo_finds_nothing(self, tmp_path):
        assert msv._discover_products(tmp_path) == []


class TestMigrateOne:
    def test_inventory_reports_legacy_unbound_without_writing(self, tmp_path):
        p = tmp_path / "reports" / "refresh_state" / "pdf" / "net" / "progress.json"
        _write(p, {"steps": ["page_update"], "pages_updated": ["a.md"]})
        results = msv.migrate_one(tmp_path, "pdf", "net", apply=False)
        progress_result = next(r for r in results if r["kind"] == "progress.json")
        assert progress_result["action"] == "legacy_unbound"
        data = json.loads(p.read_text(encoding="utf-8"))
        assert "schema_version" not in data, "dry-run must not write anything"

    def test_apply_is_disabled_and_preserves_file(self, tmp_path):
        p = tmp_path / "reports" / "refresh_state" / "pdf" / "net" / "progress.json"
        _write(p, {"steps": ["page_update"], "pages_updated": ["a.md"], "last_updated": "2026-01-01"})
        try:
            msv.migrate_one(tmp_path, "pdf", "net", apply=True)
        except ValueError as exc:
            assert "disabled" in str(exc)
        else:
            raise AssertionError("legacy apply unexpectedly succeeded")
        data = json.loads(p.read_text(encoding="utf-8"))
        assert "schema_version" not in data
        assert data["steps"] == ["page_update"]
        assert data["pages_updated"] == ["a.md"]
        assert data["last_updated"] == "2026-01-01"

    def test_schema_stamped_file_is_still_legacy_unbound(self, tmp_path):
        p = tmp_path / "reports" / "refresh_state" / "pdf" / "net" / "progress.json"
        _write(p, {"schema_version": msv._PROGRESS_SCHEMA_VERSION, "steps": []})
        results = msv.migrate_one(tmp_path, "pdf", "net", apply=False)
        progress_result = next(r for r in results if r["kind"] == "progress.json")
        assert progress_result["action"] == "legacy_unbound"

    def test_absent_file_reported_not_error(self, tmp_path):
        results = msv.migrate_one(tmp_path, "pdf", "net", apply=False)
        assert all(r["action"] == "absent" for r in results)

    def test_unreadable_file_reported_not_crashed(self, tmp_path):
        p = tmp_path / "reports" / "refresh_state" / "pdf" / "net" / "progress.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("not valid json {{{", encoding="utf-8")
        results = msv.migrate_one(tmp_path, "pdf", "net", apply=False)
        progress_result = next(r for r in results if r["kind"] == "progress.json")
        assert progress_result["action"] == "unreadable"

    def test_classifies_all_three_artifact_kinds(self, tmp_path):
        _write(tmp_path / "reports" / "refresh_state" / "pdf" / "net" / "progress.json", {})
        _write(tmp_path / "reports" / "refresh_state" / "pdf" / "net" / "execution_reconciliation.json", {})
        _write(tmp_path / "reports" / "refresh_review" / "pdf" / "net" / "page_decisions.json", {})
        results = msv.migrate_one(tmp_path, "pdf", "net", apply=False)
        assert len(results) == 3
        assert all(r["action"] == "legacy_unbound" for r in results)


class TestCLI:
    def test_dry_run_exit_0(self, tmp_path, capsys):
        _write(tmp_path / "reports" / "refresh_state" / "pdf" / "net" / "progress.json", {})
        exit_code = msv.main(["--repo-root", str(tmp_path)])
        assert exit_code == 0
        out = capsys.readouterr().out
        assert "FORENSIC-ONLY" in out
        assert "legacy_unbound=1" in out

    def test_apply_exit_2_and_does_not_write(self, tmp_path, capsys):
        p = tmp_path / "reports" / "refresh_state" / "pdf" / "net" / "progress.json"
        _write(p, {})
        exit_code = msv.main(["--apply", "--repo-root", str(tmp_path)])
        assert exit_code == 2
        assert "--apply is disabled" in capsys.readouterr().err
        data = json.loads(p.read_text(encoding="utf-8"))
        assert "schema_version" not in data

    def test_single_product_scoping(self, tmp_path, capsys):
        _write(tmp_path / "reports" / "refresh_state" / "pdf" / "net" / "progress.json", {})
        _write(tmp_path / "reports" / "refresh_state" / "cells" / "java" / "progress.json", {})
        exit_code = msv.main(["--repo-root", str(tmp_path), "--family", "pdf", "--platform", "net"])
        assert exit_code == 0
        out = capsys.readouterr().out
        assert "1 product(s)" in out

    def test_family_without_platform_errors(self, tmp_path, capsys):
        exit_code = msv.main(["--repo-root", str(tmp_path), "--family", "pdf"])
        assert exit_code == 2

    def test_no_products_found_is_clean_exit_0(self, tmp_path, capsys):
        exit_code = msv.main(["--repo-root", str(tmp_path)])
        assert exit_code == 0
