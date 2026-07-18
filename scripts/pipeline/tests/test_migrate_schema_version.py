"""Tests for migrate_schema_version.py — ST-035 format-only artifact migration."""
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
    def test_dry_run_reports_would_migrate_without_writing(self, tmp_path):
        p = tmp_path / "reports" / "refresh_state" / "pdf" / "net" / "progress.json"
        _write(p, {"steps": ["page_update"], "pages_updated": ["a.md"]})
        results = msv.migrate_one(tmp_path, "pdf", "net", apply=False)
        progress_result = next(r for r in results if r["kind"] == "progress.json")
        assert progress_result["action"] == "would_migrate"
        data = json.loads(p.read_text(encoding="utf-8"))
        assert "schema_version" not in data, "dry-run must not write anything"

    def test_apply_writes_schema_version_preserving_all_other_fields(self, tmp_path):
        p = tmp_path / "reports" / "refresh_state" / "pdf" / "net" / "progress.json"
        _write(p, {"steps": ["page_update"], "pages_updated": ["a.md"], "last_updated": "2026-01-01"})
        results = msv.migrate_one(tmp_path, "pdf", "net", apply=True)
        progress_result = next(r for r in results if r["kind"] == "progress.json")
        assert progress_result["action"] == "migrated"
        data = json.loads(p.read_text(encoding="utf-8"))
        assert data["schema_version"] == msv._PROGRESS_SCHEMA_VERSION
        # Every pre-existing field must survive untouched -- this is a format
        # migration, not a content regeneration.
        assert data["steps"] == ["page_update"]
        assert data["pages_updated"] == ["a.md"]
        assert data["last_updated"] == "2026-01-01"

    def test_already_current_is_a_no_op(self, tmp_path):
        p = tmp_path / "reports" / "refresh_state" / "pdf" / "net" / "progress.json"
        _write(p, {"schema_version": msv._PROGRESS_SCHEMA_VERSION, "steps": []})
        results = msv.migrate_one(tmp_path, "pdf", "net", apply=True)
        progress_result = next(r for r in results if r["kind"] == "progress.json")
        assert progress_result["action"] == "already_current"

    def test_absent_file_reported_not_error(self, tmp_path):
        results = msv.migrate_one(tmp_path, "pdf", "net", apply=True)
        assert all(r["action"] == "absent" for r in results)

    def test_unreadable_file_reported_not_crashed(self, tmp_path):
        p = tmp_path / "reports" / "refresh_state" / "pdf" / "net" / "progress.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("not valid json {{{", encoding="utf-8")
        results = msv.migrate_one(tmp_path, "pdf", "net", apply=True)
        progress_result = next(r for r in results if r["kind"] == "progress.json")
        assert progress_result["action"] == "unreadable"

    def test_migrates_all_three_artifact_kinds(self, tmp_path):
        _write(tmp_path / "reports" / "refresh_state" / "pdf" / "net" / "progress.json", {})
        _write(tmp_path / "reports" / "refresh_state" / "pdf" / "net" / "execution_reconciliation.json", {})
        _write(tmp_path / "reports" / "refresh_review" / "pdf" / "net" / "page_decisions.json", {})
        results = msv.migrate_one(tmp_path, "pdf", "net", apply=True)
        assert len(results) == 3
        assert all(r["action"] == "migrated" for r in results)


class TestCLI:
    def test_dry_run_exit_0(self, tmp_path, capsys):
        _write(tmp_path / "reports" / "refresh_state" / "pdf" / "net" / "progress.json", {})
        exit_code = msv.main(["--repo-root", str(tmp_path)])
        assert exit_code == 0
        out = capsys.readouterr().out
        assert "DRY-RUN" in out
        assert "would_migrate=1" in out

    def test_apply_exit_0_and_writes(self, tmp_path, capsys):
        p = tmp_path / "reports" / "refresh_state" / "pdf" / "net" / "progress.json"
        _write(p, {})
        exit_code = msv.main(["--apply", "--repo-root", str(tmp_path)])
        assert exit_code == 0
        assert "APPLY" in capsys.readouterr().out
        data = json.loads(p.read_text(encoding="utf-8"))
        assert data["schema_version"] == msv._PROGRESS_SCHEMA_VERSION

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
