"""Behavioral tests for check_grade_presence.py — CLI entry point.

Covers:
  - File WITH grade block → exit 0 (pass)
  - File WITHOUT grade block → exit 1 (fail)
  - Empty file list → exit 0 (no false positive)
  - Locale files (*.fr.md) are silently skipped
  - Nonexistent file is silently skipped (no crash, exit 0)
  - --allow-new flag: ungradded files exit 0 with warning
  - main() callable directly (not only via subprocess)
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_PIPELINE_DIR = Path(__file__).resolve().parent.parent
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

_SCRIPT = str(_PIPELINE_DIR / "commands" / "governance" / "check_grade_presence.py")
_REPO_ROOT = _PIPELINE_DIR.parent.parent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _graded_md(path: Path) -> Path:
    """Write a minimal markdown file with a valid grade block."""
    path.write_text(
        "---\ntitle: Test\ngrade: A\ngrade_model_sha: abc123\n---\n\n# Content\n",
        encoding="utf-8",
    )
    return path


def _ungraded_md(path: Path) -> Path:
    """Write a minimal markdown file with NO grade block."""
    path.write_text(
        "---\ntitle: Test\nweight: 10\n---\n\n# Content\n",
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# Section 1 — main() direct calls (no subprocess overhead)
# ---------------------------------------------------------------------------

class TestMainDirect:
    """Invoke main() directly to test logic without subprocess."""

    def setup_method(self):
        from check_grade_presence import main
        self._main = main

    def test_empty_file_list_exits_zero(self):
        """No files → nothing missing → exit 0."""
        assert self._main([]) == 0

    def test_graded_file_exits_zero(self, tmp_path):
        """A file with a grade block → exit 0."""
        f = _graded_md(tmp_path / "page.md")
        assert self._main([str(f)]) == 0

    def test_ungraded_file_exits_one(self, tmp_path):
        """A file without a grade block → exit 1."""
        f = _ungraded_md(tmp_path / "page.md")
        assert self._main([str(f)]) == 1

    def test_mix_graded_and_ungraded_exits_one(self, tmp_path):
        """Any ungraded file in the list causes exit 1."""
        g = _graded_md(tmp_path / "graded.md")
        u = _ungraded_md(tmp_path / "ungraded.md")
        assert self._main([str(g), str(u)]) == 1

    def test_nonexistent_file_is_skipped(self, tmp_path):
        """Nonexistent path must be silently skipped — no crash, exit 0."""
        ghost = str(tmp_path / "ghost.md")
        assert self._main([ghost]) == 0

    def test_locale_file_is_skipped(self, tmp_path):
        """Locale-suffixed files (*.fr.md, *.de.md) must be skipped."""
        fr = _ungraded_md(tmp_path / "page.fr.md")
        de = _ungraded_md(tmp_path / "page.de.md")
        # Locale files skipped → no missing → exit 0
        assert self._main([str(fr), str(de)]) == 0

    def test_allow_new_flag_exits_zero_with_warning(self, tmp_path, capsys):
        """--allow-new must exit 0 even when files lack grades."""
        f = _ungraded_md(tmp_path / "page.md")
        result = self._main(["--allow-new", str(f)])
        assert result == 0
        captured = capsys.readouterr()
        assert "allow-new" in captured.err.lower() or "warning" in captured.err.lower(), (
            f"Expected allow-new warning in stderr:\n{captured.err}"
        )

    def test_multiple_graded_files_exit_zero(self, tmp_path):
        """All graded → exit 0 regardless of count."""
        files = [str(_graded_md(tmp_path / f"page{i}.md")) for i in range(3)]
        assert self._main(files) == 0


# ---------------------------------------------------------------------------
# Section 1b — translations that live in a locale DIRECTORY (MT069 HC-20)
#
# Docs/KB/reference/products keep translations under content/<site>/<code>/...,
# not as *.<code>.md. Those files carry provenance.translation_origin and no
# grade by design. The check used to judge "translation" by filename suffix only
# and demanded a grade on 141 of them (found by the HC-06 CI-mirror simulation).
# The English gate must stay exactly as strict as before.
# ---------------------------------------------------------------------------

class TestLocaleDirectoryTranslations:
    def setup_method(self):
        from check_grade_presence import main
        self._main = main

    @staticmethod
    def _page(tmp_path: Path, rel: str, *, graded: bool) -> Path:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        return (_graded_md if graded else _ungraded_md)(p)

    @pytest.mark.parametrize("site", ["docs", "kb", "reference", "products"])
    def test_ungraded_translation_in_a_locale_directory_passes(self, tmp_path, site):
        f = self._page(tmp_path, f"content/{site}.aspose.org/fa/3d/python/_index.md", graded=False)
        assert self._main([str(f)]) == 0

    def test_ungraded_english_page_still_fails(self, tmp_path):
        """The gate must stay live: 'en' is not a translation."""
        f = self._page(tmp_path, "content/docs.aspose.org/en/3d/python/_index.md", graded=False)
        assert self._main([str(f)]) == 1

    def test_graded_english_page_passes(self, tmp_path):
        f = self._page(tmp_path, "content/docs.aspose.org/en/3d/python/_index.md", graded=True)
        assert self._main([str(f)]) == 0

    def test_a_locale_code_deeper_in_the_path_does_not_exempt_an_english_page(self, tmp_path):
        f = self._page(tmp_path, "content/docs.aspose.org/en/cells/no/getting-started/install.md", graded=False)
        assert self._main([str(f)]) == 1

    def test_a_locale_named_directory_outside_content_is_still_checked(self, tmp_path):
        f = self._page(tmp_path, "fa/3d/python/_index.md", graded=False)
        assert self._main([str(f)]) == 1

    def test_blog_uses_suffixes_only_so_a_locale_named_blog_directory_is_still_checked(self, tmp_path):
        f = self._page(tmp_path, "content/blog.aspose.org/de/python/post/index.md", graded=False)
        assert self._main([str(f)]) == 1

    def test_a_file_named_like_a_locale_is_not_a_locale_directory(self, tmp_path):
        f = self._page(tmp_path, "content/docs.aspose.org/fa.md", graded=False)
        assert self._main([str(f)]) == 1

    def test_only_the_english_file_is_reported_when_both_are_ungraded(self, tmp_path, capsys):
        tr = self._page(tmp_path, "content/docs.aspose.org/fa/3d/python/_index.md", graded=False)
        en = self._page(tmp_path, "content/docs.aspose.org/en/3d/python/_index.md", graded=False)
        assert self._main([str(tr), str(en)]) == 1
        err = capsys.readouterr().err
        assert "1 file(s) missing grades" in err
        assert str(en) in err and str(tr) not in err

    def test_suffix_translations_are_still_exempt(self, tmp_path):
        f = self._page(tmp_path, "content/blog.aspose.org/words/net/post/index.hi.md", graded=False)
        assert self._main([str(f)]) == 0


# ---------------------------------------------------------------------------
# Section 2 — CLI subprocess tests (integration)
# ---------------------------------------------------------------------------

class TestCLISubprocess:
    def _run(self, args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, _SCRIPT] + args,
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
        )

    def test_graded_file_exits_zero(self, tmp_path):
        f = _graded_md(tmp_path / "page.md")
        result = self._run([str(f)])
        assert result.returncode == 0, f"stderr:\n{result.stderr}"

    def test_ungraded_file_exits_one(self, tmp_path):
        f = _ungraded_md(tmp_path / "page.md")
        result = self._run([str(f)])
        assert result.returncode == 1
        assert "missing" in result.stderr.lower() or "grade" in result.stderr.lower(), (
            f"Expected missing/grade in stderr:\n{result.stderr}"
        )

    def test_no_files_exits_zero(self):
        result = self._run([])
        assert result.returncode == 0
