"""
Unit tests for scripts/generator/llms-generator.py

Each test group maps to one of the 9 production fixes. Run with:
    python -m pytest scripts/generator/tests/ -v
"""
import importlib.util
import os
import sys
import json

import pytest

# Load the hyphen-named module via importlib (regular import can't handle hyphens)
_GEN_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_GEN_FILE = os.path.join(_GEN_DIR, "llms-generator.py")
_spec = importlib.util.spec_from_file_location("llms_generator", _GEN_FILE)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

extract_h1_and_first_sentence = _mod.extract_h1_and_first_sentence
extract_description           = _mod.extract_description
make_page_url                 = _mod.make_page_url
render_llms_tree              = _mod.render_llms_tree
build_llms_tree               = _mod.build_llms_tree
is_index_file                 = _mod.is_index_file
sanitize_markdown             = _mod.sanitize_markdown
clean_title_from_filename     = _mod.clean_title_from_filename
SiteMapping                   = _mod.SiteMapping


# ---------------------------------------------------------------------------
# Fix 8: H1-only regex  (was matching ## headings)
# ---------------------------------------------------------------------------

class TestExtractH1:
    """Fix 8 — regex must match ONLY single-# headings."""

    def test_single_hash_matched(self):
        md = "# My Page Title\n\nFirst sentence here."
        h1, _ = extract_h1_and_first_sentence(md)
        assert h1 == "My Page Title"

    def test_double_hash_not_matched_as_h1(self):
        """## Related Topics must not be captured as the page H1."""
        md = "## Related Topics\n\n- [Link](url)"
        h1, _ = extract_h1_and_first_sentence(md)
        assert h1 == ""

    def test_treeview_after_body_not_matched(self):
        """Real-world: treeview appended to index page; H1 must come from body."""
        md = "# Open Source File Format Libraries\n\nMIT-licensed SDKs.\n\n## Related Topics\n- [3D](url)"
        h1, _ = extract_h1_and_first_sentence(md)
        assert h1 == "Open Source File Format Libraries"

    def test_h1_with_inline_code(self):
        md = "# Using `Scene.load()` in Python\n\nSome body."
        h1, _ = extract_h1_and_first_sentence(md)
        assert h1 == "Using `Scene.load()` in Python"

    def test_first_sentence_extracted(self):
        md = "# Title\n\nThis is the first sentence. And a second."
        _, sentence = extract_h1_and_first_sentence(md)
        assert sentence == "This is the first sentence."

    def test_first_sentence_skips_list_para(self):
        md = "# Title\n\n- list item\n\nActual first sentence."
        _, sentence = extract_h1_and_first_sentence(md)
        assert sentence == "Actual first sentence."

    def test_empty_content(self):
        h1, sentence = extract_h1_and_first_sentence("")
        assert h1 == "" and sentence == ""


# ---------------------------------------------------------------------------
# Fix 2 + extended fallback: extract_description priority chain
# ---------------------------------------------------------------------------

class TestExtractDescription:
    """Fixes 2 & 9 — description priority chain covers 6 sources."""

    def test_description_field_wins(self):
        yaml_data = {"description": "From description", "summary": "From summary"}
        result = extract_description(yaml_data, "# Title\n\nBody sentence.")
        assert result == "From description"

    def test_summary_fallback(self):
        yaml_data = {"summary": "From summary", "subtitle": "From subtitle"}
        result = extract_description(yaml_data, "# Title\n\nBody sentence.")
        assert result == "From summary"

    def test_subtitle_fallback(self):
        """Fix 4: subtitle field used for docs/kb platform index pages."""
        yaml_data = {"subtitle": "Aspose.3D FOSS for Java"}
        result = extract_description(yaml_data, "")
        assert result == "Aspose.3D FOSS for Java"

    def test_head_description_fallback(self):
        """Products pages use head_description instead of description."""
        yaml_data = {"head_description": "Free MIT-licensed open source libraries."}
        result = extract_description(yaml_data, "")
        assert result == "Free MIT-licensed open source libraries."

    def test_banner_content_fallback(self):
        """Products root page uses banner.content."""
        yaml_data = {"banner": {"content": "MIT-licensed SDKs for working with documents."}}
        result = extract_description(yaml_data, "")
        assert result == "MIT-licensed SDKs for working with documents."

    def test_body_sentence_last_resort(self):
        yaml_data = {}
        result = extract_description(yaml_data, "# Title\n\nFirst body sentence here.")
        assert "First body sentence" in result

    def test_empty_fields_skipped(self):
        """Empty string frontmatter values must not short-circuit the chain."""
        yaml_data = {"description": "", "summary": "", "subtitle": "Correct fallback"}
        result = extract_description(yaml_data, "")
        assert result == "Correct fallback"

    def test_banner_without_content_key(self):
        """banner dict without content key should not crash; falls to body extraction."""
        yaml_data = {"banner": {"enable": True}}
        result = extract_description(yaml_data, "# Title Page\n\nFallback sentence here.")
        assert result  # should fall through to body extraction


# ---------------------------------------------------------------------------
# Fix 3: Extension-free URLs / make_page_url
# ---------------------------------------------------------------------------

class TestMakePageUrl:
    """Fix 3 — URLs must be extension-free; index pages get trailing slash."""

    BASE = "https://blog.aspose.org"

    def test_index_gets_trailing_slash(self):
        url = make_page_url(self.BASE, "3d/python/introducing-foss.md", is_index=True)
        assert url == "https://blog.aspose.org/3d/python/introducing-foss/"
        assert not url.endswith(".md/")

    def test_non_index_no_trailing_slash(self):
        url = make_page_url(self.BASE, "3d/python/feature.md", is_index=False)
        assert url == "https://blog.aspose.org/3d/python/feature"
        assert not url.endswith(".md")

    def test_root_sentinel_bare_url(self):
        """index.md (root sentinel) → bare site root URL."""
        url = make_page_url("https://docs.aspose.org", "index.md", is_index=True)
        assert url == "https://docs.aspose.org/"

    def test_no_md_extension_in_any_output(self):
        for rel, is_idx in [
            ("cells/python/creating-charts.md", False),
            ("cells/python/intro/index.md", True),
            ("index.md", True),
        ]:
            url = make_page_url(self.BASE, rel, is_idx)
            assert ".md" not in url, f"Found .md in {url}"


# ---------------------------------------------------------------------------
# Fix 9: render_llms_tree — conditional description append
# ---------------------------------------------------------------------------

class TestRenderLlmsTree:
    """Fix 9 — empty description must NOT produce trailing ': ' or bare newline."""

    def _make_entry(self, rel_path, title, url, description=""):
        return {
            "rel_output_path": rel_path,
            "title": title,
            "absolute_url": url,
            "description": description,
        }

    def _build(self, entries):
        return build_llms_tree(entries)

    def test_no_trailing_colon_when_empty_desc(self):
        entry = self._make_entry("3d/python/page.md", "My Page", "https://b.org/3d/python/page")
        tree = self._build([entry])
        lines = render_llms_tree(tree, depth=4)
        bullet = next(l for l in lines if "My Page" in l)
        assert not bullet.endswith(": "), f"Trailing colon found: {repr(bullet)}"
        assert ": " not in bullet  # description absent → no colon at all

    def test_colon_present_when_desc_not_empty(self):
        entry = self._make_entry("3d/python/page.md", "My Page",
                                 "https://b.org/3d/python/page",
                                 description="Great library for 3D.")
        tree = self._build([entry])
        lines = render_llms_tree(tree, depth=4)
        bullet = next(l for l in lines if "My Page" in l)
        assert ": Great library for 3D." in bullet

    def test_section_header_no_trailing_newline_on_empty_desc(self):
        entry = self._make_entry("3d.md", "Aspose.3D", "https://b.org/3d/")
        tree = self._build([entry])
        lines = render_llms_tree(tree, depth=2)
        header = next(l for l in lines if "Aspose.3D" in l)
        assert not header.endswith("\n"), f"Trailing newline: {repr(header)}"
        assert "\n\n" not in header

    def test_section_header_includes_desc_when_present(self):
        entry = self._make_entry("3d.md", "Aspose.3D", "https://b.org/3d/",
                                 description="3D scene processing library.")
        tree = self._build([entry])
        lines = render_llms_tree(tree, depth=2)
        header = next(l for l in lines if "Aspose.3D" in l)
        assert "3D scene processing library." in header


# ---------------------------------------------------------------------------
# Fix 7: Output path collision detection (pre-collect pass logic)
# ---------------------------------------------------------------------------

class TestCollisionDetection:
    """Fix 7 — collision resolution must prefer index.md over flat file."""

    def _run_collision_logic(self, files_in_order):
        """
        Simulate the collision-detection block from the pre-collect pass.

        files_in_order: list of (input_path, out_path, is_index_file_flag)

        Returns final file_output_mapping keys.
        """
        file_output_mapping = {}
        out_path_claimed = {}

        for input_path, out_path, is_index in files_in_order:
            if out_path in out_path_claimed:
                existing_input = out_path_claimed[out_path]
                existing_is_index = any(
                    inp == existing_input and idx
                    for inp, _, idx in files_in_order
                    if inp == existing_input
                )
                if is_index and not existing_is_index:
                    del file_output_mapping[existing_input]
                else:
                    continue  # keep existing, skip new

            out_path_claimed[out_path] = input_path
            file_output_mapping[input_path] = (out_path, "display")

        return file_output_mapping

    def test_flat_then_index_prefers_index(self):
        """Index.md arriving after flat file must replace it."""
        flat = "/content/blog/cells/python/intro.md"
        idx = "/content/blog/cells/python/intro/index.md"
        out = "/output/blog/cells/python/intro.md"

        result = self._run_collision_logic([
            (flat, out, False),
            (idx,  out, True),
        ])
        assert idx in result
        assert flat not in result

    def test_index_then_flat_keeps_index(self):
        """Flat file arriving after index.md must be discarded."""
        flat = "/content/blog/cells/python/intro.md"
        idx = "/content/blog/cells/python/intro/index.md"
        out = "/output/blog/cells/python/intro.md"

        result = self._run_collision_logic([
            (idx,  out, True),
            (flat, out, False),
        ])
        assert idx in result
        assert flat not in result

    def test_no_collision_both_survive(self):
        a = "/content/blog/a.md"
        b = "/content/blog/b/index.md"
        out_a = "/output/blog/a.md"
        out_b = "/output/blog/b.md"

        result = self._run_collision_logic([
            (a, out_a, False),
            (b, out_b, True),
        ])
        assert a in result
        assert b in result

    def test_three_way_collision_index_always_wins(self):
        """When three files target same output, the index.md should win
        regardless of arrival order."""
        flat1 = "/content/blog/intro.md"
        flat2 = "/content/blog/intro-copy.md"
        idx   = "/content/blog/intro/index.md"
        out   = "/output/blog/intro.md"

        result = self._run_collision_logic([
            (flat1, out, False),
            (flat2, out, False),   # flat→flat: keep existing flat1
            (idx,   out, True),    # index arrives last → replaces flat1
        ])
        assert idx in result
        assert flat1 not in result
        assert flat2 not in result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_is_index_file(self):
        assert is_index_file("_index.md")
        assert is_index_file("index.md")
        assert is_index_file("INDEX.MD")
        assert not is_index_file("page.md")
        assert not is_index_file("index.es.md")

    def test_sanitize_markdown_strips_shortcodes(self):
        content = "{{< sections >}}\n\nSome body text."
        result = sanitize_markdown(content)
        assert "{{" not in result
        assert "Some body text." in result

    def test_clean_title_from_filename(self):
        assert clean_title_from_filename("introducing-foss-python.md") == "Introducing Foss Python"
        assert clean_title_from_filename("my_page.md") == "My Page"


# ---------------------------------------------------------------------------
# SiteMapping (needs a temp mapping.json)
# ---------------------------------------------------------------------------

class TestSiteMapping:
    SAMPLE = {
        "blog.aspose.org": {
            "type": "file",
            "url": "https://blog.aspose.org",
            "root": {"title": "Blog", "description": "A blog."},
            "families": {
                "3d": {
                    "title": "Aspose.3D",
                    "description": "3D library.",
                    "platforms": {
                        "python": "Python 3D library."
                    }
                }
            }
        }
    }

    @pytest.fixture
    def mapping_file(self, tmp_path):
        p = tmp_path / "mapping.json"
        p.write_text(json.dumps(self.SAMPLE), encoding="utf-8")
        return str(p)

    def test_get_site_url(self, mapping_file):
        sm = SiteMapping(mapping_file)
        assert sm.get_site_url("blog.aspose.org") == "https://blog.aspose.org"

    def test_get_platform_description(self, mapping_file):
        sm = SiteMapping(mapping_file)
        desc = sm.get_platform_description("blog.aspose.org", "3d", "python")
        assert desc == "Python 3D library."

    def test_get_platform_description_missing(self, mapping_file):
        sm = SiteMapping(mapping_file)
        assert sm.get_platform_description("blog.aspose.org", "3d", "java") == ""

    def test_get_virtual_metadata_root(self, mapping_file):
        sm = SiteMapping(mapping_file)
        meta = sm.get_virtual_metadata("blog.aspose.org")
        assert meta["title"] == "Blog"

    def test_get_virtual_metadata_family(self, mapping_file):
        sm = SiteMapping(mapping_file)
        meta = sm.get_virtual_metadata("blog.aspose.org", family="3d")
        assert meta["title"] == "Aspose.3D"
