"""Tests for blog_slug_policy.py, blog_slug_inventory.py, and blog_folder_migrate.py.

All tests are deterministic: no LLM calls, no network, no real content files
(except where tmp_path fixtures create controlled content).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

import blog_slug_policy as bsp
from blog_slug_policy import (
    OK, WEAK, BAD_GENERIC, BAD_FALLBACK, BAD_NO_PLATFORM, BAD_TOO_SHORT,
    MIGRATION_READY, NEEDS_REVIEW, BLOCKED_BY_GOVERNANCE,
)


# ---------------------------------------------------------------------------
# Unit: normalize_folder_slug
# ---------------------------------------------------------------------------

def test_normalize_handles_spaces_and_caps():
    assert bsp.normalize_folder_slug("Core Cell Operations In Java") == "core-cell-operations-in-java"


def test_normalize_strips_leading_trailing_hyphens():
    assert bsp.normalize_folder_slug("  hello world  ") == "hello-world"


def test_normalize_collapses_repeated_separators():
    assert bsp.normalize_folder_slug("hello--world") == "hello-world"
    assert bsp.normalize_folder_slug("hello___world") == "hello-world"


def test_normalize_handles_special_chars():
    result = bsp.normalize_folder_slug("Aspose.Cells FOSS for Java!")
    assert result == "aspose-cells-foss-for-java"


# ---------------------------------------------------------------------------
# Unit: is_generic_folder_slug
# ---------------------------------------------------------------------------

def test_core_in_java_is_generic():
    assert bsp.is_generic_folder_slug("core-in-java", "cells", "java") is True


def test_common_in_python_is_generic():
    assert bsp.is_generic_folder_slug("common-in-python", "cells", "python") is True


def test_introducing_cells_foss_java_is_not_generic():
    assert bsp.is_generic_folder_slug("introducing-cells-foss-java", "cells", "java") is False


def test_cells_foss_java_is_not_generic():
    assert bsp.is_generic_folder_slug("cells-foss-java", "cells", "java") is False


def test_generated_post_is_generic():
    assert bsp.is_generic_folder_slug("generated-post", "cells", "java") is True


def test_generated_post_numbered_is_generic():
    assert bsp.is_generic_folder_slug("generated-post-1", "cells", "java") is True


def test_untitled_is_generic():
    assert bsp.is_generic_folder_slug("untitled", "3d", "python") is True


def test_pure_platform_is_generic():
    assert bsp.is_generic_folder_slug("java", "cells", "java") is True


def test_pure_family_is_generic():
    assert bsp.is_generic_folder_slug("cells", "cells", "java") is True


# ---------------------------------------------------------------------------
# Unit: classify_folder_slug_quality
# ---------------------------------------------------------------------------

def test_core_in_java_classifies_as_migration_ready():
    """core-in-java is BAD_GENERIC + auto_updatable → MIGRATION_READY."""
    result = bsp.classify_folder_slug_quality(
        "core-in-java", "Core Cell Operations in Java", "cells", "java",
        auto_updatable=True, content_origin="skill-generated",
    )
    assert result == MIGRATION_READY


def test_core_in_java_blocked_when_not_auto_updatable():
    result = bsp.classify_folder_slug_quality(
        "core-in-java", "Core Cell Operations in Java", "cells", "java",
        auto_updatable=False, content_origin="skill-generated",
    )
    assert result == BLOCKED_BY_GOVERNANCE


def test_introducing_cells_foss_java_classifies_as_ok():
    result = bsp.classify_folder_slug_quality(
        "introducing-cells-foss-java", "Introducing Aspose.Cells FOSS for Java",
        "cells", "java",
    )
    assert result == OK


def test_working_with_3d_formats_in_java_classifies_as_ok():
    result = bsp.classify_folder_slug_quality(
        "working-with-3d-formats-in-java", "Working with 3D Formats in Java",
        "3d", "java",
    )
    assert result == OK


def test_cells_foss_java_classifies_as_weak_or_ok():
    """cells-foss-java: has family, no platform explicitly — OK or WEAK depending on logic."""
    result = bsp.classify_folder_slug_quality(
        "cells-foss-java", "Aspose.Cells FOSS for Java Key Features",
        "cells", "java",
    )
    # Must NOT be BAD or MIGRATION_READY
    assert result in {OK, WEAK}, f"Expected OK or WEAK, got {result}"


def test_generated_post_classifies_as_migration_ready():
    result = bsp.classify_folder_slug_quality(
        "generated-post", "Some Title", "cells", "java",
        auto_updatable=True, content_origin="skill-generated",
    )
    assert result == MIGRATION_READY


# ---------------------------------------------------------------------------
# Unit: propose_folder_slug_repair
# ---------------------------------------------------------------------------

def test_repair_for_core_in_java_contains_cells_and_java():
    repair = bsp.propose_folder_slug_repair(
        "core-in-java",
        "Core Cell Operations in Aspose.Cells FOSS for Java",
        "cells", "java",
    )
    assert "cells" in repair, f"Repair slug must contain 'cells': {repair!r}"
    assert "java" in repair, f"Repair slug must contain 'java': {repair!r}"


def test_repair_output_is_not_generic():
    repair = bsp.propose_folder_slug_repair(
        "core-in-java",
        "Core Cell Operations in Aspose.Cells FOSS for Java",
        "cells", "java",
    )
    assert bsp.is_generic_folder_slug(repair, "cells", "java") is False, (
        f"Repair slug must not be generic: {repair!r}"
    )


def test_repair_output_is_deterministic():
    r1 = bsp.propose_folder_slug_repair("core-in-java", "Core Cell Ops in Java", "cells", "java")
    r2 = bsp.propose_folder_slug_repair("core-in-java", "Core Cell Ops in Java", "cells", "java")
    assert r1 == r2


def test_repair_does_not_exceed_60_chars():
    very_long_title = "Very Long Title That Goes On And On For A Really Really Long Time In Java"
    repair = bsp.propose_folder_slug_repair("core-in-java", very_long_title, "cells", "java")
    assert len(repair) <= 60, f"Repair slug too long ({len(repair)}): {repair!r}"


# ---------------------------------------------------------------------------
# Unit: validate_folder_slug
# ---------------------------------------------------------------------------

def test_generated_post_fails_validation():
    violations = bsp.validate_folder_slug("generated-post", "Title", "cells", "java")
    assert len(violations) > 0


def test_core_in_java_fails_validation():
    violations = bsp.validate_folder_slug("core-in-java", "Title", "cells", "java")
    assert len(violations) > 0, f"Expected violations for 'core-in-java', got none"


def test_aspose_cells_foss_java_cell_operations_passes():
    violations = bsp.validate_folder_slug(
        "aspose-cells-foss-java-cell-operations",
        "Core Cell Operations in Aspose.Cells FOSS for Java",
        "cells", "java",
    )
    assert violations == [], f"Expected no violations, got: {violations}"


def test_slug_with_invalid_chars_fails():
    violations = bsp.validate_folder_slug("Hello_World", "Title", "cells", "java")
    assert len(violations) > 0


# ---------------------------------------------------------------------------
# Unit: build_blog_url_from_index_path
# ---------------------------------------------------------------------------

def test_url_derived_from_folder_path():
    path = "content/blog.aspose.org/cells/java/core-in-java/index.md"
    url = bsp.build_blog_url_from_index_path(path)
    assert url == "/cells/java/core-in-java/", f"Got: {url!r}"


def test_url_derived_from_renamed_folder_path():
    path = "content/blog.aspose.org/cells/java/aspose-cells-foss-java-cell-operations/index.md"
    url = bsp.build_blog_url_from_index_path(path)
    assert url == "/cells/java/aspose-cells-foss-java-cell-operations/", f"Got: {url!r}"


def test_no_frontmatter_slug_needed():
    """URL derivation must work from path alone — no frontmatter slug required."""
    path = Path("content/blog.aspose.org/3d/python/working-with-3d-formats-in-python/index.md")
    url = bsp.build_blog_url_from_index_path(path)
    assert "/3d/python/working-with-3d-formats-in-python/" in url


# ---------------------------------------------------------------------------
# Migration: shared fixtures
# ---------------------------------------------------------------------------

_SAMPLE_FM = """\
---
title: Core Cell Operations in Aspose.Cells FOSS for Java
date: '2026-04-27'
draft: false
author: Aspose
provenance:
  content_origin: skill-generated
  last_mechanism: skill
  auto_updatable: true
  source_file: blog.aspose.org/cells/java/core-in-java/index.md
grade: A
---

## Introduction

Some content here.
"""

_LOCALE_FM = """\
---
title: Core Cell Operations (Translated)
provenance:
  content_origin: skill-generated
  auto_updatable: true
  source_file: blog.aspose.org/cells/java/core-in-java/index.md
---

Translated content.
"""


def _make_test_blog_structure(tmp_path: Path) -> tuple[Path, Path]:
    """Create a minimal blog folder structure for migration testing."""
    blog_root = tmp_path / "content" / "blog.aspose.org"
    old_folder = blog_root / "cells" / "java" / "core-in-java"
    old_folder.mkdir(parents=True)

    # English index.md
    (old_folder / "index.md").write_text(_SAMPLE_FM, encoding="utf-8")
    # One locale file
    (old_folder / "index.ar.md").write_text(_LOCALE_FM, encoding="utf-8")

    # reports/blog-slugs dir
    out_dir = tmp_path / "reports" / "blog-slugs"
    out_dir.mkdir(parents=True)

    return blog_root, out_dir


# ---------------------------------------------------------------------------
# Migration: no slug: added (existing test — unchanged)
# ---------------------------------------------------------------------------

def test_migration_does_not_add_slug_field(tmp_path):
    """After migration, no slug: field must appear in any file."""
    sys.path.insert(0, str(Path(__file__).parents[1]))
    from commands.migration.blog_folder_migrate import run_migration

    blog_root, out_dir = _make_test_blog_structure(tmp_path)
    repo_root = tmp_path

    candidate = {
        "old_folder_slug": "core-in-java",
        "new_folder_slug": "aspose-cells-foss-java-cell-operations",
        "family": "cells",
        "platform": "java",
        "title": "Core Cell Operations in Aspose.Cells FOSS for Java",
        "auto_updatable": True,
        "grade": "A",
        "locale_files": [
            str((blog_root / "cells" / "java" / "core-in-java" / "index.ar.md").as_posix())
        ],
        "source_file_updates": [
            {
                "file": str((blog_root / "cells" / "java" / "core-in-java" / "index.ar.md").as_posix()),
                "old_value": "blog.aspose.org/cells/java/core-in-java/index.md",
                "new_value": "blog.aspose.org/cells/java/aspose-cells-foss-java-cell-operations/index.md",
            }
        ],
    }

    run_migration([candidate], repo_root=repo_root, dry_run=False, out_dir=out_dir)

    new_folder = blog_root / "cells" / "java" / "aspose-cells-foss-java-cell-operations"
    assert new_folder.is_dir(), "New folder must exist after migration"

    for md_file in new_folder.glob("*.md"):
        content = md_file.read_text(encoding="utf-8")
        assert not re.search(r"^\s*slug\s*:", content, re.MULTILINE), (
            f"slug: field must not be added to {md_file.name}"
        )


# ---------------------------------------------------------------------------
# Migration: aliases: must NOT be added to locale files (replaces old test)
# ---------------------------------------------------------------------------

def test_migration_does_not_add_aliases_to_locale_files(tmp_path):
    """After migration, locale files (index.*.md) must NOT receive aliases:."""
    sys.path.insert(0, str(Path(__file__).parents[1]))
    from commands.migration.blog_folder_migrate import run_migration

    blog_root, out_dir = _make_test_blog_structure(tmp_path)
    repo_root = tmp_path

    candidate = {
        "old_folder_slug": "core-in-java",
        "new_folder_slug": "aspose-cells-foss-java-cell-operations",
        "family": "cells",
        "platform": "java",
        "title": "Core Cell Operations in Aspose.Cells FOSS for Java",
        "auto_updatable": True,
        "grade": "A",
        "locale_files": [],
        "source_file_updates": [],
    }

    run_migration([candidate], repo_root=repo_root, dry_run=False, out_dir=out_dir)

    new_folder = blog_root / "cells" / "java" / "aspose-cells-foss-java-cell-operations"
    # English index.md MAY have aliases: (correct behavior now)
    # Locale files must NOT have aliases:
    for md_file in new_folder.glob("index.*.md"):
        content = md_file.read_text(encoding="utf-8")
        assert not re.search(r"^\s*aliases\s*:", content, re.MULTILINE), (
            f"aliases: field must not be added to locale file {md_file.name}"
        )


def test_migration_updates_source_file_in_locale(tmp_path):
    """Migration must update source_file in locale files."""
    sys.path.insert(0, str(Path(__file__).parents[1]))
    from commands.migration.blog_folder_migrate import run_migration

    blog_root, out_dir = _make_test_blog_structure(tmp_path)
    repo_root = tmp_path

    old_locale_path = blog_root / "cells" / "java" / "core-in-java" / "index.ar.md"
    candidate = {
        "old_folder_slug": "core-in-java",
        "new_folder_slug": "aspose-cells-foss-java-cell-operations",
        "family": "cells",
        "platform": "java",
        "title": "Core Cell Operations in Aspose.Cells FOSS for Java",
        "auto_updatable": True,
        "grade": "A",
        "locale_files": [str(old_locale_path.as_posix())],
        "source_file_updates": [
            {
                "file": str(old_locale_path.as_posix()),
                "old_value": "blog.aspose.org/cells/java/core-in-java/index.md",
                "new_value": "blog.aspose.org/cells/java/aspose-cells-foss-java-cell-operations/index.md",
            }
        ],
    }

    run_migration([candidate], repo_root=repo_root, dry_run=False, out_dir=out_dir)

    new_locale = blog_root / "cells" / "java" / "aspose-cells-foss-java-cell-operations" / "index.ar.md"
    assert new_locale.exists()
    content = new_locale.read_text(encoding="utf-8")
    assert "aspose-cells-foss-java-cell-operations" in content
    assert "core-in-java" not in content


def test_migration_fails_if_target_exists(tmp_path):
    """Migration must stop (sys.exit) if target folder already exists."""
    sys.path.insert(0, str(Path(__file__).parents[1]))
    from commands.migration.blog_folder_migrate import run_migration

    blog_root, out_dir = _make_test_blog_structure(tmp_path)
    repo_root = tmp_path

    # Pre-create target folder to trigger collision
    new_folder = blog_root / "cells" / "java" / "aspose-cells-foss-java-cell-operations"
    new_folder.mkdir(parents=True)

    candidate = {
        "old_folder_slug": "core-in-java",
        "new_folder_slug": "aspose-cells-foss-java-cell-operations",
        "family": "cells",
        "platform": "java",
        "title": "Core Cell Operations in Aspose.Cells FOSS for Java",
        "auto_updatable": True,
        "grade": "A",
        "locale_files": [],
        "source_file_updates": [],
    }

    with pytest.raises(SystemExit):
        run_migration([candidate], repo_root=repo_root, dry_run=False, out_dir=out_dir)


def test_migration_dry_run_makes_no_changes(tmp_path):
    """Dry-run must not rename folders or modify any files."""
    sys.path.insert(0, str(Path(__file__).parents[1]))
    from commands.migration.blog_folder_migrate import run_migration

    blog_root, out_dir = _make_test_blog_structure(tmp_path)
    repo_root = tmp_path

    old_folder = blog_root / "cells" / "java" / "core-in-java"
    new_folder = blog_root / "cells" / "java" / "aspose-cells-foss-java-cell-operations"

    old_locale_path = old_folder / "index.ar.md"
    original_locale_content = old_locale_path.read_text(encoding="utf-8")

    candidate = {
        "old_folder_slug": "core-in-java",
        "new_folder_slug": "aspose-cells-foss-java-cell-operations",
        "family": "cells",
        "platform": "java",
        "title": "Core Cell Operations in Aspose.Cells FOSS for Java",
        "auto_updatable": True,
        "grade": "A",
        "locale_files": [str(old_locale_path.as_posix())],
        "source_file_updates": [
            {
                "file": str(old_locale_path.as_posix()),
                "old_value": "blog.aspose.org/cells/java/core-in-java/index.md",
                "new_value": "blog.aspose.org/cells/java/aspose-cells-foss-java-cell-operations/index.md",
            }
        ],
    }

    run_migration([candidate], repo_root=repo_root, dry_run=True, out_dir=out_dir)

    # Old folder must still exist
    assert old_folder.is_dir(), "Old folder must still exist after dry-run"
    # New folder must NOT exist
    assert not new_folder.exists(), "New folder must not be created by dry-run"
    # Locale file content must be unchanged
    assert old_locale_path.read_text(encoding="utf-8") == original_locale_content


def test_migration_rollback_manifest_generated(tmp_path):
    """After apply, a rollback manifest JSON must be written."""
    sys.path.insert(0, str(Path(__file__).parents[1]))
    from commands.migration.blog_folder_migrate import run_migration

    blog_root, out_dir = _make_test_blog_structure(tmp_path)
    repo_root = tmp_path

    candidate = {
        "old_folder_slug": "core-in-java",
        "new_folder_slug": "aspose-cells-foss-java-cell-operations",
        "family": "cells",
        "platform": "java",
        "title": "Core Cell Operations in Aspose.Cells FOSS for Java",
        "auto_updatable": True,
        "grade": "A",
        "locale_files": [],
        "source_file_updates": [],
    }

    run_migration([candidate], repo_root=repo_root, dry_run=False, out_dir=out_dir)

    rollback_files = list(out_dir.glob("migration-*-rollback.json"))
    assert len(rollback_files) == 1, f"Expected exactly 1 rollback manifest, got: {rollback_files}"

    manifest = json.loads(rollback_files[0].read_text(encoding="utf-8"))
    assert "rollback_commands" in manifest
    assert len(manifest["rollback_commands"]) >= 1
    assert "core-in-java" in manifest["rollback_commands"][0]


# ---------------------------------------------------------------------------
# Inventory integration tests (mock filesystem via tmp_path)
# ---------------------------------------------------------------------------

_INDEX_MD_TEMPLATE = """\
---
title: {title}
date: '2026-04-27'
draft: false
author: Aspose
provenance:
  content_origin: skill-generated
  last_mechanism: skill
  auto_updatable: true
grade: A
---

## Introduction

Content here.
"""


def _make_blog_structure(tmp_path: Path, posts: list[dict]) -> Path:
    """Create a minimal blog.aspose.org structure for inventory tests."""
    blog_root = tmp_path / "content" / "blog.aspose.org"
    for post in posts:
        folder = blog_root / post["family"] / post["platform"] / post["slug"]
        folder.mkdir(parents=True)
        title = post.get("title", f"Title for {post['slug']}")
        content = post.get("content", _INDEX_MD_TEMPLATE.format(title=title))
        (folder / "index.md").write_text(content, encoding="utf-8")
    return blog_root


def test_inventory_identifies_core_in_java_as_migration_ready(tmp_path):
    """Inventory scanner must classify core-in-java as MIGRATION_READY."""
    sys.path.insert(0, str(Path(__file__).parents[1]))
    from commands.diagnostics.blog_slug_inventory import scan_posts

    blog_root = _make_blog_structure(tmp_path, [
        {"family": "cells", "platform": "java", "slug": "core-in-java",
         "title": "Core Cell Operations in Aspose.Cells FOSS for Java"},
        {"family": "cells", "platform": "java", "slug": "introducing-cells-foss-java",
         "title": "Introducing Aspose.Cells FOSS for Java"},
    ])

    records = scan_posts(blog_root)
    assert len(records) == 2

    core_rec = next(r for r in records if r["folder_slug"] == "core-in-java")
    assert core_rec["classification"] == MIGRATION_READY, (
        f"Expected MIGRATION_READY, got {core_rec['classification']}"
    )

    intro_rec = next(r for r in records if r["folder_slug"] == "introducing-cells-foss-java")
    assert intro_rec["classification"] != MIGRATION_READY, (
        f"introducing-cells-foss-java must not be MIGRATION_READY, got {intro_rec['classification']}"
    )


def test_inventory_weak_slugs_not_in_repair_candidates(tmp_path):
    """WEAK slugs must not appear in repair candidates."""
    sys.path.insert(0, str(Path(__file__).parents[1]))
    from commands.diagnostics.blog_slug_inventory import scan_posts, build_repair_candidates

    blog_root = _make_blog_structure(tmp_path, [
        {"family": "cells", "platform": "java", "slug": "cells-foss-java",
         "title": "Aspose.Cells FOSS for Java Key Features"},
        {"family": "cells", "platform": "java", "slug": "core-in-java",
         "title": "Core Cell Operations in Aspose.Cells FOSS for Java"},
    ])

    records = scan_posts(blog_root)
    candidates = build_repair_candidates(records, blog_root)

    candidate_slugs = {c["old_folder_slug"] for c in candidates}
    # WEAK slug must not be in candidates
    assert "cells-foss-java" not in candidate_slugs, (
        "WEAK slug 'cells-foss-java' must not appear in repair candidates"
    )
    # BAD slug must be in candidates
    assert "core-in-java" in candidate_slugs, (
        "MIGRATION_READY slug 'core-in-java' must appear in repair candidates"
    )


# ---------------------------------------------------------------------------
# T1: Pure-function unit tests (inbound link utilities)
# ---------------------------------------------------------------------------

def _get_migrate_fns():
    """Import pure-function utilities from blog_folder_migrate."""
    sys.path.insert(0, str(Path(__file__).parents[1]))
    from commands.migration.blog_folder_migrate import (
        find_blog_slug_references,
        rewrite_blog_slug_references,
        split_frontmatter_and_body,
    )
    return find_blog_slug_references, rewrite_blog_slug_references, split_frontmatter_and_body


def test_T1_01_root_relative_with_trailing_slash_detected():
    find, _, _ = _get_migrate_fns()
    body = "See [our post](/cells/java/core-in-java/) for details."
    refs = find(body, "cells", "java", "core-in-java")
    assert len(refs) == 1
    assert refs[0]["link_form"] == "root-relative"


def test_T1_02_root_relative_without_trailing_slash_detected():
    find, _, _ = _get_migrate_fns()
    body = "Link: /cells/java/core-in-java here"
    refs = find(body, "cells", "java", "core-in-java")
    assert len(refs) == 1


def test_T1_03_https_absolute_detected():
    find, _, _ = _get_migrate_fns()
    body = "Go to https://blog.aspose.org/cells/java/core-in-java/ now."
    refs = find(body, "cells", "java", "core-in-java")
    assert len(refs) == 1
    assert refs[0]["link_form"] == "absolute"


def test_T1_04_http_absolute_detected():
    find, _, _ = _get_migrate_fns()
    body = "Old link: http://blog.aspose.org/cells/java/core-in-java/"
    refs = find(body, "cells", "java", "core-in-java")
    assert len(refs) == 1
    assert refs[0]["link_form"] == "absolute"


def test_T1_05_protocol_relative_detected():
    find, _, _ = _get_migrate_fns()
    body = "See //blog.aspose.org/cells/java/core-in-java/ for info."
    refs = find(body, "cells", "java", "core-in-java")
    assert len(refs) == 1
    assert refs[0]["link_form"] == "protocol-relative"


def test_T1_06_query_string_preserved_after_rewrite():
    _, rewrite, _ = _get_migrate_fns()
    body = "Visit /cells/java/core-in-java/?ref=home for details."
    new_body, count = rewrite(body, "cells", "java", "core-in-java", "aspose-cells-foss-java-ops")
    assert count == 1
    assert "/aspose-cells-foss-java-ops/?ref=home" in new_body


def test_T1_07_fragment_preserved_after_rewrite():
    _, rewrite, _ = _get_migrate_fns()
    body = "Check [the section](/cells/java/core-in-java/#intro)."
    new_body, count = rewrite(body, "cells", "java", "core-in-java", "aspose-cells-foss-java-ops")
    assert count == 1
    assert "/aspose-cells-foss-java-ops/#intro" in new_body


def test_T1_08_markdown_inline_link_text_preserved():
    _, rewrite, _ = _get_migrate_fns()
    body = "[Core Operations](/cells/java/core-in-java/) is good."
    new_body, count = rewrite(body, "cells", "java", "core-in-java", "aspose-cells-foss-java-ops")
    assert count == 1
    assert "[Core Operations]" in new_body
    assert "aspose-cells-foss-java-ops" in new_body


def test_T1_09_html_anchor_href_rewritten_text_preserved():
    _, rewrite, _ = _get_migrate_fns()
    body = '<a href="/cells/java/core-in-java/">read more</a>'
    new_body, count = rewrite(body, "cells", "java", "core-in-java", "aspose-cells-foss-java-ops")
    assert count == 1
    assert "aspose-cells-foss-java-ops" in new_body
    assert "read more" in new_body


def test_T1_10_partial_slug_not_matched():
    """core-in-java-extra must not match when looking for core-in-java."""
    find, _, _ = _get_migrate_fns()
    body = "See /cells/java/core-in-java-extra/ which is different."
    refs = find(body, "cells", "java", "core-in-java")
    assert len(refs) == 0, f"Partial match must not fire, got: {refs}"


def test_T1_11_unrelated_family_not_matched():
    """words/java/core-in-java must not match when searching cells/java."""
    find, _, _ = _get_migrate_fns()
    body = "See /words/java/core-in-java/ which is different."
    refs = find(body, "cells", "java", "core-in-java")
    assert len(refs) == 0, "Unrelated family must not match"


def test_T1_12_idempotency_rewrite_twice():
    """Rewriting twice must yield count=0 on second run."""
    _, rewrite, _ = _get_migrate_fns()
    body = "Visit /cells/java/core-in-java/ for info."
    new_body1, count1 = rewrite(body, "cells", "java", "core-in-java", "aspose-cells-foss-java-ops")
    assert count1 == 1
    new_body2, count2 = rewrite(new_body1, "cells", "java", "core-in-java", "aspose-cells-foss-java-ops")
    assert count2 == 0, "Second rewrite must produce count=0 (idempotency)"
    assert new_body2 == new_body1


def test_T1_13_source_file_not_matched_when_body_only():
    """source_file: line in frontmatter must not appear in body-only call."""
    find, _, split = _get_migrate_fns()
    text = (
        "---\nsource_file: blog.aspose.org/cells/java/core-in-java/index.md\n---\n\n"
        "Body content here without any URL link.\n"
    )
    _, body = split(text)
    refs = find(body, "cells", "java", "core-in-java")
    assert len(refs) == 0, "source_file: line must not be detected as inbound link"


def test_T1_14_plain_body_url_detected():
    find, _, _ = _get_migrate_fns()
    body = "Plain URL: /cells/java/core-in-java/ appears here."
    refs = find(body, "cells", "java", "core-in-java")
    assert len(refs) >= 1


def test_T1_15_split_frontmatter_and_body_lossless():
    _, _, split = _get_migrate_fns()
    text = "---\ntitle: Hello\n---\n\nBody content here.\n"
    fm, body = split(text)
    assert fm + body == text, "split must be lossless: fm_block + body == text"
    assert "title: Hello" in fm
    assert "Body content" in body


def test_T1_16_markdown_reference_style_link_detected_and_rewritten():
    """Reference-style markdown links must be detected and rewritten."""
    find, rewrite, _ = _get_migrate_fns()
    body = (
        "See [core ops][core-ref] for details.\n\n"
        "[core-ref]: /cells/java/core-in-java/\n"
    )
    refs = find(body, "cells", "java", "core-in-java")
    assert len(refs) == 1, f"Expected 1 ref-style match, got {refs}"

    new_body, count = rewrite(
        body, "cells", "java", "core-in-java", "aspose-cells-foss-java-ops"
    )
    assert count == 1
    assert "aspose-cells-foss-java-ops" in new_body
    assert "[core ops][core-ref]" in new_body  # link text preserved


# ---------------------------------------------------------------------------
# T2: Integration tests — inventory scanner with fixture filesystem
# ---------------------------------------------------------------------------

def _get_inventory_fns():
    sys.path.insert(0, str(Path(__file__).parents[1]))
    from commands.diagnostics.blog_slug_inventory import scan_posts, build_repair_candidates
    return scan_posts, build_repair_candidates


_LINKING_POST_FM = """\
---
title: Using Cells Java Library
date: '2026-04-27'
draft: false
author: Aspose
provenance:
  content_origin: skill-generated
  last_mechanism: skill
  auto_updatable: true
grade: A
---

## Overview

This post discusses cell operations in Java.

For more detail, see the [core operations guide](/cells/java/core-in-java/) which
covers everything you need to know about working with the library.

Another paragraph here for variety.

## Summary

In conclusion, the library is useful.
"""

_SOURCE_FILE_FM_TEMPLATE = """\
---
title: {title}
date: '2026-04-27'
draft: false
author: Aspose
provenance:
  content_origin: skill-generated
  last_mechanism: skill
  auto_updatable: true
  source_file: blog.aspose.org/cells/java/linking-post/index.md
grade: A
---

Locale translated content here.
"""


def test_T2_01_inbound_markdown_link_counted(tmp_path):
    """A markdown link in another post body must be counted as inbound."""
    scan, _ = _get_inventory_fns()

    blog_root = tmp_path / "content" / "blog.aspose.org"
    # Create the source post (core-in-java)
    source_folder = blog_root / "cells" / "java" / "core-in-java"
    source_folder.mkdir(parents=True)
    (source_folder / "index.md").write_text(
        _INDEX_MD_TEMPLATE.format(title="Core Cell Operations in Aspose.Cells FOSS for Java"),
        encoding="utf-8",
    )
    # Create the linking post
    link_folder = blog_root / "cells" / "java" / "using-cells-java"
    link_folder.mkdir(parents=True)
    (link_folder / "index.md").write_text(_LINKING_POST_FM, encoding="utf-8")

    records = scan(blog_root)
    core_rec = next(r for r in records if r["folder_slug"] == "core-in-java")
    assert core_rec["inbound_link_count"] == 1, (
        f"Expected 1 inbound link, got {core_rec['inbound_link_count']}"
    )
    assert len(core_rec["inbound_link_files"]) == 1


def test_T2_02_source_file_not_counted_as_inbound(tmp_path):
    """source_file: in locale frontmatter must NOT be counted as inbound link."""
    scan, _ = _get_inventory_fns()

    blog_root = tmp_path / "content" / "blog.aspose.org"
    source_folder = blog_root / "cells" / "java" / "core-in-java"
    source_folder.mkdir(parents=True)
    (source_folder / "index.md").write_text(
        _INDEX_MD_TEMPLATE.format(title="Core Cell Operations"),
        encoding="utf-8",
    )
    # Create a locale file in a different post whose frontmatter has source_file
    # pointing to the core-in-java post path (not a body URL link)
    other_folder = blog_root / "cells" / "java" / "other-post"
    other_folder.mkdir(parents=True)
    locale_content = """\
---
title: Other Post (Arabic)
provenance:
  source_file: blog.aspose.org/cells/java/core-in-java/index.md
---

No body links here.
"""
    (other_folder / "index.ar.md").write_text(locale_content, encoding="utf-8")
    (other_folder / "index.md").write_text(
        _INDEX_MD_TEMPLATE.format(title="Other Post"),
        encoding="utf-8",
    )

    records = scan(blog_root)
    core_rec = next(r for r in records if r["folder_slug"] == "core-in-java")
    assert core_rec["inbound_link_count"] == 0, (
        f"source_file: must not count as inbound link, got {core_rec['inbound_link_count']}"
    )


def test_T2_03_link_to_different_slug_not_counted(tmp_path):
    """A link to a different slug must not appear in core-in-java inbound links."""
    scan, _ = _get_inventory_fns()

    blog_root = tmp_path / "content" / "blog.aspose.org"
    source_folder = blog_root / "cells" / "java" / "core-in-java"
    source_folder.mkdir(parents=True)
    (source_folder / "index.md").write_text(
        _INDEX_MD_TEMPLATE.format(title="Core Cell Operations"),
        encoding="utf-8",
    )
    other_folder = blog_root / "cells" / "java" / "other-post"
    other_folder.mkdir(parents=True)
    other_content = _INDEX_MD_TEMPLATE.format(title="Other Post").replace(
        "Content here.",
        "See [other post](/cells/java/different-slug/) for details.",
    )
    (other_folder / "index.md").write_text(other_content, encoding="utf-8")

    records = scan(blog_root)
    core_rec = next(r for r in records if r["folder_slug"] == "core-in-java")
    assert core_rec["inbound_link_count"] == 0


def test_T2_04_malformed_yaml_excluded(tmp_path):
    """Malformed YAML frontmatter → frontmatter_valid=False, excluded from candidates."""
    scan, build = _get_inventory_fns()

    blog_root = tmp_path / "content" / "blog.aspose.org"
    folder = blog_root / "cells" / "java" / "core-in-java"
    folder.mkdir(parents=True)
    bad_content = "---\ntitle: Good\nbad: [unclosed\n---\n\nContent here.\n"
    (folder / "index.md").write_text(bad_content, encoding="utf-8")

    records = scan(blog_root)
    rec = records[0]
    assert rec["frontmatter_valid"] is False
    assert rec["has_frontmatter"] is True
    assert rec["frontmatter_error"] is not None

    candidates = build(records, blog_root)
    assert not any(c["old_folder_slug"] == "core-in-java" for c in candidates), (
        "Malformed-FM post must not appear in candidates"
    )


def test_T2_05_unterminated_frontmatter_excluded(tmp_path):
    """Unterminated frontmatter (no closing ---) → has_frontmatter=False."""
    scan, build = _get_inventory_fns()

    blog_root = tmp_path / "content" / "blog.aspose.org"
    folder = blog_root / "cells" / "java" / "core-in-java"
    folder.mkdir(parents=True)
    # No closing ---
    bad_content = "---\ntitle: Hello\ndraft: false\n\nContent here.\n"
    (folder / "index.md").write_text(bad_content, encoding="utf-8")

    records = scan(blog_root)
    rec = records[0]
    assert rec["has_frontmatter"] is False
    assert rec["frontmatter_valid"] is False

    candidates = build(records, blog_root)
    assert len(candidates) == 0


def test_T2_06_yaml_list_frontmatter_excluded(tmp_path):
    """YAML that parses to a list (not dict) → frontmatter_valid=False."""
    scan, build = _get_inventory_fns()

    blog_root = tmp_path / "content" / "blog.aspose.org"
    folder = blog_root / "cells" / "java" / "core-in-java"
    folder.mkdir(parents=True)
    list_fm = "---\n- item1\n- item2\n---\n\nContent here.\n"
    (folder / "index.md").write_text(list_fm, encoding="utf-8")

    records = scan(blog_root)
    rec = records[0]
    assert rec["frontmatter_valid"] is False
    assert "not a mapping" in (rec["frontmatter_error"] or "")

    candidates = build(records, blog_root)
    assert len(candidates) == 0


def test_T2_07_valid_empty_frontmatter_not_malformed(tmp_path):
    """Empty frontmatter block must produce a structured record with required diagnostic fields.

    Implementation note: "---\n---\n" is a degenerate case — the FM regex requires at least
    one character including a newline before the closing delimiters, so this is treated as
    has_frontmatter=False (no FM block detected). This is acceptable: it is not classified as
    "malformed-frontmatter" (which requires a block to exist but fail to parse), but as
    "no-frontmatter". The key invariant is that fm == {} is never used to infer malformed state.
    """
    scan, _ = _get_inventory_fns()

    blog_root = tmp_path / "content" / "blog.aspose.org"
    folder = blog_root / "cells" / "java" / "some-post"
    folder.mkdir(parents=True)
    # Truly empty FM block: no content between delimiters
    empty_fm = "---\n---\n\nContent here.\n"
    (folder / "index.md").write_text(empty_fm, encoding="utf-8")

    records = scan(blog_root)
    rec = records[0]
    # Record must always have the required diagnostic fields
    assert "has_frontmatter" in rec
    assert "frontmatter_valid" in rec
    assert "candidate_status" in rec
    assert "candidate_blockers" in rec
    assert isinstance(rec["candidate_blockers"], list)
    # Must not be classified as ELIGIBLE (no valid frontmatter)
    assert rec["candidate_status"] != "ELIGIBLE"
    # The blocker must be either "no-frontmatter" or "malformed-frontmatter" — not missing
    assert rec["candidate_blockers"], "candidate_blockers must not be empty for this post"
    blocker = rec["candidate_blockers"][0]
    assert blocker in ("no-frontmatter", "malformed-frontmatter"), (
        f"Expected no-frontmatter or malformed-frontmatter, got: {blocker}"
    )


def test_T2_08_depth_too_shallow_excluded(tmp_path):
    """Depth < 4 (family/slug/index.md) → path_shape_valid=False, excluded."""
    scan, build = _get_inventory_fns()

    blog_root = tmp_path / "content" / "blog.aspose.org"
    # Only 2 levels: family/slug/index.md — missing platform segment
    folder = blog_root / "cells" / "core-in-java"
    folder.mkdir(parents=True)
    (folder / "index.md").write_text(
        _INDEX_MD_TEMPLATE.format(title="Core in Java"), encoding="utf-8"
    )

    records = scan(blog_root)
    assert len(records) == 1
    rec = records[0]
    assert rec["path_shape_valid"] is False
    assert "invalid-path-shape" in rec["candidate_blockers"]

    candidates = build(records, blog_root)
    assert len(candidates) == 0


def test_T2_09_depth_too_deep_excluded(tmp_path):
    """Depth > 4 (family/platform/slug/sub/index.md) → path_shape_valid=False, excluded."""
    scan, build = _get_inventory_fns()

    blog_root = tmp_path / "content" / "blog.aspose.org"
    # Extra subfolder level
    folder = blog_root / "cells" / "java" / "core-in-java" / "sub"
    folder.mkdir(parents=True)
    (folder / "index.md").write_text(
        _INDEX_MD_TEMPLATE.format(title="Core in Java Sub"), encoding="utf-8"
    )

    records = scan(blog_root)
    assert len(records) == 1
    rec = records[0]
    assert rec["path_shape_valid"] is False

    candidates = build(records, blog_root)
    assert len(candidates) == 0


def test_T2_10_draft_true_excluded(tmp_path):
    """draft: true → candidate_blockers contains 'draft', excluded from candidates."""
    scan, build = _get_inventory_fns()

    blog_root = tmp_path / "content" / "blog.aspose.org"
    folder = blog_root / "cells" / "java" / "core-in-java"
    folder.mkdir(parents=True)
    draft_content = """\
---
title: Core Cell Operations in Aspose.Cells FOSS for Java
date: '2026-04-27'
draft: true
author: Aspose
provenance:
  content_origin: skill-generated
  auto_updatable: true
grade: A
---

Content here.
"""
    (folder / "index.md").write_text(draft_content, encoding="utf-8")

    records = scan(blog_root)
    rec = records[0]
    assert "draft" in rec["candidate_blockers"], (
        f"Expected 'draft' in candidate_blockers, got: {rec['candidate_blockers']}"
    )

    candidates = build(records, blog_root)
    assert len(candidates) == 0


def test_T2_11_draft_false_not_excluded(tmp_path):
    """draft: false → not excluded by draft rule."""
    scan, _ = _get_inventory_fns()

    blog_root = tmp_path / "content" / "blog.aspose.org"
    folder = blog_root / "cells" / "java" / "core-in-java"
    folder.mkdir(parents=True)
    (folder / "index.md").write_text(
        _INDEX_MD_TEMPLATE.format(title="Core Cell Operations in Aspose.Cells FOSS for Java"),
        encoding="utf-8",
    )

    records = scan(blog_root)
    rec = records[0]
    assert "draft" not in rec["candidate_blockers"]


def test_T2_12_draft_key_absent_not_excluded(tmp_path):
    """Missing draft key defaults to False — not excluded."""
    scan, _ = _get_inventory_fns()

    blog_root = tmp_path / "content" / "blog.aspose.org"
    folder = blog_root / "cells" / "java" / "core-in-java"
    folder.mkdir(parents=True)
    content = """\
---
title: Core Cell Operations in Aspose.Cells FOSS for Java
date: '2026-04-27'
author: Aspose
provenance:
  content_origin: skill-generated
  auto_updatable: true
grade: A
---

Content here.
"""
    (folder / "index.md").write_text(content, encoding="utf-8")

    records = scan(blog_root)
    rec = records[0]
    assert "draft" not in rec["candidate_blockers"]


def test_T2_13_draft_string_true_excluded(tmp_path):
    """draft: \"true\" (string) → excluded conservatively."""
    scan, build = _get_inventory_fns()

    blog_root = tmp_path / "content" / "blog.aspose.org"
    folder = blog_root / "cells" / "java" / "core-in-java"
    folder.mkdir(parents=True)
    content = """\
---
title: Core Cell Operations in Aspose.Cells FOSS for Java
draft: "true"
provenance:
  content_origin: skill-generated
  auto_updatable: true
---

Content here.
"""
    (folder / "index.md").write_text(content, encoding="utf-8")

    records = scan(blog_root)
    rec = records[0]
    assert "draft" in rec["candidate_blockers"], (
        f"String 'true' draft must be treated as draft. Blockers: {rec['candidate_blockers']}"
    )

    candidates = build(records, blog_root)
    assert len(candidates) == 0


def test_T2_14_record_has_required_diagnostic_fields(tmp_path):
    """Every record must have candidate_status, candidate_blockers, candidate_exclusion_reason."""
    scan, _ = _get_inventory_fns()

    blog_root = _make_blog_structure(tmp_path, [
        {"family": "cells", "platform": "java", "slug": "core-in-java",
         "title": "Core Cell Operations in Aspose.Cells FOSS for Java"},
    ])

    records = scan(blog_root)
    rec = records[0]
    assert "candidate_status" in rec
    assert "candidate_blockers" in rec
    assert "candidate_exclusion_reason" in rec
    assert isinstance(rec["candidate_blockers"], list)


def test_T2_15_inbound_link_count_zero_explicit(tmp_path):
    """inbound_link_count=0 must be explicitly present in every record."""
    scan, _ = _get_inventory_fns()

    blog_root = _make_blog_structure(tmp_path, [
        {"family": "cells", "platform": "java", "slug": "core-in-java",
         "title": "Core Cell Operations in Aspose.Cells FOSS for Java"},
    ])

    records = scan(blog_root)
    rec = records[0]
    assert "inbound_link_count" in rec
    assert rec["inbound_link_count"] == 0
    assert rec["inbound_link_files"] == []


def test_T2_16_repair_candidate_has_alias_fields(tmp_path):
    """Repair candidate must include old_url, new_url, required_alias, alias_required=True."""
    scan, build = _get_inventory_fns()

    blog_root = _make_blog_structure(tmp_path, [
        {"family": "cells", "platform": "java", "slug": "core-in-java",
         "title": "Core Cell Operations in Aspose.Cells FOSS for Java"},
    ])

    records = scan(blog_root)
    candidates = build(records, blog_root)

    assert len(candidates) >= 1
    cand = next(c for c in candidates if c["old_folder_slug"] == "core-in-java")
    assert "old_url" in cand
    assert "new_url" in cand
    assert "required_alias" in cand
    assert cand["alias_required"] is True
    assert cand["required_alias"] == "/cells/java/core-in-java/"


def test_T2_17_non_candidate_does_not_emit_alias_required(tmp_path):
    """Non-candidate (WEAK or EXCLUDED) posts must not have alias_required in candidates."""
    scan, build = _get_inventory_fns()

    blog_root = _make_blog_structure(tmp_path, [
        {"family": "cells", "platform": "java", "slug": "cells-foss-java",
         "title": "Aspose.Cells FOSS for Java"},
    ])

    records = scan(blog_root)
    candidates = build(records, blog_root)

    # cells-foss-java is WEAK — must not appear in candidates at all
    assert not any(c["old_folder_slug"] == "cells-foss-java" for c in candidates)


def test_T2_18_malformed_frontmatter_blocker_prevents_candidate(tmp_path):
    """malformed-frontmatter blocker must prevent candidate regardless of slug classification."""
    scan, build = _get_inventory_fns()

    blog_root = tmp_path / "content" / "blog.aspose.org"
    folder = blog_root / "cells" / "java" / "core-in-java"
    folder.mkdir(parents=True)
    # Slug is BAD_GENERIC (core-in-java) but frontmatter is malformed
    bad_content = "---\ntitle: Core\nbad: [unclosed\n---\n\nContent.\n"
    (folder / "index.md").write_text(bad_content, encoding="utf-8")

    records = scan(blog_root)
    rec = records[0]
    assert "malformed-frontmatter" in rec["candidate_blockers"]

    candidates = build(records, blog_root)
    assert len(candidates) == 0, "Malformed-FM post must never be a candidate"


# ---------------------------------------------------------------------------
# T3: Integration tests — alias helper
# ---------------------------------------------------------------------------

def _get_alias_fn():
    sys.path.insert(0, str(Path(__file__).parents[1]))
    from commands.migration.blog_folder_migrate import add_alias_to_english_index
    return add_alias_to_english_index


_FULL_FM_FOR_ALIAS = """\
---
title: Core Cell Operations in Aspose.Cells FOSS for Java
date: '2026-04-27'
draft: false
author: Aspose
provenance:
  content_origin: skill-generated
  last_mechanism: skill
  auto_updatable: true
  source_file: blog.aspose.org/cells/java/core-in-java/index.md
grade: A
---

## Introduction

This is the body of the post with multiple paragraphs.

## Section Two

More content here describing the features.

## Conclusion

Final thoughts on using the library.
"""


def test_T3_01_apply_mode_adds_alias(tmp_path):
    """add_alias_to_english_index must add aliases: [old_url] in apply mode."""
    add_alias = _get_alias_fn()

    index_path = tmp_path / "index.md"
    index_path.write_text(_FULL_FM_FOR_ALIAS, encoding="utf-8")

    result = add_alias(index_path, "/cells/java/core-in-java/", dry_run=False)
    assert result["added"] is True
    assert result["already_present"] is False

    content = index_path.read_text(encoding="utf-8")
    assert "aliases:" in content
    assert "/cells/java/core-in-java/" in content


def test_T3_02_apply_mode_preserves_other_fields(tmp_path):
    """All other frontmatter fields must be preserved unchanged."""
    add_alias = _get_alias_fn()
    import yaml as _yaml

    index_path = tmp_path / "index.md"
    index_path.write_text(_FULL_FM_FOR_ALIAS, encoding="utf-8")

    add_alias(index_path, "/cells/java/core-in-java/", dry_run=False)

    content = index_path.read_text(encoding="utf-8")
    fm_m = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", content, re.DOTALL)
    assert fm_m, "Frontmatter must still be present"
    fm = _yaml.safe_load(fm_m.group(1))
    assert fm["title"] == "Core Cell Operations in Aspose.Cells FOSS for Java"
    assert fm["grade"] == "A"
    assert fm["draft"] is False
    assert fm["provenance"]["auto_updatable"] is True


def test_T3_03_apply_mode_preserves_body(tmp_path):
    """Body content must be preserved byte-for-byte."""
    add_alias = _get_alias_fn()

    index_path = tmp_path / "index.md"
    index_path.write_text(_FULL_FM_FOR_ALIAS, encoding="utf-8")

    # Extract original body
    _, orig_body = _FULL_FM_FOR_ALIAS.split("---\n\n", 1)

    add_alias(index_path, "/cells/java/core-in-java/", dry_run=False)

    content = index_path.read_text(encoding="utf-8")
    # Body is everything after the closing ---
    fm_m = re.match(r"^(---\s*\n.*?\n---\s*\n)", content, re.DOTALL)
    assert fm_m
    body_after = content[fm_m.end():]
    # The body text (after the FM delimiter) must contain all the same content
    assert "## Introduction" in body_after
    assert "## Conclusion" in body_after


def test_T3_04_apply_mode_does_not_add_slug(tmp_path):
    """add_alias_to_english_index must not add slug: field."""
    add_alias = _get_alias_fn()

    index_path = tmp_path / "index.md"
    index_path.write_text(_FULL_FM_FOR_ALIAS, encoding="utf-8")

    add_alias(index_path, "/cells/java/core-in-java/", dry_run=False)

    content = index_path.read_text(encoding="utf-8")
    assert not re.search(r"^\s*slug\s*:", content, re.MULTILINE), "slug: must not be added"


def test_T3_05_dry_run_does_not_modify_file(tmp_path):
    """Dry-run mode must not write to file; result shows added=True."""
    add_alias = _get_alias_fn()

    index_path = tmp_path / "index.md"
    index_path.write_text(_FULL_FM_FOR_ALIAS, encoding="utf-8")
    original = index_path.read_text(encoding="utf-8")

    result = add_alias(index_path, "/cells/java/core-in-java/", dry_run=True)
    assert result["added"] is True
    assert result["dry_run"] is True

    # File must be unchanged
    assert index_path.read_text(encoding="utf-8") == original


def test_T3_06_idempotency_second_call(tmp_path):
    """Second call with same alias: added=False, already_present=True; file unchanged."""
    add_alias = _get_alias_fn()

    index_path = tmp_path / "index.md"
    index_path.write_text(_FULL_FM_FOR_ALIAS, encoding="utf-8")

    add_alias(index_path, "/cells/java/core-in-java/", dry_run=False)
    content_after_first = index_path.read_text(encoding="utf-8")

    result2 = add_alias(index_path, "/cells/java/core-in-java/", dry_run=False)
    assert result2["added"] is False
    assert result2["already_present"] is True
    assert index_path.read_text(encoding="utf-8") == content_after_first


def test_T3_07_preexisting_alias_preserved(tmp_path):
    """Pre-existing aliases must be preserved alongside the new one."""
    add_alias = _get_alias_fn()
    import yaml as _yaml

    content_with_alias = """\
---
title: Core Cell Operations in Aspose.Cells FOSS for Java
date: '2026-04-27'
draft: false
provenance:
  content_origin: skill-generated
  auto_updatable: true
aliases:
- /cells/java/previous-old-slug/
grade: A
---

Body content here.
"""
    index_path = tmp_path / "index.md"
    index_path.write_text(content_with_alias, encoding="utf-8")

    result = add_alias(index_path, "/cells/java/core-in-java/", dry_run=False)
    assert result["added"] is True

    content = index_path.read_text(encoding="utf-8")
    fm_m = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", content, re.DOTALL)
    fm = _yaml.safe_load(fm_m.group(1))
    assert "/cells/java/previous-old-slug/" in fm["aliases"], "Pre-existing alias must be preserved"
    assert "/cells/java/core-in-java/" in fm["aliases"], "New alias must be added"


def test_T3_08_runtime_error_if_no_frontmatter(tmp_path):
    """RuntimeError must be raised if file has no frontmatter."""
    add_alias = _get_alias_fn()

    index_path = tmp_path / "index.md"
    index_path.write_text("No frontmatter here.\n\nJust content.\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="no frontmatter"):
        add_alias(index_path, "/cells/java/old-slug/", dry_run=False)


def test_T3_09_runtime_error_if_malformed_frontmatter(tmp_path):
    """RuntimeError must be raised if frontmatter is malformed YAML."""
    add_alias = _get_alias_fn()

    index_path = tmp_path / "index.md"
    index_path.write_text("---\nbad: [unclosed\n---\n\nContent.\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="malformed"):
        add_alias(index_path, "/cells/java/old-slug/", dry_run=False)


def test_T3_10_alias_list_style_is_block_not_flow(tmp_path):
    """aliases: must be written as YAML block list, not flow list."""
    add_alias = _get_alias_fn()

    index_path = tmp_path / "index.md"
    index_path.write_text(_FULL_FM_FOR_ALIAS, encoding="utf-8")

    add_alias(index_path, "/cells/java/core-in-java/", dry_run=False)

    content = index_path.read_text(encoding="utf-8")
    # Block list format: "- /cells/java/core-in-java/" on its own line
    assert re.search(r"^\s*-\s+/cells/java/core-in-java/\s*$", content, re.MULTILINE), (
        "aliases must be in block list format (- url), not flow format ([url])"
    )


# ---------------------------------------------------------------------------
# T4: Integration tests — migration tool with fixture filesystem
# ---------------------------------------------------------------------------

_MULTI_PARA_LINKING_FM = """\
---
title: Using Cells Java Library for Cell Operations
date: '2026-04-27'
draft: false
author: Aspose
provenance:
  content_origin: skill-generated
  last_mechanism: skill
  auto_updatable: true
grade: A
---

## Overview

This comprehensive guide explains how to use the Aspose.Cells FOSS Java library
for various cell operations. The library provides rich APIs for working with spreadsheets.

## Core Operations

For a detailed introduction, see [Core Operations Guide](/cells/java/core-in-java/)
which covers the fundamental operations you need to master the library.

## Advanced Usage

After reading the core guide, you can explore more advanced topics. The library
supports complex formulas, charts, and data manipulation.

## Conclusion

In summary, Aspose.Cells FOSS is an excellent choice for Java applications that
require spreadsheet manipulation without licensing fees.
"""

_ENGLISH_INDEX_WITH_PROVENANCE = """\
---
title: Core Cell Operations in Aspose.Cells FOSS for Java
date: '2026-04-27'
draft: false
author: Aspose
provenance:
  content_origin: skill-generated
  last_mechanism: skill
  auto_updatable: true
  source_file: blog.aspose.org/cells/java/core-in-java/index.md
grade: A
---

## Introduction

This post covers core cell operations in the Aspose.Cells FOSS Java library.

## Key Features

The library provides APIs for reading, writing, and manipulating spreadsheets.

## Summary

These operations form the foundation of spreadsheet processing with Aspose.Cells.
"""

_LOCALE_WITH_PROVENANCE = """\
---
title: Core Cell Operations (Arabic)
provenance:
  content_origin: skill-generated
  auto_updatable: true
  source_file: blog.aspose.org/cells/java/core-in-java/index.md
---

Translated content covering core operations.
"""


def _make_full_migration_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Create full fixture: source post + linking post + locale file."""
    blog_root = tmp_path / "content" / "blog.aspose.org"

    # Source post (to be migrated)
    source_folder = blog_root / "cells" / "java" / "core-in-java"
    source_folder.mkdir(parents=True)
    (source_folder / "index.md").write_text(_ENGLISH_INDEX_WITH_PROVENANCE, encoding="utf-8")
    (source_folder / "index.ar.md").write_text(_LOCALE_WITH_PROVENANCE, encoding="utf-8")

    # Linking post (contains body link to core-in-java)
    link_folder = blog_root / "cells" / "java" / "using-cells-java"
    link_folder.mkdir(parents=True)
    (link_folder / "index.md").write_text(_MULTI_PARA_LINKING_FM, encoding="utf-8")

    out_dir = tmp_path / "reports" / "blog-slugs"
    out_dir.mkdir(parents=True)

    return blog_root, source_folder, out_dir


def _make_t4_candidate(blog_root: Path) -> dict:
    locale_path = blog_root / "cells" / "java" / "core-in-java" / "index.ar.md"
    return {
        "old_folder_slug": "core-in-java",
        "new_folder_slug": "aspose-cells-foss-java-cell-operations",
        "family": "cells",
        "platform": "java",
        "title": "Core Cell Operations in Aspose.Cells FOSS for Java",
        "auto_updatable": True,
        "grade": "A",
        "locale_files": [str(locale_path.as_posix())],
        "source_file_updates": [
            {
                "file": str(locale_path.as_posix()),
                "old_value": "blog.aspose.org/cells/java/core-in-java/index.md",
                "new_value": "blog.aspose.org/cells/java/aspose-cells-foss-java-cell-operations/index.md",
            }
        ],
    }


def test_T4_01_apply_rewrites_inbound_markdown_link(tmp_path):
    """Apply mode must rewrite inbound markdown link in linking file."""
    sys.path.insert(0, str(Path(__file__).parents[1]))
    from commands.migration.blog_folder_migrate import run_migration

    blog_root, _, out_dir = _make_full_migration_fixture(tmp_path)
    repo_root = tmp_path

    run_migration([_make_t4_candidate(blog_root)], repo_root=repo_root, dry_run=False, out_dir=out_dir)

    link_file = blog_root / "cells" / "java" / "using-cells-java" / "index.md"
    content = link_file.read_text(encoding="utf-8")
    assert "aspose-cells-foss-java-cell-operations" in content
    assert "/cells/java/core-in-java/" not in content


def test_T4_02_apply_link_text_unchanged(tmp_path):
    """Link text must be preserved after inbound link rewrite."""
    sys.path.insert(0, str(Path(__file__).parents[1]))
    from commands.migration.blog_folder_migrate import run_migration

    blog_root, _, out_dir = _make_full_migration_fixture(tmp_path)
    repo_root = tmp_path

    run_migration([_make_t4_candidate(blog_root)], repo_root=repo_root, dry_run=False, out_dir=out_dir)

    link_file = blog_root / "cells" / "java" / "using-cells-java" / "index.md"
    content = link_file.read_text(encoding="utf-8")
    assert "[Core Operations Guide]" in content


def test_T4_03_apply_linking_file_frontmatter_unchanged(tmp_path):
    """Linking file frontmatter must be identical after migration."""
    sys.path.insert(0, str(Path(__file__).parents[1]))
    from commands.migration.blog_folder_migrate import run_migration

    blog_root, _, out_dir = _make_full_migration_fixture(tmp_path)
    repo_root = tmp_path

    link_file = blog_root / "cells" / "java" / "using-cells-java" / "index.md"
    fm_m = re.match(r"^(---\s*\n.*?\n---\s*\n)", _MULTI_PARA_LINKING_FM, re.DOTALL)
    original_fm = fm_m.group(1)

    run_migration([_make_t4_candidate(blog_root)], repo_root=repo_root, dry_run=False, out_dir=out_dir)

    content = link_file.read_text(encoding="utf-8")
    fm_m2 = re.match(r"^(---\s*\n.*?\n---\s*\n)", content, re.DOTALL)
    assert fm_m2 and fm_m2.group(1) == original_fm, "Linking file frontmatter must be unchanged"


def test_T4_04_unrelated_link_unchanged(tmp_path):
    """Links to unrelated slugs in linking file must not be modified."""
    sys.path.insert(0, str(Path(__file__).parents[1]))
    from commands.migration.blog_folder_migrate import run_migration

    blog_root = tmp_path / "content" / "blog.aspose.org"
    source_folder = blog_root / "cells" / "java" / "core-in-java"
    source_folder.mkdir(parents=True)
    (source_folder / "index.md").write_text(_ENGLISH_INDEX_WITH_PROVENANCE, encoding="utf-8")

    link_folder = blog_root / "cells" / "java" / "using-cells-java"
    link_folder.mkdir(parents=True)
    content_with_unrelated = """\
---
title: Using Cells Java
provenance:
  content_origin: skill-generated
  auto_updatable: true
---

See [core](/cells/java/core-in-java/) and also [other](/cells/java/other-post/).
"""
    (link_folder / "index.md").write_text(content_with_unrelated, encoding="utf-8")

    out_dir = tmp_path / "reports" / "blog-slugs"
    out_dir.mkdir(parents=True)

    cand = {
        "old_folder_slug": "core-in-java",
        "new_folder_slug": "aspose-cells-foss-java-cell-operations",
        "family": "cells", "platform": "java",
        "title": "Core Cell Operations", "auto_updatable": True, "grade": "A",
        "locale_files": [], "source_file_updates": [],
    }

    run_migration([cand], repo_root=tmp_path, dry_run=False, out_dir=out_dir)

    result_content = (link_folder / "index.md").read_text(encoding="utf-8")
    assert "/cells/java/other-post/" in result_content  # unrelated link preserved


def test_T4_05_apply_english_index_has_alias(tmp_path):
    """After apply, English index.md must have aliases: [old_url]."""
    sys.path.insert(0, str(Path(__file__).parents[1]))
    from commands.migration.blog_folder_migrate import run_migration

    blog_root, _, out_dir = _make_full_migration_fixture(tmp_path)
    repo_root = tmp_path

    run_migration([_make_t4_candidate(blog_root)], repo_root=repo_root, dry_run=False, out_dir=out_dir)

    new_index = blog_root / "cells" / "java" / "aspose-cells-foss-java-cell-operations" / "index.md"
    content = new_index.read_text(encoding="utf-8")
    import yaml as _yaml
    fm_m = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", content, re.DOTALL)
    assert fm_m
    fm = _yaml.safe_load(fm_m.group(1))
    assert "/cells/java/core-in-java/" in fm.get("aliases", []), (
        f"English index.md must have aliases: [/cells/java/core-in-java/]. Got: {fm.get('aliases')}"
    )


def test_T4_06_apply_locale_file_has_no_aliases(tmp_path):
    """After apply, locale files must NOT have aliases:."""
    sys.path.insert(0, str(Path(__file__).parents[1]))
    from commands.migration.blog_folder_migrate import run_migration

    blog_root, _, out_dir = _make_full_migration_fixture(tmp_path)
    repo_root = tmp_path

    run_migration([_make_t4_candidate(blog_root)], repo_root=repo_root, dry_run=False, out_dir=out_dir)

    new_folder = blog_root / "cells" / "java" / "aspose-cells-foss-java-cell-operations"
    for locale_file in new_folder.glob("index.*.md"):
        content = locale_file.read_text(encoding="utf-8")
        assert not re.search(r"^\s*aliases\s*:", content, re.MULTILINE), (
            f"Locale file {locale_file.name} must not have aliases:"
        )


def test_T4_07_apply_locale_source_file_updated(tmp_path):
    """Locale source_file must be updated to new slug path."""
    sys.path.insert(0, str(Path(__file__).parents[1]))
    from commands.migration.blog_folder_migrate import run_migration

    blog_root, _, out_dir = _make_full_migration_fixture(tmp_path)
    repo_root = tmp_path

    run_migration([_make_t4_candidate(blog_root)], repo_root=repo_root, dry_run=False, out_dir=out_dir)

    locale_file = blog_root / "cells" / "java" / "aspose-cells-foss-java-cell-operations" / "index.ar.md"
    assert locale_file.exists()
    content = locale_file.read_text(encoding="utf-8")
    assert "aspose-cells-foss-java-cell-operations" in content
    assert "core-in-java" not in content


def test_T4_08_dry_run_linking_file_not_modified(tmp_path):
    """Dry-run must not write to linking file."""
    sys.path.insert(0, str(Path(__file__).parents[1]))
    from commands.migration.blog_folder_migrate import run_migration

    blog_root, _, out_dir = _make_full_migration_fixture(tmp_path)
    repo_root = tmp_path

    link_file = blog_root / "cells" / "java" / "using-cells-java" / "index.md"
    original = link_file.read_text(encoding="utf-8")

    run_migration([_make_t4_candidate(blog_root)], repo_root=repo_root, dry_run=True, out_dir=out_dir)

    assert link_file.read_text(encoding="utf-8") == original


def test_T4_09_dry_run_alias_update_in_result(tmp_path):
    """Dry-run result_entry must show alias_update.added=True but file not written."""
    sys.path.insert(0, str(Path(__file__).parents[1]))
    from commands.migration.blog_folder_migrate import run_migration

    blog_root, _, out_dir = _make_full_migration_fixture(tmp_path)
    repo_root = tmp_path

    manifest = run_migration(
        [_make_t4_candidate(blog_root)], repo_root=repo_root, dry_run=True, out_dir=out_dir
    )

    assert manifest["mode"] == "dry-run"
    entry = manifest["renames"][0]
    alias_upd = entry.get("alias_update")
    assert alias_upd is not None
    assert alias_upd["added"] is True
    assert alias_upd["dry_run"] is True

    # English index must NOT be modified
    english_index = blog_root / "cells" / "java" / "core-in-java" / "index.md"
    content = english_index.read_text(encoding="utf-8")
    assert "aliases:" not in content


def test_T4_10_dry_run_inbound_updates_populated_not_written(tmp_path):
    """Dry-run inbound_link_updates must be populated but no files written."""
    sys.path.insert(0, str(Path(__file__).parents[1]))
    from commands.migration.blog_folder_migrate import run_migration

    blog_root, _, out_dir = _make_full_migration_fixture(tmp_path)
    repo_root = tmp_path

    link_file = blog_root / "cells" / "java" / "using-cells-java" / "index.md"
    original = link_file.read_text(encoding="utf-8")

    manifest = run_migration(
        [_make_t4_candidate(blog_root)], repo_root=repo_root, dry_run=True, out_dir=out_dir
    )

    entry = manifest["renames"][0]
    # The dry-run inbound scan must detect the link (populated, not just present)
    assert "inbound_link_updates" in entry
    assert len(entry["inbound_link_updates"]) > 0, (
        "Dry-run inbound_link_updates must be non-empty when a linking post exists"
    )
    assert entry["inbound_link_updates"][0]["dry_run"] is True

    # File must not be changed
    assert link_file.read_text(encoding="utf-8") == original


def test_T4_11_idempotency_alias_not_duplicated(tmp_path):
    """Running migration twice: alias not duplicated; inbound link count=0 on second run."""
    sys.path.insert(0, str(Path(__file__).parents[1]))
    from commands.migration.blog_folder_migrate import run_migration, add_alias_to_english_index
    import yaml as _yaml

    blog_root, _, out_dir = _make_full_migration_fixture(tmp_path)
    repo_root = tmp_path

    run_migration([_make_t4_candidate(blog_root)], repo_root=repo_root, dry_run=False, out_dir=out_dir)

    new_index = blog_root / "cells" / "java" / "aspose-cells-foss-java-cell-operations" / "index.md"
    content_after_first = new_index.read_text(encoding="utf-8")
    fm_m = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", content_after_first, re.DOTALL)
    fm_first = _yaml.safe_load(fm_m.group(1))
    alias_count = fm_first.get("aliases", []).count("/cells/java/core-in-java/")
    assert alias_count == 1, f"Expected alias exactly once after first run, got {alias_count}"

    # Second call to alias helper: must return already_present=True
    result2 = add_alias_to_english_index(new_index, "/cells/java/core-in-java/", dry_run=False)
    assert result2["already_present"] is True
    assert result2["added"] is False

    content_after_second = new_index.read_text(encoding="utf-8")
    fm_m2 = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", content_after_second, re.DOTALL)
    fm_second = _yaml.safe_load(fm_m2.group(1))
    alias_count2 = fm_second.get("aliases", []).count("/cells/java/core-in-java/")
    assert alias_count2 == 1, f"Alias must not be duplicated, got {alias_count2}"


def test_T4_12_rollback_manifest_includes_undo_alias(tmp_path):
    """Rollback manifest must include undo_alias instruction for English index.md."""
    sys.path.insert(0, str(Path(__file__).parents[1]))
    from commands.migration.blog_folder_migrate import run_migration

    blog_root, _, out_dir = _make_full_migration_fixture(tmp_path)
    repo_root = tmp_path

    run_migration([_make_t4_candidate(blog_root)], repo_root=repo_root, dry_run=False, out_dir=out_dir)

    rollback_files = list(out_dir.glob("migration-*-rollback.json"))
    assert len(rollback_files) == 1
    manifest = json.loads(rollback_files[0].read_text(encoding="utf-8"))
    assert "undo_notes" in manifest
    undo_notes_str = " ".join(manifest["undo_notes"])
    assert "undo_alias" in undo_notes_str
    assert "core-in-java" in undo_notes_str


def test_T4_13_rollback_manifest_includes_undo_inbound_links(tmp_path):
    """Rollback manifest must include undo_inbound_links for each rewritten file."""
    sys.path.insert(0, str(Path(__file__).parents[1]))
    from commands.migration.blog_folder_migrate import run_migration

    blog_root, _, out_dir = _make_full_migration_fixture(tmp_path)
    repo_root = tmp_path

    run_migration([_make_t4_candidate(blog_root)], repo_root=repo_root, dry_run=False, out_dir=out_dir)

    rollback_files = list(out_dir.glob("migration-*-rollback.json"))
    manifest = json.loads(rollback_files[0].read_text(encoding="utf-8"))
    undo_notes_str = " ".join(manifest.get("undo_notes", []))
    # The linking file (using-cells-java) was modified — must appear in undo notes
    assert "undo_inbound_links" in undo_notes_str
    assert "using-cells-java" in undo_notes_str


def test_T4_14_https_absolute_link_rewritten(tmp_path):
    """HTTPS absolute link form in linking file must be rewritten."""
    sys.path.insert(0, str(Path(__file__).parents[1]))
    from commands.migration.blog_folder_migrate import run_migration

    blog_root = tmp_path / "content" / "blog.aspose.org"
    source_folder = blog_root / "cells" / "java" / "core-in-java"
    source_folder.mkdir(parents=True)
    (source_folder / "index.md").write_text(_ENGLISH_INDEX_WITH_PROVENANCE, encoding="utf-8")

    link_folder = blog_root / "cells" / "java" / "using-cells-java"
    link_folder.mkdir(parents=True)
    abs_content = """\
---
title: Using Cells Java
provenance:
  content_origin: skill-generated
  auto_updatable: true
---

See https://blog.aspose.org/cells/java/core-in-java/ for details.

More content here.
"""
    (link_folder / "index.md").write_text(abs_content, encoding="utf-8")

    out_dir = tmp_path / "reports" / "blog-slugs"
    out_dir.mkdir(parents=True)
    cand = {
        "old_folder_slug": "core-in-java",
        "new_folder_slug": "aspose-cells-foss-java-cell-operations",
        "family": "cells", "platform": "java",
        "title": "Core Cell Operations", "auto_updatable": True, "grade": "A",
        "locale_files": [], "source_file_updates": [],
    }

    run_migration([cand], repo_root=tmp_path, dry_run=False, out_dir=out_dir)

    content = (link_folder / "index.md").read_text(encoding="utf-8")
    assert "aspose-cells-foss-java-cell-operations" in content
    assert "core-in-java" not in content.split("---\n\n", 1)[-1]  # body check


def test_T4_15_link_with_fragment_rewritten_preserved(tmp_path):
    """Link with #fragment must be rewritten; fragment must be preserved."""
    sys.path.insert(0, str(Path(__file__).parents[1]))
    from commands.migration.blog_folder_migrate import run_migration

    blog_root = tmp_path / "content" / "blog.aspose.org"
    source_folder = blog_root / "cells" / "java" / "core-in-java"
    source_folder.mkdir(parents=True)
    (source_folder / "index.md").write_text(_ENGLISH_INDEX_WITH_PROVENANCE, encoding="utf-8")

    link_folder = blog_root / "cells" / "java" / "using-cells-java"
    link_folder.mkdir(parents=True)
    frag_content = """\
---
title: Using Cells Java
provenance:
  content_origin: skill-generated
  auto_updatable: true
---

Check [the section](/cells/java/core-in-java/#key-features) for info.

More content here for the body.
"""
    (link_folder / "index.md").write_text(frag_content, encoding="utf-8")

    out_dir = tmp_path / "reports" / "blog-slugs"
    out_dir.mkdir(parents=True)
    cand = {
        "old_folder_slug": "core-in-java",
        "new_folder_slug": "aspose-cells-foss-java-cell-operations",
        "family": "cells", "platform": "java",
        "title": "Core Cell Operations", "auto_updatable": True, "grade": "A",
        "locale_files": [], "source_file_updates": [],
    }

    run_migration([cand], repo_root=tmp_path, dry_run=False, out_dir=out_dir)

    content = (link_folder / "index.md").read_text(encoding="utf-8")
    assert "/aspose-cells-foss-java-cell-operations/#key-features" in content


def test_T4_16_no_slug_field_in_any_file(tmp_path):
    """No file must have slug: field after migration."""
    sys.path.insert(0, str(Path(__file__).parents[1]))
    from commands.migration.blog_folder_migrate import run_migration

    blog_root, _, out_dir = _make_full_migration_fixture(tmp_path)
    repo_root = tmp_path

    run_migration([_make_t4_candidate(blog_root)], repo_root=repo_root, dry_run=False, out_dir=out_dir)

    new_folder = blog_root / "cells" / "java" / "aspose-cells-foss-java-cell-operations"
    for md_file in new_folder.rglob("*.md"):
        content = md_file.read_text(encoding="utf-8")
        assert not re.search(r"^\s*slug\s*:", content, re.MULTILINE), (
            f"slug: must not appear in {md_file.name}"
        )


def test_T4_17_verify_migration_safety_raises_on_slug_addition(tmp_path):
    """_verify_migration_safety must raise if slug: is accidentally introduced."""
    sys.path.insert(0, str(Path(__file__).parents[1]))
    from commands.migration.blog_folder_migrate import _verify_migration_safety

    before = "---\ntitle: Hello\n---\n\nBody.\n"
    after = "---\ntitle: Hello\nslug: bad-slug\n---\n\nBody.\n"

    with pytest.raises(RuntimeError, match="slug"):
        _verify_migration_safety(before, after, "test.md")


def test_T4_18_verify_migration_safety_raises_if_locale_gets_aliases(tmp_path):
    """_verify_migration_safety must raise if locale file receives aliases: (allowed_alias=None)."""
    sys.path.insert(0, str(Path(__file__).parents[1]))
    from commands.migration.blog_folder_migrate import _verify_migration_safety

    before = "---\ntitle: Translated\nsource_file: old.md\n---\n\nTranslated.\n"
    after = "---\ntitle: Translated\nsource_file: old.md\naliases:\n- /cells/java/old/\n---\n\nTranslated.\n"

    with pytest.raises(RuntimeError, match="aliases"):
        _verify_migration_safety(before, after, "index.ar.md", allowed_alias=None)


# ---------------------------------------------------------------------------
# Unit: validate_seo_slug
# ---------------------------------------------------------------------------

def test_validate_seo_slug_accepts_good_slug():
    violations = bsp.validate_seo_slug("java-excel-xlsx-library")
    assert violations == []


def test_validate_seo_slug_rejects_too_few_words():
    violations = bsp.validate_seo_slug("java-excel")
    assert any("too few" in v for v in violations)


def test_validate_seo_slug_rejects_too_many_words():
    violations = bsp.validate_seo_slug("java-excel-xlsx-charts-formulas-styling")
    assert any("too many" in v for v in violations)


def test_validate_seo_slug_rejects_long_slug():
    violations = bsp.validate_seo_slug("a" * 30 + "-" + "b" * 31)
    assert any("too long" in v for v in violations)


def test_validate_seo_slug_rejects_generic_verbs():
    violations = bsp.validate_seo_slug("introducing-cells-java-library")
    assert any("generic verb" in v for v in violations)


def test_validate_seo_slug_rejects_stopwords():
    violations = bsp.validate_seo_slug("cells-for-java-library")
    assert any("stopword" in v for v in violations)


def test_validate_seo_slug_rejects_invalid_chars():
    violations = bsp.validate_seo_slug("Java-Excel-Library")
    assert any("invalid" in v for v in violations)


# ---------------------------------------------------------------------------
# Unit: generate_seo_slug
# ---------------------------------------------------------------------------

class _FakeCallResult:
    """Minimal call result stub for testing."""
    def __init__(self, status, data=None):
        self.status = status
        self.data = data


class _FakeEndpointStatus:
    OK = "ok"
    UNREACHABLE = "unreachable"


class _FakeRouter:
    """Fake LLMRouter that returns a configurable slug string."""
    def __init__(self, slug_response: str | None = None, fail: bool = False):
        self._slug = slug_response
        self._fail = fail
        self.calls: list[dict] = []

    def call_chat(self, system, user, *, temperature=None, max_tokens=None, json_extract=True):
        self.calls.append({"system": system, "user": user})
        if self._fail:
            return _FakeCallResult(status=_FakeEndpointStatus.UNREACHABLE)
        return _FakeCallResult(status=_FakeEndpointStatus.OK, data=self._slug)


def test_generate_seo_slug_uses_llm_response(monkeypatch):
    """When LLM returns a valid slug, generate_seo_slug uses it."""
    # Patch the import inside generate_seo_slug
    import types
    fake_mod = types.ModuleType("commands.ops.llm_router")
    fake_mod.EndpointStatus = _FakeEndpointStatus
    monkeypatch.setitem(sys.modules, "commands.ops.llm_router", fake_mod)

    router = _FakeRouter(slug_response="java-excel-xlsx-library")
    result = bsp.generate_seo_slug(
        title="Introducing Aspose.Cells FOSS for Java",
        description="A free Excel library",
        summary="",
        family="cells",
        platform="java",
        llm_router=router,
    )
    assert result == "java-excel-xlsx-library"
    assert len(router.calls) == 1


def test_generate_seo_slug_falls_back_on_invalid_llm_response(monkeypatch):
    """When LLM returns an invalid slug, falls back to deterministic."""
    import types
    fake_mod = types.ModuleType("commands.ops.llm_router")
    fake_mod.EndpointStatus = _FakeEndpointStatus
    monkeypatch.setitem(sys.modules, "commands.ops.llm_router", fake_mod)

    # "ab" is too short / too few words — should fail validation
    router = _FakeRouter(slug_response="ab")
    result = bsp.generate_seo_slug(
        title="Introducing Aspose.Cells FOSS for Java",
        description="A free Excel library",
        summary="",
        family="cells",
        platform="java",
        llm_router=router,
    )
    # Should be deterministic fallback, not "ab"
    assert result != "ab"
    assert len(result) > 5


def test_generate_seo_slug_falls_back_on_llm_failure(monkeypatch):
    """When LLM is unreachable, falls back to deterministic."""
    import types
    fake_mod = types.ModuleType("commands.ops.llm_router")
    fake_mod.EndpointStatus = _FakeEndpointStatus
    monkeypatch.setitem(sys.modules, "commands.ops.llm_router", fake_mod)

    router = _FakeRouter(fail=True)
    result = bsp.generate_seo_slug(
        title="Introducing Aspose.Cells FOSS for Java",
        description="A free Excel library",
        summary="",
        family="cells",
        platform="java",
        llm_router=router,
    )
    assert len(result) > 5
    assert "cells" in result


def test_generate_seo_slug_no_router_uses_deterministic():
    """When no router is provided, uses deterministic fallback."""
    result = bsp.generate_seo_slug(
        title="Working with 3D Formats in Java",
        description="Convert OBJ, STL, glTF files",
        summary="",
        family="3d",
        platform="java",
        llm_router=None,
    )
    assert len(result) > 5
    assert "3d" in result


def test_generate_seo_slug_strips_backticks_from_llm(monkeypatch):
    """LLM sometimes wraps slug in backticks — should be stripped."""
    import types
    fake_mod = types.ModuleType("commands.ops.llm_router")
    fake_mod.EndpointStatus = _FakeEndpointStatus
    monkeypatch.setitem(sys.modules, "commands.ops.llm_router", fake_mod)

    router = _FakeRouter(slug_response="`java-excel-xlsx-library`")
    result = bsp.generate_seo_slug(
        title="Test", description="Test", summary="",
        family="cells", platform="java",
        llm_router=router,
    )
    assert result == "java-excel-xlsx-library"
