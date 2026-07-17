"""
Tests for scripts/pipeline/lib/forbidden_claims_check.py (RPR-E-02 / RPR-F-04).

The centerpiece is a faithful reproduction of the real 3d/net "3MF" fabrication
(plan §2.4): the knowledge model marks Microsoft3MFFormat.* as forbidden (methods
throw NotImplementedException), yet content claimed 3MF support across 13 files
and nothing re-scanned it. scan() must flag a candidate that makes that claim.
"""

import json
from pathlib import Path

from lib.forbidden_claims_check import (
    extract_symbols,
    load_forbidden_claims,
    newly_introduced,
    scan,
)

# The real 3d/net forbidden entries (verbatim shape from merged/index.json).
_3MF_FORBIDDEN = [
    "supports Microsoft3MFFormat.IsBuildable",
    "supports Microsoft3MFFormat.GetTransformForBuild",
    "supports Microsoft3MFFormat.SetBuildable",
]


# ── extract_symbols ──────────────────────────────────────────────────────

def test_extract_fully_qualified_and_owning_class():
    fq, classes = extract_symbols("supports Microsoft3MFFormat.IsBuildable")
    assert "Microsoft3MFFormat.IsBuildable" in fq
    assert "Microsoft3MFFormat" in classes


def test_extract_bare_class_when_no_dotted_symbol():
    fq, classes = extract_symbols("supports DocumentCollection")
    assert fq == set()
    assert "DocumentCollection" in classes


# ── scan: the 3MF regression ─────────────────────────────────────────────

def test_scan_detects_known_violation_fully_qualified():
    text = "You can call `Microsoft3MFFormat.IsBuildable` to check buildability."
    v = scan(text, _3MF_FORBIDDEN)
    assert len(v) >= 1
    assert any(x["match_type"] == "fully_qualified" for x in v)
    assert any("Microsoft3MFFormat.IsBuildable" == x["matched_symbol"] for x in v)


def test_3mf_regression_fixture_blocked():
    """The 13-file 3MF case: a page affirmatively claiming 3MF/Microsoft3MFFormat
    support must be flagged."""
    page_body = (
        "## Supported Formats\n\n"
        "Aspose.3D FOSS for .NET supports Microsoft3MFFormat for reading and writing "
        "3MF scenes.\n"
    )
    v = scan(page_body, _3MF_FORBIDDEN)
    assert v, "expected the 3MF support claim to be flagged as a forbidden-claim violation"


def test_scan_class_match_requires_capability_language():
    """A bare owning-class mention with NO capability verb is NOT flagged
    (avoids WARN-fatigue on incidental references)."""
    text = "The Microsoft3MFFormat enum value exists in the namespace listing.\n"
    v = scan(text, ["supports Microsoft3MFFormat"])
    assert v == []


def test_scan_class_match_with_capability_language_flagged():
    text = "Aspose.3D supports Microsoft3MFFormat export.\n"
    v = scan(text, ["supports Microsoft3MFFormat"])
    assert len(v) == 1
    assert v[0]["match_type"] == "class_with_capability_language"


def test_scan_negation_not_flagged():
    """An explicitly-negative statement must not be flagged as a support claim."""
    text = "Note: Microsoft3MFFormat is NOT supported in this FOSS build.\n"
    v = scan(text, ["supports Microsoft3MFFormat"])
    assert v == []


def test_scan_clean_text_no_violations():
    text = "This page discusses PDF conversion using Document.Save.\n"
    v = scan(text, _3MF_FORBIDDEN)
    assert v == []


def test_scan_empty_inputs():
    assert scan("", _3MF_FORBIDDEN) == []
    assert scan("some text", []) == []


# ── newly_introduced ─────────────────────────────────────────────────────

def test_newly_introduced_only_flags_added_violations():
    old = "Old prose with no forbidden claims.\n"
    new = "Now you can use `Microsoft3MFFormat.IsBuildable` here.\n"
    v = newly_introduced(old, new, ["supports Microsoft3MFFormat.IsBuildable"])
    assert len(v) == 1
    assert v[0]["matched_symbol"] == "Microsoft3MFFormat.IsBuildable"


def test_newly_introduced_flags_every_violated_claim():
    """A single line violating 3 forbidden claims (all sharing the owning class)
    reports one violation per forbidden claim — useful, not a bug."""
    old = "Clean prose.\n"
    new = "Now you can use `Microsoft3MFFormat.IsBuildable` here.\n"
    v = newly_introduced(old, new, _3MF_FORBIDDEN)
    assert len(v) == 3


def test_newly_introduced_ignores_preexisting_violation():
    """A forbidden claim already present in old_text is NOT re-flagged when the
    edit leaves it in place — that is a separate remediation concern, not a
    reason to abort an unrelated edit to the same page."""
    old = "Legacy line: Microsoft3MFFormat.IsBuildable returns true.\n"
    new = old + "A newly added, unrelated, clean paragraph.\n"
    v = newly_introduced(old, new, _3MF_FORBIDDEN)
    assert v == []


# ── load_forbidden_claims ────────────────────────────────────────────────

def test_load_forbidden_claims_from_index(tmp_path):
    merged = tmp_path / "knowledge" / "3d" / "net" / "merged"
    merged.mkdir(parents=True)
    (merged / "index.json").write_text(
        json.dumps({"forbidden_claims": _3MF_FORBIDDEN}), encoding="utf-8"
    )
    loaded = load_forbidden_claims("3d", "net", repo_root=tmp_path)
    assert loaded == _3MF_FORBIDDEN


def test_load_forbidden_claims_absent_returns_empty(tmp_path):
    assert load_forbidden_claims("no", "product", repo_root=tmp_path) == []
