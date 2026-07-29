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
