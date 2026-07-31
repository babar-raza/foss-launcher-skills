"""SEO-000: schema.py structural classification tests.

Regression coverage for the schema-drift bug this module fixes: validate.py
and map_url.py each used to hardcode their own incomplete Schema-B filename
allowlist (5 and 4 entries respectively, out of 7 real Schema B files),
which silently dropped or misclassified blog.aspose.org.json,
kb.aspose.org.json, and (inconsistently) docs.aspose.org.json.

This test asserts against the real keywords/*.json files on disk (not
synthetic fixtures) so it fails loudly if a future edit reintroduces a
partial filename list or a real file's shape stops matching either schema.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Ensure scripts/seo and scripts/pipeline are on sys.path
_SCRIPTS = Path(__file__).resolve().parents[2]
_PIPELINE = _SCRIPTS / "pipeline"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
if str(_PIPELINE) not in sys.path:
    sys.path.insert(0, str(_PIPELINE))

from seo.pipeline.schema import (  # noqa: E402
    SCHEMA_A,
    SCHEMA_B,
    SCHEMA_UNKNOWN,
    classify_entry_shape,
    classify_keyword_file,
    classify_keyword_path,
)
import seo.pipeline.validate as validate  # noqa: E402
import seo.pipeline.map_url as map_url  # noqa: E402

_REPO_ROOT = _SCRIPTS.parents[0]
_KEYWORDS_DIR = _REPO_ROOT / "keywords"

_EXPECTED_SCHEMA_B = {
    "blog.aspose.org.json",
    "docs.aspose.org.json",
    "kb.aspose.org.json",
    "products.aspose.org.json",
    "reference.aspose.org.json",
    "websites.aspose.org.json",
    "www.aspose.org.json",
}

_EXPECTED_SCHEMA_A = {
    "3d.json",
    "barcode.json",
    "cad.json",
    "cells.json",
    "email.json",
    "font.json",
    "home.json",
    "html.json",
    "imaging.json",
    "note.json",
    "ocr.json",
    "page.json",
    "pdf.json",
    "psd.json",
    "slides.json",
    "tasks.json",
    "tex.json",
    "words.json",
    "zip.json",
}

# SEO-SCHEMA-A-QUARANTINE-STALE-ENTRIES (2026-07-29) quarantined 7 files'
# entries (100% drifted_title_mismatch, confirmed by audit_schema_a.py) to
# keywords/_stale/{family}.json, leaving the live files empty [] pending
# SEO-SCHEMA-A-BOOTSTRAP-REGENERATION. SEO-SCHEMA-A-BOOTSTRAP-REGENERATION
# (2026-07-30/08-01) has since fully repopulated all 7, plus the 5 families
# named in Finding #35 that had no Schema A file at all before (3d, email,
# font, note, slides) -- all 12 target families are now real, regenerated
# content. Kept as a historical record of which files were quarantined, not
# because that state is still true.
_FORMERLY_QUARANTINED_NOW_REGENERATED = {
    "barcode.json",
    "cells.json",
    "html.json",
    "page.json",
    "pdf.json",
    "tex.json",
    "words.json",
}
# Every Schema A file has real content now: the 7 formerly-quarantined files
# were regenerated, the 5 Finding-#35 files were created fresh, and the 6
# stub-tier prospective files (cad, imaging, ocr, psd, tasks, zip) plus
# home.json were never touched by either the quarantine or the regeneration
# -- they retain their original prospective content throughout.
_EXPECTED_SCHEMA_A_WITH_CONTENT = _EXPECTED_SCHEMA_A


def _real_keyword_files() -> list[Path]:
    files = sorted(_KEYWORDS_DIR.glob("*.json"))
    assert files, f"no keywords/*.json files found under {_KEYWORDS_DIR}"
    return files


class TestEntryShapeClassification:
    def test_schema_b_entry_with_queries(self):
        entry = {"url": "https://docs.aspose.org/words/", "lang": "en",
                  "lastUpdated": "2026-07-26", "queries": [{"query": "x"}]}
        assert classify_entry_shape(entry) == SCHEMA_B

    def test_schema_b_entry_with_agg_and_keywords_list(self):
        # Schema B entries also carry a "keywords" dedup list alongside
        # "queries"/"agg" -- this must NOT be misread as Schema A.
        entry = {"url": "https://docs.aspose.org/", "lang": "en",
                  "lastUpdated": "2026-07-26", "keywords": ["a", "b"],
                  "agg": {"total_clicks": 1}}
        assert classify_entry_shape(entry) == SCHEMA_B

    def test_schema_a_entry(self):
        entry = {"pageTitle": "Aspose.PDF Plugins for .NET", "keywords": ["a", "b"]}
        assert classify_entry_shape(entry) == SCHEMA_A

    def test_malformed_entry_is_unknown(self):
        assert classify_entry_shape({"tags": ["x"], "pluginDescriptions": {}}) == SCHEMA_UNKNOWN
        assert classify_entry_shape("not a dict") == SCHEMA_UNKNOWN


class TestFileClassification:
    def test_empty_payload_is_unknown(self):
        assert classify_keyword_file([]) == SCHEMA_UNKNOWN

    def test_non_list_payload_is_unknown(self):
        assert classify_keyword_file({"not": "a list"}) == SCHEMA_UNKNOWN

    def test_majority_vote_survives_one_contaminated_entry(self):
        # Reproduces the 2026-03-27 contamination incident shape: a Schema A
        # file with one stray Schema-B-shaped entry must still classify A.
        payload = [
            {"pageTitle": "Title 1", "keywords": ["a"]},
            {"pageTitle": "Title 2", "keywords": ["b"]},
            {"url": "https://x/", "lang": "en", "lastUpdated": "2026-01-01", "queries": []},
        ]
        assert classify_keyword_file(payload) == SCHEMA_A

    @pytest.mark.parametrize("filename", sorted(_EXPECTED_SCHEMA_B))
    def test_real_schema_b_files_classify_as_b(self, filename):
        path = _KEYWORDS_DIR / filename
        assert path.exists(), f"expected real file missing: {path}"
        assert classify_keyword_path(path) == SCHEMA_B

    @pytest.mark.parametrize("filename", sorted(_EXPECTED_SCHEMA_A_WITH_CONTENT))
    def test_real_schema_a_files_classify_as_a(self, filename):
        path = _KEYWORDS_DIR / filename
        assert path.exists(), f"expected real file missing: {path}"
        assert classify_keyword_path(path) == SCHEMA_A

    @pytest.mark.parametrize("filename", sorted(_FORMERLY_QUARANTINED_NOW_REGENERATED))
    def test_formerly_quarantined_files_are_repopulated_and_classify_as_a(self, filename):
        """SEO-SCHEMA-A-BOOTSTRAP-REGENERATION closed the loop the quarantine
        opened: these 7 files were emptied pending regeneration, and are now
        real, non-empty Schema A content again."""
        path = _KEYWORDS_DIR / filename
        assert path.exists(), f"expected real file missing: {path}"
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload != [], (
            f"{filename} is empty -- SEO-SCHEMA-A-BOOTSTRAP-REGENERATION was "
            "expected to have repopulated it by now"
        )
        assert classify_keyword_path(path) == SCHEMA_A

    def test_all_26_real_files_accounted_for(self):
        real_files = {p.name for p in _real_keyword_files()}
        assert real_files == _EXPECTED_SCHEMA_B | _EXPECTED_SCHEMA_A, (
            "keywords/ directory contents changed -- update this test's expected "
            "sets (and re-check validate.py/map_url.py behavior) rather than "
            "silently letting a new file go unclassified"
        )


class TestConsumerAgreement:
    """validate.py and map_url.py must agree on every real file, since both
    now delegate to the same schema.classify_keyword_file()."""

    def test_validate_and_map_url_agree_on_schema_b_membership(self, tmp_path, monkeypatch):
        monkeypatch.setattr(validate, "REPORTS_DIR", tmp_path)
        result = validate.run_validation(keywords_dir=_KEYWORDS_DIR)
        validate_schema_b_files = {
            s["filename"] for s in result["_file_summaries"] if s.get("schema") == "B"
        }
        assert validate_schema_b_files == _EXPECTED_SCHEMA_B

        url_map_result = map_url.build_url_map(keywords_dir=_KEYWORDS_DIR)
        map_url_schema_b_files = {
            e["source_file"] for e in url_map_result["url_map"]
        }
        assert map_url_schema_b_files == _EXPECTED_SCHEMA_B

    def test_map_url_covers_all_7_schema_b_files_not_just_4(self):
        # Direct regression pin for the specific historical bug: map_url.py's
        # old hardcoded set only had 4 names (products, reference, websites,
        # www), missing docs, blog, and kb entirely.
        url_map_result = map_url.build_url_map(keywords_dir=_KEYWORDS_DIR)
        source_files = {e["source_file"] for e in url_map_result["url_map"]}
        assert "docs.aspose.org.json" in source_files
        assert "blog.aspose.org.json" in source_files
        assert "kb.aspose.org.json" in source_files
