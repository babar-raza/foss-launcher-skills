"""Tests for blog_slug_policy.py, blog_slug_inventory.py, and blog_folder_migrate.py.

All tests are deterministic: no LLM calls, no network, no real content files
(except where tmp_path fixtures create controlled content).
"""
from __future__ import annotations

import json
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
# Migration: no slug: or aliases: added (tmp_path fixture)
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


def test_migration_does_not_add_slug_field(tmp_path):
    """After migration, no slug: field must appear in any file."""
    import sys
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
        import re
        assert not re.search(r"^\s*slug\s*:", content, re.MULTILINE), (
            f"slug: field must not be added to {md_file.name}"
        )


def test_migration_does_not_add_aliases_field(tmp_path):
    """After migration, no aliases: field must appear in any file."""
    import sys
    sys.path.insert(0, str(Path(__file__).parents[1]))
    from commands.migration.blog_folder_migrate import run_migration
    import re

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
    for md_file in new_folder.glob("*.md"):
        content = md_file.read_text(encoding="utf-8")
        assert not re.search(r"^\s*aliases\s*:", content, re.MULTILINE), (
            f"aliases: field must not be added to {md_file.name}"
        )


def test_migration_updates_source_file_in_locale(tmp_path):
    """Migration must update source_file in locale files."""
    import sys
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
    import sys
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
    import sys
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
    import sys
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
        (folder / "index.md").write_text(
            _INDEX_MD_TEMPLATE.format(title=title), encoding="utf-8"
        )
    return blog_root


def test_inventory_identifies_core_in_java_as_migration_ready(tmp_path):
    """Inventory scanner must classify core-in-java as MIGRATION_READY."""
    import sys
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
    import sys
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
