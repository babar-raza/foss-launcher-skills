"""
Tests for backlink_approve_authority.py — focused on merge_authority() logic
and _infer_subdomain() cross-subdomain routing.

TC-AUTHORITY-MERGE-SAFETY-001: verifies that --merge preserves cross-family records
and that per-family runs without --merge (correctly) overwrite everything.

TC-P2-6-OPT: regression tests for _infer_subdomain (target_path prefix takes
precedence over source subdomain) and merge_authority add_only mode (Stage 1c
blog->products records accumulate without destroying existing reference records).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline"))

from commands.ops.backlink_approve_authority import _infer_subdomain, merge_authority


# ── Fixtures ───────────────────────────────────────────────────────────────────

def _make_record(source_path: str, family: str, platform: str, decision: str = "AUTO_APPROVE_EXACT") -> dict:
    return {
        "source_path": source_path,
        "family": family,
        "platform": platform,
        "decision": decision,
        "score": 0.90,
    }


# ── merge_authority() tests ────────────────────────────────────────────────────

class TestMergeAuthority:

    def test_merge_preserves_other_families(self):
        """Core safety test: merging font records must not touch note/slides records."""
        existing = {
            "content/note/a.md": _make_record("content/note/a.md", "note", "python"),
            "content/slides/b.md": _make_record("content/slides/b.md", "slides", "java"),
            "content/font/old.md": _make_record("content/font/old.md", "font", "python"),
        }
        new_font = {
            "content/font/new.md": _make_record("content/font/new.md", "font", "python"),
        }

        merged = merge_authority(existing, new_font, family="font")

        # Other families intact
        assert "content/note/a.md" in merged
        assert "content/slides/b.md" in merged
        assert merged["content/note/a.md"]["family"] == "note"
        assert merged["content/slides/b.md"]["family"] == "slides"

        # Old font record removed; new font record added
        assert "content/font/old.md" not in merged
        assert "content/font/new.md" in merged
        assert merged["content/font/new.md"]["family"] == "font"

    def test_merge_removes_only_target_family(self):
        """Only records matching the specified family are removed."""
        existing = {
            "content/3d/x.md": _make_record("content/3d/x.md", "3d", "java"),
            "content/cells/y.md": _make_record("content/cells/y.md", "cells", "net"),
            "content/pdf/z.md": _make_record("content/pdf/z.md", "pdf", "java"),
        }
        new_cells = {
            "content/cells/new.md": _make_record("content/cells/new.md", "cells", "net"),
        }

        merged = merge_authority(existing, new_cells, family="cells")

        assert "content/3d/x.md" in merged
        assert "content/pdf/z.md" in merged
        assert "content/cells/y.md" not in merged
        assert "content/cells/new.md" in merged

    def test_merge_with_platform_filter(self):
        """When platform is specified, only records for that platform are replaced."""
        existing = {
            "content/slides/cpp/a.md": _make_record("content/slides/cpp/a.md", "slides", "cpp"),
            "content/slides/java/b.md": _make_record("content/slides/java/b.md", "slides", "java"),
        }
        new_slides_java = {
            "content/slides/java/new.md": _make_record("content/slides/java/new.md", "slides", "java"),
        }

        merged = merge_authority(existing, new_slides_java, family="slides", platform="java")

        # cpp record preserved
        assert "content/slides/cpp/a.md" in merged
        # java old record removed; new added
        assert "content/slides/java/b.md" not in merged
        assert "content/slides/java/new.md" in merged

    def test_merge_into_empty_existing(self):
        """Merging into empty dict works same as plain insert."""
        new_font = {
            "content/font/a.md": _make_record("content/font/a.md", "font", "python"),
        }
        merged = merge_authority({}, new_font, family="font")
        assert len(merged) == 1
        assert "content/font/a.md" in merged

    def test_merge_no_existing_records_for_family(self):
        """When family has no existing records, merge is purely additive."""
        existing = {
            "content/note/a.md": _make_record("content/note/a.md", "note", "python"),
        }
        new_font = {
            "content/font/b.md": _make_record("content/font/b.md", "font", "python"),
        }
        merged = merge_authority(existing, new_font, family="font")
        assert len(merged) == 2
        assert "content/note/a.md" in merged
        assert "content/font/b.md" in merged

    def test_merge_does_not_mutate_inputs(self):
        """merge_authority is pure — inputs are not modified."""
        existing = {
            "content/font/old.md": _make_record("content/font/old.md", "font", "python"),
        }
        new_font = {
            "content/font/new.md": _make_record("content/font/new.md", "font", "python"),
        }
        existing_copy = dict(existing)
        new_copy = dict(new_font)

        merge_authority(existing, new_font, family="font")

        assert existing == existing_copy
        assert new_font == new_copy

    def test_merge_new_records_overwrite_same_source_path(self):
        """If old and new record have same source_path, new record wins."""
        existing = {
            "content/font/a.md": _make_record("content/font/a.md", "font", "python", "REVIEW_REQUIRED"),
        }
        new_font = {
            "content/font/a.md": _make_record("content/font/a.md", "font", "python", "AUTO_APPROVE_EXACT"),
        }
        merged = merge_authority(existing, new_font, family="font")
        assert merged["content/font/a.md"]["decision"] == "AUTO_APPROVE_EXACT"

    def test_merge_without_platform_removes_all_family_platforms(self):
        """Without platform filter, all platforms for the family are replaced."""
        existing = {
            "content/slides/cpp/a.md": _make_record("content/slides/cpp/a.md", "slides", "cpp"),
            "content/slides/java/b.md": _make_record("content/slides/java/b.md", "slides", "java"),
            "content/slides/net/c.md": _make_record("content/slides/net/c.md", "slides", "net"),
        }
        new_slides = {
            "content/slides/python/d.md": _make_record("content/slides/python/d.md", "slides", "python"),
        }
        merged = merge_authority(existing, new_slides, family="slides")
        # All old slides records removed
        assert "content/slides/cpp/a.md" not in merged
        assert "content/slides/java/b.md" not in merged
        assert "content/slides/net/c.md" not in merged
        # New record present
        assert "content/slides/python/d.md" in merged


# ── TC-P2-6-OPT: _infer_subdomain regression tests ────────────────────────────

class TestInferSubdomain:
    """Regression tests for _infer_subdomain() target_path prefix routing.

    Bug: before fix, _infer_subdomain("blog.aspose.org", "products/cells/python-net")
    returned "blog" because it used source subdomain mapping only.  After fix,
    target_path prefix takes precedence: "products/..." -> "products".
    """

    def test_products_prefix_returns_products(self):
        """Stage 1c: blog source + products target -> subdomain = 'products'."""
        result = _infer_subdomain("blog.aspose.org", "products/cells/python-net")
        assert result == "products", (
            f"Expected 'products' for target 'products/cells/python-net', got '{result}'. "
            "This is the Stage 1c bug: blog source was returning 'blog' instead of 'products'."
        )

    def test_products_prefix_other_families(self):
        """All families under 'products/' resolve to 'products'."""
        for path in ("products/3d/python-net", "products/pdf/go-cpp", "products/email/python-net"):
            assert _infer_subdomain("blog.aspose.org", path) == "products", path

    def test_reference_prefix_returns_reference(self):
        """Reference API paths resolve to 'reference' regardless of source."""
        assert _infer_subdomain("blog.aspose.org", "reference/3d/net/A3DObject") == "reference"
        assert _infer_subdomain("docs.aspose.org", "reference/cells/java/com.aspose.cells/Workbook") == "reference"

    def test_docs_prefix_returns_docs(self):
        assert _infer_subdomain("blog.aspose.org", "docs/cells/net/developer-guide") == "docs"

    def test_kb_prefix_returns_kb(self):
        assert _infer_subdomain("reference.aspose.org", "kb/email/python/how-to-send") == "kb"

    def test_blog_prefix_returns_blog(self):
        assert _infer_subdomain("reference.aspose.org", "blog/cells/python/intro-post") == "blog"

    def test_no_prefix_falls_back_to_source_mapping(self):
        """When target_path has no known prefix, use source subdomain mapping."""
        assert _infer_subdomain("blog.aspose.org", "some-path") == "blog"
        assert _infer_subdomain("reference.aspose.org", "some-path") == "reference"
        assert _infer_subdomain("docs.aspose.org", "some-path") == "docs"
        assert _infer_subdomain("kb.aspose.org", "some-path") == "kb"
        assert _infer_subdomain("products.aspose.org", "some-path") == "products"

    def test_unknown_source_falls_back_to_reference(self):
        """Unknown source subdomain with no path prefix defaults to 'reference'."""
        assert _infer_subdomain("unknown.aspose.org", "some-path") == "reference"

    def test_path_prefix_beats_source_for_blog_source(self):
        """Critical regression: blog source + non-blog path -> path prefix wins."""
        # Before fix: "blog.aspose.org" mapped to "blog" for any target.
        # After fix: "products/..." must override that mapping.
        assert _infer_subdomain("blog.aspose.org", "products/slides/python-net") == "products"
        assert _infer_subdomain("blog.aspose.org", "reference/pdf/net/Document") == "reference"
        assert _infer_subdomain("blog.aspose.org", "docs/email/net/overview") == "docs"


# ── TC-P2-6-OPT: merge_authority add_only regression tests ────────────────────

class TestMergeAuthorityAddOnly:
    """Regression tests for merge_authority(add_only=True).

    Stage 1c generates blog->products authority records that must be ADDED on top
    of existing reference->reference records for the same family.  Without add_only,
    a blog-only candidate build would destroy all existing reference records.
    """

    def test_add_only_preserves_existing_family_records(self):
        """add_only=True: existing records for the SAME family are not removed."""
        existing = {
            "reference/cells/java/Workbook.md": _make_record(
                "reference/cells/java/Workbook.md", "cells", "java"
            ),
            "reference/cells/net/Workbook.md": _make_record(
                "reference/cells/net/Workbook.md", "cells", "net"
            ),
        }
        new_blog_cells = {
            "blog/cells/python/intro.md": _make_record(
                "blog/cells/python/intro.md", "cells", "python"
            ),
        }
        merged = merge_authority(existing, new_blog_cells, family="cells", add_only=True)

        # Existing reference records for cells must survive
        assert "reference/cells/java/Workbook.md" in merged, "add_only destroyed existing java record"
        assert "reference/cells/net/Workbook.md" in merged, "add_only destroyed existing net record"
        # New blog record added
        assert "blog/cells/python/intro.md" in merged

    def test_add_only_preserves_other_families(self):
        """add_only=True: records for other families are also preserved."""
        existing = {
            "reference/cells/java/Workbook.md": _make_record(
                "reference/cells/java/Workbook.md", "cells", "java"
            ),
            "reference/email/net/MailMessage.md": _make_record(
                "reference/email/net/MailMessage.md", "email", "net"
            ),
        }
        new_blog_cells = {
            "blog/cells/python/intro.md": _make_record(
                "blog/cells/python/intro.md", "cells", "python"
            ),
        }
        merged = merge_authority(existing, new_blog_cells, family="cells", add_only=True)

        assert "reference/email/net/MailMessage.md" in merged, "add_only affected another family"

    def test_add_only_false_still_removes_existing(self):
        """Regression: default behavior (add_only=False) still removes old family records."""
        existing = {
            "reference/cells/java/Workbook.md": _make_record(
                "reference/cells/java/Workbook.md", "cells", "java"
            ),
        }
        new_blog_cells = {
            "blog/cells/python/intro.md": _make_record(
                "blog/cells/python/intro.md", "cells", "python"
            ),
        }
        merged = merge_authority(existing, new_blog_cells, family="cells", add_only=False)

        assert "reference/cells/java/Workbook.md" not in merged, (
            "Default merge should have removed old cells record but did not"
        )
        assert "blog/cells/python/intro.md" in merged

    def test_add_only_accumulates_across_multiple_calls(self):
        """Simulates 10-family Stage 1c loop: each call adds records without destroying prior."""
        auth = {}
        families = ["3d", "cells", "email", "font", "note", "page", "pdf", "slides", "tex", "words"]

        # First pass: build reference records for all families
        for fam in families:
            ref_rec = {f"reference/{fam}/java/Cls.md": _make_record(f"reference/{fam}/java/Cls.md", fam, "java")}
            auth = merge_authority(auth, ref_rec, family=fam)  # normal merge

        assert len(auth) == 10, f"Expected 10 reference records, got {len(auth)}"

        # Second pass: add blog records for each family without destroying reference records
        for fam in families:
            blog_rec = {f"blog/{fam}/python/post.md": _make_record(f"blog/{fam}/python/post.md", fam, "python")}
            auth = merge_authority(auth, blog_rec, family=fam, add_only=True)

        assert len(auth) == 20, f"Expected 20 records (10 reference + 10 blog), got {len(auth)}"

        # All reference records still present
        for fam in families:
            key = f"reference/{fam}/java/Cls.md"
            assert key in auth, f"Reference record for {fam} was destroyed by add_only merge"

        # All blog records present
        for fam in families:
            key = f"blog/{fam}/python/post.md"
            assert key in auth, f"Blog record for {fam} missing after add_only merge"

    def test_add_only_updates_existing_record_at_same_path(self):
        """add_only=True: if new record has same key as existing, new record wins."""
        existing = {
            "blog/cells/python/post.md": _make_record(
                "blog/cells/python/post.md", "cells", "python", "REVIEW_REQUIRED"
            ),
        }
        new_blog = {
            "blog/cells/python/post.md": _make_record(
                "blog/cells/python/post.md", "cells", "python", "AUTO_APPROVE_EXACT"
            ),
        }
        merged = merge_authority(existing, new_blog, family="cells", add_only=True)
        assert merged["blog/cells/python/post.md"]["decision"] == "AUTO_APPROVE_EXACT"
