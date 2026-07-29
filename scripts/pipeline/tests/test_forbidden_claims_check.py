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


# ── HARDEN-FC-01: bare-class-in-inline-code false positive (2026-07-29) ─────
# Real incident: batch_reference.py --rebuild-all refused to regenerate 29
# 3d/java reference pages (SaveOptions/LoadOptions family) because their
# Methods tables have rows like:
#   | `getFileSystem()` -> `FileSystem` | Allow user to handle how to manage
#   the external dependencies during load/save. |
# "FileSystem" (a return-type annotation inside backticks) plus "Allow" (in
# the free-text description) tripped "supports FileSystem.readFile"/"supports
# FileSystem.writeFile" even though the description never mentions FileSystem
# in prose, and never mentions reading or writing at all.

_FILESYSTEM_FORBIDDEN = ["supports FileSystem.readFile", "supports FileSystem.writeFile"]


def test_bare_class_inside_inline_code_not_flagged():
    """The exact real-world trigger: a class name appearing ONLY as a
    backtick-quoted return-type annotation, on a line whose free-text
    description carries generic capability language but never mentions the
    class or the forbidden action, must not be flagged."""
    line = ("| `getFileSystem()` → `FileSystem` | Allow user to handle how to "
            "manage the external dependencies during load/save. |\n")
    v = scan(line, _FILESYSTEM_FORBIDDEN)
    assert v == []


def test_bare_class_in_prose_still_flagged():
    """The same owning class mentioned in actual free-text prose (not inside
    inline code), with capability language, is still flagged for every
    forbidden claim sharing that owning class -- tier 2 keeps working for
    real prose capability claims, only inline-code type annotations are
    excluded."""
    text = "This class supports FileSystem for direct file access.\n"
    v = scan(text, _FILESYSTEM_FORBIDDEN)
    assert len(v) == 2
    assert all(x["match_type"] == "class_with_capability_language" for x in v)


def test_properties_table_access_column_not_mistaken_for_capability_language():
    """Real second trigger: a Properties table row's Access column is
    literally the word "Read" (or "Read/Write") -- and "read"/"write" are
    themselves in the generic capability-verb list, so a naive whole-line
    scan flags EVERY properties row regardless of what the description says.
    The description here ("Gets the factory class for FileSystem.") mentions
    FileSystem as bare prose but makes no claim about reading or writing
    files at all -- must not be flagged."""
    line = ("| `fileSystemFactory` | `FileSystemFactory` | Read | Gets the "
            "factory class for FileSystem. |\n")
    v = scan(line, _FILESYSTEM_FORBIDDEN)
    assert v == []


def test_properties_table_description_prose_still_flagged():
    """The same table shape, but the Description column genuinely claims the
    forbidden action in prose -- still caught."""
    line = ("| `fileSystemFactory` | `FileSystemFactory` | Read | This class "
            "supports FileSystem for direct file access. |\n")
    v = scan(line, _FILESYSTEM_FORBIDDEN)
    assert len(v) == 2


def test_exact_member_reference_inside_inline_code_still_flagged():
    """A literal, backtick-quoted reference to the exact forbidden member
    (not just the owning class) is still caught by tier 1 regardless of the
    inline-code stripping applied to tier 2."""
    text = "Call `FileSystem.readFile` to load the bytes directly.\n"
    v = scan(text, _FILESYSTEM_FORBIDDEN)
    assert len(v) == 1
    assert v[0]["match_type"] == "fully_qualified"
    assert v[0]["matched_symbol"] == "FileSystem.readFile"


# ── HARDEN-FC-02: relational/possessive class mention (2026-07-29) ─────────
# Real incident: A3dwSaveOptions.md's Properties table description "Export
# meta data associated with Scene/Node to client." tripped "supports
# Scene.render" purely because "Export" (capability language) and "Scene"
# (the forbidden claim's owning class) both appear -- but the sentence
# describes an unrelated exportMetaData boolean flag; "Scene" is only named
# via "associated with", never as the subject of a capability claim.

_SCENE_FORBIDDEN = ["supports Scene.render"]


def test_class_reached_only_via_relation_not_flagged():
    """The exact real-world trigger: the owning class is named only through
    'associated with' / 'properties of', never as a direct capability
    subject."""
    text = "Export meta data associated with Scene/Node to client.\n"
    v = scan(text, _SCENE_FORBIDDEN)
    assert v == []


def test_class_as_direct_capability_subject_still_flagged():
    """The same owning class named as the direct subject of capability
    language (not behind a relational phrase) is still flagged."""
    text = "This exporter fully supports Scene rendering to PNG.\n"
    v = scan(text, _SCENE_FORBIDDEN)
    assert len(v) == 1
    assert v[0]["match_type"] == "class_with_capability_language"


def test_direct_mention_still_flagged_even_alongside_relational_mention():
    """A genuine direct capability claim about the class is still caught even
    when an unrelated relational mention of the same class also appears in
    the text -- per-occurrence checking, not a blanket suppression."""
    text = (
        "Export meta data associated with Scene/Node to client. "
        "Separately, this class also supports Scene directly.\n"
    )
    v = scan(text, _SCENE_FORBIDDEN)
    assert len(v) == 1


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


def test_newly_introduced_flags_the_specific_referenced_member():
    """HARDEN-FC-01 (2026-07-29) behavior change: a literal, backtick-quoted
    reference to ONE specific member (`Microsoft3MFFormat.IsBuildable`) is a
    strong tier-1 violation for THAT claim. It no longer cascades into flagging
    two OTHER, unrelated forbidden claims (GetTransformForBuild, SetBuildable)
    that merely share the same owning class and are not otherwise mentioned
    anywhere in the text -- that cascade was tier 2's bare-class-name search
    matching "Microsoft3MFFormat" inside the same backtick span, the exact
    over-broad shape that let a reference page's unrelated `FileSystem` type
    annotation trip a completely different forbidden claim (see
    test_bare_class_inside_inline_code_not_flagged below). Precision over
    breadth: tier 1 still catches the exact member if referenced; tier 2 still
    catches free-text prose that actually discusses the class's capabilities."""
    old = "Clean prose.\n"
    new = "Now you can use `Microsoft3MFFormat.IsBuildable` here.\n"
    v = newly_introduced(old, new, _3MF_FORBIDDEN)
    assert len(v) == 1
    assert v[0]["matched_symbol"] == "Microsoft3MFFormat.IsBuildable"
    assert v[0]["match_type"] == "fully_qualified"


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
