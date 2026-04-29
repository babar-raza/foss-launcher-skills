"""Unit tests for scripts/ci/checks/check-blog-slugs.py.

Coverage:
- collect_flat_english_files: depth filtering, locale exclusion, index.md exclusion
- collect_index_files: depth filtering (must be >= 4 parts)
- _check_aliases_for_test_slugs: test-prefixed alias detection
- extract_frontmatter: YAML parsing edge cases

All tests are deterministic — no network, synthetic filesystem via tmp_path.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Module loader
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).parents[3]


def _load_slugs():
    spec = importlib.util.spec_from_file_location(
        "check_blog_slugs",
        _REPO_ROOT / "scripts" / "ci" / "check-blog-slugs.py",
    )
    m = importlib.util.module_from_spec(spec)
    import sys as _sys
    _sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


slugs = _load_slugs()


# ===========================================================================
# collect_flat_english_files
# ===========================================================================

class TestCollectFlatEnglishFiles:
    def _make_root(self, tmp_path: Path) -> Path:
        root = tmp_path / "content" / "blog.aspose.org"
        root.mkdir(parents=True)
        return root

    def test_flat_leaf_at_depth3_included(self, tmp_path):
        root = self._make_root(tmp_path)
        f = root / "email" / "cpp" / "reading-msg.md"
        f.parent.mkdir(parents=True)
        f.write_text("---\ndraft: false\n---\n", encoding="utf-8")
        result = slugs.collect_flat_english_files(root)
        assert f in result

    def test_index_md_excluded(self, tmp_path):
        """index.md is directory-structured — not a flat file."""
        root = self._make_root(tmp_path)
        f = root / "email" / "cpp" / "reading-msg" / "index.md"
        f.parent.mkdir(parents=True)
        f.write_text("---\ndraft: false\n---\n", encoding="utf-8")
        result = slugs.collect_flat_english_files(root)
        assert f not in result

    def test_underscore_index_excluded(self, tmp_path):
        root = self._make_root(tmp_path)
        f = root / "email" / "cpp" / "_index.md"
        f.parent.mkdir(parents=True)
        f.write_text("---\n---\n", encoding="utf-8")
        result = slugs.collect_flat_english_files(root)
        assert f not in result

    def test_root_level_utility_excluded_depth1(self, tmp_path):
        root = self._make_root(tmp_path)
        f = root / "archive.md"
        f.write_text("---\n---\n", encoding="utf-8")
        result = slugs.collect_flat_english_files(root)
        assert f not in result

    def test_platform_level_utility_excluded_depth2(self, tmp_path):
        root = self._make_root(tmp_path)
        f = root / "email" / "index.md"
        f.parent.mkdir(parents=True)
        f.write_text("---\n---\n", encoding="utf-8")
        result = slugs.collect_flat_english_files(root)
        assert f not in result

    def test_locale_file_excluded(self, tmp_path):
        root = self._make_root(tmp_path)
        f = root / "email" / "cpp" / "reading-msg.ar.md"
        f.parent.mkdir(parents=True)
        f.write_text("---\n---\n", encoding="utf-8")
        result = slugs.collect_flat_english_files(root)
        assert f not in result


# ===========================================================================
# collect_index_files
# ===========================================================================

class TestCollectIndexFiles:
    def _make_root(self, tmp_path: Path) -> Path:
        root = tmp_path / "content" / "blog.aspose.org"
        root.mkdir(parents=True)
        return root

    def _make_index(self, root: Path, *parts: str) -> Path:
        f = root.joinpath(*parts)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("---\ndraft: false\n---\n", encoding="utf-8")
        return f

    def test_leaf_post_at_depth4_included(self, tmp_path):
        root = self._make_root(tmp_path)
        f = self._make_index(root, "email", "cpp", "reading-msg", "index.md")
        result = slugs.collect_index_files(root)
        assert f in result

    def test_platform_index_at_depth3_excluded(self, tmp_path):
        root = self._make_root(tmp_path)
        f = self._make_index(root, "email", "cpp", "index.md")
        result = slugs.collect_index_files(root)
        assert f not in result

    def test_family_index_at_depth2_excluded(self, tmp_path):
        root = self._make_root(tmp_path)
        f = self._make_index(root, "email", "index.md")
        result = slugs.collect_index_files(root)
        assert f not in result

    def test_root_index_at_depth1_excluded(self, tmp_path):
        root = self._make_root(tmp_path)
        f = self._make_index(root, "index.md")
        result = slugs.collect_index_files(root)
        assert f not in result

    def test_multiple_leaf_posts_all_included(self, tmp_path):
        root = self._make_root(tmp_path)
        f1 = self._make_index(root, "email", "cpp", "post-one", "index.md")
        f2 = self._make_index(root, "note", "python", "post-two", "index.md")
        result = slugs.collect_index_files(root)
        assert f1 in result
        assert f2 in result


# ===========================================================================
# _check_aliases_for_test_slugs
# ===========================================================================

class TestCheckAliasesForTestSlugs:
    def _run(self, aliases: list) -> list:
        fails = []
        slugs._check_aliases_for_test_slugs(aliases, Path("email/cpp/post/index.md"), fails)
        return fails

    def test_no_aliases_no_fails(self):
        assert self._run([]) == []

    def test_clean_alias_no_fail(self):
        assert self._run(["/email/cpp/reading-msg/"]) == []

    def test_test_prefixed_final_segment_fails(self):
        fails = self._run(["/cells/python/testcreateallcharts-spreadsheets/"])
        assert len(fails) == 1
        assert "testcreateallcharts-spreadsheets" in fails[0]

    def test_test_prefix_case_insensitive(self):
        fails = self._run(["/TEST-something/"])
        assert len(fails) == 1

    def test_multiple_aliases_only_bad_ones_fail(self):
        fails = self._run(["/clean-path/", "/testbadpath/", "/another-clean/"])
        assert len(fails) == 1
        assert "testbadpath" in fails[0]

    def test_alias_without_trailing_slash(self):
        fails = self._run(["/cells/python/testfoo"])
        assert len(fails) == 1

    def test_alias_string_not_list_handled_via_caller(self):
        """The function receives a list; callers normalize strings to lists first."""
        fails = self._run(["testonly"])
        assert len(fails) == 1


# ===========================================================================
# extract_frontmatter
# ===========================================================================

class TestExtractFrontmatter:
    def test_valid_frontmatter_parsed(self):
        text = "---\ntitle: Foo\ndraft: false\n---\n\nContent.\n"
        result = slugs.extract_frontmatter(text)
        assert result == {"title": "Foo", "draft": False}

    def test_no_frontmatter_returns_empty_dict(self):
        result = slugs.extract_frontmatter("No frontmatter here.\n")
        assert result == {}

    def test_malformed_yaml_returns_empty_dict(self):
        result = slugs.extract_frontmatter("---\n: bad: yaml:\n---\n")
        assert result == {}

    def test_non_dict_yaml_returns_empty_dict(self):
        result = slugs.extract_frontmatter("---\n- item1\n- item2\n---\n")
        assert result == {}
