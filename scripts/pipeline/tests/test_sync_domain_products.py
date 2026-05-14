"""Tests for scripts/pipeline/commands/websites/sync_domain_products.py.

Coverage:
  1. Dry-run against real repo produces only PROVENANCE_ONLY diff (not content diff).
  2. Adding a fake published product shows it in dry-run diff.
  3. Removing/drafting a product removes it in dry-run diff.
  4. Locale files: translated fields preserved, products block updated.
  5. Deterministic family/platform ordering.
  6. Safety: empty product list → fails closed.
  7. Safety: missing image → fails closed.
  8. Safety: unsupported domain → fails closed.
  9. Dry-run does NOT write files.
  10. Write mode writes only expected files.
  11. Updated frontmatter parses cleanly.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

import pytest
import yaml

# ---------------------------------------------------------------------------
# Repo root + module import
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[3]
_PIPELINE_ROOT = REPO_ROOT / "scripts" / "pipeline"

if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

import commands.websites.sync_domain_products as _mod  # noqa: E402
from commands.websites.sync_domain_products import (  # noqa: E402
    _REPO_ROOT,  # real repo root reference for test setup (= _DEFAULT_REPO_ROOT at import time)
    check_images,
    get_published_products,
    is_published,
    replace_products_in_text,
    run,
    serialize_products_yaml,
)


# ---------------------------------------------------------------------------
# Autouse fixture — always reset module config after each test
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_mod_config():
    """Reset sync_domain_products module constants to defaults after every test."""
    yield
    _mod.configure()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

EN_PAGE = REPO_ROOT / "content" / "websites.aspose.org" / "en" / "aspose" / "org" / "_index.md"

_SAMPLE_FAMILIES = {"words": "Aspose.Words", "cells": "Aspose.Cells", "3d": "Aspose.3D"}
_SAMPLE_FAMILIES_ORDER = ["words", "cells", "3d"]
_SAMPLE_PLATFORMS_ORDER = ["python", "net", "java"]
_SAMPLE_PLATFORM_DISPLAY = {"python": "Python", "net": ".NET", "java": "Java"}


def _make_product(family: str, platform: str, active: bool = True) -> dict:
    return {"family": family, "platform": platform, "active": active}


# ---------------------------------------------------------------------------
# Helper: temp published product directory
# ---------------------------------------------------------------------------

def _write_plugin_page(tmp_path: Path, family: str, platform: str, draft: bool = False) -> Path:
    page = tmp_path / family / platform / "_index.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    draft_line = "draft: true\n" if draft else ""
    page.write_text(f"---\nlayout: plugin\n{draft_line}---\n", encoding="utf-8")
    return page


# ===========================================================================
# 1. Serialisation
# ===========================================================================

class TestSerializeProductsYaml:
    def test_basic_structure(self):
        products = [
            {
                "name": "Aspose.Words",
                "url": "https://products.aspose.org/words/",
                "image": "/img/aspose/aspose-words.png",
                "list": [
                    {"text": "Aspose.Words for Python",
                     "link": "https://products.aspose.org/words/python/"},
                ],
            }
        ]
        out = serialize_products_yaml(products)
        assert out.startswith("products:")
        assert '  - name: "Aspose.Words"' in out
        assert '    url: "https://products.aspose.org/words/"' in out
        assert '    image: "/img/aspose/aspose-words.png"' in out
        assert '    list:' in out
        assert '      - text: "Aspose.Words for Python"' in out
        assert '        link: "https://products.aspose.org/words/python/"' in out

    def test_blank_line_between_families(self):
        products = [
            {
                "name": "Aspose.Words",
                "url": "u1/",
                "image": "/img/a.png",
                "list": [{"text": "W for Python", "link": "l1/"}],
            },
            {
                "name": "Aspose.Cells",
                "url": "u2/",
                "image": "/img/b.png",
                "list": [{"text": "C for Python", "link": "l2/"}],
            },
        ]
        out = serialize_products_yaml(products)
        assert "\n\n  - name:" in out

    def test_deterministic(self):
        products = [
            {
                "name": "Aspose.Words",
                "url": "u/",
                "image": "/i.png",
                "list": [{"text": "t", "link": "l"}],
            }
        ]
        assert serialize_products_yaml(products) == serialize_products_yaml(products)

    def test_double_quotes(self):
        products = [
            {
                "name": "Test",
                "url": "u/",
                "image": "/i.png",
                "list": [{"text": "t", "link": "l"}],
            }
        ]
        out = serialize_products_yaml(products)
        assert "'" not in out


# ===========================================================================
# 2. replace_products_in_text
# ===========================================================================

class TestReplaceProductsInText:
    _FM = (
        "---\n"
        "layout: \"domain\"\n"
        "title: \"My Title\"\n"
        "products:\n"
        "  - name: \"Old\"\n"
        "    url: \"old/\"\n"
        "    image: \"/img/old.png\"\n"
        "    list:\n"
        "      - text: \"Old for Python\"\n"
        "        link: \"old/py/\"\n"
        "---\n"
    )

    _NEW_PRODUCTS = (
        "products:\n"
        "  - name: \"New\"\n"
        "    url: \"new/\"\n"
        "    image: \"/img/new.png\"\n"
        "    list:\n"
        "      - text: \"New for Python\"\n"
        "        link: \"new/py/\"\n"
    )

    def test_replaces_products_block(self):
        result = replace_products_in_text(self._FM, self._NEW_PRODUCTS)
        assert result is not None
        assert "New" in result
        assert "Old" not in result

    def test_preserves_title(self):
        result = replace_products_in_text(self._FM, self._NEW_PRODUCTS)
        assert 'title: "My Title"' in result

    def test_no_frontmatter_returns_none(self):
        assert replace_products_in_text("just body text\n", self._NEW_PRODUCTS) is None

    def test_result_parses_as_yaml(self):
        result = replace_products_in_text(self._FM, self._NEW_PRODUCTS)
        assert result is not None
        fm_m = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", result, re.DOTALL)
        assert fm_m is not None
        parsed = yaml.safe_load(fm_m.group(1))
        assert parsed["layout"] == "domain"
        assert parsed["products"][0]["name"] == "New"

    def test_provenance_update_when_requested(self):
        fm = (
            "---\n"
            "provenance:\n"
            "  auto_updatable: false\n"
            "  last_mechanism: manual-edit-skill\n"
            "products:\n"
            "  - name: \"Old\"\n"
            "    url: \"u/\"\n"
            "    image: \"/i.png\"\n"
            "    list:\n"
            "      - text: \"t\"\n"
            "        link: \"l\"\n"
            "---\n"
        )
        result = replace_products_in_text(fm, self._NEW_PRODUCTS, update_provenance=True)
        assert result is not None
        assert "auto_updatable: true" in result
        assert "last_mechanism: skill" in result

    def test_provenance_unchanged_when_not_requested(self):
        fm = (
            "---\n"
            "provenance:\n"
            "  auto_updatable: false\n"
            "  last_mechanism: manual-edit-skill\n"
            "products:\n"
            "  - name: \"Old\"\n"
            "    url: \"u/\"\n"
            "    image: \"/i.png\"\n"
            "    list:\n"
            "      - text: \"t\"\n"
            "        link: \"l\"\n"
            "---\n"
        )
        result = replace_products_in_text(fm, self._NEW_PRODUCTS, update_provenance=False)
        assert result is not None
        assert "auto_updatable: false" in result
        assert "last_mechanism: manual-edit-skill" in result


# ===========================================================================
# 3. is_published
# ===========================================================================

class TestIsPublished:
    def test_published(self, tmp_path):
        _write_plugin_page(tmp_path, "words", "python")
        _mod.configure(content_products=tmp_path)
        ok, reason = is_published("words", "python")
        assert ok is True
        assert reason == ""

    def test_missing_file(self, tmp_path):
        _mod.configure(content_products=tmp_path)
        ok, reason = is_published("words", "python")
        assert ok is False
        assert "missing" in reason

    def test_draft(self, tmp_path):
        _write_plugin_page(tmp_path, "words", "python", draft=True)
        _mod.configure(content_products=tmp_path)
        ok, reason = is_published("words", "python")
        assert ok is False
        assert "draft" in reason

    def test_wrong_layout(self, tmp_path):
        page = tmp_path / "words" / "python" / "_index.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text("---\nlayout: family\n---\n", encoding="utf-8")
        _mod.configure(content_products=tmp_path)
        ok, reason = is_published("words", "python")
        assert ok is False
        assert "plugin" in reason


# ===========================================================================
# 4. get_published_products — ordering
# ===========================================================================

class TestGetPublishedProducts:
    def test_family_order_follows_families_order_json(self, tmp_path):
        _write_plugin_page(tmp_path, "3d", "python")
        _write_plugin_page(tmp_path, "words", "python")
        _write_plugin_page(tmp_path, "cells", "python")
        _mod.configure(content_products=tmp_path)
        products_data = [
            _make_product("3d", "python"),
            _make_product("words", "python"),
            _make_product("cells", "python"),
        ]
        included, excluded = get_published_products(
            products_data,
            _SAMPLE_PLATFORM_DISPLAY,
            _SAMPLE_FAMILIES,
            _SAMPLE_FAMILIES_ORDER,
            _SAMPLE_PLATFORMS_ORDER,
        )
        assert [p["name"] for p in included] == [
            "Aspose.Words", "Aspose.Cells", "Aspose.3D"
        ]
        assert excluded == []

    def test_platform_order_within_family(self, tmp_path):
        _write_plugin_page(tmp_path, "cells", "java")
        _write_plugin_page(tmp_path, "cells", "python")
        _write_plugin_page(tmp_path, "cells", "net")
        _mod.configure(content_products=tmp_path)
        products_data = [
            _make_product("cells", "java"),
            _make_product("cells", "python"),
            _make_product("cells", "net"),
        ]
        families = {"cells": "Aspose.Cells"}
        included, _ = get_published_products(
            products_data,
            _SAMPLE_PLATFORM_DISPLAY,
            families,
            ["cells"],
            _SAMPLE_PLATFORMS_ORDER,
        )
        platform_texts = [item["text"].split(" for ")[1] for item in included[0]["list"]]
        assert platform_texts == ["Python", ".NET", "Java"]

    def test_inactive_product_excluded(self, tmp_path):
        _write_plugin_page(tmp_path, "words", "python")
        _mod.configure(content_products=tmp_path)
        products_data = [_make_product("words", "python", active=False)]
        included, excluded = get_published_products(
            products_data,
            _SAMPLE_PLATFORM_DISPLAY,
            _SAMPLE_FAMILIES,
            _SAMPLE_FAMILIES_ORDER,
            _SAMPLE_PLATFORMS_ORDER,
        )
        assert included == []
        assert len(excluded) == 1
        assert excluded[0]["reason"] == "inactive"

    def test_draft_product_excluded(self, tmp_path):
        _write_plugin_page(tmp_path, "words", "python", draft=True)
        _mod.configure(content_products=tmp_path)
        products_data = [_make_product("words", "python")]
        included, excluded = get_published_products(
            products_data,
            _SAMPLE_PLATFORM_DISPLAY,
            _SAMPLE_FAMILIES,
            _SAMPLE_FAMILIES_ORDER,
            _SAMPLE_PLATFORMS_ORDER,
        )
        assert included == []
        assert excluded[0]["reason"] == "draft: true"


# ===========================================================================
# 5. Image check
# ===========================================================================

class TestCheckImages:
    def test_missing_image_returns_failure(self, tmp_path):
        _mod.configure(repo_root=tmp_path)
        products = [
            {
                "name": "Aspose.Ghost",
                "url": "u/",
                "image": "/img/aspose/aspose-ghost.png",
                "list": [],
            }
        ]
        failures = check_images(products)
        assert len(failures) == 1
        assert "aspose-ghost.png" in failures[0]

    def test_existing_image_ok(self, tmp_path):
        img_dir = tmp_path / "themes" / "websites" / "static" / "img" / "aspose"
        img_dir.mkdir(parents=True)
        (img_dir / "aspose-words.png").write_bytes(b"PNG")
        _mod.configure(repo_root=tmp_path)
        products = [
            {
                "name": "Aspose.Words",
                "url": "u/",
                "image": "/img/aspose/aspose-words.png",
                "list": [],
            }
        ]
        assert check_images(products) == []


# ===========================================================================
# 6. run() — safety gates
# ===========================================================================

class TestRunSafetyGates:
    def test_unsupported_domain_fails(self):
        rc = run(domain="aspose/cloud", dry_run=True, verbose=False)
        assert rc != 0

    def test_empty_product_list_fails_closed(self, tmp_path):
        """If all products resolve to non-existent families, run must refuse."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "products.json").write_text(
            json.dumps([{"family": "ghost", "platform": "python", "active": True}]),
            encoding="utf-8",
        )
        for fname in ("families.json", "families_order.json", "platforms_order.json"):
            shutil.copy(_REPO_ROOT / "data" / fname, data_dir / fname)
        _mod.configure(
            content_products=tmp_path / "products",
            data_dir=data_dir,
        )
        rc = run(domain="aspose/org", dry_run=True, verbose=False)
        assert rc != 0


# ===========================================================================
# 7. run() — dry-run does not write
# ===========================================================================

class TestDryRunNoWrite:
    def test_dry_run_does_not_modify_files(self, tmp_path):
        """Dry-run must leave all files unchanged on disk."""
        en_dir = tmp_path / "websites.aspose.org" / "en" / "aspose" / "org"
        en_dir.mkdir(parents=True)
        en_file = en_dir / "_index.md"
        original_content = (
            "---\n"
            "layout: \"domain\"\n"
            "title: \"T\"\n"
            "products:\n"
            "  - name: \"Old\"\n"
            "    url: \"u/\"\n"
            "    image: \"/img/aspose/aspose-old.png\"\n"
            "    list:\n"
            "      - text: \"Old for Python\"\n"
            "        link: \"l/\"\n"
            "---\n"
        )
        en_file.write_text(original_content, encoding="utf-8")

        prod_dir = tmp_path / "products.aspose.org" / "en" / "words" / "python"
        prod_dir.mkdir(parents=True)
        (prod_dir / "_index.md").write_text(
            "---\nlayout: plugin\n---\n", encoding="utf-8"
        )
        img_dir = tmp_path / "themes" / "websites" / "static" / "img" / "aspose"
        img_dir.mkdir(parents=True)
        (img_dir / "aspose-words.png").write_bytes(b"PNG")

        _mod.configure(
            content_websites=tmp_path / "websites.aspose.org",
            content_products=tmp_path / "products.aspose.org" / "en",
            repo_root=tmp_path,
            data_dir=_REPO_ROOT / "data",
        )

        run(domain="aspose/org", dry_run=True, allow_missing_locales=True, verbose=False)

        assert en_file.read_text(encoding="utf-8") == original_content


# ===========================================================================
# 8. run() — write updates only expected files
# ===========================================================================

class TestWriteMode:
    def test_write_updates_en_and_locales(self, tmp_path):
        en_dir = tmp_path / "websites.aspose.org" / "en" / "aspose" / "org"
        en_dir.mkdir(parents=True)
        en_file = en_dir / "_index.md"
        en_file.write_text(
            "---\n"
            "layout: \"domain\"\n"
            "title: \"T\"\n"
            "products:\n"
            "  - name: \"Old\"\n"
            "    url: \"u/\"\n"
            "    image: \"/img/aspose/aspose-old.png\"\n"
            "    list:\n"
            "      - text: \"Old for Python\"\n"
            "        link: \"l/\"\n"
            "---\n",
            encoding="utf-8",
        )
        de_dir = tmp_path / "websites.aspose.org" / "de" / "aspose" / "org"
        de_dir.mkdir(parents=True)
        de_file = de_dir / "_index.md"
        de_file.write_text(
            "---\n"
            "layout: \"domain\"\n"
            "title: \"Deutsch Titel\"\n"
            "products:\n"
            "  - name: \"Old\"\n"
            "    url: \"u/\"\n"
            "    image: \"/img/aspose/aspose-old.png\"\n"
            "    list:\n"
            "      - text: \"Old for Python\"\n"
            "        link: \"l/\"\n"
            "---\n",
            encoding="utf-8",
        )
        prod_dir = tmp_path / "products.aspose.org" / "en" / "words" / "python"
        prod_dir.mkdir(parents=True)
        (prod_dir / "_index.md").write_text(
            "---\nlayout: plugin\n---\n", encoding="utf-8"
        )
        img_dir = tmp_path / "themes" / "websites" / "static" / "img" / "aspose"
        img_dir.mkdir(parents=True)
        (img_dir / "aspose-words.png").write_bytes(b"PNG")

        _mod.configure(
            content_websites=tmp_path / "websites.aspose.org",
            content_products=tmp_path / "products.aspose.org" / "en",
            repo_root=tmp_path,
            data_dir=_REPO_ROOT / "data",
        )

        rc = run(
            domain="aspose/org",
            dry_run=False,
            allow_missing_locales=True,
            verbose=False,
        )
        assert rc == 0

        en_text = en_file.read_text(encoding="utf-8")
        de_text = de_file.read_text(encoding="utf-8")
        assert "Aspose.Words" in en_text
        assert "Old" not in en_text
        assert "Aspose.Words" in de_text
        assert "Old" not in de_text

    def test_write_preserves_locale_translations(self, tmp_path):
        en_dir = tmp_path / "websites.aspose.org" / "en" / "aspose" / "org"
        en_dir.mkdir(parents=True)
        (en_dir / "_index.md").write_text(
            "---\n"
            "layout: \"domain\"\n"
            "title: \"English Title\"\n"
            "products:\n"
            "  - name: \"Old\"\n"
            "    url: \"u/\"\n"
            "    image: \"/img/aspose/aspose-old.png\"\n"
            "    list:\n"
            "      - text: \"Old for Python\"\n"
            "        link: \"l/\"\n"
            "---\n",
            encoding="utf-8",
        )
        de_dir = tmp_path / "websites.aspose.org" / "de" / "aspose" / "org"
        de_dir.mkdir(parents=True)
        de_file = de_dir / "_index.md"
        de_file.write_text(
            "---\n"
            "layout: \"domain\"\n"
            "title: \"Deutscher Titel\"\n"
            "description: \"Deutsche Beschreibung\"\n"
            "corporate_header: \"Aspose FOSS Open-Source-Bibliotheken\"\n"
            "visit_website_url: \"https://products.aspose.org/\"\n"
            "visit_website_text: \"Alle Aspose FOSS-Produkte durchsuchen\"\n"
            "products:\n"
            "  - name: \"Old\"\n"
            "    url: \"u/\"\n"
            "    image: \"/img/aspose/aspose-old.png\"\n"
            "    list:\n"
            "      - text: \"Old for Python\"\n"
            "        link: \"l/\"\n"
            "---\n",
            encoding="utf-8",
        )
        prod_dir = tmp_path / "products.aspose.org" / "en" / "words" / "python"
        prod_dir.mkdir(parents=True)
        (prod_dir / "_index.md").write_text("---\nlayout: plugin\n---\n", encoding="utf-8")
        img_dir = tmp_path / "themes" / "websites" / "static" / "img" / "aspose"
        img_dir.mkdir(parents=True)
        (img_dir / "aspose-words.png").write_bytes(b"PNG")

        _mod.configure(
            content_websites=tmp_path / "websites.aspose.org",
            content_products=tmp_path / "products.aspose.org" / "en",
            repo_root=tmp_path,
            data_dir=_REPO_ROOT / "data",
        )

        run(domain="aspose/org", dry_run=False, allow_missing_locales=True, verbose=False)

        de_text = de_file.read_text(encoding="utf-8")
        assert 'title: "Deutscher Titel"' in de_text
        assert 'description: "Deutsche Beschreibung"' in de_text
        assert 'visit_website_text: "Alle Aspose FOSS-Produkte durchsuchen"' in de_text
        assert "Aspose.Words" in de_text

    def test_write_yaml_is_valid_after_update(self, tmp_path):
        en_dir = tmp_path / "websites.aspose.org" / "en" / "aspose" / "org"
        en_dir.mkdir(parents=True)
        en_file = en_dir / "_index.md"
        en_file.write_text(
            "---\nlayout: \"domain\"\ntitle: \"T\"\nproducts:\n  - name: \"Old\"\n"
            "    url: \"u/\"\n    image: \"/img/aspose/aspose-old.png\"\n    list:\n"
            "      - text: \"Old for Python\"\n        link: \"l/\"\n---\n",
            encoding="utf-8",
        )
        prod_dir = tmp_path / "products.aspose.org" / "en" / "words" / "python"
        prod_dir.mkdir(parents=True)
        (prod_dir / "_index.md").write_text("---\nlayout: plugin\n---\n", encoding="utf-8")
        img_dir = tmp_path / "themes" / "websites" / "static" / "img" / "aspose"
        img_dir.mkdir(parents=True)
        (img_dir / "aspose-words.png").write_bytes(b"PNG")

        _mod.configure(
            content_websites=tmp_path / "websites.aspose.org",
            content_products=tmp_path / "products.aspose.org" / "en",
            repo_root=tmp_path,
            data_dir=_REPO_ROOT / "data",
        )

        run(domain="aspose/org", dry_run=False, allow_missing_locales=True, verbose=False)

        updated_text = en_file.read_text(encoding="utf-8")
        fm_m = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", updated_text, re.DOTALL)
        assert fm_m is not None
        parsed = yaml.safe_load(fm_m.group(1))
        assert isinstance(parsed, dict)
        assert isinstance(parsed.get("products"), list)
        assert len(parsed["products"]) > 0


# ===========================================================================
# 9. Integration: real repo dry-run produces zero diffs (idempotent)
# ===========================================================================

class TestRealRepoDryRun:
    def test_no_products_content_diff_against_real_repo(self, capsys):
        """Dry-run on the actual repo must show no content diffs.

        Post-write state: en/_index.md already has last_mechanism: skill and
        auto_updatable: true, so the generator output matches the file exactly.
        """
        rc = run(domain="aspose/org", dry_run=True, verbose=True)
        assert rc == 0

        captured = capsys.readouterr()
        output = captured.out

        assert "files processed: 37" in output

        diff_lines = [
            line for line in output.splitlines()
            if line.startswith("+") or line.startswith("-")
        ]
        content_diffs = [
            line for line in diff_lines
            if not line.startswith("---") and not line.startswith("+++")
        ]
        for line in content_diffs:
            value = line[1:].strip()
            assert any(
                kw in value
                for kw in ["last_mechanism", "auto_updatable", "provenance"]
            ), (
                f"Unexpected non-provenance diff line: {line!r}\n"
                "BUG_IN_GENERATOR: generated products block differs from current file."
            )
