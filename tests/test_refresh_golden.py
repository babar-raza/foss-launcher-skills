"""Tests for scripts/refresh_golden.py — golden corpus refresh utility."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from refresh_golden import refresh


class TestRefresh:
    def test_adds_new_files(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()

        (source / "page-one.md").write_text("# Page One\n\nContent here.\n")
        (source / "page-two.md").write_text("# Page Two\n\nMore content.\n")

        result = refresh(source, target)
        assert len(result["added"]) == 2
        assert len(result["modified"]) == 0
        assert len(result["unchanged"]) == 0
        assert (target / "page-one.md").is_file()
        assert (target / "page-two.md").is_file()

    def test_detects_modified_files(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()

        (source / "page.md").write_text("# Updated\n\nNew content.\n")
        (target / "page.md").write_text("# Original\n\nOld content.\n")

        result = refresh(source, target)
        assert len(result["modified"]) == 1
        assert len(result["added"]) == 0
        # Target should have new content
        assert "Updated" in (target / "page.md").read_text()

    def test_detects_unchanged_files(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()

        content = "# Same\n\nIdentical content.\n"
        (source / "page.md").write_text(content)
        (target / "page.md").write_text(content)

        result = refresh(source, target)
        assert len(result["unchanged"]) == 1
        assert len(result["added"]) == 0
        assert len(result["modified"]) == 0

    def test_detects_deleted_in_source(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()

        (target / "orphan.md").write_text("# Orphan\n\nNo longer in source.\n")

        result = refresh(source, target)
        assert len(result["deleted_in_source"]) == 1
        # File should NOT be auto-deleted
        assert (target / "orphan.md").is_file()

    def test_missing_source_dir(self, tmp_path):
        source = tmp_path / "nonexistent"
        target = tmp_path / "target"
        target.mkdir()

        result = refresh(source, target)
        assert "error" in result

    def test_creates_target_dir(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target" / "nested"
        source.mkdir()

        (source / "page.md").write_text("# Content\n")

        result = refresh(source, target)
        assert len(result["added"]) == 1
        assert target.is_dir()

    def test_preserves_subdirectory_structure(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        (source / "sub").mkdir()
        (source / "sub" / "deep.md").write_text("# Deep\n\nNested file.\n")

        result = refresh(source, target)
        assert len(result["added"]) == 1
        assert (target / "sub" / "deep.md").is_file()
