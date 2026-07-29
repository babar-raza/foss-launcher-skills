"""SEO-002b map_url.py: URL-to-content-path resolution tests.

Regression coverage for Finding #36/#41 (plan v5/v6): Strategy 5 (bare .md
fallback) never tried an /en/-prefixed path for docs/kb/reference domains,
even though Strategy 4 already does exactly that for index.md/_index.md.
Discovered via a real pilot rerun against this repo's actual content, not a
synthetic fixture -- confirmed here with both a synthetic fixture (fast,
deterministic) and a real-content case (test_real_content_regression_pin).
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure scripts/seo and scripts/pipeline are on sys.path
_SCRIPTS = Path(__file__).resolve().parents[2]
_PIPELINE = _SCRIPTS / "pipeline"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
if str(_PIPELINE) not in sys.path:
    sys.path.insert(0, str(_PIPELINE))

from seo.pipeline.map_url import _resolve_url_to_content_path  # noqa: E402

_REPO_ROOT = _SCRIPTS.parents[0]
_CONTENT_ROOT = _REPO_ROOT / "content"


class TestBareMdFileEnPrefix:
    """Strategy 5b: bare .md files under docs/kb/reference need the /en/ prefix."""

    def test_docs_bare_md_with_en_prefix(self, tmp_path):
        site_root = tmp_path / "docs.aspose.org"
        target = site_root / "en" / "words" / "python" / "getting-started" / "installation.md"
        target.parent.mkdir(parents=True)
        target.write_text("---\ntitle: x\n---\n", encoding="utf-8")

        path, match_type = _resolve_url_to_content_path(
            "https://docs.aspose.org/words/python/getting-started/installation/", tmp_path
        )
        assert path == target
        assert match_type == "bare_file"

    def test_kb_bare_md_with_en_prefix(self, tmp_path):
        site_root = tmp_path / "kb.aspose.org"
        target = site_root / "en" / "3d" / "python" / "how-to-convert-fbx-to-gltf-python.md"
        target.parent.mkdir(parents=True)
        target.write_text("---\ntitle: x\n---\n", encoding="utf-8")

        path, match_type = _resolve_url_to_content_path(
            "https://kb.aspose.org/3d/python/how-to-convert-fbx-to-gltf-python/", tmp_path
        )
        assert path == target
        assert match_type == "bare_file"

    def test_reference_bare_md_with_en_prefix(self, tmp_path):
        site_root = tmp_path / "reference.aspose.org"
        target = site_root / "en" / "slides" / "net" / "saveformat.md"
        target.parent.mkdir(parents=True)
        target.write_text("---\ntitle: x\n---\n", encoding="utf-8")

        path, match_type = _resolve_url_to_content_path(
            "https://reference.aspose.org/slides/net/saveformat/", tmp_path
        )
        assert path == target
        assert match_type == "bare_file"

    def test_still_unmatched_when_file_absent(self, tmp_path):
        site_root = tmp_path / "docs.aspose.org"
        (site_root / "en").mkdir(parents=True)

        path, match_type = _resolve_url_to_content_path(
            "https://docs.aspose.org/words/python/getting-started/nonexistent/", tmp_path
        )
        assert path is None
        assert match_type == "unmatched"

    def test_products_domain_not_affected(self, tmp_path):
        """Strategy 5b is scoped to docs/kb/reference only (Finding #36's exact
        scope) -- products.aspose.org must not gain a bare-.md /en/ fallback
        it was never shown to need, to avoid silently widening this fix's
        blast radius beyond what was actually investigated."""
        site_root = tmp_path / "products.aspose.org"
        target = site_root / "en" / "pdf" / "somepage.md"
        target.parent.mkdir(parents=True)
        target.write_text("---\ntitle: x\n---\n", encoding="utf-8")

        path, match_type = _resolve_url_to_content_path(
            "https://products.aspose.org/pdf/somepage/", tmp_path
        )
        assert path is None
        assert match_type == "unmatched"


class TestRealContentRegressionPin:
    """Pin the exact real-content case that motivated this fix (Finding #36),
    against this repo's actual content/ tree."""

    def test_words_python_installation_now_resolves(self):
        path, match_type = _resolve_url_to_content_path(
            "https://docs.aspose.org/words/python/getting-started/installation/",
            _CONTENT_ROOT,
        )
        assert path is not None, "Finding #36's exact motivating case must resolve"
        assert path.name == "installation.md"
        assert match_type == "bare_file"


class TestWebsitesAsposeOrgEnPrefix:
    """Strategy 3 extended to websites.aspose.org (Finding #45): this site's
    content also lives under an /en/ prefix (e.g.
    content/websites.aspose.org/en/aspose/app/_index.md), but it was missing
    from every /en/-prefix strategy -- real, existing content misreported as
    an unmatched/content-gap candidate. Discovered while building
    SEO-KEYWORD-GAP-REPORT: 6 of 8 English "unmatched" GSC URLs turned out to
    be this exact bug, not real content gaps.
    """

    def test_websites_root_with_en_prefix(self, tmp_path):
        site_root = tmp_path / "websites.aspose.org"
        target = site_root / "en" / "_index.md"
        target.parent.mkdir(parents=True)
        target.write_text("---\ntitle: x\n---\n", encoding="utf-8")

        path, match_type = _resolve_url_to_content_path("https://websites.aspose.org/", tmp_path)
        assert path == target
        assert match_type == "exact"

    def test_websites_nested_section_with_en_prefix(self, tmp_path):
        site_root = tmp_path / "websites.aspose.org"
        target = site_root / "en" / "aspose" / "app" / "_index.md"
        target.parent.mkdir(parents=True)
        target.write_text("---\ntitle: x\n---\n", encoding="utf-8")

        path, match_type = _resolve_url_to_content_path(
            "https://websites.aspose.org/aspose/app/", tmp_path
        )
        assert path == target
        assert match_type == "exact"

    def test_websites_still_unmatched_when_file_absent(self, tmp_path):
        site_root = tmp_path / "websites.aspose.org"
        (site_root / "en").mkdir(parents=True)

        path, match_type = _resolve_url_to_content_path(
            "https://websites.aspose.org/nonexistent/", tmp_path
        )
        assert path is None
        assert match_type == "unmatched"

    def test_real_websites_aspose_org_app_pages_now_resolve(self):
        """Pin the exact real cases found while auditing unmatched English
        GSC URLs for SEO-KEYWORD-GAP-REPORT."""
        for url in (
            "https://websites.aspose.org/aspose/app/",
            "https://websites.aspose.org/conholdate/app/",
            "https://websites.aspose.org/aspose/cloud/",
            "https://websites.aspose.org/groupdocs/",
        ):
            path, match_type = _resolve_url_to_content_path(url, _CONTENT_ROOT)
            assert path is not None, f"{url} must resolve to real content"
            assert match_type == "exact"
