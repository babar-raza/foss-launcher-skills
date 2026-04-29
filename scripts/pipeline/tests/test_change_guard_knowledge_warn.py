"""Tests for change_guard knowledge availability WARN (S1-5 fix).

When knowledge artifacts are missing, the guard must emit WARN issues with
check='knowledge_availability' instead of silently passing.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

_PIPELINE_DIR = Path(__file__).resolve().parent.parent
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

import change_guard  # noqa: E402
from commands.knowledge import knowledge_core  # noqa: E402
from change_guard import DECISION_WARN, guard_text  # noqa: E402

_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _build_knowledge_dir(tmp_path, *, include_index: bool = True):
    """Build a fake knowledge dir, optionally omitting index.json."""
    merged = tmp_path / "knowledge" / "fake" / "python" / "merged"
    merged.mkdir(parents=True)

    for fname in (
        "fake_api_surface.json",
        "fake_model.yaml",
        "fake_claims.json",
        "fake_formats.json",
    ):
        dest = fname.replace("fake_", "")
        shutil.copy(_FIXTURES_DIR / fname, merged / dest)

    if include_index:
        shutil.copy(_FIXTURES_DIR / "fake_index.json", merged / "index.json")

    (merged / "install.md").write_text(
        "pip install aspose-fake-foss\n", encoding="utf-8"
    )
    return tmp_path / "knowledge"


class TestMissingForbiddenClaimsProducesWarn:
    """Empty forbidden_claims must produce WARN issue, not silent pass."""

    def test_no_index_file_emits_knowledge_availability_warn(self, tmp_path):
        """When index.json is missing, forbidden_claims is empty -> WARN."""
        knowledge_root = _build_knowledge_dir(tmp_path, include_index=False)

        original_kc = knowledge_core._KNOWLEDGE_ROOT
        change_guard.configure(repo_root=tmp_path)
        knowledge_core._KNOWLEDGE_ROOT = knowledge_root
        try:
            result = guard_text(
                "This is some plain text with no API references.",
                "fake",
                "python",
            )
        finally:
            change_guard.configure()
            knowledge_core._KNOWLEDGE_ROOT = original_kc

        ka_issues = [
            i for i in result["issues"] if i["check"] == "knowledge_availability"
        ]
        assert len(ka_issues) >= 1, "Expected at least one knowledge_availability issue"
        assert any("forbidden_claims" in i["detail"] for i in ka_issues)
        assert result["decision"] == DECISION_WARN

    def test_empty_forbidden_claims_in_index(self, tmp_path):
        """index.json exists but forbidden_claims is [] -> WARN."""
        knowledge_root = _build_knowledge_dir(tmp_path, include_index=True)
        index_path = knowledge_root / "fake" / "python" / "merged" / "index.json"
        data = json.loads(index_path.read_text(encoding="utf-8"))
        data["forbidden_claims"] = []
        index_path.write_text(json.dumps(data), encoding="utf-8")

        original_kc = knowledge_core._KNOWLEDGE_ROOT
        change_guard.configure(repo_root=tmp_path)
        knowledge_core._KNOWLEDGE_ROOT = knowledge_root
        try:
            result = guard_text(
                "This is some plain text with no API references.",
                "fake",
                "python",
            )
        finally:
            change_guard.configure()
            knowledge_core._KNOWLEDGE_ROOT = original_kc

        ka_issues = [
            i for i in result["issues"] if i["check"] == "knowledge_availability"
        ]
        assert any("forbidden_claims" in i["detail"] for i in ka_issues)
        assert result["decision"] == DECISION_WARN


class TestMissingKnowledgeProducesWarn:
    """Knowledge.available=False must produce WARN issue."""

    def test_unavailable_knowledge_emits_warn(self, tmp_path):
        """When knowledge.available is False, WARN is emitted."""
        # Build knowledge dir but without api_surface.json so knowledge.available is False
        merged = tmp_path / "knowledge" / "noapi" / "python" / "merged"
        merged.mkdir(parents=True)
        (merged / "model.yaml").write_text("family: noapi\nplatform: python\n", encoding="utf-8")
        # No api_surface.json -> knowledge.available will be False

        original_kc = knowledge_core._KNOWLEDGE_ROOT
        change_guard.configure(repo_root=tmp_path)
        knowledge_core._KNOWLEDGE_ROOT = tmp_path / "knowledge"
        try:
            result = guard_text(
                "This is some plain text with no API references.",
                "noapi",
                "python",
            )
        finally:
            change_guard.configure()
            knowledge_core._KNOWLEDGE_ROOT = original_kc

        ka_issues = [
            i for i in result["issues"] if i["check"] == "knowledge_availability"
        ]
        assert any("knowledge unavailable" in i["detail"] for i in ka_issues)
        assert result["decision"] == DECISION_WARN

    def test_both_missing_emits_two_warnings(self, tmp_path):
        """Both forbidden_claims empty AND knowledge unavailable -> two WARN issues."""
        merged = tmp_path / "knowledge" / "noapi" / "python" / "merged"
        merged.mkdir(parents=True)
        (merged / "model.yaml").write_text("family: noapi\nplatform: python\n", encoding="utf-8")

        original_kc = knowledge_core._KNOWLEDGE_ROOT
        change_guard.configure(repo_root=tmp_path)
        knowledge_core._KNOWLEDGE_ROOT = tmp_path / "knowledge"
        try:
            result = guard_text(
                "This is some plain text with no API references.",
                "noapi",
                "python",
            )
        finally:
            change_guard.configure()
            knowledge_core._KNOWLEDGE_ROOT = original_kc

        ka_issues = [
            i for i in result["issues"] if i["check"] == "knowledge_availability"
        ]
        assert len(ka_issues) == 2, f"Expected 2 knowledge_availability issues, got {len(ka_issues)}"
        details = [i["detail"] for i in ka_issues]
        assert any("forbidden_claims" in d for d in details)
        assert any("knowledge unavailable" in d for d in details)
        assert result["decision"] == DECISION_WARN
