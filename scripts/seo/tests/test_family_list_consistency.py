"""SEO-SCHEMA-A-FAMILY-LIST-RECONCILE: family-list drift regression tests.

Before this fix, three scripts independently hand-maintained the list of
Schema A product families and had silently drifted apart (Finding #32):
get_keywords.py declared 18 names, review_keywords.py declared 13, and
validate.py's _SCHEMA_A_FAMILIES dict declared 14 (a dead dict that added
zero information beyond filename.replace(".json", "")). None of the three
matched data/family_descriptions.json, the 25-family registry already
treated as authoritative elsewhere in this repo (4 Hugo home templates).

This test asserts structural derivation, not a fixed enumerated count, so it
does not need updating every time a new family launches -- it fails loudly
only if the three call sites stop agreeing with each other or with the
registry.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[2]
_PIPELINE = _SCRIPTS / "pipeline"
_REPO_ROOT = _SCRIPTS.parents[0]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
if str(_PIPELINE) not in sys.path:
    sys.path.insert(0, str(_PIPELINE))

from seo.pipeline.schema import canonical_families  # noqa: E402
import seo.get_keywords as get_keywords  # noqa: E402
import seo.review_keywords as review_keywords  # noqa: E402


def test_canonical_families_matches_real_registry():
    expected = sorted(
        json.loads((_REPO_ROOT / "data" / "family_descriptions.json").read_text(encoding="utf-8")).keys()
    )
    assert canonical_families() == expected
    assert len(expected) >= 20  # sanity: this is the real, populated registry


def test_get_keywords_default_families_matches_canonical():
    assert get_keywords.DEFAULT_FAMILIES == canonical_families()


def test_review_keywords_default_families_matches_canonical():
    assert review_keywords.DEFAULT_FAMILIES == canonical_families()


def test_all_three_call_sites_agree():
    """The exact regression this task exists to close: no more drift."""
    assert get_keywords.DEFAULT_FAMILIES == review_keywords.DEFAULT_FAMILIES


def test_canonical_families_includes_previously_missing_font():
    # Finding #35: "font" wasn't in get_keywords.py's list despite having
    # full launched site content -- confirm it's covered now.
    assert "font" in canonical_families()


def test_canonical_families_returns_sorted_list():
    families = canonical_families()
    assert families == sorted(families)


def test_canonical_families_degrades_gracefully_on_missing_registry(tmp_path, monkeypatch):
    import seo.pipeline.schema as schema_mod

    monkeypatch.setattr(schema_mod, "_FAMILY_DESCRIPTIONS_PATH", tmp_path / "does_not_exist.json")
    assert schema_mod.canonical_families() == []


def test_get_keywords_falls_back_to_legacy_list_if_registry_unreadable(tmp_path, monkeypatch):
    import importlib
    import seo.pipeline.schema as schema_mod

    monkeypatch.setattr(schema_mod, "_FAMILY_DESCRIPTIONS_PATH", tmp_path / "does_not_exist.json")
    try:
        reloaded = importlib.reload(get_keywords)
        assert reloaded.DEFAULT_FAMILIES == reloaded._FALLBACK_FAMILIES
        assert "pdf" in reloaded.DEFAULT_FAMILIES
    finally:
        importlib.reload(schema_mod)
        importlib.reload(get_keywords)
