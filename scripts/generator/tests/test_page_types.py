"""
TC-W4-001: Tests for detect_page_type() function.

Tests all 6 page type constants across all 5 subdomains.

Run with:
    .venv/Scripts/python -m pytest scripts/generator/tests/test_page_types.py -v
"""
import importlib.util
import os

# Load the hyphen-named module via importlib
_GEN_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_GEN_FILE = os.path.join(_GEN_DIR, "llms-generator.py")
_spec = importlib.util.spec_from_file_location("llms_generator", _GEN_FILE)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

detect_page_type = _mod.detect_page_type
PAGE_TYPE_REFERENCE = _mod.PAGE_TYPE_REFERENCE
PAGE_TYPE_DOCS      = _mod.PAGE_TYPE_DOCS
PAGE_TYPE_KB        = _mod.PAGE_TYPE_KB
PAGE_TYPE_BLOG      = _mod.PAGE_TYPE_BLOG
PAGE_TYPE_PRODUCT   = _mod.PAGE_TYPE_PRODUCT
PAGE_TYPE_INDEX     = _mod.PAGE_TYPE_INDEX
PAGE_TYPE_UNKNOWN   = _mod.PAGE_TYPE_UNKNOWN


class TestDetectPageType:
    def test_reference_class_page(self):
        result = detect_page_type(
            "content/reference.aspose.org/en/pdf/net/Document.md",
            "Document.md",
            "reference.aspose.org"
        )
        assert result == PAGE_TYPE_REFERENCE

    def test_reference_lowercase_page(self):
        # e.g. 'camera.md' — still reference subdomain
        result = detect_page_type(
            "content/reference.aspose.org/en/3d/java/camera.md",
            "camera.md",
            "reference.aspose.org"
        )
        assert result == PAGE_TYPE_REFERENCE

    def test_docs_page(self):
        result = detect_page_type(
            "content/docs.aspose.org/en/pdf/net/getting-started/quickstart.md",
            "quickstart.md",
            "docs.aspose.org"
        )
        assert result == PAGE_TYPE_DOCS

    def test_kb_page(self):
        result = detect_page_type(
            "content/kb.aspose.org/en/pdf/net/how-to-extract-text.md",
            "how-to-extract-text.md",
            "kb.aspose.org"
        )
        assert result == PAGE_TYPE_KB

    def test_blog_post(self):
        result = detect_page_type(
            "content/blog.aspose.org/pdf/net/pdf-release-notes/index.md",
            "index.md",
            "blog.aspose.org"
        )
        # index.md is detected as INDEX type (not BLOG — index rule fires first)
        assert result == PAGE_TYPE_INDEX

    def test_blog_non_index(self):
        # Blog uses file-based layout; normal .md pages (non-index) are BLOG
        result = detect_page_type(
            "content/blog.aspose.org/pdf/net/announcing-pdf-26.md",
            "announcing-pdf-26.md",
            "blog.aspose.org"
        )
        assert result == PAGE_TYPE_BLOG

    def test_product_page(self):
        result = detect_page_type(
            "content/products.aspose.org/en/pdf/net.md",
            "net.md",
            "products.aspose.org"
        )
        assert result == PAGE_TYPE_PRODUCT

    def test_index_file_underscore(self):
        result = detect_page_type(
            "content/reference.aspose.org/en/pdf/net/_index.md",
            "_index.md",
            "reference.aspose.org"
        )
        assert result == PAGE_TYPE_INDEX

    def test_index_file_plain(self):
        result = detect_page_type(
            "content/docs.aspose.org/en/pdf/net/getting-started/index.md",
            "index.md",
            "docs.aspose.org"
        )
        assert result == PAGE_TYPE_INDEX

    def test_unknown_subdomain(self):
        result = detect_page_type(
            "content/other.aspose.org/en/foo.md",
            "foo.md",
            "other.aspose.org"
        )
        assert result == PAGE_TYPE_UNKNOWN

    def test_all_constants_are_distinct(self):
        types = {
            PAGE_TYPE_REFERENCE, PAGE_TYPE_DOCS, PAGE_TYPE_KB,
            PAGE_TYPE_BLOG, PAGE_TYPE_PRODUCT, PAGE_TYPE_INDEX, PAGE_TYPE_UNKNOWN
        }
        assert len(types) == 7, "Page type constants must all be distinct"
