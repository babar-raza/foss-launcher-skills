"""Tests for scripts/pipeline/ground_check.py (S-23 grounding ratio gate)."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

_PIPELINE_DIR = Path(__file__).resolve().parent.parent
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

import ground_check  # noqa: E402

_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(autouse=True)
def _reset_ground_check():
    yield
    ground_check.configure()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_knowledge(tmp_path: Path, api_surface_file: str = "fake_api_surface.json") -> Path:
    """Copy a fixture api_surface.json into a fake knowledge merged/ dir."""
    merged = tmp_path / "knowledge" / "fake" / "python" / "merged"
    merged.mkdir(parents=True)
    shutil.copy(_FIXTURES_DIR / api_surface_file, merged / "api_surface.json")
    ground_check.configure(repo_root=tmp_path)
    return merged / "api_surface.json"


# ---------------------------------------------------------------------------
# Unit: _build_known_identifiers
# ---------------------------------------------------------------------------

class TestBuildKnownIdentifiers:
    def test_extracts_class_names(self):
        api = [{"name": "Scene", "methods": [], "properties": [], "enum_members": []}]
        known = ground_check._build_known_identifiers(api)
        assert "scene" in known

    def test_extracts_method_names(self):
        api = [{"name": "Scene", "methods": [{"name": "open"}], "properties": [], "enum_members": []}]
        known = ground_check._build_known_identifiers(api)
        assert "open" in known

    def test_extracts_property_names(self):
        api = [{"name": "Scene", "methods": [], "properties": [{"name": "root_node"}], "enum_members": []}]
        known = ground_check._build_known_identifiers(api)
        assert "root_node" in known

    def test_extracts_enum_members(self):
        api = [{"name": "FileFormat", "methods": [], "properties": [], "enum_members": [{"name": "OBJ"}]}]
        known = ground_check._build_known_identifiers(api)
        assert "obj" in known

    def test_extracts_method_details_field(self):
        """Supports both 'methods' and 'method_details' keys."""
        api = [{"name": "Cls", "method_details": [{"name": "do_thing"}], "property_details": [], "enum_members": []}]
        known = ground_check._build_known_identifiers(api)
        assert "do_thing" in known

    def test_empty_api_surface(self):
        assert ground_check._build_known_identifiers([]) == set()

    def test_identifiers_are_lowercased(self):
        api = [{"name": "MyScene", "methods": [{"name": "OpenFile"}], "properties": [], "enum_members": []}]
        known = ground_check._build_known_identifiers(api)
        assert "myscene" in known
        assert "openfile" in known
        assert "MyScene" not in known


# ---------------------------------------------------------------------------
# Unit: compute_grounding_ratio
# ---------------------------------------------------------------------------

class TestComputeGroundingRatio:
    def test_all_identifiers_matched(self, tmp_path):
        _make_knowledge(tmp_path)
        content = tmp_path / "page.md"
        # All identifiers exist in fake_api_surface: Scene, open, save
        content.write_text(
            "Use `Scene` to load files. Call `Scene.open` then `Scene.save`.",
            encoding="utf-8",
        )
        ratio, matched, total, ungrounded = ground_check.compute_grounding_ratio(
            content, ground_check.KNOWLEDGE_ROOT / "fake" / "python" / "merged" / "api_surface.json"
        )
        assert ratio == 1.0
        assert total == 3
        assert matched == 3
        assert ungrounded == []

    def test_partial_match_in_warn_range(self, tmp_path):
        _make_knowledge(tmp_path)
        api_path = ground_check.KNOWLEDGE_ROOT / "fake" / "python" / "merged" / "api_surface.json"
        content = tmp_path / "page.md"
        # 3 known (Scene, open, save) + 1 unknown = 75% -> WARN
        content.write_text(
            "Use `Scene`. Call `Scene.open`. Also `Scene.save`. Finally `UnknownWidget` helps.",
            encoding="utf-8",
        )
        ratio, matched, total, ungrounded = ground_check.compute_grounding_ratio(content, api_path)
        assert total == 4
        assert matched == 3
        assert abs(ratio - 0.75) < 0.01
        assert "UnknownWidget" in ungrounded

    def test_low_match_in_fail_range(self, tmp_path):
        _make_knowledge(tmp_path)
        api_path = ground_check.KNOWLEDGE_ROOT / "fake" / "python" / "merged" / "api_surface.json"
        content = tmp_path / "page.md"
        # 1 known (Scene) + 4 unknowns = 20% -> FAIL
        content.write_text(
            "`Scene` loads. `FakeClass.go` does. `Blargh` helps. `Nonexistent` runs. `NotReal` works.",
            encoding="utf-8",
        )
        ratio, matched, total, ungrounded = ground_check.compute_grounding_ratio(content, api_path)
        assert total == 5
        assert matched == 1
        assert ratio < ground_check.WARN_THRESHOLD
        assert len(ungrounded) == 4

    def test_no_identifiers_returns_pass(self, tmp_path):
        _make_knowledge(tmp_path)
        api_path = ground_check.KNOWLEDGE_ROOT / "fake" / "python" / "merged" / "api_surface.json"
        content = tmp_path / "page.md"
        content.write_text("This page has no backtick identifiers at all.", encoding="utf-8")
        ratio, matched, total, ungrounded = ground_check.compute_grounding_ratio(content, api_path)
        assert ratio == 1.0
        assert total == 0
        assert matched == 0
        assert ungrounded == []

    def test_frontmatter_identifiers_are_stripped(self, tmp_path):
        _make_knowledge(tmp_path)
        api_path = ground_check.KNOWLEDGE_ROOT / "fake" / "python" / "merged" / "api_surface.json"
        content = tmp_path / "page.md"
        # Frontmatter contains `UnknownFrontmatterRef` — should NOT count
        content.write_text(
            "---\ntitle: test\ndescription: '`UnknownFrontmatterRef`'\n---\n\n`Scene` is the main class.\n",
            encoding="utf-8",
        )
        ratio, matched, total, ungrounded = ground_check.compute_grounding_ratio(content, api_path)
        assert total == 1
        assert matched == 1
        assert ratio == 1.0

    def test_dotted_identifier_partial_match(self, tmp_path):
        _make_knowledge(tmp_path)
        api_path = ground_check.KNOWLEDGE_ROOT / "fake" / "python" / "merged" / "api_surface.json"
        content = tmp_path / "page.md"
        # `Scene.open` — "Scene" is known -> matched
        content.write_text("`Scene.open` returns the scene object.", encoding="utf-8")
        ratio, matched, total, ungrounded = ground_check.compute_grounding_ratio(content, api_path)
        assert matched == 1
        assert total == 1

    def test_missing_api_surface_raises(self, tmp_path):
        missing = tmp_path / "no_such" / "api_surface.json"
        content = tmp_path / "page.md"
        content.write_text("`Scene` is great.", encoding="utf-8")
        with pytest.raises(FileNotFoundError):
            ground_check.compute_grounding_ratio(content, missing)


# ---------------------------------------------------------------------------
# Integration: main() exit codes
# ---------------------------------------------------------------------------

class TestMain:
    """Test main() argument parsing and exit codes via configure() seam."""

    def test_pass_exit_code_all_matched(self, tmp_path):
        _make_knowledge(tmp_path)
        content = tmp_path / "page.md"
        # All identifiers are known: ratio = 100%
        content.write_text(
            "Use `Scene` to load. Call `Scene.open` and `Scene.save`.",
            encoding="utf-8",
        )
        result = ground_check.main(["fake", "python", str(content)])
        assert result == 0

    def test_warn_exit_code_75_pct(self, tmp_path):
        _make_knowledge(tmp_path)
        content = tmp_path / "page.md"
        # 3 known + 1 unknown = 75%
        content.write_text(
            "`Scene` loads. `Scene.open` opens. `Scene.save` saves. `FakeThing` fakes.",
            encoding="utf-8",
        )
        result = ground_check.main(["fake", "python", str(content)])
        assert result == 1

    def test_fail_exit_code_20_pct(self, tmp_path):
        _make_knowledge(tmp_path)
        content = tmp_path / "page.md"
        # 1 known + 4 unknowns = 20%
        content.write_text(
            "`Scene` loads. `FakeA.go` runs. `FakeB` works. `FakeC` helps. `FakeD` does.",
            encoding="utf-8",
        )
        result = ground_check.main(["fake", "python", str(content)])
        assert result == 2

    def test_no_identifiers_is_pass(self, tmp_path):
        _make_knowledge(tmp_path)
        content = tmp_path / "page.md"
        content.write_text("This page has no identifiers — just plain English prose.", encoding="utf-8")
        result = ground_check.main(["fake", "python", str(content)])
        assert result == 0

    def test_missing_content_file_returns_2(self, tmp_path):
        _make_knowledge(tmp_path)
        result = ground_check.main(["fake", "python", str(tmp_path / "nonexistent.md")])
        assert result == 2

    def test_missing_knowledge_returns_2(self, tmp_path):
        content = tmp_path / "page.md"
        content.write_text("`Scene` is great.", encoding="utf-8")
        ground_check.configure(knowledge_root=tmp_path / "no_such_knowledge")
        result = ground_check.main(["fake", "python", str(content)])
        assert result == 2
