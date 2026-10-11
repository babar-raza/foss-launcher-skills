"""Tests for slug sanitization and write-order enforcement in batch_reference.

TC-01: Verifies that:
  - Class names with special characters are sanitized to filesystem-safe slugs
  - PEP 8 Python names pass through unchanged
  - knowledge.available=False causes sys.exit(1) before any page writes
  - Invalid kind_arg raises ValueError
"""
import json
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Import helpers
# ---------------------------------------------------------------------------

_PIPELINE_ROOT = Path(__file__).resolve().parent.parent
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = _PIPELINE_ROOT / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))
_CMD_CONTENT = _PIPELINE_ROOT / "commands" / "content"
if str(_CMD_CONTENT) not in sys.path:
    sys.path.insert(0, str(_CMD_CONTENT))

import batch_reference


# ---------------------------------------------------------------------------
# Slug sanitization unit tests
# ---------------------------------------------------------------------------

class TestSanitizeSlug:
    """Verify _sanitize_slug handles all edge cases."""

    def test_pep8_name_unchanged(self):
        assert batch_reference._sanitize_slug("Font") == "Font"

    def test_pep8_underscore_unchanged(self):
        assert batch_reference._sanitize_slug("FontLoader") == "FontLoader"

    def test_dot_replaced(self):
        assert batch_reference._sanitize_slug("Outer.Inner") == "Outer_Inner"

    def test_colon_replaced(self):
        # :: is a single run of unsafe chars, so collapses to one _
        assert batch_reference._sanitize_slug("ns::Class") == "ns_Class"

    def test_brackets_replaced(self):
        assert batch_reference._sanitize_slug("List[int]") == "List_int_"

    def test_slash_replaced(self):
        assert batch_reference._sanitize_slug("path/to/Class") == "path_to_Class"

    def test_backslash_replaced(self):
        assert batch_reference._sanitize_slug("ns\\Class") == "ns_Class"

    def test_multiple_special_chars(self):
        result = batch_reference._sanitize_slug("A.B::C[D]")
        assert "." not in result
        assert ":" not in result
        assert "[" not in result
        assert "]" not in result

    def test_question_mark_replaced(self):
        assert batch_reference._sanitize_slug("Nullable?") == "Nullable_"

    def test_angle_brackets_replaced(self):
        assert batch_reference._sanitize_slug("Generic<T>") == "Generic_T_"

    def test_pipe_replaced(self):
        assert batch_reference._sanitize_slug("Union|Type") == "Union_Type"

    def test_empty_string(self):
        assert batch_reference._sanitize_slug("") == ""

    def test_already_safe_with_digits(self):
        assert batch_reference._sanitize_slug("CMapFormat4") == "CMapFormat4"


# ---------------------------------------------------------------------------
# Kind filter validation
# ---------------------------------------------------------------------------

class TestKindFilterValidation:
    """Verify _apply_kind_filter rejects invalid kind_arg."""

    def test_valid_all(self):
        entries = [{"name": "A", "kind": "class_definition"}]
        result = batch_reference._apply_kind_filter(entries, "all", "python")
        assert len(result) == 1

    def test_valid_enum(self):
        entries = [{"name": "A", "kind": "class_definition"}]
        result = batch_reference._apply_kind_filter(entries, "enum", "python")
        assert len(result) == 0

    def test_valid_class(self):
        entries = [{"name": "A", "kind": "class_definition"}]
        result = batch_reference._apply_kind_filter(entries, "class", "python")
        assert len(result) == 1

    def test_invalid_kind_arg_raises(self):
        entries = [{"name": "A", "kind": "class_definition"}]
        with pytest.raises(ValueError, match="Invalid kind_arg"):
            batch_reference._apply_kind_filter(entries, "invalid", "python")


# ---------------------------------------------------------------------------
# Knowledge availability before writes (LH-02 enforcement)
# ---------------------------------------------------------------------------

class TestKnowledgeAvailabilityGate:
    """Verify batch_reference exits before writes when knowledge unavailable."""

    def test_missing_api_surface_exits(self, tmp_path):
        """Missing api_surface.json must cause sys.exit(1) before any writes."""
        merged = tmp_path / "knowledge" / "test" / "python" / "merged"
        merged.mkdir(parents=True)

        # model.yaml present but NO api_surface.json
        (merged / "model.yaml").write_text(
            "family: test\nplatform: python\nstale_since: null\n"
            "repo_sha: abc123\nversion: 1.0.0\n",
            encoding="utf-8",
        )

        content_dir = tmp_path / "content" / "reference.aspose.org" / "en"
        content_dir.mkdir(parents=True)

        batch_reference.configure(
            repo_root=tmp_path,
            knowledge_root=tmp_path / "knowledge",
            content_root=content_dir,
        )

        with pytest.raises(SystemExit) as exc_info:
            batch_reference.run("test", "python", run_id="TEST-RUN")

        assert exc_info.value.code == 1

        # No pages should exist
        output = content_dir / "test" / "python"
        if output.exists():
            generated = list(output.glob("*.md"))
            assert len(generated) == 0, f"Pages written despite missing knowledge: {generated}"

    def test_knowledge_available_check_exists_in_code(self):
        """Verify the knowledge.available check is present before the write loop."""
        import inspect
        source = inspect.getsource(batch_reference.run)
        # The knowledge.available check must appear before the main generation loop
        avail_pos = source.find("if not knowledge.available:")
        loop_pos = source.find("for i, entry in enumerate(to_write")
        assert avail_pos != -1, "knowledge.available check not found in run()"
        assert avail_pos < loop_pos, (
            "knowledge.available check must appear BEFORE the generation loop"
        )
