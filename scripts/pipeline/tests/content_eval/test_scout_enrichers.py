"""Tests for scout_enrichers docstring extraction."""

# sys.path is set by tests/conftest.py — no manual insert needed here.
from scout_enrichers._javadoc import _extract_javadoc_comment, enrich_javadoc
from scout_enrichers._doxygen import _extract_doxygen_comment, enrich_doxygen
from scout_enrichers._xml_doc import _extract_xml_doc_comment, enrich_xml_doc
from scout_enrichers import enrich_classes


# ---------------------------------------------------------------------------
# Javadoc
# ---------------------------------------------------------------------------

JAVA_SOURCE = """\
package com.aspose.threed;

/**
 * Represents a 3D scene with nodes and meshes.
 * @author Aspose
 */
public class Scene {

    /**
     * Opens a scene from file.
     * @param filename the file to load
     * @return true if successful
     */
    public boolean open(String filename) {
        return true;
    }
}
"""


class TestJavadocExtraction:
    def test_class_docstring(self, tmp_path):
        lines = JAVA_SOURCE.splitlines()
        # "public class Scene" is at line index 6
        doc, _ = _extract_javadoc_comment(lines, 6)
        assert "Represents a 3D scene" in doc
        assert "@author" not in doc

    def test_method_docstring(self, tmp_path):
        lines = JAVA_SOURCE.splitlines()
        # "public boolean open" is at line index 13
        doc, _ = _extract_javadoc_comment(lines, 13)
        assert "Opens a scene" in doc
        assert "@param" not in doc

    def test_enricher(self, tmp_path):
        (tmp_path / "Scene.java").write_text(JAVA_SOURCE)
        classes = [{"name": "Scene", "file": "Scene.java", "doc": "",
                    "methods": [{"name": "open", "doc": ""}]}]
        count = enrich_javadoc(classes, tmp_path)
        assert count == 2
        assert "Represents a 3D scene" in classes[0]["doc"]
        assert "Opens a scene" in classes[0]["methods"][0]["doc"]

    def test_skip_existing_doc(self, tmp_path):
        (tmp_path / "Scene.java").write_text(JAVA_SOURCE)
        classes = [{"name": "Scene", "file": "Scene.java",
                    "doc": "Already documented", "methods": []}]
        count = enrich_javadoc(classes, tmp_path)
        assert count == 0
        assert classes[0]["doc"] == "Already documented"

    def test_no_javadoc(self):
        lines = ["public class Empty {", "}"]
        doc, dep_reason = _extract_javadoc_comment(lines, 0)
        assert doc == ""
        assert dep_reason is None


# ---------------------------------------------------------------------------
# Javadoc @deprecated capture (Task 15, mission-plan-the-end-to-end-vast-
# hejlsberg.md §9.10, closes G9)
# ---------------------------------------------------------------------------

JAVA_SOURCE_DEPRECATED_METHOD = """\
public class Scene {
    /**
     * Opens a scene from file.
     * @deprecated Use openFile(Path) instead.
     * @param filename the file to load
     */
    public boolean open(String filename) {
        return true;
    }
}
"""

JAVA_SOURCE_DEPRECATED_BARE = """\
public class Scene {
    /**
     * Opens a scene from file.
     * @deprecated
     */
    public boolean open(String filename) {
        return true;
    }
}
"""


class TestJavadocDeprecatedCapture:
    def test_deprecated_tag_with_reason_captured_and_excluded_from_doc(self):
        lines = JAVA_SOURCE_DEPRECATED_METHOD.splitlines()
        doc, dep_reason = _extract_javadoc_comment(lines, 6)
        assert "Opens a scene" in doc
        assert "@deprecated" not in doc
        assert dep_reason == "Use openFile(Path) instead."

    def test_bare_deprecated_tag_yields_empty_reason_not_none(self):
        lines = JAVA_SOURCE_DEPRECATED_BARE.splitlines()
        _doc, dep_reason = _extract_javadoc_comment(lines, 5)
        assert dep_reason == ""  # found, no text -- distinct from None (not found)

    def test_enrich_javadoc_sets_deprecated_true_and_reason(self, tmp_path):
        (tmp_path / "Scene.java").write_text(JAVA_SOURCE_DEPRECATED_METHOD)
        classes = [{"name": "Scene", "file": "Scene.java", "doc": "",
                    "methods": [{"name": "open", "doc": "", "deprecated": False}]}]
        enrich_javadoc(classes, tmp_path)
        method = classes[0]["methods"][0]
        assert method["deprecated"] is True
        assert method["deprecated_reason"] == "Use openFile(Path) instead."

    def test_enrich_javadoc_deprecated_capture_runs_even_when_doc_already_set(self, tmp_path):
        """A member whose doc was already populated by an earlier pass must
        still pick up @deprecated on a later re-scout -- the doc-text guard
        and the deprecated-capture must be independent (see _javadoc.py's own
        comment on why the old `if md.get("doc"): continue` early-skip was
        removed)."""
        (tmp_path / "Scene.java").write_text(JAVA_SOURCE_DEPRECATED_METHOD)
        classes = [{"name": "Scene", "file": "Scene.java", "doc": "already set",
                    "methods": [{"name": "open", "doc": "already set"}]}]
        enrich_javadoc(classes, tmp_path)
        assert classes[0]["doc"] == "already set"  # unchanged, per existing contract
        assert classes[0]["methods"][0]["doc"] == "already set"  # unchanged
        assert classes[0]["methods"][0]["deprecated"] is True  # still captured
        assert classes[0]["methods"][0]["deprecated_reason"] == "Use openFile(Path) instead."

    def test_no_deprecated_tag_leaves_field_unset(self, tmp_path):
        (tmp_path / "Scene.java").write_text(JAVA_SOURCE)
        classes = [{"name": "Scene", "file": "Scene.java", "doc": "",
                    "methods": [{"name": "open", "doc": ""}]}]
        enrich_javadoc(classes, tmp_path)
        assert "deprecated" not in classes[0]
        assert "deprecated" not in classes[0]["methods"][0]


# ---------------------------------------------------------------------------
# Doxygen
# ---------------------------------------------------------------------------

CPP_SOURCE = """\
#pragma once

/// Represents a 3D scene with nodes and meshes.
/// Supports loading and saving various formats.
class Scene {
public:
    /**
     * Opens a scene from file.
     * @param filename the file path
     */
    bool open(const std::string& filename);
};
"""


class TestDoxygenExtraction:
    def test_triple_slash(self):
        lines = CPP_SOURCE.splitlines()
        # "class Scene" is at index 4
        doc = _extract_doxygen_comment(lines, 4)
        assert "Represents a 3D scene" in doc
        assert "Supports loading" in doc

    def test_block_comment(self):
        lines = CPP_SOURCE.splitlines()
        # "bool open" is at index 10
        doc = _extract_doxygen_comment(lines, 10)
        assert "Opens a scene" in doc
        assert "@param" not in doc

    def test_enricher(self, tmp_path):
        (tmp_path / "Scene.h").write_text(CPP_SOURCE)
        classes = [{"name": "Scene", "file": "Scene.h", "doc": "",
                    "methods": [{"name": "open", "doc": ""}]}]
        count = enrich_doxygen(classes, tmp_path)
        assert count == 2

    def test_brief_tag_stripped(self):
        lines = ["/// @brief A short description.", "class Foo {"]
        doc = _extract_doxygen_comment(lines, 1)
        assert doc == "A short description."


# ---------------------------------------------------------------------------
# XML doc
# ---------------------------------------------------------------------------

CS_SOURCE = """\
namespace Aspose.ThreeD
{
    /// <summary>
    /// Represents a 3D scene with nodes and meshes.
    /// </summary>
    public class Scene
    {
        /// <summary>
        /// Opens a scene from file.
        /// </summary>
        public bool Open(string filename)
        {
            return true;
        }
    }
}
"""


class TestXmlDocExtraction:
    def test_class_docstring(self):
        lines = CS_SOURCE.splitlines()
        # "public class Scene" is at index 5
        doc, dep_reason = _extract_xml_doc_comment(lines, 5)
        assert "Represents a 3D scene" in doc
        assert "<summary>" not in doc
        assert dep_reason is None

    def test_method_docstring(self):
        lines = CS_SOURCE.splitlines()
        # "public bool Open" is at index 10
        doc, _ = _extract_xml_doc_comment(lines, 10)
        assert "Opens a scene" in doc

    def test_enricher(self, tmp_path):
        (tmp_path / "Scene.cs").write_text(CS_SOURCE)
        classes = [{"name": "Scene", "file": "Scene.cs", "doc": "",
                    "methods": [{"name": "Open", "doc": ""}]}]
        count = enrich_xml_doc(classes, tmp_path)
        assert count == 2

    def test_attribute_lines_skipped(self):
        lines = [
            "    /// <summary>",
            "    /// Gets the name.",
            "    /// </summary>",
            "    [Obsolete]",
            "    public string Name { get; }",
        ]
        doc, dep_reason = _extract_xml_doc_comment(lines, 4)
        assert "Gets the name" in doc
        # Task 15 (§9.10, closes G9): a bare [Obsolete] (no reason argument)
        # is still captured as a real signal -- "" (found, no reason text),
        # not None (not found at all).
        assert dep_reason == ""


# ---------------------------------------------------------------------------
# XML-doc [Obsolete] capture (Task 15, mission-plan-the-end-to-end-vast-
# hejlsberg.md §9.10, closes G9)
# ---------------------------------------------------------------------------

CS_SOURCE_OBSOLETE_METHOD = """\
public class Scene {
    /// <summary>
    /// Opens a scene from file.
    /// </summary>
    [Obsolete("Use OpenFile(Path) instead.")]
    public bool Open(string filename) {
        return true;
    }
}
"""


class TestXmlDocDeprecatedCapture:
    def test_obsolete_with_reason_captured(self):
        lines = CS_SOURCE_OBSOLETE_METHOD.splitlines()
        # "public bool Open" is at index 5
        doc, dep_reason = _extract_xml_doc_comment(lines, 5)
        assert "Opens a scene" in doc
        assert dep_reason == "Use OpenFile(Path) instead."

    def test_enrich_xml_doc_sets_deprecated_true_and_reason(self, tmp_path):
        (tmp_path / "Scene.cs").write_text(CS_SOURCE_OBSOLETE_METHOD)
        classes = [{"name": "Scene", "file": "Scene.cs", "doc": "",
                    "methods": [{"name": "Open", "doc": "", "deprecated": False}]}]
        enrich_xml_doc(classes, tmp_path)
        method = classes[0]["methods"][0]
        assert method["deprecated"] is True
        assert method["deprecated_reason"] == "Use OpenFile(Path) instead."

    def test_enrich_xml_doc_deprecated_capture_runs_even_when_doc_already_set(self, tmp_path):
        (tmp_path / "Scene.cs").write_text(CS_SOURCE_OBSOLETE_METHOD)
        classes = [{"name": "Scene", "file": "Scene.cs", "doc": "already set",
                    "methods": [{"name": "Open", "doc": "already set"}]}]
        enrich_xml_doc(classes, tmp_path)
        assert classes[0]["methods"][0]["doc"] == "already set"
        assert classes[0]["methods"][0]["deprecated"] is True
        assert classes[0]["methods"][0]["deprecated_reason"] == "Use OpenFile(Path) instead."

    def test_no_obsolete_attribute_leaves_field_unset(self, tmp_path):
        (tmp_path / "Scene.cs").write_text(CS_SOURCE)
        classes = [{"name": "Scene", "file": "Scene.cs", "doc": "",
                    "methods": [{"name": "Open", "doc": ""}]}]
        enrich_xml_doc(classes, tmp_path)
        assert "deprecated" not in classes[0]
        assert "deprecated" not in classes[0]["methods"][0]


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

class TestEnrichDispatch:
    def test_java_dispatch(self, tmp_path):
        (tmp_path / "Scene.java").write_text(JAVA_SOURCE)
        classes = [{"name": "Scene", "file": "Scene.java", "doc": "",
                    "methods": []}]
        count = enrich_classes(classes, tmp_path, "java")
        assert count >= 1

    def test_python_no_enricher(self, tmp_path):
        classes = [{"name": "Foo", "file": "foo.py", "doc": "",
                    "methods": []}]
        count = enrich_classes(classes, tmp_path, "python")
        assert count == 0

    def test_unknown_platform(self, tmp_path):
        classes = [{"name": "Foo", "file": "foo.go", "doc": "",
                    "methods": []}]
        count = enrich_classes(classes, tmp_path, "go")
        assert count == 0
