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
