"""Tests for scripts/ci/check_content_filenames.py.

Coverage:
  Unit tests — is_valid_filename() rule table (all structural + prose + reference cases)
  Integration tests — CLI behaviour (exit codes, output, --report-only / --strict)
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
CHECKER = REPO_ROOT / "scripts" / "ci" / "checks" / "check_content_filenames.py"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_prose_path(tmp_path: Path, filename: str) -> tuple[Path, Path]:
    """Return (content_root, file_path) for a prose-tree file."""
    content_root = tmp_path / "content"
    file_path = content_root / "docs.aspose.org" / "en" / "test" / filename
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text("# test\n", encoding="utf-8")
    return content_root, file_path


def _make_ref_path(tmp_path: Path, filename: str) -> tuple[Path, Path]:
    """Return (content_root, file_path) for a reference-tree file."""
    content_root = tmp_path / "content"
    file_path = content_root / "reference.aspose.org" / "en" / "product" / filename
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text("# ref\n", encoding="utf-8")
    return content_root, file_path


def _run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CHECKER)] + list(args),
        capture_output=True,
        text=True,
        cwd=str(cwd or REPO_ROOT),
    )


# Bring is_valid_filename into scope for unit tests
sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci" / "checks"))
from check_content_filenames import is_valid_filename  # noqa: E402


# ===========================================================================
# Unit tests — prose tree
# ===========================================================================

class TestProseValid:
    def test_valid_index_md(self, tmp_path):
        root, p = _make_prose_path(tmp_path, "index.md")
        valid, reason = is_valid_filename(p, root)
        assert valid, reason

    def test_valid_underscore_index(self, tmp_path):
        root, p = _make_prose_path(tmp_path, "_index.md")
        valid, reason = is_valid_filename(p, root)
        assert valid, reason

    def test_valid_slug(self, tmp_path):
        root, p = _make_prose_path(tmp_path, "quickstart.md")
        valid, reason = is_valid_filename(p, root)
        assert valid, reason

    def test_valid_scene_graph(self, tmp_path):
        root, p = _make_prose_path(tmp_path, "scene-graph.md")
        valid, reason = is_valid_filename(p, root)
        assert valid, reason

    def test_valid_long_slug(self, tmp_path):
        root, p = _make_prose_path(tmp_path, "anything-that-is-a-sentence.md")
        valid, reason = is_valid_filename(p, root)
        assert valid, reason

    def test_valid_locale_index(self, tmp_path):
        root, p = _make_prose_path(tmp_path, "index.fr.md")
        valid, reason = is_valid_filename(p, root)
        assert valid, reason

    def test_valid_slug_with_locale_suffix(self, tmp_path):
        root, p = _make_prose_path(tmp_path, "quickstart.fr.md")
        valid, reason = is_valid_filename(p, root)
        assert valid, reason

    def test_valid_zh_tw_locale(self, tmp_path):
        root, p = _make_prose_path(tmp_path, "index.zh-tw.md")
        valid, reason = is_valid_filename(p, root)
        assert valid, reason


class TestProseInvalid:
    def test_invalid_leading_hyphen(self, tmp_path):
        root, p = _make_prose_path(tmp_path, "-graph.md")
        valid, reason = is_valid_filename(p, root)
        assert not valid
        assert "hyphen" in reason

    def test_invalid_leading_hyphen_index(self, tmp_path):
        root, p = _make_prose_path(tmp_path, "-index.md")
        valid, reason = is_valid_filename(p, root)
        assert not valid
        assert "hyphen" in reason

    def test_invalid_trailing_hyphen(self, tmp_path):
        root, p = _make_prose_path(tmp_path, "graph-.md")
        valid, reason = is_valid_filename(p, root)
        assert not valid
        assert "hyphen" in reason

    def test_invalid_doubled_hyphen(self, tmp_path):
        root, p = _make_prose_path(tmp_path, "scene--graph.md")
        valid, reason = is_valid_filename(p, root)
        assert not valid
        assert "--" in reason

    def test_invalid_uppercase_stem_prose(self, tmp_path):
        root, p = _make_prose_path(tmp_path, "Scene-Graph.md")
        valid, reason = is_valid_filename(p, root)
        assert not valid
        assert "slug" in reason.lower()

    def test_invalid_space_in_filename(self, tmp_path):
        # Directly construct path without writing so we can test the filename check
        content_root = tmp_path / "content"
        content_root.mkdir(parents=True, exist_ok=True)
        # Create a fake path object — we don't need the file to exist for the function
        fake = content_root / "docs.aspose.org" / "en" / "test" / "scene graph.md"
        valid, reason = is_valid_filename(fake, content_root)
        assert not valid
        assert "space" in reason

    def test_invalid_uppercase_extension_MD(self, tmp_path):
        root, p = _make_prose_path(tmp_path, "file.MD")
        # Rename to uppercase extension (the function checks path.suffix)
        upper = p.parent / "file.MD"
        p.rename(upper)
        valid, reason = is_valid_filename(upper, root)
        assert not valid
        assert "uppercase" in reason.lower()

    def test_invalid_uppercase_extension_Md(self, tmp_path):
        content_root = tmp_path / "content"
        fake = content_root / "docs.aspose.org" / "en" / "test" / "file.Md"
        valid, reason = is_valid_filename(fake, content_root)
        assert not valid
        assert "uppercase" in reason.lower()

    def test_invalid_uppercase_extension_mD(self, tmp_path):
        content_root = tmp_path / "content"
        fake = content_root / "docs.aspose.org" / "en" / "test" / "file.mD"
        valid, reason = is_valid_filename(fake, content_root)
        assert not valid
        assert "uppercase" in reason.lower()

    def test_invalid_uppercase_locale_suffix(self, tmp_path):
        content_root = tmp_path / "content"
        fake = content_root / "docs.aspose.org" / "en" / "test" / "index.EN.md"
        valid, reason = is_valid_filename(fake, content_root)
        assert not valid
        assert "locale" in reason.lower()

    def test_invalid_double_dot(self, tmp_path):
        content_root = tmp_path / "content"
        fake = content_root / "docs.aspose.org" / "en" / "test" / "abc..md"
        valid, reason = is_valid_filename(fake, content_root)
        assert not valid
        assert ".." in reason

    def test_invalid_leading_whitespace(self, tmp_path):
        content_root = tmp_path / "content"
        fake = content_root / "docs.aspose.org" / "en" / "test" / " scene-graph.md"
        valid, reason = is_valid_filename(fake, content_root)
        assert not valid

    def test_invalid_trailing_whitespace(self, tmp_path):
        content_root = tmp_path / "content"
        fake = content_root / "docs.aspose.org" / "en" / "test" / "scene-graph .md"
        valid, reason = is_valid_filename(fake, content_root)
        assert not valid


# ===========================================================================
# Unit tests — reference tree
# ===========================================================================

class TestReferenceTree:
    def test_pascal_case_allowed_under_reference(self, tmp_path):
        root, p = _make_ref_path(tmp_path, "AdjustValue.md")
        valid, reason = is_valid_filename(p, root)
        assert valid, reason

    def test_iface_pascal_allowed(self, tmp_path):
        root, p = _make_ref_path(tmp_path, "ICamera.md")
        valid, reason = is_valid_filename(p, root)
        assert valid, reason

    def test_leading_hyphen_rejected_under_reference(self, tmp_path):
        root, p = _make_ref_path(tmp_path, "-Bad.md")
        valid, reason = is_valid_filename(p, root)
        assert not valid
        assert "hyphen" in reason

    def test_doubled_hyphen_rejected_under_reference(self, tmp_path):
        content_root = tmp_path / "content"
        fake = content_root / "reference.aspose.org" / "en" / "p" / "Bad--Name.md"
        valid, reason = is_valid_filename(fake, content_root)
        assert not valid
        assert "--" in reason

    def test_pascal_case_rejected_under_docs(self, tmp_path):
        root, p = _make_prose_path(tmp_path, "AdjustValue.md")
        valid, reason = is_valid_filename(p, root)
        assert not valid
        assert "slug" in reason.lower()


# ===========================================================================
# Integration tests — CLI
# ===========================================================================

class TestCLI:
    def test_clean_fixture_exits_0_strict(self, tmp_path):
        """A tree with only valid filenames → exit 0 in strict mode."""
        root = tmp_path / "content"
        d = root / "docs.aspose.org" / "en" / "test"
        d.mkdir(parents=True)
        (d / "index.md").write_text("# ok\n", encoding="utf-8")
        (d / "scene-graph.md").write_text("# ok\n", encoding="utf-8")
        result = _run("--root", str(root), "--strict")
        assert result.returncode == 0, result.stdout + result.stderr

    def test_invalid_fixture_exits_1_strict(self, tmp_path):
        """A tree with a leading-hyphen file → exit 1 in strict mode."""
        root = tmp_path / "content"
        d = root / "docs.aspose.org" / "en" / "test"
        d.mkdir(parents=True)
        (d / "-bad.md").write_text("# bad\n", encoding="utf-8")
        result = _run("--root", str(root), "--strict")
        assert result.returncode == 1, result.stdout + result.stderr

    def test_invalid_fixture_exits_0_report_only(self, tmp_path):
        """A tree with violations → exit 0 in --report-only mode."""
        root = tmp_path / "content"
        d = root / "docs.aspose.org" / "en" / "test"
        d.mkdir(parents=True)
        (d / "-bad.md").write_text("# bad\n", encoding="utf-8")
        result = _run("--root", str(root), "--report-only")
        assert result.returncode == 0, result.stdout + result.stderr

    def test_output_includes_exact_path(self, tmp_path):
        """Violation output must include the exact relative path."""
        root = tmp_path / "content"
        d = root / "docs.aspose.org" / "en" / "test"
        d.mkdir(parents=True)
        bad = d / "-bad.md"
        bad.write_text("# bad\n", encoding="utf-8")
        result = _run("--root", str(root), "--report-only", cwd=tmp_path)
        assert "-bad.md" in result.stdout, result.stdout

    def test_uppercase_extension_detected(self, tmp_path):
        """Files with uppercase extension are detected by the unit-level check.

        Note: Windows NTFS is case-insensitive, so we cannot create both
        ``file.md`` and ``file.MD`` in the same directory.  The unit-level
        ``is_valid_filename`` API is tested directly instead.
        """
        from check_content_filenames import is_valid_filename as _ivf
        content_root = tmp_path / "content"
        content_root.mkdir(parents=True, exist_ok=True)
        fake_MD = content_root / "docs.aspose.org" / "en" / "test" / "badext.MD"
        valid, reason = _ivf(fake_MD, content_root)
        assert not valid
        assert "uppercase" in reason.lower(), reason

        fake_Md = content_root / "docs.aspose.org" / "en" / "test" / "badext.Md"
        valid2, reason2 = _ivf(fake_Md, content_root)
        assert not valid2
        assert "uppercase" in reason2.lower(), reason2

    def test_reference_pascal_allowed(self, tmp_path):
        """PascalCase file under reference.aspose.org → exit 0 strict."""
        root = tmp_path / "content"
        d = root / "reference.aspose.org" / "en" / "product"
        d.mkdir(parents=True)
        (d / "AdjustValue.md").write_text("# ref\n", encoding="utf-8")
        result = _run("--root", str(root), "--strict")
        assert result.returncode == 0, result.stdout + result.stderr

    def test_prose_pascal_rejected(self, tmp_path):
        """PascalCase file under docs.aspose.org → exit 1 strict."""
        root = tmp_path / "content"
        d = root / "docs.aspose.org" / "en" / "product"
        d.mkdir(parents=True)
        (d / "AdjustValue.md").write_text("# wrong\n", encoding="utf-8")
        result = _run("--root", str(root), "--strict")
        assert result.returncode == 1, result.stdout + result.stderr

    def test_missing_root_exits_2(self, tmp_path):
        """Non-existent root → exit 2."""
        result = _run("--root", str(tmp_path / "nonexistent"), "--strict")
        assert result.returncode == 2, result.stdout + result.stderr

    def test_default_mode_is_strict(self, tmp_path):
        """Without --strict or --report-only, violations should cause exit 1."""
        root = tmp_path / "content"
        d = root / "docs.aspose.org" / "en" / "test"
        d.mkdir(parents=True)
        (d / "-bad.md").write_text("# bad\n", encoding="utf-8")
        result = _run("--root", str(root))
        assert result.returncode == 1, result.stdout + result.stderr

    def test_repository_zero_violations_strict(self):
        """Running against the real content/ in strict mode must exit 0."""
        result = _run("--root", "content", "--strict")
        assert result.returncode == 0, (
            f"Repository has filename violations:\n{result.stdout}"
        )
