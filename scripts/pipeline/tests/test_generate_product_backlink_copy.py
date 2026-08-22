"""test_generate_product_backlink_copy.py — TC6 (2026-08-21): canonical_overrides
wiring for generate_product_backlink_copy.py's build_request().

Confirmed live gap before this fix: build_request() called resolve_backlink()
without ever passing canonical_overrides=, so a verified platform-slug override
(e.g. words/python -> python-net) was silently inert for products.aspose.org
LLM copy generation specifically -- the resolved target would silently fall
back to the family-level link even when the real platform-specific bridge
page existed and was HTTP-verified, exactly the recurring call-site-omission
pattern MT043 already found and fixed once, independently, in
readme_refresh_run.py.

Run:
    python -m pytest scripts/pipeline/tests/test_generate_product_backlink_copy.py -v
"""
from __future__ import annotations

from pathlib import Path

from generate_product_backlink_copy import build_request

FAMILIES_MAP = {"testfam": "Aspose.TestFam"}
PLATFORMS_MAP = {"python": "Python", "python-net": "Python via .NET"}


def _write_page(tmp_path: Path) -> Path:
    content_dir = tmp_path / "content" / "products.aspose.org" / "en" / "testfam" / "python"
    content_dir.mkdir(parents=True)
    fp = content_dir / "_index.md"
    fp.write_text(
        "---\n"
        "overview:\n"
        "  content: \"Aspose.TestFam FOSS is a free library.\"\n"
        "supportandlearning:\n"
        "  enable: false\n"
        "---\n",
        encoding="utf-8",
    )
    return fp


def _target_map_with_override_only_reachable() -> dict:
    """testfam/python-net exists and is HTTP 200; testfam/python does NOT
    exist as its own platform entry -- only reachable via the override."""
    return {
        "targets": {
            "products.aspose.com": {
                "families": {
                    "testfam": {"url": "https://products.aspose.com/testfam/", "http_status": 200},
                },
                "platforms": {
                    "testfam/python-net": {
                        "url": "https://products.aspose.com/testfam/python-net/",
                        "http_status": 200,
                    },
                },
            },
        },
        "all_urls": {},
    }


def test_canonical_override_resolves_platform_target_when_local_slug_missing(tmp_path):
    """The fix: passing canonical_overrides= lets build_request() resolve the
    real platform-specific bridge page instead of silently falling back to
    the family-level link."""
    fp = _write_page(tmp_path)
    target_map = _target_map_with_override_only_reachable()
    canonical_overrides = {
        "overrides": {
            "testfam/python": {"target_platform": "python-net", "http_verified": True},
        },
    }
    req = build_request(
        fp, "testfam", "python", tmp_path, FAMILIES_MAP, PLATFORMS_MAP, target_map,
        canonical_overrides=canonical_overrides,
    )
    assert req is not None
    assert req.resolved_target_url == "https://products.aspose.com/testfam/python-net/"
    # Anchor text describes the SOURCE page's own platform identity ("Python"),
    # not the target URL's internal bridge-page slug ("python-net") -- that's
    # a URL implementation detail, not something that should leak into anchor
    # wording. platforms_map is keyed by the local platform ("python"), not
    # the resolved override_platform.
    assert req.product_display_name == "Aspose.TestFam for Python"


def test_without_canonical_overrides_silently_falls_back_to_family(tmp_path):
    """Regression control: this is the CONFIRMED pre-fix defect -- omitting
    canonical_overrides= (the exact bug this card fixes) makes the override
    inert and the real platform-specific target is never found, silently
    degrading to the family-level link instead."""
    fp = _write_page(tmp_path)
    target_map = _target_map_with_override_only_reachable()
    req = build_request(
        fp, "testfam", "python", tmp_path, FAMILIES_MAP, PLATFORMS_MAP, target_map,
        canonical_overrides=None,
    )
    assert req is not None
    assert req.resolved_target_url == "https://products.aspose.com/testfam/"
    assert req.product_display_name == "Aspose.TestFam"  # family-only, no platform suffix


def test_canonical_overrides_omitted_entirely_defaults_to_none(tmp_path):
    """Negative control: the keyword is optional (backward compatible) --
    a caller that omits it entirely (not even passing None) must behave
    identically to explicitly passing None."""
    fp = _write_page(tmp_path)
    target_map = _target_map_with_override_only_reachable()
    req = build_request(fp, "testfam", "python", tmp_path, FAMILIES_MAP, PLATFORMS_MAP, target_map)
    assert req is not None
    assert req.resolved_target_url == "https://products.aspose.com/testfam/"


def test_local_slug_present_resolves_correctly_regardless_of_overrides(tmp_path):
    """Negative control: when the local platform slug IS directly present
    in the target map, canonical_overrides must not be needed for a correct
    resolution (overrides only matter when the plain lookup fails)."""
    fp = _write_page(tmp_path)
    target_map = {
        "targets": {
            "products.aspose.com": {
                "families": {
                    "testfam": {"url": "https://products.aspose.com/testfam/", "http_status": 200},
                },
                "platforms": {
                    "testfam/python": {
                        "url": "https://products.aspose.com/testfam/python/",
                        "http_status": 200,
                    },
                },
            },
        },
        "all_urls": {},
    }
    req = build_request(
        fp, "testfam", "python", tmp_path, FAMILIES_MAP, PLATFORMS_MAP, target_map,
        canonical_overrides=None,
    )
    assert req is not None
    assert req.resolved_target_url == "https://products.aspose.com/testfam/python/"
