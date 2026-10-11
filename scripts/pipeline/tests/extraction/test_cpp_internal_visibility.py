"""HARDEN-cpp-internal-collision (MT012): C++-only vendor-path detection for
`include/internal/`.

Found live while generating pdf/cpp's reference pages: batch_reference.py
refused (correctly) to generate 13 pages for classes like `DecodedImage`,
`Options`, `Point`, and `Rectangle` because the SAME short name is
independently reused across many unrelated files under `include/internal/`
(e.g. `internal/bmp_decoder.hpp`, `internal/png_decoder.hpp`,
`internal/tiff_decoder.hpp` each define their own private `struct
DecodedImage`) -- these are genuinely private implementation details,
unreachable from the library's public `#include <aspose/pdf/...>` surface.

This must NOT affect Java/.NET, where slides/java and slides/net ship real,
already-published reference pages for classes living under an `internal`
package/directory (PptxExporter, OpcPackage, ShapeFactory, etc.) -- that is a
deliberate, different convention this fix must leave untouched.
"""
from pathlib import Path

from extraction.api_surface import _detect_vendor_files


class TestCppInternalVendorDetection:
    def test_cpp_internal_dir_is_vendor(self, tmp_path):
        pkg_root = tmp_path / "include"
        internal_dir = pkg_root / "internal"
        internal_dir.mkdir(parents=True)
        f = internal_dir / "bmp_decoder.hpp"
        f.write_text("struct DecodedImage {};\n", encoding="utf-8")

        vendor = _detect_vendor_files([f], pkg_root, language="cpp")
        assert f in vendor

    def test_cpp_public_dir_not_vendor(self, tmp_path):
        pkg_root = tmp_path / "include"
        public_dir = pkg_root / "aspose" / "pdf"
        public_dir.mkdir(parents=True)
        f = public_dir / "document.hpp"
        f.write_text("class Document {};\n", encoding="utf-8")

        vendor = _detect_vendor_files([f], pkg_root, language="cpp")
        assert f not in vendor

    def test_java_internal_package_not_vendor(self, tmp_path):
        """Regression guard: Java's 'internal' package convention (slides/java
        ships real reference pages for PptxExporter/OpcPackage/etc. under
        org.aspose.slides.foss.internal) must be completely unaffected."""
        pkg_root = tmp_path / "src"
        internal_dir = pkg_root / "org" / "aspose" / "slides" / "foss" / "internal"
        internal_dir.mkdir(parents=True)
        f = internal_dir / "PptxExporter.java"
        f.write_text("class PptxExporter {}\n", encoding="utf-8")

        vendor = _detect_vendor_files([f], pkg_root, language="java")
        assert f not in vendor

    def test_default_no_language_unaffected(self, tmp_path):
        """Regression guard: omitting language= (existing callers/tests) must
        keep the pre-fix behavior exactly -- 'internal' is not vendor unless
        language=='cpp' is passed explicitly."""
        pkg_root = tmp_path / "include"
        internal_dir = pkg_root / "internal"
        internal_dir.mkdir(parents=True)
        f = internal_dir / "bmp_decoder.hpp"
        f.write_text("struct DecodedImage {};\n", encoding="utf-8")

        vendor = _detect_vendor_files([f], pkg_root)
        assert f not in vendor

    def test_existing_vendor_segments_still_work_for_cpp(self, tmp_path):
        """Regression guard: the pre-existing vendor/third_party detection is
        unaffected by the new cpp-only segment addition."""
        pkg_root = tmp_path / "include"
        vendor_dir = pkg_root / "third_party"
        vendor_dir.mkdir(parents=True)
        f = vendor_dir / "zlib.hpp"
        f.write_text("class Zlib {};\n", encoding="utf-8")

        vendor = _detect_vendor_files([f], pkg_root, language="cpp")
        assert f in vendor

    def test_underscore_internal_still_exempt_for_cpp(self, tmp_path):
        """Regression guard: the pre-existing _internal/ (leading underscore)
        exemption is unaffected -- only the bare 'internal' (no underscore)
        segment is newly cpp-vendor."""
        pkg_root = tmp_path / "include"
        exempt_dir = pkg_root / "_internal"
        exempt_dir.mkdir(parents=True)
        f = exempt_dir / "helper.hpp"
        f.write_text("class Helper {};\n", encoding="utf-8")

        vendor = _detect_vendor_files([f], pkg_root, language="cpp")
        assert f not in vendor
