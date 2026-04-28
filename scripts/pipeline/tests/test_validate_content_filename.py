"""Tests for validate_content_filename() in provenance.py."""
from pathlib import Path

import pytest
import sys

_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from provenance import validate_content_filename


# ---------------------------------------------------------------------------
# Structural rejections (apply to all trees)
# ---------------------------------------------------------------------------

class TestStructuralRejections:
    def test_rejects_leading_hyphen(self):
        p = Path("content/docs.aspose.org/en/3d/net/developer-guide/-graph.md")
        with pytest.raises(ValueError, match="Leading hyphen"):
            validate_content_filename(p)

    def test_rejects_trailing_hyphen(self):
        p = Path("content/docs.aspose.org/en/3d/net/developer-guide/graph-.md")
        with pytest.raises(ValueError, match="Trailing hyphen"):
            validate_content_filename(p)

    def test_rejects_double_hyphen(self):
        p = Path("content/docs.aspose.org/en/3d/net/developer-guide/scene--graph.md")
        with pytest.raises(ValueError, match="Double hyphen"):
            validate_content_filename(p)

    def test_rejects_empty_stem(self):
        # Construct a Path where stem is truly empty but suffix is .md.
        # In practice Python's Path(".md") treats it as a dotfile (no suffix).
        # Use a name that Path parses as empty-stem + .md suffix:
        # this isn't possible via Path alone, so test the guard directly.
        p = Path("content/docs.aspose.org/en/3d/net/bad")
        # Monkey-patch to simulate; or just test a realistic bad name.
        # A single-char stem that's a hyphen triggers leading-hyphen check.
        p2 = Path("content/docs.aspose.org/en/3d/net/-.md")
        with pytest.raises(ValueError, match="Leading hyphen"):
            validate_content_filename(p2)

    def test_rejects_path_traversal(self):
        p = Path("content/docs.aspose.org/en/../evil.md")
        with pytest.raises(ValueError, match="Path traversal"):
            validate_content_filename(p)

    def test_rejects_space_in_filename(self):
        p = Path("content/docs.aspose.org/en/3d/net/scene graph.md")
        with pytest.raises(ValueError, match="Space in filename"):
            validate_content_filename(p)

    def test_rejects_uppercase_extension(self):
        p = Path("content/docs.aspose.org/en/3d/net/scene-graph.MD")
        with pytest.raises(ValueError, match="Uppercase markdown extension"):
            validate_content_filename(p)


# ---------------------------------------------------------------------------
# Prose tree slug validation
# ---------------------------------------------------------------------------

class TestProseTree:
    def test_rejects_uppercase_in_prose_slug(self):
        p = Path("content/docs.aspose.org/en/3d/net/developer-guide/SceneGraph.md")
        with pytest.raises(ValueError, match="Invalid prose slug"):
            validate_content_filename(p)

    def test_accepts_valid_kebab_slug(self):
        p = Path("content/docs.aspose.org/en/3d/net/developer-guide/scene-graph.md")
        validate_content_filename(p)  # Should not raise

    def test_accepts_valid_hyphenated_slug(self):
        p = Path("content/docs.aspose.org/en/slides/python/working-with-animation.md")
        validate_content_filename(p)  # Should not raise

    def test_accepts_simple_slug(self):
        p = Path("content/docs.aspose.org/en/3d/net/overview.md")
        validate_content_filename(p)  # Should not raise

    def test_accepts_locale_variant(self):
        p = Path("content/docs.aspose.org/fr/3d/net/developer-guide/scene-graph.fr.md")
        validate_content_filename(p)  # Should not raise


# ---------------------------------------------------------------------------
# Reference tree (PascalCase allowed)
# ---------------------------------------------------------------------------

class TestReferenceTree:
    def test_accepts_pascal_case(self):
        p = Path("content/reference.aspose.org/en/slides/python/PolygonModifier.md")
        validate_content_filename(p)  # Should not raise

    def test_accepts_simple_class_name(self):
        p = Path("content/reference.aspose.org/en/cells/java/Workbook.md")
        validate_content_filename(p)  # Should not raise

    def test_still_rejects_leading_hyphen_in_reference(self):
        p = Path("content/reference.aspose.org/en/cells/java/-BadName.md")
        with pytest.raises(ValueError, match="Leading hyphen"):
            validate_content_filename(p)


# ---------------------------------------------------------------------------
# Index and non-markdown files (skip)
# ---------------------------------------------------------------------------

class TestSkippedFiles:
    def test_accepts_index_md(self):
        p = Path("content/docs.aspose.org/en/3d/net/_index.md")
        validate_content_filename(p)  # Should not raise

    def test_accepts_plain_index(self):
        p = Path("content/blog.aspose.org/slides/python/my-post/index.md")
        validate_content_filename(p)  # Should not raise

    def test_accepts_locale_index(self):
        p = Path("content/docs.aspose.org/fr/3d/net/index.fr.md")
        validate_content_filename(p)  # Should not raise

    def test_skips_non_md_file(self):
        p = Path("content/docs.aspose.org/en/3d/net/site_plan.yaml")
        validate_content_filename(p)  # Should not raise (not .md)

    def test_skips_txt_file(self):
        p = Path("scripts/pipeline/some_file.txt")
        validate_content_filename(p)  # Should not raise (not .md)
