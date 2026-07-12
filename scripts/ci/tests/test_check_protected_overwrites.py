"""Tests for scripts/ci/checks/check_protected_overwrites.py.

Coverage:
  Unit  — _is_english_source() classification (all content path patterns)
  Unit  — _is_content_file() boundary check
  Unit  — _get_protected_in_head() subprocess output parsing + error handling
  Unit  — check_files() small-set per-file path (< _BATCH_THRESHOLD)
  Unit  — check_files() large-set batch path (>= _BATCH_THRESHOLD)
  Unit  — check_files() batch path: git grep false-positive rejection
  Unit  — check_files() batch path: git grep error → fallback empty frozenset
  Integration — check_files() filters non-content and non-.md files
  Negative  — locale translations never trigger violation
  Negative  — new files (not in HEAD) are never flagged
  Performance-path — batch threshold boundary (49 vs 50 candidates)
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci" / "checks"))

import check_protected_overwrites as _mod  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PROTECTED_FRONTMATTER = """\
---
title: "Test Page"
provenance:
  auto_updatable: false
  content_hash: abc123
---
Body content.
"""

_UNPROTECTED_FRONTMATTER = """\
---
title: "Test Page"
provenance:
  auto_updatable: true
  content_hash: abc123
---
Body content.
"""

_NO_PROVENANCE = """\
---
title: "Test Page"
---
Body content.
"""


def _make_run_result(stdout: str = "", returncode: int = 0) -> MagicMock:
    """Build a mock subprocess.CompletedProcess."""
    r = MagicMock()
    r.returncode = returncode
    r.stdout = stdout
    r.stderr = ""
    return r


# ---------------------------------------------------------------------------
# _is_english_source() — pure function, no mocking needed
# ---------------------------------------------------------------------------

class TestIsEnglishSource:
    """_is_english_source() must accept English and reject locale files."""

    # --- docs / kb / products / reference: /en/ directory segment ---

    def test_docs_en(self):
        assert _mod._is_english_source(
            "content/docs.aspose.org/en/3d/net/developer-guide/render.md"
        )

    def test_kb_en(self):
        assert _mod._is_english_source(
            "content/kb.aspose.org/en/cells/cpp/faq.md"
        )

    def test_products_en(self):
        assert _mod._is_english_source(
            "content/products.aspose.org/en/cells/_index.md"
        )

    def test_reference_en(self):
        assert _mod._is_english_source(
            "content/reference.aspose.org/en/pdf/net/Document.md"
        )

    def test_kb_locale_ar_rejected(self):
        assert not _mod._is_english_source(
            "content/kb.aspose.org/ar/cells/cpp/faq.md"
        )

    def test_kb_locale_de_rejected(self):
        assert not _mod._is_english_source(
            "content/kb.aspose.org/de/cells/python/troubleshooting.md"
        )

    def test_kb_locale_zh_rejected(self):
        assert not _mod._is_english_source(
            "content/kb.aspose.org/zh/slides/cpp/how-to-get-started-slides-cpp.md"
        )

    # --- blog: index.md vs index.XX.md ---

    def test_blog_english_index(self):
        assert _mod._is_english_source(
            "content/blog.aspose.org/cells/net/some-post/index.md"
        )

    def test_blog_english_root_index(self):
        assert _mod._is_english_source(
            "content/blog.aspose.org/_index.md"
        )

    def test_blog_english_family_index(self):
        assert _mod._is_english_source(
            "content/blog.aspose.org/cells/_index.md"
        )

    def test_blog_english_platform_index(self):
        assert _mod._is_english_source(
            "content/blog.aspose.org/cells/net/_index.md"
        )

    def test_blog_locale_sv_rejected(self):
        assert not _mod._is_english_source(
            "content/blog.aspose.org/cells/net/some-post/index.sv.md"
        )

    def test_blog_locale_ar_rejected(self):
        assert not _mod._is_english_source(
            "content/blog.aspose.org/3d/net/3d-utilities-net/index.ar.md"
        )

    def test_blog_archive_locale_rejected(self):
        assert not _mod._is_english_source(
            "content/blog.aspose.org/archive.ar.md"
        )

    def test_blog_archive_english(self):
        assert _mod._is_english_source(
            "content/blog.aspose.org/archive.md"
        )

    # --- Windows backslash paths ---

    def test_windows_backslash_en(self):
        assert _mod._is_english_source(
            r"content\kb.aspose.org\en\cells\cpp\faq.md"
        )

    def test_windows_backslash_locale_rejected(self):
        assert not _mod._is_english_source(
            r"content\kb.aspose.org\ar\cells\cpp\faq.md"
        )


# ---------------------------------------------------------------------------
# _is_content_file() — pure function
# ---------------------------------------------------------------------------

class TestIsContentFile:
    def test_docs(self):
        assert _mod._is_content_file("content/docs.aspose.org/en/a.md")

    def test_blog(self):
        assert _mod._is_content_file("content/blog.aspose.org/a/b/index.md")

    def test_kb(self):
        assert _mod._is_content_file("content/kb.aspose.org/en/a.md")

    def test_products(self):
        assert _mod._is_content_file("content/products.aspose.org/en/a/_index.md")

    def test_reference(self):
        assert _mod._is_content_file("content/reference.aspose.org/en/a/A.md")

    def test_scripts_rejected(self):
        assert not _mod._is_content_file("scripts/pipeline/something.py")

    def test_knowledge_rejected(self):
        assert not _mod._is_content_file("knowledge/pdf/net/merged/model.yaml")

    def test_windows_path(self):
        assert _mod._is_content_file(r"content\kb.aspose.org\en\a.md")


# ---------------------------------------------------------------------------
# _get_protected_in_head() — subprocess output parsing
# ---------------------------------------------------------------------------

class TestGetProtectedInHead:
    """_get_protected_in_head() parses git grep output into a frozenset of paths."""

    def test_parses_head_prefixed_lines(self):
        grep_output = (
            "HEAD:content/kb.aspose.org/en/cells/cpp/faq.md\n"
            "HEAD:content/docs.aspose.org/en/3d/net/render.md\n"
        )
        with patch("subprocess.run", return_value=_make_run_result(grep_output)):
            result = _mod._get_protected_in_head()
        assert "content/kb.aspose.org/en/cells/cpp/faq.md" in result
        assert "content/docs.aspose.org/en/3d/net/render.md" in result
        assert len(result) == 2

    def test_returns_frozenset(self):
        with patch("subprocess.run", return_value=_make_run_result("HEAD:content/a/b.md\n")):
            result = _mod._get_protected_in_head()
        assert isinstance(result, frozenset)

    def test_empty_on_no_matches(self):
        # git grep exits 1 when no matches — not an error
        with patch("subprocess.run", return_value=_make_run_result("", returncode=1)):
            result = _mod._get_protected_in_head()
        assert result == frozenset()

    def test_empty_on_git_error(self):
        # git grep exits 2+ on real error → fail-open (empty set)
        with patch("subprocess.run", return_value=_make_run_result("", returncode=2)):
            result = _mod._get_protected_in_head()
        assert result == frozenset()

    def test_empty_on_timeout(self):
        import subprocess as _sp
        with patch("subprocess.run", side_effect=_sp.TimeoutExpired(cmd=[], timeout=60)):
            result = _mod._get_protected_in_head()
        assert result == frozenset()

    def test_empty_on_oserror(self):
        with patch("subprocess.run", side_effect=OSError("git not found")):
            result = _mod._get_protected_in_head()
        assert result == frozenset()

    def test_normalizes_windows_backslashes(self):
        grep_output = "HEAD:content\\kb.aspose.org\\en\\faq.md\n"
        with patch("subprocess.run", return_value=_make_run_result(grep_output)):
            result = _mod._get_protected_in_head()
        assert "content/kb.aspose.org/en/faq.md" in result

    def test_ignores_lines_without_colon(self):
        grep_output = "content/kb.aspose.org/en/faq.md\n"  # missing HEAD: prefix
        with patch("subprocess.run", return_value=_make_run_result(grep_output)):
            result = _mod._get_protected_in_head()
        assert result == frozenset()

    def test_uses_correct_git_grep_command(self):
        with patch("subprocess.run", return_value=_make_run_result("")) as mock_run:
            _mod._get_protected_in_head()
        args = mock_run.call_args[0][0]
        assert args[:3] == ["git", "grep", "-lF"]
        assert "auto_updatable: false" in args
        assert "HEAD" in args


# ---------------------------------------------------------------------------
# check_files() — per-file path (< _BATCH_THRESHOLD)
# ---------------------------------------------------------------------------

class TestCheckFilesPerFile:
    """Small file counts use per-file git show subprocess (original path)."""

    def test_single_protected_file_detected(self):
        fp = "content/kb.aspose.org/en/cells/cpp/faq.md"
        with patch("subprocess.run", return_value=_make_run_result(_PROTECTED_FRONTMATTER)):
            result = _mod.check_files([fp])
        assert result == [fp]

    def test_unprotected_file_not_flagged(self):
        fp = "content/kb.aspose.org/en/cells/cpp/faq.md"
        with patch("subprocess.run", return_value=_make_run_result(_UNPROTECTED_FRONTMATTER)):
            result = _mod.check_files([fp])
        assert result == []

    def test_new_file_not_in_head(self):
        # returncode != 0 → file not in HEAD → not protected
        fp = "content/kb.aspose.org/en/new-page.md"
        with patch("subprocess.run", return_value=_make_run_result("", returncode=1)):
            result = _mod.check_files([fp])
        assert result == []

    def test_no_provenance_field(self):
        fp = "content/kb.aspose.org/en/cells/cpp/faq.md"
        with patch("subprocess.run", return_value=_make_run_result(_NO_PROVENANCE)):
            result = _mod.check_files([fp])
        assert result == []

    def test_non_content_file_filtered(self):
        with patch("subprocess.run") as mock_run:
            result = _mod.check_files(["scripts/pipeline/something.py"])
        mock_run.assert_not_called()
        assert result == []

    def test_non_md_file_filtered(self):
        with patch("subprocess.run") as mock_run:
            result = _mod.check_files(["content/kb.aspose.org/en/a.yaml"])
        mock_run.assert_not_called()
        assert result == []

    def test_empty_list_returns_empty(self):
        with patch("subprocess.run") as mock_run:
            result = _mod.check_files([])
        mock_run.assert_not_called()
        assert result == []

    def test_batch_threshold_boundary_below(self):
        # 49 files → per-file path; subprocess called once per file (git show)
        files = [
            f"content/kb.aspose.org/en/cells/cpp/faq{i}.md"
            for i in range(_mod._BATCH_THRESHOLD - 1)
        ]
        with patch("subprocess.run", return_value=_make_run_result(_UNPROTECTED_FRONTMATTER)):
            result = _mod.check_files(files)
        assert result == []


# ---------------------------------------------------------------------------
# check_files() — batch path (>= _BATCH_THRESHOLD)
# ---------------------------------------------------------------------------

class TestCheckFilesBatchPath:
    """Large file counts use the git grep batch approach."""

    def _make_files(self, n: int, prefix: str = "content/kb.aspose.org/en/f") -> list[str]:
        return [f"{prefix}{i}.md" for i in range(n)]

    def test_batch_threshold_boundary_at(self):
        # Exactly _BATCH_THRESHOLD files → batch path activated
        files = self._make_files(_mod._BATCH_THRESHOLD)
        # git grep returns empty → no protected files
        with patch("subprocess.run", return_value=_make_run_result("", returncode=1)):
            result = _mod.check_files(files)
        assert result == []

    def test_batch_path_no_intersection(self):
        # Protected set has no overlap with staged files → no violations
        files = self._make_files(100)
        grep_output = "HEAD:content/docs.aspose.org/en/other/page.md\n"
        with patch("subprocess.run", return_value=_make_run_result(grep_output)):
            result = _mod.check_files(files)
        assert result == []

    def test_batch_path_intersection_verified(self):
        # One staged file is in the protected set and confirms protected
        files = self._make_files(100)
        protected_file = files[5]  # e.g. "content/kb.aspose.org/en/f5.md"
        grep_output = f"HEAD:{protected_file}\n"

        def _fake_run(cmd, **kwargs):
            if cmd[1] == "grep":
                return _make_run_result(grep_output)
            # git show for verification → protected frontmatter
            return _make_run_result(_PROTECTED_FRONTMATTER)

        with patch("subprocess.run", side_effect=_fake_run):
            result = _mod.check_files(files)
        assert result == [protected_file]

    def test_batch_path_false_positive_rejected(self):
        # git grep flags a file, but full regex check reveals it's NOT protected
        files = self._make_files(100)
        candidate = files[10]
        grep_output = f"HEAD:{candidate}\n"

        def _fake_run(cmd, **kwargs):
            if cmd[1] == "grep":
                return _make_run_result(grep_output)
            # Full frontmatter regex says auto_updatable: true → not protected
            return _make_run_result(_UNPROTECTED_FRONTMATTER)

        with patch("subprocess.run", side_effect=_fake_run):
            result = _mod.check_files(files)
        assert result == []

    def test_batch_path_grep_empty_skips_show(self):
        # When git grep returns empty, git show must NOT be called
        files = self._make_files(200)
        show_calls = []

        def _fake_run(cmd, **kwargs):
            if cmd[1] == "grep":
                return _make_run_result("", returncode=1)
            show_calls.append(cmd)
            return _make_run_result(_PROTECTED_FRONTMATTER)

        with patch("subprocess.run", side_effect=_fake_run):
            result = _mod.check_files(files)
        assert result == []
        assert show_calls == [], "git show must not be called when git grep finds nothing"

    def test_batch_path_grep_error_returns_empty(self):
        # git grep exit 2 → fail-open (no violations, no crash)
        files = self._make_files(100)
        with patch("subprocess.run", return_value=_make_run_result("", returncode=2)):
            result = _mod.check_files(files)
        assert result == []

    def test_locale_files_excluded_by_intersection(self):
        # Locale files staged (9940-pattern); none should appear in violations
        locale_files = [
            f"content/kb.aspose.org/ar/cells/cpp/faq{i}.md"
            for i in range(200)
        ]
        # Protected set has only English files
        grep_output = "HEAD:content/kb.aspose.org/en/cells/cpp/faq.md\n"

        def _fake_run(cmd, **kwargs):
            if cmd[1] == "grep":
                return _make_run_result(grep_output)
            return _make_run_result(_PROTECTED_FRONTMATTER)

        with patch("subprocess.run", side_effect=_fake_run):
            result = _mod.check_files(locale_files)
        # Locale files don't match protected English path → no violations
        assert result == []


# ---------------------------------------------------------------------------
# _get_staged_files() — locale filter behaviour
# ---------------------------------------------------------------------------

class TestGetStagedFiles:
    """_get_staged_files() must filter out locale translations."""

    def _mock_git_diff(self, file_list: list[str]) -> MagicMock:
        return _make_run_result("\n".join(file_list) + "\n")

    def test_english_kb_included(self):
        files = ["content/kb.aspose.org/en/cells/cpp/faq.md"]
        with patch("subprocess.run", return_value=self._mock_git_diff(files)):
            result = _mod._get_staged_files()
        assert result == files

    def test_locale_kb_excluded(self):
        files = [
            "content/kb.aspose.org/ar/cells/cpp/faq.md",
            "content/kb.aspose.org/de/cells/cpp/faq.md",
        ]
        with patch("subprocess.run", return_value=self._mock_git_diff(files)):
            result = _mod._get_staged_files()
        assert result == []

    def test_blog_english_included(self):
        files = ["content/blog.aspose.org/cells/net/post/index.md"]
        with patch("subprocess.run", return_value=self._mock_git_diff(files)):
            result = _mod._get_staged_files()
        assert result == files

    def test_blog_locale_excluded(self):
        files = ["content/blog.aspose.org/cells/net/post/index.sv.md"]
        with patch("subprocess.run", return_value=self._mock_git_diff(files)):
            result = _mod._get_staged_files()
        assert result == []

    def test_mixed_batch_filters_correctly(self):
        # 9940-style mix: many locale files, few English
        locale_files = [
            f"content/kb.aspose.org/ar/cells/cpp/faq{i}.md" for i in range(100)
        ]
        english_files = [
            "content/kb.aspose.org/en/cells/cpp/faq.md",
            "content/blog.aspose.org/cells/net/post/index.md",
        ]
        all_files = locale_files + english_files
        with patch("subprocess.run", return_value=self._mock_git_diff(all_files)):
            result = _mod._get_staged_files()
        assert set(result) == set(english_files)

    def test_git_diff_error_returns_empty(self):
        with patch("subprocess.run", return_value=_make_run_result("", returncode=128)):
            result = _mod._get_staged_files()
        assert result == []

    def test_git_diff_timeout_returns_empty(self):
        import subprocess as _sp
        with patch("subprocess.run", side_effect=_sp.TimeoutExpired(cmd=[], timeout=15)):
            result = _mod._get_staged_files()
        assert result == []


# ---------------------------------------------------------------------------
# Regression: _BATCH_THRESHOLD constant is 50
# ---------------------------------------------------------------------------

def test_batch_threshold_value():
    """Threshold must be 50 — the calibrated boundary where git grep wins."""
    assert _mod._BATCH_THRESHOLD == 50
