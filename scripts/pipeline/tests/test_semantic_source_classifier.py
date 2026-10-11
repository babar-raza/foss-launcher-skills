"""Tests for semantic_source_classifier.py (Lane 4A)."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_PIPELINE_DIR = Path(__file__).resolve().parents[1]
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

from commands.ops.semantic_source_classifier import (
    _aggregate_impact,
    _classify_file,
    classify,
)


# ---------------------------------------------------------------------------
# Unit tests: _classify_file
# ---------------------------------------------------------------------------

class TestClassifyFile:
    def test_test_directory(self):
        cat, reason = _classify_file("tests/test_font.py")
        assert cat == "TEST_ONLY"

    def test_test_file_naming(self):
        cat, reason = _classify_file("src/aspose/test_utils.py")
        assert cat == "TEST_ONLY"

    def test_test_underscore_suffix(self):
        cat, reason = _classify_file("src/font_test.py")
        assert cat == "TEST_ONLY"

    def test_build_toml(self):
        cat, reason = _classify_file("pyproject.toml")
        assert cat == "BUILD_ONLY"

    def test_build_csproj(self):
        cat, reason = _classify_file("Aspose.Cells.csproj")
        assert cat == "BUILD_ONLY"

    def test_doc_readme(self):
        cat, reason = _classify_file("README.md")
        assert cat == "DOC_ONLY_UPSTREAM"

    def test_doc_changelog(self):
        cat, reason = _classify_file("CHANGELOG.rst")
        assert cat == "DOC_ONLY_UPSTREAM"

    def test_apidocs_html(self):
        cat, reason = _classify_file("apidocs/com/aspose/cells/Chart.html")
        assert cat == "DOC_ONLY_UPSTREAM"

    def test_examples_directory(self):
        cat, reason = _classify_file("examples/ConvertToHtml.py")
        assert cat == "EXAMPLE_CHANGE"

    def test_samples_directory(self):
        cat, reason = _classify_file("samples/demo.cs")
        assert cat == "EXAMPLE_CHANGE"

    def test_definitely_user_facing_py_in_src(self):
        cat, reason = _classify_file("src/aspose_font/ttf/instancer.py")
        assert cat == "DEFINITELY_USER_FACING"

    def test_definitely_user_facing_java_in_main(self):
        cat, reason = _classify_file("src/main/java/com/aspose/cells/Chart.java")
        assert cat == "DEFINITELY_USER_FACING"

    def test_definitely_user_facing_cs(self):
        cat, reason = _classify_file("src/Aspose.Cells/Workbook.cs")
        assert cat == "DEFINITELY_USER_FACING"

    def test_probably_user_facing_py_not_in_src(self):
        cat, reason = _classify_file("aspose/font/ttf_font.py")
        assert cat in ("DEFINITELY_USER_FACING", "PROBABLY_USER_FACING")

    def test_unknown_for_unrecognized(self):
        cat, reason = _classify_file("some/binary.dat")
        assert cat == "UNKNOWN"


# ---------------------------------------------------------------------------
# Unit tests: _aggregate_impact
# ---------------------------------------------------------------------------

class TestAggregateImpact:
    def test_definitely_user_facing_gives_high(self):
        impact = _aggregate_impact(["DEFINITELY_USER_FACING", "TEST_ONLY"])
        assert impact == "HIGH"

    def test_probably_user_facing_gives_medium(self):
        impact = _aggregate_impact(["PROBABLY_USER_FACING", "TEST_ONLY"])
        assert impact == "MEDIUM"

    def test_example_change_gives_medium(self):
        impact = _aggregate_impact(["EXAMPLE_CHANGE", "BUILD_ONLY"])
        assert impact == "MEDIUM"

    def test_test_and_build_only_gives_internal(self):
        impact = _aggregate_impact(["TEST_ONLY", "BUILD_ONLY", "DOC_ONLY_UPSTREAM"])
        assert impact == "INTERNAL_ONLY"

    def test_unknown_alone_gives_unknown(self):
        impact = _aggregate_impact(["UNKNOWN"])
        assert impact == "UNKNOWN"

    def test_mixed_unknown_with_internal_gives_unknown(self):
        impact = _aggregate_impact(["TEST_ONLY", "UNKNOWN"])
        assert impact == "UNKNOWN"

    def test_empty_gives_internal(self):
        impact = _aggregate_impact([])
        assert impact == "INTERNAL_ONLY"


# ---------------------------------------------------------------------------
# Integration tests: classify()
# ---------------------------------------------------------------------------

class TestClassify:
    def _make_diff_lines(self, entries: list[tuple[str, str]]) -> list[str]:
        """Build fake `git diff --name-status` output as list of lines."""
        return [f"{status}\t{path}" for status, path in entries]

    def test_classifies_definitely_user_facing(self, tmp_path):
        """Single DEFINITELY_USER_FACING .py file → impact HIGH."""
        diff_out = self._make_diff_lines([("M", "src/aspose_font/ttf/instancer.py")])
        with patch(
            "commands.ops.semantic_source_classifier._run_git_diff",
            return_value=(diff_out, "", False),
        ):
            result, _ = classify(
                "font", "python",
                old_sha="abc123", new_sha="def456",
                clone_cache_override=str(tmp_path),
                out_path=tmp_path / "semantic_source_delta.json",
                repo_root=tmp_path,
            )
        assert result["source_change_impact"] == "HIGH"
        assert result["diff_available"] is True
        assert any(
            f["category"] == "DEFINITELY_USER_FACING"
            for f in result["files_classified"]
        )

    def test_classifies_test_only(self, tmp_path):
        """TEST_ONLY files → impact INTERNAL_ONLY."""
        diff_out = self._make_diff_lines([("M", "tests/test_font.py")])
        with patch(
            "commands.ops.semantic_source_classifier._run_git_diff",
            return_value=(diff_out, "", False),
        ):
            result, _ = classify(
                "font", "python",
                old_sha="abc123", new_sha="def456",
                clone_cache_override=str(tmp_path),
                out_path=tmp_path / "semantic_source_delta.json",
                repo_root=tmp_path,
            )
        assert result["source_change_impact"] == "INTERNAL_ONLY"

    def test_classifies_mixed_highest_wins(self, tmp_path):
        """Mixed: DEFINITELY_USER_FACING + TEST_ONLY → HIGH."""
        diff_out = self._make_diff_lines([
            ("M", "src/aspose_font/core.py"),
            ("M", "tests/test_core.py"),
        ])
        with patch(
            "commands.ops.semantic_source_classifier._run_git_diff",
            return_value=(diff_out, "", False),
        ):
            result, _ = classify(
                "font", "python",
                old_sha="abc123", new_sha="def456",
                clone_cache_override=str(tmp_path),
                out_path=tmp_path / "semantic_source_delta.json",
                repo_root=tmp_path,
            )
        assert result["source_change_impact"] == "HIGH"

    def test_shallow_clone_unknown(self, tmp_path):
        """Diff unavailable (shallow clone) → diff_available=False, impact=UNKNOWN, exit 0."""
        with patch(
            "commands.ops.semantic_source_classifier._run_git_diff",
            return_value=([], "shallow: unknown revision", True),
        ):
            result, _ = classify(
                "font", "python",
                old_sha="abc123", new_sha="def456",
                clone_cache_override=str(tmp_path),
                out_path=tmp_path / "semantic_source_delta.json",
                repo_root=tmp_path,
            )
        assert result["diff_available"] is False
        assert result["source_change_impact"] == "UNKNOWN"
        # JSON file should still be written
        out = tmp_path / "semantic_source_delta.json"
        assert out.is_file()

    def test_no_source_files_changed(self, tmp_path):
        """Only .md and config → DOC_ONLY_UPSTREAM/BUILD_ONLY → INTERNAL_ONLY."""
        diff_out = self._make_diff_lines([
            ("M", "README.md"),
            ("M", "pyproject.toml"),
        ])
        with patch(
            "commands.ops.semantic_source_classifier._run_git_diff",
            return_value=(diff_out, "", False),
        ):
            result, _ = classify(
                "font", "python",
                old_sha="abc123", new_sha="def456",
                clone_cache_override=str(tmp_path),
                out_path=tmp_path / "semantic_source_delta.json",
                repo_root=tmp_path,
            )
        assert result["source_change_impact"] == "INTERNAL_ONLY"

    def test_claim_delta_attached(self, tmp_path):
        """knowledge_delta.json provided → claim_delta_count populated."""
        # knowledge_delta.json stores claims as lists of IDs
        kd = {
            "new_claims": ["CLM-001", "CLM-002", "CLM-003"],
            "modified_claims": ["CLM-004", "CLM-005"],
            "removed_claims": ["CLM-006"],
            "new_apis": ["API-001", "API-002", "API-003"],
            "modified_apis": ["API-004", "API-005"],
            "removed_apis": [],
        }
        kd_path = tmp_path / "knowledge_delta.json"
        kd_path.write_text(json.dumps(kd), encoding="utf-8")

        diff_out = self._make_diff_lines([("M", "src/core.py")])
        with patch(
            "commands.ops.semantic_source_classifier._run_git_diff",
            return_value=(diff_out, "", False),
        ):
            result, _ = classify(
                "cells", "java",
                old_sha="abc123", new_sha="def456",
                clone_cache_override=str(tmp_path),
                knowledge_delta_path=kd_path,
                out_path=tmp_path / "semantic_source_delta.json",
                repo_root=tmp_path,
            )
        # 3 new + 2 modified + 1 removed + 3 new_apis + 2 modified_apis + 0 removed_apis = 11
        assert result["claim_delta_count"] == 11
        assert result["claim_delta_detail"]["modified_claims"] == 2
        assert result["claim_delta_detail"]["removed_claims"] == 1

    def test_output_json_written(self, tmp_path):
        """Output JSON file is written with required fields."""
        diff_out = self._make_diff_lines([("M", "src/aspose/core.py")])
        out_path = tmp_path / "semantic_source_delta.json"
        with patch(
            "commands.ops.semantic_source_classifier._run_git_diff",
            return_value=(diff_out, "", False),
        ):
            classify(
                "font", "python",
                old_sha="abc123", new_sha="def456",
                clone_cache_override=str(tmp_path),
                out_path=out_path,
                repo_root=tmp_path,
            )
        assert out_path.is_file()
        data = json.loads(out_path.read_text())
        for field in ("family", "platform", "old_source_sha", "new_source_sha",
                      "source_changed", "diff_available", "source_change_impact",
                      "files_classified", "claim_delta_count", "proof", "created_at"):
            assert field in data, f"Missing field: {field}"
