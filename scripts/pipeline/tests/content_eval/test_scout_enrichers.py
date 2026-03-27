"""Tests for scout_enrichers docstring extraction."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts" / "pipeline"))

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
        doc = _extract_javadoc_comment(lines, 6)
        assert "Represents a 3D scene" in doc
        assert "@author" not in doc

    def test_method_docstring(self, tmp_path):
        lines = JAVA_SOURCE.splitlines()
        # "public boolean open" is at line index 13
        doc = _extract_javadoc_comment(lines, 13)
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
        doc = _extract_javadoc_comment(lines, 0)
        assert doc == ""


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
        doc = _extract_xml_doc_comment(lines, 5)
        assert "Represents a 3D scene" in doc
        assert "<summary>" not in doc

    def test_method_docstring(self):
        lines = CS_SOURCE.splitlines()
        # "public bool Open" is at index 10
        doc = _extract_xml_doc_comment(lines, 10)
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
        doc = _extract_xml_doc_comment(lines, 4)
        assert "Gets the name" in doc


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
