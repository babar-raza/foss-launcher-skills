"""Tests for check_skill_readme_coverage.py — file existence and count validation."""
from __future__ import annotations

import sys
from pathlib import Path

_CI_ROOT = Path(__file__).resolve().parent.parent
if str(_CI_ROOT) not in sys.path:
    sys.path.insert(0, str(_CI_ROOT))

import pytest
import check_skill_readme_coverage as cov  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_cov():
    yield
    cov.configure()


# ---------------------------------------------------------------------------
# _check_file
# ---------------------------------------------------------------------------


class TestCheckFile:
    def test_missing_file_fails(self, tmp_path: Path, monkeypatch):
        cov.configure(repo_root=tmp_path)
        passed, reason = cov._check_file(tmp_path / "nope.md", None)
        assert not passed
        assert "does not exist" in reason

    def test_short_file_fails(self, tmp_path: Path, monkeypatch):
        cov.configure(repo_root=tmp_path)
        f = tmp_path / "short.md"
        f.write_text("# Title\nOne line.\n", encoding="utf-8")
        passed, reason = cov._check_file(f, None)
        assert not passed
        assert "lines" in reason

    def test_adequate_file_passes(self, tmp_path: Path):
        f = tmp_path / "good.md"
        f.write_text("\n".join(f"Line {i}" for i in range(25)), encoding="utf-8")
        passed, reason = cov._check_file(f, None)
        assert passed

    def test_required_substring_present(self, tmp_path: Path):
        f = tmp_path / "root.md"
        f.write_text("See skills/README.md for details.", encoding="utf-8")
        passed, reason = cov._check_file(f, "skills/README.md")
        assert passed

    def test_required_substring_absent(self, tmp_path: Path, monkeypatch):
        cov.configure(repo_root=tmp_path)
        f = tmp_path / "root.md"
        f.write_text("No link here.", encoding="utf-8")
        passed, reason = cov._check_file(f, "skills/README.md")
        assert not passed


# ---------------------------------------------------------------------------
# _count_skills
# ---------------------------------------------------------------------------


class TestCountSkills:
    def test_flat_layout(self, tmp_path: Path):
        (tmp_path / "foo.md").write_text("# Foo", encoding="utf-8")
        (tmp_path / "bar.md").write_text("# Bar", encoding="utf-8")
        (tmp_path / "README.md").write_text("# Index", encoding="utf-8")
        assert cov._count_skills(tmp_path, "flat") == 2

    def test_nested_layout(self, tmp_path: Path):
        for name in ("alpha", "beta", "gamma"):
            d = tmp_path / name
            d.mkdir()
            (d / "SKILL.md").write_text(f"# {name}", encoding="utf-8")
        # A directory without SKILL.md should not be counted
        (tmp_path / "empty-dir").mkdir()
        assert cov._count_skills(tmp_path, "nested") == 3

    def test_empty_directory(self, tmp_path: Path):
        assert cov._count_skills(tmp_path, "flat") == 0
        assert cov._count_skills(tmp_path, "nested") == 0


# ---------------------------------------------------------------------------
# fix_counts
# ---------------------------------------------------------------------------


class TestFixCounts:
    def _make_tree(self, tmp_path: Path, monkeypatch):
        """Build a minimal skill tree with a README containing a wrong count."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        for name in ("alpha", "beta", "gamma"):
            (skills_dir / f"{name}.md").write_text(f"# {name}", encoding="utf-8")
        readme = skills_dir / "README.md"
        readme.write_text(
            "This catalog has 2 registered skills in it.\n" * 25,
            encoding="utf-8",
        )
        cov.configure(repo_root=tmp_path)
        monkeypatch.setattr(
            cov,
            "_SKILL_DIRS",
            {"skills": (skills_dir, "flat")},
        )
        monkeypatch.setattr(
            cov,
            "_COUNT_PATTERNS",
            [
                (
                    readme,
                    r"(\d+)\s+registered\s+skills",
                    "skills",
                    "skills/README.md registered count",
                ),
            ],
        )
        return readme

    def test_fix_corrects_wrong_count(self, tmp_path: Path, monkeypatch):
        readme = self._make_tree(tmp_path, monkeypatch)
        fixed = cov.fix_counts()
        assert fixed == 1
        assert "3 registered skills" in readme.read_text(encoding="utf-8")

    def test_fix_is_idempotent(self, tmp_path: Path, monkeypatch):
        self._make_tree(tmp_path, monkeypatch)
        cov.fix_counts()
        assert cov.fix_counts() == 0

    def test_fix_then_check_passes(self, tmp_path: Path, monkeypatch):
        self._make_tree(tmp_path, monkeypatch)
        # Stub out _CHECKS so check() only validates counts, not real repo files
        monkeypatch.setattr(cov, "_CHECKS", [])
        cov.fix_counts()
        assert cov.check() == 0


# ---------------------------------------------------------------------------
# Count validation — integration against real repo
# ---------------------------------------------------------------------------


class TestCountValidationIntegration:
    def test_real_repo_passes(self):
        """All README count claims should match actual disk counts."""
        result = cov.check()
        assert result == 0
