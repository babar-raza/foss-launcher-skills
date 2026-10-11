"""SEO-SCHEMA-A-DUAL-FIELD-GENERATION (Finding #57 Section J): validate.py's
mechanical, no-LLM structural check for the new optional title_ready_variants
field. Real naturalness/grounding validation is Contract D's job (SEO-
METADATA-NATURALNESS-EVALUATOR, not yet built) -- this only proves the cheap,
deterministic structural gate: keyed to a real keyword, non-empty string,
within the word limit; malformed data is dropped and flagged, never fatal to
the entry (keywords itself already validated fine by that point).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[2]
_PIPELINE = _SCRIPTS / "pipeline"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
if str(_PIPELINE) not in sys.path:
    sys.path.insert(0, str(_PIPELINE))

import seo.pipeline.validate as validate  # noqa: E402


def _write_family_file(tmp_path, family, entries):
    keywords_dir = tmp_path / "keywords"
    keywords_dir.mkdir(exist_ok=True)
    (keywords_dir / f"{family}.json").write_text(json.dumps(entries), encoding="utf-8")
    return keywords_dir


def test_valid_title_ready_variants_pass_through():
    issues = []
    variants = validate._validate_title_ready_variants(
        {"foo bar keyword": "Foo Bar Title"},
        ["foo bar keyword", "other keyword"],
        0,
        issues,
    )
    assert variants == {"foo bar keyword": "Foo Bar Title"}
    assert issues == []


def test_variant_keyed_to_unknown_keyword_is_dropped_and_flagged():
    issues = []
    variants = validate._validate_title_ready_variants(
        {"never appears": "Some Title"},
        ["real keyword"],
        3,
        issues,
    )
    assert variants == {}
    assert any("entry 3" in i and "never appears" in i for i in issues)


def test_variant_exceeding_word_limit_is_dropped_and_flagged():
    issues = []
    long_variant = "This Title Ready Variant Has Way Too Many Words"  # 8 words
    variants = validate._validate_title_ready_variants(
        {"kw": long_variant},
        ["kw"],
        0,
        issues,
    )
    assert variants == {}
    assert any("exceeds" in i for i in issues)


def test_non_string_variant_is_dropped_and_flagged():
    issues = []
    variants = validate._validate_title_ready_variants(
        {"kw": 12345},
        ["kw"],
        0,
        issues,
    )
    assert variants == {}
    assert any("must be a non-empty string" in i for i in issues)


def test_non_dict_title_ready_variants_is_rejected_wholesale():
    issues = []
    variants = validate._validate_title_ready_variants(
        ["not", "a", "dict"],
        ["kw"],
        0,
        issues,
    )
    assert variants == {}
    assert any("must be an object" in i for i in issues)


def test_missing_title_ready_variants_is_a_silent_noop():
    issues = []
    variants = validate._validate_title_ready_variants(None, ["kw"], 0, issues)
    assert variants == {}
    assert issues == []


def test_run_validation_keeps_clean_variants_and_drops_bad_ones(tmp_path):
    entries = [
        {
            "pageTitle": "Page One",
            "sourcePath": "content/x/one.md",
            "keywords": ["good keyword", "second keyword"],
            "title_ready_variants": {
                "good keyword": "Good Keyword Title",
                "not a real keyword": "Should Be Dropped",
            },
            "schema_version": 2,
        },
        {
            "pageTitle": "Page Two",
            "keywords": ["legacy keyword"],
        },
    ]
    keywords_dir = _write_family_file(tmp_path, "tex", entries)

    result = validate.run_validation(keywords_dir=keywords_dir)

    schema_a = {r["pageTitle"]: r for r in result["schema_a"]}
    assert schema_a["Page One"]["title_ready_variants"] == {"good keyword": "Good Keyword Title"}
    assert "title_ready_variants" not in schema_a["Page Two"]
    assert any(
        "not a real keyword" in issue
        for f in result["_file_summaries"]
        for issue in f.get("issues", [])
    )


def test_run_validation_entry_with_no_variants_field_is_unaffected(tmp_path):
    entries = [{"pageTitle": "Plain Page", "keywords": ["kw one", "kw two"]}]
    keywords_dir = _write_family_file(tmp_path, "tex", entries)

    result = validate.run_validation(keywords_dir=keywords_dir)

    assert len(result["schema_a"]) == 1
    assert "title_ready_variants" not in result["schema_a"][0]
