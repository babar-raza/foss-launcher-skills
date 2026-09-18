"""Tests for check_site_plan_mandatory_roles.py.

Covers the 6 cases specified in plans/healing/2026-09-18-site-plan-bookkeeping-
self-review-remediation.md Taskcard SPBK-02, plus explicit coverage of the
--apply repair logic's ambiguity-refusal behavior (the taskcard's core safety
property: never invent a survivor when one isn't unambiguous).

All fixtures are built under pytest's tmp_path -- no repo files are read or
written by these tests, and no network access occurs anywhere.
"""
from __future__ import annotations

import sys
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_PIPELINE_ROOT = _TESTS_DIR.parent  # scripts/pipeline/tests/ -> scripts/pipeline/
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_DIAG_DIR = str(_PIPELINE_ROOT / "commands" / "diagnostics")
if _DIAG_DIR not in sys.path:
    sys.path.insert(0, _DIAG_DIR)

import check_site_plan_mandatory_roles as csp  # noqa: E402


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _plan_yaml(*, announcement_slug: str, features_slug: str,
                extra_announcement_fields: str = "", extra_features_fields: str = "") -> str:
    """Build a minimal but structurally real site_plan.yaml blog section."""
    return f"""\
plan:
  schema_version: 1
  family: testfam
  platform: testplat
  sections:
    blog:
      page_count: 2
      justified: true
      pages:
      - slug: {announcement_slug}
        path: content/blog.aspose.org/testfam/testplat/{announcement_slug}/index.md
        type: blog-post
        weight: 1
        mandatory: true
        page_class: generated
        blog_role: announcement
        note: Introductory announcement post
        source: discovered
{extra_announcement_fields}
      - slug: {features_slug}
        path: content/blog.aspose.org/testfam/testplat/{features_slug}/index.md
        type: blog-post
        weight: 2
        mandatory: true
        page_class: generated
        blog_role: features
        note: Key features overview post
        source: discovered
{extra_features_fields}
"""


def _content(root: Path, family: str, platform: str, slug: str, *, draft: bool,
             aliases: list[str] | None = None, title: str = "Test Post") -> None:
    alias_yaml = ""
    if aliases:
        alias_yaml = "aliases:\n" + "\n".join(f"- {a}" for a in aliases) + "\n"
    text = f"""---
title: {title}
draft: {"true" if draft else "false"}
{alias_yaml}---

## Introduction
Body.
"""
    _write(root / "content" / "blog.aspose.org" / family / platform / slug / "index.md", text)


def test_stale_announcement_pointer_detected(tmp_path):
    """Case 1: announcement record points at a retired (draft:true) page."""
    root = tmp_path
    _write(root / "reports" / "plans" / "testfam" / "testplat" / "site_plan.yaml",
           _plan_yaml(announcement_slug="old-intro", features_slug="live-features"))
    _content(root, "testfam", "testplat", "old-intro", draft=True)
    _content(root, "testfam", "testplat", "live-features", draft=False)

    result = csp.check_plan(
        root / "reports" / "plans" / "testfam" / "testplat" / "site_plan.yaml", root
    )
    assert result["parse_error"] is None
    assert result["stale"] == [{"role": "announcement", "slug": "old-intro",
                                 "path": "content/blog.aspose.org/testfam/testplat/old-intro/index.md"}]
    assert result["missing"] == []
    assert result["double_role"] == []


def test_stale_features_pointer_detected(tmp_path):
    """Case 2: features record points at a retired (draft:true) page."""
    root = tmp_path
    _write(root / "reports" / "plans" / "testfam" / "testplat" / "site_plan.yaml",
           _plan_yaml(announcement_slug="live-intro", features_slug="old-features"))
    _content(root, "testfam", "testplat", "live-intro", draft=False)
    _content(root, "testfam", "testplat", "old-features", draft=True)

    result = csp.check_plan(
        root / "reports" / "plans" / "testfam" / "testplat" / "site_plan.yaml", root
    )
    assert len(result["stale"]) == 1
    assert result["stale"][0]["role"] == "features"
    assert result["stale"][0]["slug"] == "old-features"


def test_live_correctly_pointed_record_not_flagged(tmp_path):
    """Case 3: both mandatory records point at live pages -- zero findings."""
    root = tmp_path
    _write(root / "reports" / "plans" / "testfam" / "testplat" / "site_plan.yaml",
           _plan_yaml(announcement_slug="live-intro", features_slug="live-features"))
    _content(root, "testfam", "testplat", "live-intro", draft=False)
    _content(root, "testfam", "testplat", "live-features", draft=False)

    result = csp.check_plan(
        root / "reports" / "plans" / "testfam" / "testplat" / "site_plan.yaml", root
    )
    assert result["stale"] == []
    assert result["missing"] == []
    assert result["double_role"] == []
    assert result["parse_error"] is None


def test_double_role_assignment_flagged_not_repaired(tmp_path):
    """Case 4: same slug assigned to both announcement and features -- flagged, never
    silently resolved (this is the real words/python anomaly found in production)."""
    root = tmp_path
    _write(root / "reports" / "plans" / "testfam" / "testplat" / "site_plan.yaml",
           _plan_yaml(announcement_slug="shared-slug", features_slug="shared-slug"))
    _content(root, "testfam", "testplat", "shared-slug", draft=False)

    result = csp.check_plan(
        root / "reports" / "plans" / "testfam" / "testplat" / "site_plan.yaml", root
    )
    assert result["double_role"] == [{"slug": "shared-slug", "roles": ["announcement", "features"]}]
    # apply_repairs must never touch a double_role-only finding (no stale entries here).
    repaired = csp.apply_repairs(result, root)
    assert repaired == []


def test_missing_target_file_distinct_from_stale(tmp_path):
    """Case 5: path points at a file that was never generated -- reported as `missing`,
    never conflated with `stale` (this is the real email/cpp shape found in production)."""
    root = tmp_path
    _write(root / "reports" / "plans" / "testfam" / "testplat" / "site_plan.yaml",
           _plan_yaml(announcement_slug="never-generated", features_slug="live-features"))
    _content(root, "testfam", "testplat", "live-features", draft=False)
    # Deliberately do NOT create content for "never-generated".

    result = csp.check_plan(
        root / "reports" / "plans" / "testfam" / "testplat" / "site_plan.yaml", root
    )
    assert result["stale"] == []
    assert result["missing"] == [{"role": "announcement", "slug": "never-generated",
                                   "path": "content/blog.aspose.org/testfam/testplat/never-generated/index.md"}]


def test_reordered_yaml_fields_still_parsed(tmp_path):
    """Case 6: regression test for the original defect class -- a site_plan.yaml whose
    per-page field order differs from the 14-product sample must still be parsed
    correctly, because this script uses yaml.safe_load, not a field-order-sensitive
    regex (the root cause of the ad hoc first-pass checker's fragility)."""
    root = tmp_path
    reordered = """\
plan:
  family: testfam
  platform: testplat
  sections:
    blog:
      pages:
      - blog_role: announcement
        mandatory: true
        slug: old-intro
        note: Introductory announcement post
        path: content/blog.aspose.org/testfam/testplat/old-intro/index.md
        source: discovered
        page_class: generated
        weight: 1
        type: blog-post
      - slug: live-features
        path: content/blog.aspose.org/testfam/testplat/live-features/index.md
        blog_role: features
        mandatory: true
"""
    _write(root / "reports" / "plans" / "testfam" / "testplat" / "site_plan.yaml", reordered)
    _content(root, "testfam", "testplat", "old-intro", draft=True)
    _content(root, "testfam", "testplat", "live-features", draft=False)

    result = csp.check_plan(
        root / "reports" / "plans" / "testfam" / "testplat" / "site_plan.yaml", root
    )
    assert result["parse_error"] is None
    assert len(result["stale"]) == 1
    assert result["stale"][0]["slug"] == "old-intro"


def test_apply_repairs_unambiguous_survivor(tmp_path):
    """--apply's happy path: exactly one live sibling aliases back to the stale slug."""
    root = tmp_path
    plan_path = root / "reports" / "plans" / "testfam" / "testplat" / "site_plan.yaml"
    _write(plan_path, _plan_yaml(announcement_slug="old-intro", features_slug="live-features"))
    _content(root, "testfam", "testplat", "old-intro", draft=True)
    _content(root, "testfam", "testplat", "new-intro", draft=False,
             aliases=["/testfam/testplat/old-intro/"])
    _content(root, "testfam", "testplat", "live-features", draft=False)

    result = csp.check_plan(plan_path, root)
    assert len(result["stale"]) == 1

    repaired = csp.apply_repairs(result, root)
    assert repaired == [{"role": "announcement", "old_slug": "old-intro", "new_slug": "new-intro"}]

    # Re-check: the plan file must now be clean.
    re_result = csp.check_plan(plan_path, root)
    assert re_result["stale"] == []
    assert "new-intro" in plan_path.read_text(encoding="utf-8")


def test_apply_repairs_refuses_ambiguous_survivor(tmp_path):
    """--apply must never guess: zero or multiple aliasing candidates -> no repair applied."""
    root = tmp_path
    plan_path = root / "reports" / "plans" / "testfam" / "testplat" / "site_plan.yaml"
    _write(plan_path, _plan_yaml(announcement_slug="old-intro", features_slug="live-features"))
    _content(root, "testfam", "testplat", "old-intro", draft=True)
    # Two different live siblings both alias back to old-intro -- genuinely ambiguous.
    _content(root, "testfam", "testplat", "candidate-a", draft=False,
             aliases=["/testfam/testplat/old-intro/"])
    _content(root, "testfam", "testplat", "candidate-b", draft=False,
             aliases=["/testfam/testplat/old-intro/"])
    _content(root, "testfam", "testplat", "live-features", draft=False)

    result = csp.check_plan(plan_path, root)
    repaired = csp.apply_repairs(result, root)
    assert repaired == []

    # Plan file must be byte-identical to before -- refusing must never partially edit.
    re_result = csp.check_plan(plan_path, root)
    assert len(re_result["stale"]) == 1
    assert re_result["stale"][0]["slug"] == "old-intro"


def test_discover_plans_filters_to_requested_products(tmp_path):
    """discover_plans() with --products only returns the requested, existing plan files."""
    root = tmp_path
    _write(root / "reports" / "plans" / "famA" / "platA" / "site_plan.yaml", "plan: {}\n")
    _write(root / "reports" / "plans" / "famB" / "platB" / "site_plan.yaml", "plan: {}\n")

    only_a = csp.discover_plans(root, ["famA/platA"])
    assert len(only_a) == 1
    assert only_a[0].parts[-3:] == ("famA", "platA", "site_plan.yaml")

    nonexistent = csp.discover_plans(root, ["famZ/platZ"])
    assert nonexistent == []

    all_plans = csp.discover_plans(root, None)
    assert len(all_plans) == 2


def test_missing_target_covered_by_live_alias_is_alias_covered_not_missing(tmp_path):
    """A never-generated slug that a live sibling already aliases is a renamed page
    the plan never followed (the real pdf/go, pdf/java, cells/java, cells/typescript,
    font/python shape). It must NOT be reported as missing -- generating a page there
    would collide with the alias redirect."""
    root = tmp_path
    plan_path = root / "reports" / "plans" / "testfam" / "testplat" / "site_plan.yaml"
    _write(plan_path, _plan_yaml(announcement_slug="old-intro", features_slug="live-features"))
    _content(root, "testfam", "testplat", "new-intro", draft=False,
             aliases=["/testfam/testplat/old-intro/"])
    _content(root, "testfam", "testplat", "live-features", draft=False)
    # Deliberately no content for "old-intro" itself.

    result = csp.check_plan(plan_path, root)
    assert result["missing"] == []
    assert result["stale"] == []
    assert result["alias_covered"] == [{
        "role": "announcement", "slug": "old-intro", "survivor": "new-intro",
        "path": "content/blog.aspose.org/testfam/testplat/old-intro/index.md",
    }]


def test_missing_target_with_ambiguous_alias_holders_stays_missing(tmp_path):
    """Two live siblings both alias the slug -> ambiguous -> needs a human, so it must
    stay in `missing` (never guessed into alias_covered)."""
    root = tmp_path
    plan_path = root / "reports" / "plans" / "testfam" / "testplat" / "site_plan.yaml"
    _write(plan_path, _plan_yaml(announcement_slug="old-intro", features_slug="live-features"))
    _content(root, "testfam", "testplat", "cand-a", draft=False,
             aliases=["/testfam/testplat/old-intro/"])
    _content(root, "testfam", "testplat", "cand-b", draft=False,
             aliases=["/testfam/testplat/old-intro/"])
    _content(root, "testfam", "testplat", "live-features", draft=False)

    result = csp.check_plan(plan_path, root)
    assert result["alias_covered"] == []
    assert [m["slug"] for m in result["missing"]] == ["old-intro"]


def test_retired_alias_holder_does_not_count_as_alias_cover(tmp_path):
    """A draft:true page's alias generates no redirect, so it can't cover the slug."""
    root = tmp_path
    plan_path = root / "reports" / "plans" / "testfam" / "testplat" / "site_plan.yaml"
    _write(plan_path, _plan_yaml(announcement_slug="old-intro", features_slug="live-features"))
    _content(root, "testfam", "testplat", "retired-holder", draft=True,
             aliases=["/testfam/testplat/old-intro/"])
    _content(root, "testfam", "testplat", "live-features", draft=False)

    result = csp.check_plan(plan_path, root)
    assert result["alias_covered"] == []
    assert [m["slug"] for m in result["missing"]] == ["old-intro"]


def test_apply_repairs_repoints_alias_covered_record(tmp_path):
    """--apply repoints an unambiguous alias_covered record to the aliasing live page,
    leaves the plan parseable, and never generates or touches any content file."""
    root = tmp_path
    plan_path = root / "reports" / "plans" / "testfam" / "testplat" / "site_plan.yaml"
    _write(plan_path, _plan_yaml(announcement_slug="old-intro", features_slug="live-features"))
    _content(root, "testfam", "testplat", "new-intro", draft=False,
             aliases=["/testfam/testplat/old-intro/"])
    _content(root, "testfam", "testplat", "live-features", draft=False)

    result = csp.check_plan(plan_path, root)
    repaired = csp.apply_repairs(result, root)
    assert repaired == [{"role": "announcement", "old_slug": "old-intro", "new_slug": "new-intro"}]

    re_result = csp.check_plan(plan_path, root)
    assert re_result["parse_error"] is None
    assert re_result["alias_covered"] == [] and re_result["missing"] == [] and re_result["stale"] == []
    text = plan_path.read_text(encoding="utf-8")
    assert "slug: new-intro" in text and "aliases: redirect" in text
    assert not (root / "content" / "blog.aspose.org" / "testfam" / "testplat" / "old-intro").exists()
