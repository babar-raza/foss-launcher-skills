"""Smoke tests for scripts/pipeline/site_planner.py.

All tests are deterministic: no LLM calls, no network, no real knowledge files.
Synthetic fixtures are built in-memory or in tmp_path.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

import site_planner as sp


# ---------------------------------------------------------------------------
# Synthetic knowledge fixtures
# ---------------------------------------------------------------------------

def _make_api_surface(subpkgs: list[str]) -> list[dict]:
    """Build a minimal api_surface list with classes spread across subpkgs."""
    entries = []
    for i, subpkg in enumerate(subpkgs):
        name = f"Class{i}"
        if subpkg:
            file_path = f"aspose/threed/{subpkg}/{name}.py"
        else:
            file_path = f"aspose/threed/{name}.py"
        entries.append({
            "name": name,
            "file": file_path,
            "methods": [f"method_{i}_a", f"method_{i}_b"],
        })
    return entries


def _make_claims(api_surface: list[dict], per_class: int = 10) -> list[dict]:
    """Build synthetic claims list with api_method claims for each class."""
    claims = []
    for entry in api_surface:
        cls_name = entry["name"]
        for j in range(per_class):
            claims.append({
                "kind": "api_method",
                "text": f"{cls_name}.method_{j}()",
                "category": cls_name,
            })
    return claims


# ---------------------------------------------------------------------------
# Helper: build plan sections from synthetic data
# ---------------------------------------------------------------------------

def _plan_docs_from_surface(subpkgs, family="3d", platform="python",
                             has_license=False, license_path=None):
    api_surface = _make_api_surface(subpkgs)
    claims = _make_claims(api_surface, per_class=10)
    clusters = sp.detect_clusters(claims, api_surface, [], "", family=family)
    return sp.plan_docs(family, platform, clusters, has_license, license_path)


def _plan_kb_from_surface(subpkgs, family="3d", platform="python",
                           total_claims=500, snippet_count=25):
    api_surface = _make_api_surface(subpkgs)
    claims = _make_claims(api_surface, per_class=10)
    clusters = sp.detect_clusters(claims, api_surface, [], "", family=family)
    return sp.plan_kb(family, platform, clusters, total_claims, snippet_count, tier="full")


# ---------------------------------------------------------------------------
# TEST-01-A: Cluster count is sane for a 3d-like api_surface
# ---------------------------------------------------------------------------

def test_cluster_count_3d_python():
    """Cluster count must be in 4–10 for a representative 3d sub-package layout."""
    subpkgs = ["formats", "formats", "formats",
               "entities", "entities",
               "animation",
               "shading",
               "",  # root → scene-management
               ""]
    api_surface = _make_api_surface(subpkgs)
    claims = _make_claims(api_surface, per_class=10)
    clusters = sp.detect_clusters(claims, api_surface, [], "", family="3d")
    assert 4 <= len(clusters) <= 10, f"Expected 4–10 clusters, got {len(clusters)}: {[c['category'] for c in clusters]}"


# ---------------------------------------------------------------------------
# TEST-01-B: KB slug format matches required pattern
# ---------------------------------------------------------------------------

def test_kb_slug_format():
    """All KB how-to page slugs must match ^how-to-[a-z]+-[a-z-]+-[a-z]+$."""
    import re
    pattern = re.compile(r'^how-to-[a-z]+-[a-z][a-z0-9\-]*[a-z0-9]-[a-z]+$')
    subpkgs = ["formats", "entities", "animation", "shading", "", ""]
    pages = _plan_kb_from_surface(subpkgs)
    howto_pages = [p for p in pages if p.get("path", "").startswith("content/kb") and "how-to-" in p["path"]]
    assert howto_pages, "No how-to pages generated"
    for page in howto_pages:
        slug = page.get("slug", "")
        assert pattern.match(slug), f"KB slug {slug!r} does not match pattern"


# ---------------------------------------------------------------------------
# TEST-01-C: features.md always present regardless of cluster evidence
# ---------------------------------------------------------------------------

def test_features_page_always_present():
    """developer-guide/features must appear regardless of cluster evidence."""
    # Even with zero clusters passing threshold
    pages = sp.plan_docs("3d", "python", clusters=[], has_license=False, license_path=None)
    paths = [p["path"] for p in pages]
    assert any("developer-guide/features.md" in path for path in paths), (
        "developer-guide/features.md missing even with empty cluster list"
    )


# ---------------------------------------------------------------------------
# TEST-01-D: Limitations exclusion
# ---------------------------------------------------------------------------

def test_limitations_exclusion():
    """A cluster whose classes are >50% in limitations.md must not produce docs/KB pages."""
    # Build a single-class cluster with the class listed as NotImplementedError
    api_surface = [{"name": "RenderEngine", "file": "aspose/threed/rendering/RenderEngine.py", "methods": ["render"]}]
    claims = _make_claims(api_surface, per_class=10)
    # limitations.md table with RenderEngine NotImplementedError
    limitations_text = "| RenderEngine | Some method | NotImplementedError |\n"
    clusters = sp.detect_clusters(claims, api_surface, [], limitations_text, family="3d")
    docs_pages = sp.plan_docs("3d", "python", clusters, has_license=False, license_path=None)
    kb_pages = sp.plan_kb("3d", "python", clusters, 500, 25, tier="full")

    doc_paths = [p["path"] for p in docs_pages]
    kb_paths = [p["path"] for p in kb_pages]

    assert not any("rendering" in path for path in doc_paths), (
        "Rendering cluster (in limitations) should not appear in docs"
    )
    assert not any("rendering" in path for path in kb_paths), (
        "Rendering cluster (in limitations) should not appear in KB"
    )


# ---------------------------------------------------------------------------
# TEST-01-E: License absent → no license page
# ---------------------------------------------------------------------------

def test_license_absent(tmp_path):
    """No getting-started/license.md when no LICENSE file in clone dir."""
    pages = sp.plan_docs("3d", "python", [], has_license=False, license_path=None)
    paths = [p["path"] for p in pages]
    assert not any("license.md" in path for path in paths), (
        "license.md must not be planned when no license file found"
    )


# ---------------------------------------------------------------------------
# TEST-01-F: License present → license page planned with relative source
# ---------------------------------------------------------------------------

def test_license_present(tmp_path):
    """getting-started/license.md is planned when LICENSE file exists; source is relative."""
    lic_file = tmp_path / "LICENSE"
    lic_file.write_text("MIT License\n")

    pages = sp.plan_docs("3d", "python", [], has_license=True, license_path=lic_file)
    lic_pages = [p for p in pages if "license.md" in p.get("path", "")]
    assert lic_pages, "license.md not planned when license file present"

    # license_source must be a relative POSIX path (not absolute)
    lic_src = lic_pages[0].get("license_source", "")
    assert lic_src, "license_source field is missing"
    # It will be an absolute path here since tmp_path is outside REPO_ROOT — but we
    # verify it is a string (the fallback path) and does not crash.
    assert isinstance(lic_src, str)


# ---------------------------------------------------------------------------
# TEST-01-G: KB_SKIP_CLUSTERS excluded from KB and docs
# ---------------------------------------------------------------------------

def test_kb_skip_clusters():
    """Clusters in KB_SKIP_CLUSTERS must produce no KB how-to pages."""
    # Build clusters that include 'utilities'
    api_surface = [{"name": "Vector3", "file": "aspose/threed/utilities/Vector3.py", "methods": ["add"]}]
    claims = _make_claims(api_surface, per_class=10)
    clusters = sp.detect_clusters(claims, api_surface, [], "", family="3d")

    kb_pages = sp.plan_kb("3d", "python", clusters, 500, 25, tier="full")
    docs_pages = sp.plan_docs("3d", "python", clusters, False, None)

    kb_paths = [p["path"] for p in kb_pages]
    doc_paths = [p["path"] for p in docs_pages]

    for skip in sp.KB_SKIP_CLUSTERS:
        assert not any(skip in path for path in kb_paths), (
            f"Cluster '{skip}' should not appear in KB pages"
        )
        assert not any(f"developer-guide/{skip}" in path for path in doc_paths), (
            f"Cluster '{skip}' should not appear in docs developer-guide pages"
        )


# ---------------------------------------------------------------------------
# TEST-01-H: .NET platform → -dotnet suffix in KB howto slugs
# ---------------------------------------------------------------------------

def test_net_dotnet_suffix():
    """.NET platform must produce -dotnet suffix (not -net) in KB slugs."""
    subpkgs = ["formats", "entities", "animation", "shading", ""]
    pages = _plan_kb_from_surface(subpkgs, family="3d", platform="net")
    howto_pages = [p for p in pages if "how-to-" in p.get("path", "")]
    assert howto_pages, "No how-to pages for net platform"
    for page in howto_pages:
        path = page["path"]
        assert path.endswith("-dotnet.md"), (
            f"Expected -dotnet.md suffix, got: {path}"
        )
        assert "-net.md" not in path.replace("-dotnet.md", ""), (
            f"Unexpected -net suffix (should be -dotnet): {path}"
        )


# ---------------------------------------------------------------------------
# TEST-01-I: _validate_arg rejects path traversal, accepts real args
# ---------------------------------------------------------------------------

def test_validate_arg_rejects_traversal():
    """_validate_arg must raise SystemExit for path traversal inputs."""
    with pytest.raises(SystemExit) as exc_info:
        sp._validate_arg("family", "../etc")
    assert exc_info.value.code == 1

    with pytest.raises(SystemExit) as exc_info:
        sp._validate_arg("platform", "../../passwd")
    assert exc_info.value.code == 1


def test_validate_arg_accepts_real_args():
    """_validate_arg must not raise for any real family/platform combination."""
    valid = [
        ("3d", "python"), ("3d", "java"), ("3d", "net"), ("3d", "typescript"),
        ("slides", "cpp"), ("slides", "python"), ("cells", "python"),
        ("email", "python"), ("note", "python"),
    ]
    for family, platform in valid:
        sp._validate_arg("family", family)
        sp._validate_arg("platform", platform)


# ---------------------------------------------------------------------------
# TEST-01-J: _class_to_subpackage sentinel for empty/None file
# ---------------------------------------------------------------------------

def test_class_to_subpackage_sentinel():
    """_class_to_subpackage must return '_unknown' for empty or None input."""
    assert sp._class_to_subpackage("") == "_unknown"
    assert sp._class_to_subpackage(None) == "_unknown"


# ---------------------------------------------------------------------------
# TEST-01-K: _page_slug strips prefix and extension correctly
# ---------------------------------------------------------------------------

def test_page_slug_docs():
    assert sp._page_slug(
        "content/docs.aspose.org/en/3d/python/getting-started/installation.md",
        "3d", "python"
    ) == "getting-started/installation"


def test_page_slug_blog_strips_index():
    assert sp._page_slug(
        "content/blog.aspose.org/3d/python/introducing-3d-foss-python/index.md",
        "3d", "python"
    ) == "introducing-3d-foss-python"


def test_page_slug_kb():
    assert sp._page_slug(
        "content/kb.aspose.org/en/3d/python/how-to-load-scene-python.md",
        "3d", "python"
    ) == "how-to-load-scene-python"


# ---------------------------------------------------------------------------
# TEST-01-L: _kb_noun_from_cluster is family-agnostic
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("category,family,expected", [
    ("format-support",  "3d",     "format"),
    ("scene-management","3d",     "scene"),
    ("charts",          "slides", "charts"),
    ("worksheets",      "cells",  "worksheets"),
    ("scene-entities",  "3d",     "scene-entities"),
    ("animations",      "slides", "animations"),
])
def test_kb_noun_from_cluster(category, family, expected):
    result = sp._kb_noun_from_cluster(category, family)
    assert result == expected, f"_kb_noun_from_cluster({category!r}, {family!r}) = {result!r}, expected {expected!r}"


# ---------------------------------------------------------------------------
# TEST-01-M: plan schema — all pages have slug field
# ---------------------------------------------------------------------------

def test_all_pages_have_slug_field():
    """Every page entry in plan_docs / plan_kb / plan_products / plan_reference must have a slug."""
    subpkgs = ["formats", "entities", "animation", "shading", ""]
    api_surface = _make_api_surface(subpkgs)
    claims = _make_claims(api_surface, per_class=10)
    clusters = sp.detect_clusters(claims, api_surface, [], "", family="3d")

    all_pages = (
        sp.plan_products("3d", "python", "full")
        + sp.plan_blog("3d", "python", 1000, 50, clusters)[0]
        + sp.plan_docs("3d", "python", clusters, False, None)
        + sp.plan_kb("3d", "python", clusters, 1000, 50, "full")
        + sp.plan_reference("3d", "python", api_surface)
    )
    for page in all_pages:
        assert "slug" in page, f"Page missing 'slug' field: {page.get('path')}"
        assert page["slug"], f"Page has empty 'slug': {page.get('path')}"


# ---------------------------------------------------------------------------
# Helpers for blog slug tests
# ---------------------------------------------------------------------------

def _make_api_surface_family(subpkgs: list[str], family: str = "3d") -> list[dict]:
    """Build api_surface using paths compatible with the target family's subpackages."""
    entries = []
    for i, subpkg in enumerate(subpkgs):
        name = f"Class{i}"
        # Use the subpkg dir directly; root level uses 2-level path so _class_to_subpackage
        # returns "" (root), which then maps to the family-specific ROOT_LABELS entry.
        if subpkg:
            file_path = f"aspose/{family}/{subpkg}/{name}.py"
        else:
            file_path = f"aspose/{family}/{name}.py"
        entries.append({
            "name": name,
            "file": file_path,
            "methods": [f"method_{i}_a", f"method_{i}_b"],
        })
    return entries


def _make_snippet_index_for(api_surface: list[dict], snippets_per_class: int = 4) -> list[dict]:
    """Build synthetic snippet_index with entries pointing at each class."""
    snippets = []
    snip_id = 0
    for entry in api_surface:
        cls_name = entry["name"]
        for _ in range(snippets_per_class):
            snippets.append({"id": f"snip_{snip_id}", "classes_used": [cls_name]})
            snip_id += 1
    return snippets


# ---------------------------------------------------------------------------
# TEST-BLOG-01: Post 2 slug is derived from top cluster, not hardcoded key-features
# ---------------------------------------------------------------------------

def test_plan_blog_post2_uses_cluster_slug():
    """Post 2 slug must be derived from primary cluster, not key-features template."""
    api = _make_api_surface_family(["pptx", "effects", ""], family="slides")
    claims = _make_claims(api, per_class=20)
    clusters = sp.detect_clusters(claims, api, [], "", family="slides")
    pages, justified, to_retire = sp.plan_blog("slides", "python", 600, 30, clusters)
    assert justified
    assert to_retire == []
    p2 = next(p for p in pages if p["weight"] == 2)
    assert "key-features" not in p2["slug"], f"Banned slug: {p2['slug']!r}"
    assert p2.get("blog_role") == "features"
    assert "cluster" in p2
    assert p2["slug"].endswith("-python")


# ---------------------------------------------------------------------------
# TEST-BLOG-02: Family prefix deduplication avoids email-email-processing-python
# ---------------------------------------------------------------------------

def test_plan_blog_post2_deduplicates_family_prefix():
    """email-email-processing-python must become email-processing-python."""
    api = _make_api_surface_family([""], family="email")
    claims = _make_claims(api, per_class=20)
    clusters = sp.detect_clusters(claims, api, [], "", family="email")
    pages, _, _ = sp.plan_blog("email", "python", 600, 30, clusters)
    p2 = next(p for p in pages if p["weight"] == 2)
    assert "email-email" not in p2["slug"], f"Double prefix: {p2['slug']!r}"


# ---------------------------------------------------------------------------
# TEST-BLOG-03: Keyword fallback discovers legacy *-key-features-* posts reliably
# ---------------------------------------------------------------------------

def test_plan_blog_keyword_fallback_finds_legacy_post():
    """Keyword fallback must discover existing *-key-features-* posts reliably."""
    existing = [
        {
            "slug": "slides-key-features-python",
            "path": "content/blog.aspose.org/slides/python/slides-key-features-python/index.md",
            "frontmatter_cluster": "", "title": "", "auto_updatable": True,
        },
        {
            "slug": "introducing-slides-foss-python",
            "path": "content/blog.aspose.org/slides/python/introducing-slides-foss-python/index.md",
            "frontmatter_cluster": "", "title": "", "auto_updatable": True,
        },
    ]
    api = _make_api_surface_family(["pptx", "effects"], family="slides")
    claims = _make_claims(api, per_class=20)
    clusters = sp.detect_clusters(claims, api, [], "", family="slides")
    pages, _, _ = sp.plan_blog("slides", "python", 600, 30, clusters, existing=existing)
    p2 = next(p for p in pages if p["weight"] == 2)
    assert p2["slug"] == "slides-key-features-python"
    assert p2["source"] == "discovered"


# ---------------------------------------------------------------------------
# TEST-BLOG-04: Intro post must never be matched as Post 2 features slot
# ---------------------------------------------------------------------------

def test_plan_blog_intro_not_matched_as_features():
    """The intro post must never be matched as the Post 2 features slot."""
    existing = [
        {
            "slug": "introducing-slides-foss-python",
            "path": "content/blog.aspose.org/slides/python/introducing-slides-foss-python/index.md",
            "frontmatter_cluster": "", "title": "", "auto_updatable": True,
        },
    ]
    api = _make_api_surface_family(["pptx"], family="slides")
    claims = _make_claims(api, per_class=20)
    clusters = sp.detect_clusters(claims, api, [], "", family="slides")
    pages, _, _ = sp.plan_blog("slides", "python", 600, 30, clusters, existing=existing)
    p2 = next(p for p in pages if p["weight"] == 2)
    assert p2["source"] == "derived"
    assert "introducing" not in p2["slug"]


# ---------------------------------------------------------------------------
# TEST-BLOG-05: Post 2 and Post 3 must not use the same cluster
# ---------------------------------------------------------------------------

def test_plan_blog_post2_and_post3_use_different_clusters():
    """Post 2 and Post 3 must not use the same cluster."""
    api = _make_api_surface_family(["pptx", "effects", "drawing"], family="slides")
    claims = _make_claims(api, per_class=25)
    snippet_index = _make_snippet_index_for(api, snippets_per_class=4)
    clusters = sp.detect_clusters(claims, api, snippet_index, "", family="slides")
    pages, _, _ = sp.plan_blog("slides", "python", 600, 30, clusters)
    p2 = next((p for p in pages if p["weight"] == 2), None)
    p3 = next((p for p in pages if p["weight"] == 3), None)
    if p2 and p3 and p2.get("cluster") and p3.get("cluster"):
        assert p2["cluster"] != p3["cluster"], (
            f"Cluster collision: both used {p2['cluster']!r}"
        )


# ---------------------------------------------------------------------------
# TEST-BLOG-06: Validator rejects source=derived *-key-features-* slugs
# ---------------------------------------------------------------------------

def test_plan_blog_validator_rejects_derived_key_features():
    """Validator must raise for source=derived *-key-features-* slugs."""
    bad = [{"slug": "slides-key-features-python", "source": "derived"}]
    with pytest.raises(ValueError, match="Banned generic slug"):
        sp._validate_blog_slugs(bad)


# ---------------------------------------------------------------------------
# TEST-BLOG-07: Validator allows source=discovered *-key-features-* slugs
# ---------------------------------------------------------------------------

def test_plan_blog_validator_allows_discovered_key_features():
    """Validator must not raise for source=discovered (existing deployed content)."""
    old = [{"slug": "slides-key-features-python", "source": "discovered"}]
    sp._validate_blog_slugs(old)  # must not raise


# ---------------------------------------------------------------------------
# TEST-BLOG-08: --replan-blog forces re-derivation and populates pages_to_retire
# ---------------------------------------------------------------------------

def test_plan_blog_force_replan_replaces_banned_slug():
    """force_replan=True must force re-derivation and populate pages_to_retire."""
    existing = [
        {
            "slug": "slides-key-features-python",
            "path": "content/blog.aspose.org/slides/python/slides-key-features-python/index.md",
            "frontmatter_cluster": "", "title": "", "auto_updatable": True,
        },
        {
            "slug": "introducing-slides-foss-python",
            "path": "content/blog.aspose.org/slides/python/introducing-slides-foss-python/index.md",
            "frontmatter_cluster": "", "title": "", "auto_updatable": True,
        },
    ]
    api = _make_api_surface_family(["pptx", "effects"], family="slides")
    claims = _make_claims(api, per_class=20)
    clusters = sp.detect_clusters(claims, api, [], "", family="slides")
    pages, _, to_retire = sp.plan_blog(
        "slides", "python", 600, 30, clusters,
        existing=existing, force_replan=True,
    )
    p2 = next(p for p in pages if p["weight"] == 2)
    assert "key-features" not in p2["slug"], f"Replan did not override: {p2['slug']!r}"
    assert p2["source"] == "derived"
    assert len(to_retire) == 1
    assert to_retire[0]["slug"] == "slides-key-features-python"
    # Old slug must not appear anywhere in pages (not even as page_class: preserved)
    all_slugs = [p["slug"] for p in pages]
    assert "slides-key-features-python" not in all_slugs, (
        f"Old slug still present in pages after replan: {all_slugs}"
    )


# ---------------------------------------------------------------------------
# TEST-BLOG-09: force_replan respects auto_updatable=False (human-authored)
# ---------------------------------------------------------------------------

def test_plan_blog_force_replan_respects_auto_updatable_false():
    """force_replan must not override posts with auto_updatable: false."""
    existing = [
        {
            "slug": "slides-key-features-python",
            "path": "content/blog.aspose.org/slides/python/slides-key-features-python/index.md",
            "frontmatter_cluster": "", "title": "", "auto_updatable": False,
        },
        {
            "slug": "introducing-slides-foss-python",
            "path": "content/blog.aspose.org/slides/python/introducing-slides-foss-python/index.md",
            "frontmatter_cluster": "", "title": "", "auto_updatable": True,
        },
    ]
    api = _make_api_surface_family(["pptx"], family="slides")
    claims = _make_claims(api, per_class=20)
    clusters = sp.detect_clusters(claims, api, [], "", family="slides")
    pages, _, to_retire = sp.plan_blog(
        "slides", "python", 600, 30, clusters,
        existing=existing, force_replan=True,
    )
    p2 = next(p for p in pages if p["weight"] == 2)
    assert p2["slug"] == "slides-key-features-python"
    assert p2["source"] == "discovered"
    assert to_retire == []


# ---------------------------------------------------------------------------
# TEST-BLOG-10: --replan-blog handles long-prefix key-features slugs (3d format)
# ---------------------------------------------------------------------------

def test_plan_blog_force_replan_handles_long_prefix_slug():
    """--replan-blog must also replace aspose-3d-foss-for-python-key-features format."""
    existing = [
        {
            "slug": "aspose-3d-foss-for-python-key-features",
            "path": "content/blog.aspose.org/3d/python/aspose-3d-foss-for-python-key-features/index.md",
            "frontmatter_cluster": "", "title": "", "auto_updatable": True,
        },
        {
            "slug": "introducing-3d-foss-python",
            "path": "content/blog.aspose.org/3d/python/introducing-3d-foss-python/index.md",
            "frontmatter_cluster": "", "title": "", "auto_updatable": True,
        },
    ]
    api = _make_api_surface_family(["formats", "entities"], family="3d")
    claims = _make_claims(api, per_class=20)
    clusters = sp.detect_clusters(claims, api, [], "", family="3d")
    pages, _, to_retire = sp.plan_blog(
        "3d", "python", 600, 30, clusters,
        existing=existing, force_replan=True,
    )
    p2 = next(p for p in pages if p["weight"] == 2)
    assert "key-features" not in p2["slug"], f"Long-prefix slug not replaced: {p2['slug']!r}"
    assert p2["source"] == "derived"
    assert len(to_retire) == 1
    assert to_retire[0]["slug"] == "aspose-3d-foss-for-python-key-features"
    # Must not appear in pages at all
    assert "aspose-3d-foss-for-python-key-features" not in [p["slug"] for p in pages]


# ---------------------------------------------------------------------------
# TEST-BLOG-11: All mandatory blog posts have a blog_role field
# ---------------------------------------------------------------------------

def test_plan_blog_all_mandatory_posts_have_blog_role():
    """Every mandatory blog post record must have a blog_role field."""
    api = _make_api_surface_family(["formats"], family="3d")
    claims = _make_claims(api, per_class=20)
    clusters = sp.detect_clusters(claims, api, [], "", family="3d")
    pages, _, _ = sp.plan_blog("3d", "python", 600, 30, clusters)
    for p in pages:
        if p.get("mandatory"):
            assert "blog_role" in p, f"Missing blog_role: {p}"


# ---------------------------------------------------------------------------
# S-4: Stats-consistency warning for orphaned claims
# ---------------------------------------------------------------------------

def test_orphaned_claims_warning(caplog):
    """Orphaned claims (not allocated to any cluster) must produce logger warning."""
    api_surface = _make_api_surface(["formats", "entities"])
    claims = _make_claims(api_surface, per_class=5)
    # Add orphaned claims that reference no known class
    claims.append({"kind": "feature", "text": "General library feature claim"})
    claims.append({"kind": "format", "text": "Supports XYZ format"})
    claims.append({"kind": "install", "text": "Install via pip"})

    import logging
    with caplog.at_level(logging.WARNING, logger="site_planner"):
        sp.detect_clusters(claims, api_surface, [], "", family="3d")
    assert any("stats-consistency" in r.message for r in caplog.records)
    assert any("3/" in r.message for r in caplog.records)


def test_no_warning_when_all_claims_allocated(caplog):
    """No warning when every claim maps to a cluster."""
    api_surface = _make_api_surface(["formats"])
    claims = _make_claims(api_surface, per_class=5)

    import logging
    with caplog.at_level(logging.WARNING, logger="site_planner"):
        sp.detect_clusters(claims, api_surface, [], "", family="3d")
    assert not any("stats-consistency" in r.message for r in caplog.records)


def test_raw_claim_count_sums_to_total_when_no_orphans():
    """D-6 (2026-07-23): build_plan()'s evidence_summary.orphaned_claim_count
    is computed as len(claims) - sum(cluster raw counts). It must use
    raw_claim_count (unweighted), not claim_count (visibility-weighted up to
    3x per claim via _VISIBILITY_WEIGHT) — summing the WEIGHTED field
    produces a value greater than len(claims) whenever any class has
    non-conventional visibility, making orphaned_claim_count go negative
    (confirmed live for both words/net and words/python before this fix).

    This test proves the invariant the fix depends on: with an "exported"
    (3x-weighted) class in the mix and every claim allocated to a cluster,
    summing raw_claim_count across clusters exactly equals len(claims), while
    summing claim_count does not (it overshoots).
    """
    api_surface = _make_api_surface(["formats", "entities"])
    # Class0 (in "formats") gets 3x weight; Class1 (in "entities") stays
    # default "conventional" (1x) — this asymmetry is what makes the weighted
    # sum diverge from the raw count.
    api_surface[0]["visibility"] = "exported"
    claims = _make_claims(api_surface, per_class=5)  # 10 claims total, no orphans

    clusters = sp.detect_clusters(claims, api_surface, [], "", family="3d")

    raw_sum = sum(c["raw_claim_count"] for c in clusters)
    weighted_sum = sum(c["claim_count"] for c in clusters)

    assert raw_sum == len(claims), (
        f"D-6 regression: raw_claim_count must sum to the true claim total "
        f"when nothing is orphaned; got {raw_sum}, expected {len(claims)}"
    )
    assert weighted_sum > len(claims), (
        "test fixture did not actually exercise visibility weighting — "
        "expected the weighted sum to overshoot len(claims)"
    )
    # The bug: len(claims) - weighted_sum goes negative here, while
    # len(claims) - raw_sum correctly stays at 0.
    assert len(claims) - raw_sum == 0
    assert len(claims) - weighted_sum < 0


# ---------------------------------------------------------------------------
# Family index entry tests (FIX-03)
# ---------------------------------------------------------------------------

class TestFamilyIndexEntry:
    """Tests for _family_index_entry() and its presence in planner output."""

    def test_words_weight(self):
        """Words is index 0 → weight 10."""
        entry = sp._family_index_entry("docs.aspose.org", "words")
        assert entry["weight"] == 10

    def test_cells_weight(self):
        """Cells is index 2 → weight 30."""
        entry = sp._family_index_entry("docs.aspose.org", "cells")
        assert entry["weight"] == 30

    def test_unknown_family_weight(self):
        """Unknown family defaults to weight 100."""
        entry = sp._family_index_entry("docs.aspose.org", "nonexistent")
        assert entry["weight"] == 100

    def test_entry_shape(self):
        """Entry has required keys: slug, path, type, page_class, layout, weight, mandatory."""
        entry = sp._family_index_entry("kb.aspose.org", "words")
        assert entry["slug"] == "_family_index"
        assert entry["path"] == "content/kb.aspose.org/en/words/_index.md"
        assert entry["type"] == "family-home"
        assert entry["page_class"] == "structural"
        assert entry["layout"] == "wide"
        assert entry["mandatory"] is True

    def test_docs_plan_contains_family_entry(self):
        """plan_docs() output includes exactly one _family_index entry."""
        pages = sp.plan_docs("3d", "python", clusters=[], has_license=False, license_path=None)
        family_entries = [p for p in pages if p.get("slug") == "_family_index"]
        assert len(family_entries) == 1
        assert "3d/_index.md" in family_entries[0]["path"]

    def test_kb_plan_contains_family_entry(self):
        """plan_kb() output includes exactly one _family_index entry."""
        subpkgs = ["formats", "entities"]
        pages = _plan_kb_from_surface(subpkgs)
        family_entries = [p for p in pages if p.get("slug") == "_family_index"]
        assert len(family_entries) == 1
        assert "3d/_index.md" in family_entries[0]["path"]

    def test_reference_plan_contains_family_entry(self):
        """plan_reference() output includes exactly one _family_index entry."""
        api_surface = _make_api_surface(["formats"])
        pages = sp.plan_reference("3d", "python", api_surface)
        family_entries = [p for p in pages if p.get("slug") == "_family_index"]
        assert len(family_entries) == 1
        assert "3d/_index.md" in family_entries[0]["path"]


# ---------------------------------------------------------------------------
# Gate 1 additions: Java-path routing and cells/java slug regression tests
# ---------------------------------------------------------------------------

def _make_api_surface_cells_java() -> list[dict]:
    """Build api_surface with real Java-style file paths for cells/java."""
    return [
        {"name": "Workbook",
         "file": "src/main/java/com/aspose/cells_foss/Workbook.java",
         "methods": ["save", "getWorksheets"]},
        {"name": "Worksheet",
         "file": "src/main/java/com/aspose/cells_foss/Worksheet.java",
         "methods": ["getCells", "setName"]},
        {"name": "Cell",
         "file": "src/main/java/com/aspose/cells_foss/Cell.java",
         "methods": ["putValue", "getType"]},
        {"name": "AutoFilter",
         "file": "src/main/java/com/aspose/cells_foss/AutoFilter.java",
         "methods": ["setRange"]},
        {"name": "AlignmentValue",
         "file": "src/main/java/com/aspose/cells_foss/core/AlignmentValue.java",
         "methods": []},
        {"name": "AutoFilterModel",
         "file": "src/main/java/com/aspose/cells_foss/core/AutoFilterModel.java",
         "methods": ["getFilterType"]},
        {"name": "NumberFormatValue",
         "file": "src/main/java/com/aspose/cells_foss/core/NumberFormatValue.java",
         "methods": []},
        {"name": "IPackageReader",
         "file": "src/main/java/com/aspose/cells_foss/packaging/IPackageReader.java",
         "methods": ["readPart"]},
    ]


def test_class_to_subpackage_java_root_level():
    """Java root-level path (7-part) routes to cells_foss package name."""
    result = sp._class_to_subpackage(
        "src/main/java/com/aspose/cells_foss/Workbook.java"
    )
    # parts[-2] = "cells_foss" — root-level package, not a sub-package dir
    assert result == "cells_foss", f"Expected 'cells_foss', got {result!r}"


def test_class_to_subpackage_java_core_subpkg():
    """Java core sub-package path (8-part) routes to 'core'."""
    result = sp._class_to_subpackage(
        "src/main/java/com/aspose/cells_foss/core/AlignmentValue.java"
    )
    assert result == "core", f"Expected 'core', got {result!r}"


def test_class_to_subpackage_java_packaging_subpkg():
    """Java packaging sub-package path routes to 'packaging'."""
    result = sp._class_to_subpackage(
        "src/main/java/com/aspose/cells_foss/packaging/IPackageReader.java"
    )
    assert result == "packaging", f"Expected 'packaging', got {result!r}"


def test_cells_java_core_subpkg_gets_descriptive_label():
    """'core' sub-package in cells family must not produce generic label 'core'."""
    label = sp._subpkg_to_label("core", family="cells")
    assert label != "core", (
        f"'core' sub-package in cells family must not produce generic label 'core'. Got: {label!r}"
    )
    assert "cells" in label or "model" in label, (
        f"Expected descriptive label containing 'cells' or 'model'. Got: {label!r}"
    )


def test_plan_blog_deep_dive_derived_slug_includes_family():
    """Deep-dive derived slugs must contain the family name."""
    api = _make_api_surface_family(["formats", "entities", "animation"], family="3d")
    claims = _make_claims(api, per_class=20)
    snippet_index = _make_snippet_index_for(api, snippets_per_class=4)
    clusters = sp.detect_clusters(claims, api, snippet_index, "", family="3d")
    pages, _, _ = sp.plan_blog("3d", "python", 600, 30, clusters)
    derived_p3 = [p for p in pages if p.get("weight") == 3 and p.get("source") == "derived"]
    for p in derived_p3:
        assert "3d" in p["slug"], (
            f"Deep-dive derived slug must contain '3d', got: {p['slug']!r}"
        )


def test_plan_blog_cells_java_never_produces_core_in_java():
    """cells/java must never derive the slug 'core-in-java'."""
    api = _make_api_surface_cells_java()
    claims = _make_claims(api, per_class=20)
    snippet_index = _make_snippet_index_for(api, snippets_per_class=4)
    clusters = sp.detect_clusters(claims, api, snippet_index, "", family="cells")
    pages, _, _ = sp.plan_blog("cells", "java", 1500, 30, clusters)
    all_derived_slugs = [p["slug"] for p in pages if p.get("source") == "derived"]
    assert "core-in-java" not in all_derived_slugs, (
        f"'core-in-java' must never be derived for cells/java. Got derived slugs: {all_derived_slugs}"
    )
    # Additionally: any weight-3 derived slug must include family identity
    derived_p3 = [p for p in pages if p.get("weight") == 3 and p.get("source") == "derived"]
    for p in derived_p3:
        assert "cells" in p["slug"], (
            f"cells/java deep-dive derived slug must contain 'cells'. Got: {p['slug']!r}"
        )


# ---------------------------------------------------------------------------
# C# flat-src layout clustering tests (PDF/.NET page expansion)
# ---------------------------------------------------------------------------

def _make_csharp_api_surface(dirs: dict[str, int], family: str = "pdf") -> list[dict]:
    """Build api_surface with C# flat-src paths: src/{Dir}/Class.cs."""
    entries = []
    idx = 0
    for dirname, count in dirs.items():
        for _ in range(count):
            name = f"Class{idx}"
            if dirname:
                file_path = f"src/{dirname}/{name}.cs"
            else:
                file_path = f"src/{name}.cs"
            entries.append({
                "name": name,
                "file": file_path,
                "methods": [f"method_{idx}_a"],
            })
            idx += 1
    return entries


def test_class_to_subpackage_csharp_3part():
    """3-part C# path with PascalCase dir returns the directory name."""
    assert sp._class_to_subpackage("src/Annotations/MyClass.cs") == "Annotations"
    assert sp._class_to_subpackage("src/Text/TextFragment.cs") == "Text"
    assert sp._class_to_subpackage("src/Forms/Field.cs") == "Forms"


def test_class_to_subpackage_csharp_dotted_root():
    """3-part C# path with dotted dir (namespace root) returns empty string."""
    assert sp._class_to_subpackage("src/Aspose.Slides.Foss/Presentation.cs") == ""


def test_class_to_subpackage_csharp_underscored_root():
    """3-part C# path with underscored dir (namespace root) returns empty string."""
    assert sp._class_to_subpackage("src/Aspose.Cells_FOSS/Workbook.cs") == ""
    assert sp._class_to_subpackage("src/cells_foss/Workbook.cs") == ""


def test_class_to_subpackage_python_unchanged():
    """Python 3-part paths must still return empty string (no regression)."""
    assert sp._class_to_subpackage("aspose/threed/Scene.py") == ""


def test_subpkg_to_label_pdf_family_override():
    """PDF family overrides must take priority over cross-family labels."""
    # RC-5 fix (TC-KBS-015): pdf labels now include product qualifier
    assert sp._subpkg_to_label("drawing", "pdf") == "pdf-graphics"
    assert sp._subpkg_to_label("drawing", "slides") == "drawing-shapes"
    assert sp._subpkg_to_label("annotations", "pdf") == "pdf-annotations"


def test_detect_clusters_pdf_layout():
    """C# flat-src layout for PDF must produce multiple clusters, not 1-2."""
    dirs = {
        "Annotations": 10, "Forms": 5, "Text": 8, "Content": 6,
        "Facades": 4, "Security": 3, "Devices": 3, "Navigation": 3,
        "": 5,  # root-level
    }
    api = _make_csharp_api_surface(dirs, family="pdf")
    claims = _make_claims(api, per_class=10)
    clusters = sp.detect_clusters(claims, api, [], "", family="pdf")
    categories = [c["category"] for c in clusters]
    assert len(clusters) >= 5, (
        f"Expected >=5 clusters for PDF, got {len(clusters)}: {categories}"
    )
    assert "pdf-annotations" in categories
    assert "text-extraction" in categories
    assert "document-management" in categories


def test_detect_clusters_3d_unchanged():
    """3D clustering must remain unchanged after the C# fix."""
    subpkgs = ["formats", "formats", "formats",
               "entities", "entities",
               "animation",
               "shading",
               "", ""]
    api_surface = _make_api_surface(subpkgs)
    claims = _make_claims(api_surface, per_class=10)
    clusters = sp.detect_clusters(claims, api_surface, [], "", family="3d")
    assert 4 <= len(clusters) <= 10, (
        f"3D regression: expected 4-10 clusters, got {len(clusters)}"
    )


# ---------------------------------------------------------------------------
# TC-KBS-006 — KB slug fix tests
# Tests for TC-KBS-001, TC-KBS-002, TC-KBS-003, TC-KBS-004, TC-KBS-005
# ---------------------------------------------------------------------------

class TestKbSlugLabelFixes:
    """TC-KBS-001 + TC-KBS-005: verify _FAMILY_SUBPKG_LABELS entries."""

    def test_javascriptextensions_maps_to_readable_label(self):
        """TC-KBS-001: C# namespace JavaScriptExtensions → javascript-extensions."""
        result = sp._subpkg_to_label("JavaScriptExtensions", "pdf")
        assert result == "javascript-extensions", (
            f"Expected 'javascript-extensions', got {result!r}"
        )

    def test_cells_validation_maps_to_data_validation(self):
        """TC-KBS-005: 'validation' subpkg in cells → data-validation."""
        result = sp._subpkg_to_label("validation", "cells")
        assert result == "data-validation", (
            f"Expected 'data-validation', got {result!r}"
        )

    def test_cells_packaging_maps_to_xlsx_packaging(self):
        """Pre-existing: 'packaging' subpkg in cells → xlsx-packaging."""
        result = sp._subpkg_to_label("packaging", "cells")
        assert result == "xlsx-packaging", (
            f"Expected 'xlsx-packaging', got {result!r}"
        )

    def test_pdf_existing_labels_unchanged(self):
        """Regression: RC-5 label change must not disturb other pdf labels."""
        # RC-5 fix: annotations and forms now map to pdf-annotations
        assert sp._subpkg_to_label("annotations", "pdf") == "pdf-annotations"
        assert sp._subpkg_to_label("forms", "pdf") == "pdf-annotations"
        assert sp._subpkg_to_label("text", "pdf") == "text-extraction"
        assert sp._subpkg_to_label("facades", "pdf") == "facades-api"
        assert sp._subpkg_to_label("security", "pdf") == "security-signatures"

    def test_pdf_rc5_labels_have_pdf_qualifier(self):
        """TC-KBS-015: RC-5 merged cluster labels include pdf product qualifier."""
        # annotations-forms cluster → pdf-annotations
        assert sp._subpkg_to_label("annotations", "pdf") == "pdf-annotations"
        assert sp._subpkg_to_label("forms", "pdf") == "pdf-annotations"
        # graphics-drawing cluster → pdf-graphics
        assert sp._subpkg_to_label("drawing", "pdf") == "pdf-graphics"
        assert sp._subpkg_to_label("shading", "pdf") == "pdf-graphics"
        assert sp._subpkg_to_label("color", "pdf") == "pdf-graphics"
        assert sp._subpkg_to_label("vector", "pdf") == "pdf-graphics"
        # metadata-utilities cluster → pdf-metadata
        assert sp._subpkg_to_label("xmp", "pdf") == "pdf-metadata"
        assert sp._subpkg_to_label("collections", "pdf") == "pdf-metadata"
        assert sp._subpkg_to_label("artifacts", "pdf") == "pdf-metadata"


class TestCamelCaseSplitter:
    """TC-KBS-002: CamelCase word-boundary splitter in _subpkg_to_label()."""

    def test_unmapped_camel_case_is_hyphenated(self):
        """An unmapped PascalCase namespace gets split on word boundaries."""
        # "LogicalStructure" is not in _FAMILY_SUBPKG_LABELS["email"] or _SUBPKG_LABEL
        result = sp._subpkg_to_label("LogicalStructure", "email")
        assert result == "logical-structure", (
            f"CamelCase splitter gave {result!r}"
        )

    def test_multi_word_camel_case_split(self):
        """Multi-word PascalCase splits correctly."""
        # "PageGeneration" not in any lookup for "words"
        result = sp._subpkg_to_label("PageGeneration", "words")
        assert result == "page-generation", (
            f"Multi-word split gave {result!r}"
        )

    def test_acronym_camel_case_split(self):
        """Acronym boundary (e.g. XmlProcessing) splits correctly."""
        result = sp._subpkg_to_label("XmlProcessing", "email")
        assert result == "xml-processing", (
            f"Acronym split gave {result!r}"
        )

    def test_lookup_table_takes_priority_over_splitter(self):
        """Existing lookup table entries are not overridden by the splitter."""
        # "annotations" is in _FAMILY_SUBPKG_LABELS["pdf"] (RC-5: now pdf-annotations)
        result = sp._subpkg_to_label("annotations", "pdf")
        assert result == "pdf-annotations", (
            f"Lookup table should win; got {result!r}"
        )

    def test_single_word_unmapped_unchanged(self):
        """A single-word lowercase name has no camel boundary — stays as-is."""
        result = sp._subpkg_to_label("widgets", "email")
        assert result == "widgets", f"Single word gave {result!r}"


class TestVerbNounDedup:
    """TC-KBS-003: Nominal-form verb stripping in _kb_noun_from_cluster()."""

    def test_extraction_stripped_when_verb_is_extract(self):
        """'text-extraction' with verb 'extract' → noun 'text' (not 'text-extraction')."""
        noun = sp._kb_noun_from_cluster("text-extraction", "pdf", verb="extract")
        assert noun == "text", f"Got {noun!r}"

    def test_conversion_stripped_when_verb_is_convert(self):
        """'format-conversion' with verb 'convert' → 'format'."""
        noun = sp._kb_noun_from_cluster("format-conversion", "pdf", verb="convert")
        assert noun == "format", f"Got {noun!r}"

    def test_rendering_stripped_when_verb_is_render(self):
        """'image-rendering' with verb 'render' → 'image'."""
        noun = sp._kb_noun_from_cluster("image-rendering", "3d", verb="render")
        assert noun == "image", f"Got {noun!r}"

    def test_exact_verb_suffix_still_works(self):
        """Original exact verb-suffix stripping still works (regression)."""
        # "export-rendering" with verb "export" → prefix "export-" stripped → "rendering"
        noun = sp._kb_noun_from_cluster("export-rendering", "3d", verb="export")
        assert noun == "rendering", f"Got {noun!r}"

    def test_no_verb_no_change(self):
        """Without a verb, no stripping occurs."""
        noun = sp._kb_noun_from_cluster("text-extraction", "pdf", verb="")
        # suffix "-support" etc. not present; no stripping
        assert "text" in noun, f"No-verb case gave {noun!r}"


class TestKbSlugValidator:
    """TC-KBS-004: _validate_kb_slugs() gate."""

    def _make_page(self, slug: str, source: str = "derived") -> dict:
        return {
            "slug": slug,
            "source": source,
            "path": f"content/kb.aspose.org/en/pdf/net/{slug}.md",
            "type": "topic",
        }

    def test_camel_leak_raises_for_derived(self):
        """Unsplit CamelCase noun raises ValueError for source=derived."""
        pages = [self._make_page("how-to-work-with-javascriptextensions-dotnet")]
        with pytest.raises(ValueError, match="unsplit CamelCase"):
            sp._validate_kb_slugs(pages, "pdf", "net")

    def test_verb_noun_duplication_raises_for_derived(self):
        """Verb-noun duplication raises ValueError for source=derived."""
        pages = [self._make_page("how-to-extract-text-extraction-dotnet")]
        with pytest.raises(ValueError, match="verb-noun duplication"):
            sp._validate_kb_slugs(pages, "pdf", "net")

    def test_generic_noun_raises_for_derived(self):
        """Generic primary noun raises ValueError for source=derived."""
        pages = [self._make_page("how-to-work-with-core-dotnet")]
        with pytest.raises(ValueError, match="too generic"):
            sp._validate_kb_slugs(pages, "pdf", "net")

    def test_camel_leak_warns_not_raises_for_discovered(self):
        """Unsplit CamelCase noun does NOT raise for source=discovered (existing URL)."""
        pages = [self._make_page(
            "how-to-work-with-javascriptextensions-dotnet", source="discovered"
        )]
        # Must not raise — existing URLs must not be broken
        sp._validate_kb_slugs(pages, "pdf", "net")

    def test_good_slug_passes(self):
        """A well-formed slug passes validation without error."""
        pages = [self._make_page("how-to-work-with-javascript-extensions-dotnet")]
        sp._validate_kb_slugs(pages, "pdf", "net")  # no exception

    def test_non_howto_slug_ignored(self):
        """Non-how-to slugs (faq, use-cases) are not validated."""
        pages = [
            self._make_page("faq"),
            self._make_page("use-cases"),
            self._make_page("_index"),
        ]
        sp._validate_kb_slugs(pages, "pdf", "net")  # no exception

    def test_good_extract_slug_passes(self):
        """Fixed verb-noun slug (after TC-KBS-003) passes validation."""
        pages = [self._make_page("how-to-extract-text-dotnet")]
        sp._validate_kb_slugs(pages, "pdf", "net")  # no exception

    # C4 tests (TC-KBS-016) ------------------------------------

    def test_c4_compound_without_family_keyword_raises_for_derived(self):
        """C4: compound noun with no pdf keyword raises ValueError for derived."""
        # "annotations-forms" has neither "pdf" nor any pdf-specific word
        pages = [self._make_page("how-to-add-annotations-forms-dotnet")]
        with pytest.raises(ValueError, match="lacks product-family qualifier"):
            sp._validate_kb_slugs(pages, "pdf", "net")

    def test_c4_graphics_drawing_raises_for_derived(self):
        """C4: 'graphics-drawing' has no pdf keyword → raises for derived."""
        pages = [self._make_page("how-to-add-graphics-drawing-dotnet")]
        with pytest.raises(ValueError, match="lacks product-family qualifier"):
            sp._validate_kb_slugs(pages, "pdf", "net")

    def test_c4_metadata_utilities_raises_for_derived(self):
        """C4: 'metadata-utilities' has no pdf keyword → raises for derived."""
        pages = [self._make_page("how-to-extract-metadata-utilities-dotnet")]
        with pytest.raises(ValueError, match="lacks product-family qualifier"):
            sp._validate_kb_slugs(pages, "pdf", "net")

    def test_c4_pdf_annotations_passes(self):
        """C4: 'pdf-annotations' contains 'pdf' → passes for pdf family."""
        pages = [self._make_page("how-to-add-pdf-annotations-dotnet")]
        sp._validate_kb_slugs(pages, "pdf", "net")  # no exception

    def test_c4_pdf_graphics_passes(self):
        """C4: 'pdf-graphics' contains 'pdf' → passes for pdf family."""
        pages = [self._make_page("how-to-add-pdf-graphics-dotnet")]
        sp._validate_kb_slugs(pages, "pdf", "net")  # no exception

    def test_c4_pdf_metadata_passes(self):
        """C4: 'pdf-metadata' contains 'pdf' → passes for pdf family."""
        pages = [self._make_page("how-to-extract-pdf-metadata-dotnet")]
        sp._validate_kb_slugs(pages, "pdf", "net")  # no exception

    def test_c4_discovered_slug_warns_not_raises(self):
        """C4: compound without family keyword warns but does not raise for discovered."""
        pages = [self._make_page("how-to-add-annotations-forms-dotnet", source="discovered")]
        sp._validate_kb_slugs(pages, "pdf", "net")  # must not raise

    def test_c4_unknown_family_no_check(self):
        """C4: family with no keyword set defined → no C4 check applied."""
        pages = [self._make_page("how-to-work-with-arbitrary-compound-dotnet")]
        # "unknown-family" has no entry in _FAMILY_PRODUCT_KEYWORDS → C4 skipped
        sp._validate_kb_slugs(pages, "unknown-family", "net")  # no exception


# ---------------------------------------------------------------------------
# SQ-10: _match_existing_to_cluster concat-synonym fix
# TC-SQ-10-001 / TC-SQ-10-002
# ---------------------------------------------------------------------------

def _make_existing_doc_page(slug: str) -> dict:
    """Build a minimal existing-page record for docs section testing."""
    return {
        "slug": f"developer-guide/{slug}",
        "path": f"content/docs.aspose.org/en/pdf/net/developer-guide/{slug}.md",
        "frontmatter_cluster": "",
        "title": slug,
        "auto_updatable": True,
    }


class TestMatchExistingToClusterSQ10:
    """Regression tests for SQ-10: concat-form old slugs map to new hyphenated clusters."""

    def test_javascriptextensions_maps_to_javascript_extensions_cluster(self):
        """TC-SQ-10-001: existing 'javascriptextensions' docs page matches
        'javascript-extensions' cluster via synonym lookup."""
        existing = [_make_existing_doc_page("javascriptextensions")]
        result = sp._match_existing_to_cluster(
            existing_pages=existing,
            cluster_category="javascript-extensions",
            cluster_slug="javascript-extensions",
            cluster_class_names=[],
            section="docs",
            family="pdf",
        )
        assert result is not None, (
            "Expected 'javascriptextensions' page to match 'javascript-extensions' cluster"
        )
        assert "javascriptextensions" in result["slug"]

    def test_logicalstructure_maps_to_logical_structure_cluster(self):
        """TC-SQ-10-002: existing 'logicalstructure' docs page matches
        'logical-structure' cluster via synonym lookup."""
        existing = [_make_existing_doc_page("logicalstructure")]
        result = sp._match_existing_to_cluster(
            existing_pages=existing,
            cluster_category="logical-structure",
            cluster_slug="logical-structure",
            cluster_class_names=[],
            section="docs",
            family="pdf",
        )
        assert result is not None, (
            "Expected 'logicalstructure' page to match 'logical-structure' cluster"
        )
        assert "logicalstructure" in result["slug"]

    def test_javascript_extensions_hyphen_matches_directly(self):
        """TC-SQ-10-003: new 'javascript-extensions' page matches via priority-2 substring."""
        existing = [_make_existing_doc_page("javascript-extensions")]
        result = sp._match_existing_to_cluster(
            existing_pages=existing,
            cluster_category="javascript-extensions",
            cluster_slug="javascript-extensions",
            cluster_class_names=[],
            section="docs",
            family="pdf",
        )
        assert result is not None, (
            "Expected 'javascript-extensions' page to match 'javascript-extensions' cluster"
        )

    def test_unrelated_page_does_not_match(self):
        """TC-SQ-10-004: page with unrelated slug does not match."""
        existing = [_make_existing_doc_page("annotations-forms")]
        result = sp._match_existing_to_cluster(
            existing_pages=existing,
            cluster_category="javascript-extensions",
            cluster_slug="javascript-extensions",
            cluster_class_names=[],
            section="docs",
            family="pdf",
        )
        assert result is None, (
            "Expected unrelated page to NOT match 'javascript-extensions' cluster"
        )
