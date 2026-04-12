"""Tests for plan_check.py — slug validation against site plan.

Coverage:
- slug found in plan → (True, "")
- slug not found → (False, warning msg)
- plan file missing → (True, "") — plan absence is permissive
- bypass=True with missing slug → (True, "plan_bypass")
- malformed YAML → (True, "") — permissive on read error
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import plan_check


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_plan(reports_root: Path, family: str, platform: str, plan_data: dict) -> Path:
    plan_path = reports_root / family / platform / "site_plan.yaml"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(yaml.dump(plan_data), encoding="utf-8")
    return plan_path


def _simple_plan(slugs: list[str]) -> dict:
    return {
        "plan": {
            "sections": {
                "docs": {
                    "pages": [{"slug": s, "path": f"content/docs/3d/python/{s}.md"} for s in slugs]
                }
            }
        }
    }


# ---------------------------------------------------------------------------
# TASK-06 tests
# ---------------------------------------------------------------------------

class TestSlugFound:
    def test_slug_in_plan_returns_true(self, tmp_path, monkeypatch):
        monkeypatch.setattr(plan_check, "REPORTS_ROOT", tmp_path)
        _write_plan(tmp_path, "3d", "python", _simple_plan(["getting-started", "installation"]))

        allowed, msg = plan_check.check_slug_in_plan("3d", "python", "docs", "getting-started")
        assert allowed is True
        assert msg == ""

    def test_slug_matched_by_path_suffix(self, tmp_path, monkeypatch):
        monkeypatch.setattr(plan_check, "REPORTS_ROOT", tmp_path)
        plan_data = {
            "plan": {
                "sections": {
                    "docs": {
                        "pages": [{"slug": "", "path": "content/docs/3d/python/installation.md"}]
                    }
                }
            }
        }
        _write_plan(tmp_path, "3d", "python", plan_data)

        allowed, msg = plan_check.check_slug_in_plan("3d", "python", "docs", "installation")
        assert allowed is True


class TestSlugNotFound:
    def test_slug_absent_returns_false_with_message(self, tmp_path, monkeypatch):
        """Core bug class: slug not in plan → must return False."""
        monkeypatch.setattr(plan_check, "REPORTS_ROOT", tmp_path)
        _write_plan(tmp_path, "3d", "python", _simple_plan(["getting-started"]))

        allowed, msg = plan_check.check_slug_in_plan("3d", "python", "docs", "unknown-page")
        assert allowed is False
        assert "unknown-page" in msg
        assert "PLAN WARNING" in msg

    def test_bypass_overrides_missing_slug(self, tmp_path, monkeypatch):
        """bypass=True must return (True, 'plan_bypass') even when slug absent."""
        monkeypatch.setattr(plan_check, "REPORTS_ROOT", tmp_path)
        _write_plan(tmp_path, "3d", "python", _simple_plan(["getting-started"]))

        allowed, msg = plan_check.check_slug_in_plan(
            "3d", "python", "docs", "unknown-page", bypass=True
        )
        assert allowed is True
        assert msg == "plan_bypass"


class TestPlanMissing:
    def test_no_plan_file_is_permissive(self, tmp_path, monkeypatch):
        """When plan file doesn't exist, allow generation."""
        monkeypatch.setattr(plan_check, "REPORTS_ROOT", tmp_path)
        # no plan file written

        allowed, msg = plan_check.check_slug_in_plan("3d", "python", "docs", "any-slug")
        assert allowed is True
        assert msg == ""


class TestMalformedYAML:
    def test_malformed_yaml_is_permissive(self, tmp_path, monkeypatch):
        monkeypatch.setattr(plan_check, "REPORTS_ROOT", tmp_path)
        plan_path = tmp_path / "3d" / "python" / "site_plan.yaml"
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(": invalid: yaml: [[[", encoding="utf-8")

        allowed, msg = plan_check.check_slug_in_plan("3d", "python", "docs", "any-slug")
        # malformed YAML → permissive (returns True)
        assert allowed is True


class TestSectionVariants:
    def test_empty_section_does_not_crash(self, tmp_path, monkeypatch):
        monkeypatch.setattr(plan_check, "REPORTS_ROOT", tmp_path)
        plan_data = {"plan": {"sections": {"docs": {"pages": []}}}}
        _write_plan(tmp_path, "3d", "python", plan_data)

        allowed, msg = plan_check.check_slug_in_plan("3d", "python", "docs", "any-slug")
        assert allowed is False

    def test_missing_section_key_does_not_crash(self, tmp_path, monkeypatch):
        monkeypatch.setattr(plan_check, "REPORTS_ROOT", tmp_path)
        plan_data = {"plan": {"sections": {}}}
        _write_plan(tmp_path, "3d", "python", plan_data)

        allowed, msg = plan_check.check_slug_in_plan("3d", "python", "kb", "any-slug")
        assert allowed is False
