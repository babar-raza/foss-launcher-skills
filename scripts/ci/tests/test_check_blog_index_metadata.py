"""Unit tests for check_blog_index_metadata.py (V-05).

All tests use tmp_path for synthetic file trees — zero live content dependency,
zero network calls.
"""
import importlib
import sys
from pathlib import Path

import pytest
import yaml

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_fm(path: Path, fm: dict) -> None:
    """Write a file with YAML frontmatter at path (creating parents as needed)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fm_text = yaml.dump(fm, allow_unicode=True, default_flow_style=False, sort_keys=False)
    path.write_text(f"---\n{fm_text}---\n\nBody.\n", encoding="utf-8")


def _load_checker(tmp_path: Path, families: dict, platforms: dict):
    """Import check_blog_index_metadata with patched data-loading functions.

    Returns the module after monkey-patching _load_family_routes,
    _load_platforms, and _BLOG_CONTENT to point at tmp_path.
    """
    # Ensure fresh import each call to avoid stale module state
    mod_name = "check_blog_index_metadata"
    if mod_name in sys.modules:
        del sys.modules[mod_name]

    checker_path = Path(__file__).resolve().parents[2] / "ci" / "checks" / mod_name
    spec = importlib.util.spec_from_file_location(
        mod_name,
        str(checker_path.with_suffix(".py")),
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)

    # Patch data loaders, content root, and repo root
    mod._load_family_routes = lambda: families
    mod._load_platforms = lambda: platforms
    mod._BLOG_CONTENT = tmp_path / "content" / "blog.aspose.org"
    mod._REPO_ROOT = tmp_path

    return mod


def _run(mod) -> list[str]:
    """Run main() and return violation lines (not PASS line) and exit code."""
    import io
    from contextlib import redirect_stdout, redirect_stderr
    buf = io.StringIO()
    with redirect_stdout(buf), redirect_stderr(io.StringIO()):
        rc = mod.main()
    output = buf.getvalue()
    violations = [
        ln for ln in output.splitlines()
        if ln.strip() and not ln.startswith("PASS:")
    ]
    return violations, rc


# ---------------------------------------------------------------------------
# Class A tests — platform _index.md
# ---------------------------------------------------------------------------

class TestPlatformIndexMetadata:
    FAMILIES = {"words": "Aspose.Words"}
    PLATFORMS = {"python": "Python"}

    def _blog_root(self, tmp_path):
        return tmp_path / "content" / "blog.aspose.org"

    def test_correct_words_python(self, tmp_path):
        root = self._blog_root(tmp_path)
        _write_fm(root / "words" / "python" / "my-post" / "index.md", {"title": "A post", "categories": ["Aspose.Words"]})
        _write_fm(root / "words" / "python" / "_index.md", {
            "title": "Aspose.Words FOSS for Python",
            "linkTitle": "Python",
            "categories": ["Aspose.Words"],
        })
        mod = _load_checker(tmp_path, self.FAMILIES, self.PLATFORMS)
        violations, rc = _run(mod)
        assert rc == 0
        assert not violations

    def test_correct_cells_net(self, tmp_path):
        families = {"cells": "Aspose.Cells"}
        platforms = {"net": ".NET"}
        root = self._blog_root(tmp_path)
        _write_fm(root / "cells" / "net" / "p1" / "index.md", {"title": "P", "categories": ["Aspose.Cells"]})
        _write_fm(root / "cells" / "net" / "_index.md", {
            "title": "Aspose.Cells FOSS for .NET",
            "linkTitle": ".NET",
            "categories": ["Aspose.Cells"],
        })
        mod = _load_checker(tmp_path, families, platforms)
        violations, rc = _run(mod)
        assert rc == 0
        assert not violations

    def test_correct_email_cpp(self, tmp_path):
        families = {"email": "Aspose.Email"}
        platforms = {"cpp": "C++"}
        root = self._blog_root(tmp_path)
        _write_fm(root / "email" / "cpp" / "p1" / "index.md", {"title": "P", "categories": ["Aspose.Email"]})
        _write_fm(root / "email" / "cpp" / "_index.md", {
            "title": "Aspose.Email FOSS for C++",
            "linkTitle": "C++",
            "categories": ["Aspose.Email"],
        })
        mod = _load_checker(tmp_path, families, platforms)
        violations, rc = _run(mod)
        assert rc == 0
        assert not violations

    def test_missing_foss_in_title(self, tmp_path):
        root = self._blog_root(tmp_path)
        _write_fm(root / "words" / "python" / "p1" / "index.md", {"title": "P", "categories": ["Aspose.Words"]})
        _write_fm(root / "words" / "python" / "_index.md", {
            "title": "Aspose.Words for Python",  # missing FOSS
            "linkTitle": "Python",
            "categories": ["Aspose.Words"],
        })
        mod = _load_checker(tmp_path, self.FAMILIES, self.PLATFORMS)
        violations, rc = _run(mod)
        assert rc == 1
        assert any("WRONG_TITLE_NO_FOSS" in v for v in violations)

    def test_null_categories(self, tmp_path):
        root = self._blog_root(tmp_path)
        _write_fm(root / "words" / "python" / "p1" / "index.md", {"title": "P", "categories": ["Aspose.Words"]})
        _write_fm(root / "words" / "python" / "_index.md", {
            "title": "Aspose.Words FOSS for Python",
            "linkTitle": "Python",
            # categories absent
        })
        mod = _load_checker(tmp_path, self.FAMILIES, self.PLATFORMS)
        violations, rc = _run(mod)
        assert rc == 1
        assert any("MISSING_CATEGORIES" in v for v in violations)

    def test_wrong_family_category(self, tmp_path):
        root = self._blog_root(tmp_path)
        _write_fm(root / "words" / "python" / "p1" / "index.md", {"title": "P", "categories": ["Aspose.Words"]})
        _write_fm(root / "words" / "python" / "_index.md", {
            "title": "Aspose.Words FOSS for Python",
            "linkTitle": "Python",
            "categories": ["Aspose.PDF"],  # wrong family
        })
        mod = _load_checker(tmp_path, self.FAMILIES, self.PLATFORMS)
        violations, rc = _run(mod)
        assert rc == 1
        assert any("WRONG_CATEGORY" in v for v in violations)

    def test_missing_title_field(self, tmp_path):
        root = self._blog_root(tmp_path)
        _write_fm(root / "words" / "python" / "p1" / "index.md", {"title": "P", "categories": ["Aspose.Words"]})
        _write_fm(root / "words" / "python" / "_index.md", {
            "linkTitle": "Python",
            "categories": ["Aspose.Words"],
            # no title field
        })
        mod = _load_checker(tmp_path, self.FAMILIES, self.PLATFORMS)
        violations, rc = _run(mod)
        assert rc == 1
        assert any("MISSING_TITLE" in v for v in violations)

    def test_unknown_platform_slug(self, tmp_path):
        """Unknown platform slug falls back to capitalized name — no UNKNOWN_PLATFORM error,
        but title comparison still catches wrong titles."""
        root = self._blog_root(tmp_path)
        _write_fm(root / "words" / "exotic" / "p1" / "index.md", {"title": "P", "categories": ["Aspose.Words"]})
        _write_fm(root / "words" / "exotic" / "_index.md", {
            "title": "Aspose.Words FOSS for Exotic",  # capitalized fallback
            "linkTitle": "Exotic",
            "categories": ["Aspose.Words"],
        })
        mod = _load_checker(tmp_path, self.FAMILIES, {"python": "Python"})  # no "exotic"
        violations, rc = _run(mod)
        assert rc == 0  # capitalized fallback matches


# ---------------------------------------------------------------------------
# Class B tests — blog post index.md
# ---------------------------------------------------------------------------

class TestBlogPostMetadata:
    FAMILIES = {"cells": "Aspose.Cells"}
    PLATFORMS = {"java": "Java"}

    def _blog_root(self, tmp_path):
        return tmp_path / "content" / "blog.aspose.org"

    def test_correct_post_categories(self, tmp_path):
        root = self._blog_root(tmp_path)
        _write_fm(root / "cells" / "java" / "my-post" / "index.md", {
            "title": "My Post",
            "categories": ["Aspose.Cells"],
        })
        _write_fm(root / "cells" / "java" / "_index.md", {
            "title": "Aspose.Cells FOSS for Java",
            "categories": ["Aspose.Cells"],
        })
        mod = _load_checker(tmp_path, self.FAMILIES, self.PLATFORMS)
        violations, rc = _run(mod)
        assert rc == 0
        assert not violations

    def test_post_empty_categories(self, tmp_path):
        root = self._blog_root(tmp_path)
        _write_fm(root / "cells" / "java" / "my-post" / "index.md", {
            "title": "My Post",
            "categories": [],  # empty list
        })
        _write_fm(root / "cells" / "java" / "_index.md", {
            "title": "Aspose.Cells FOSS for Java",
            "categories": ["Aspose.Cells"],
        })
        mod = _load_checker(tmp_path, self.FAMILIES, self.PLATFORMS)
        violations, rc = _run(mod)
        assert rc == 1
        assert any("MISSING_CATEGORIES" in v and "my-post" in v for v in violations)

    def test_post_missing_categories_key(self, tmp_path):
        root = self._blog_root(tmp_path)
        _write_fm(root / "cells" / "java" / "my-post" / "index.md", {
            "title": "My Post",
            # no categories key
        })
        _write_fm(root / "cells" / "java" / "_index.md", {
            "title": "Aspose.Cells FOSS for Java",
            "categories": ["Aspose.Cells"],
        })
        mod = _load_checker(tmp_path, self.FAMILIES, self.PLATFORMS)
        violations, rc = _run(mod)
        assert rc == 1
        assert any("MISSING_CATEGORIES" in v and "my-post" in v for v in violations)

    def test_post_wrong_family(self, tmp_path):
        root = self._blog_root(tmp_path)
        _write_fm(root / "cells" / "java" / "my-post" / "index.md", {
            "title": "My Post",
            "categories": ["Java", "Cells"],  # wrong taxonomy_term
        })
        _write_fm(root / "cells" / "java" / "_index.md", {
            "title": "Aspose.Cells FOSS for Java",
            "categories": ["Aspose.Cells"],
        })
        mod = _load_checker(tmp_path, self.FAMILIES, self.PLATFORMS)
        violations, rc = _run(mod)
        assert rc == 1
        assert any("WRONG_CATEGORY" in v and "my-post" in v for v in violations)

    def test_post_title_not_checked(self, tmp_path):
        """Any title value on a blog post produces 0 title violations."""
        root = self._blog_root(tmp_path)
        _write_fm(root / "cells" / "java" / "my-post" / "index.md", {
            "title": "Some arbitrary title that doesn't match FOSS pattern",
            "categories": ["Aspose.Cells"],
        })
        _write_fm(root / "cells" / "java" / "_index.md", {
            "title": "Aspose.Cells FOSS for Java",
            "categories": ["Aspose.Cells"],
        })
        mod = _load_checker(tmp_path, self.FAMILIES, self.PLATFORMS)
        violations, rc = _run(mod)
        assert rc == 0
        assert not any("MISSING_TITLE" in v or "WRONG_TITLE" in v for v in violations)


# ---------------------------------------------------------------------------
# Scope filtering tests
# ---------------------------------------------------------------------------

class TestScopeFiltering:
    FAMILIES = {"words": "Aspose.Words"}
    PLATFORMS = {"python": "Python"}

    def _blog_root(self, tmp_path):
        return tmp_path / "content" / "blog.aspose.org"

    def test_locale_dirs_skipped(self, tmp_path):
        """Two-letter locale dirs (de, fr, etc.) must not be scanned."""
        root = self._blog_root(tmp_path)
        # Write a defective _index.md under a locale dir
        _write_fm(root / "de" / "words" / "python" / "_index.md", {
            "title": "Aspose.Words for Python",  # would fail if scanned
        })
        # Also write a valid non-locale product to ensure scanner still runs
        _write_fm(root / "words" / "python" / "p1" / "index.md", {
            "categories": ["Aspose.Words"],
        })
        _write_fm(root / "words" / "python" / "_index.md", {
            "title": "Aspose.Words FOSS for Python",
            "categories": ["Aspose.Words"],
        })
        mod = _load_checker(tmp_path, self.FAMILIES, self.PLATFORMS)
        violations, rc = _run(mod)
        # de/ locale dir skipped → no violations from the defective de/ file
        assert rc == 0

    def test_family_level_index_skipped(self, tmp_path):
        """words/_index.md (family-level, no platform) must not be treated as Class A."""
        root = self._blog_root(tmp_path)
        # Family-level _index.md — deliberately missing FOSS
        _write_fm(root / "words" / "_index.md", {
            "title": "Aspose.Words",
        })
        # Valid platform section to ensure scanner runs
        _write_fm(root / "words" / "python" / "p1" / "index.md", {
            "categories": ["Aspose.Words"],
        })
        _write_fm(root / "words" / "python" / "_index.md", {
            "title": "Aspose.Words FOSS for Python",
            "categories": ["Aspose.Words"],
        })
        mod = _load_checker(tmp_path, self.FAMILIES, self.PLATFORMS)
        violations, rc = _run(mod)
        # words/_index.md is a file in words/ dir, not in a platform subdir — not scanned as Class A
        assert rc == 0
