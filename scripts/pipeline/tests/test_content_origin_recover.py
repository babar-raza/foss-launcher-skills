"""test_content_origin_recover.py — Unit tests for content_origin_recover.py.

Covers:
- Rule A: grade A/B + non-empty claims → skill-generated (existing rule)
- Rule B: grade A/B + non-empty apis + empty claims → skill-generated (new rule)
- Rule B: low grade + non-empty apis → no-qualify (grade required)
- Locale file with translation_origin → skipped
- File with content_origin != unknown → not-unknown
- File with no provenance → no-provenance
- Rule B wins only when Rule A doesn't fire (apis non-empty, claims empty)
- Dry-run: process_file returns 'inferred' but does not write
- Apply: process_file writes skill-generated
- Idempotency: second apply → not-unknown
"""
import sys
from pathlib import Path

import pytest

# Ensure scripts/pipeline is on path
_PIPELINE = Path(__file__).resolve().parent.parent
if str(_PIPELINE) not in sys.path:
    sys.path.insert(0, str(_PIPELINE))

from provenance import read_provenance, write_provenance
from content_origin_recover import process_file, _qualifies_rule_a, _qualifies_rule_b


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_page(tmp_path: Path, subdir: str, content_origin: str = "unknown",
               grade: str = "B", claims: list | None = None, apis: list | None = None,
               translation_origin: str | None = None) -> Path:
    """Create a minimal .md file with provenance and evidence block."""
    d = tmp_path / subdir
    d.mkdir(parents=True, exist_ok=True)
    p = d / "index.md"

    grade_line = f"grade: {grade}\n" if grade else ""
    claims_yaml = repr(claims).replace("'", '"') if claims is not None else "[]"
    apis_yaml = repr(apis).replace("'", '"') if apis is not None else "[]"

    # evidence must be inside the frontmatter (between --- delimiters)
    evidence_block = f"evidence:\n  claims: {claims_yaml}\n  apis: {apis_yaml}\n"
    p.write_text(
        f"---\ntitle: Test\n{grade_line}{evidence_block}---\nBody.\n",
        encoding="utf-8",
    )

    if translation_origin:
        prov = {
            "translation_origin": translation_origin,
            "source_file": "en/test.md",
            "content_hash": "abc123",
        }
    else:
        prov = {
            "content_origin": content_origin,
            "last_mechanism": "unknown",
            "auto_updatable": True,
            "content_hash": "abc123",
        }
    write_provenance(p, prov)
    return p


# ---------------------------------------------------------------------------
# Unit tests for qualification functions
# ---------------------------------------------------------------------------

def test_qualifies_rule_a_with_claims():
    fields = {"grade": "A", "evidence": {"claims": ["Claim1", "Claim2"], "apis": []}}
    assert _qualifies_rule_a(fields) is True


def test_qualifies_rule_a_fails_empty_claims():
    fields = {"grade": "A", "evidence": {"claims": [], "apis": ["Foo.bar"]}}
    assert _qualifies_rule_a(fields) is False


def test_qualifies_rule_b_with_apis_empty_claims():
    fields = {"grade": "B", "evidence": {"claims": [], "apis": ["Foo.bar"]}}
    assert _qualifies_rule_b(fields) is True


def test_qualifies_rule_b_fails_low_grade():
    fields = {"grade": "C", "evidence": {"claims": [], "apis": ["Foo.bar"]}}
    assert _qualifies_rule_b(fields) is False


def test_qualifies_rule_b_fails_empty_apis():
    fields = {"grade": "B", "evidence": {"claims": [], "apis": []}}
    assert _qualifies_rule_b(fields) is False


def test_qualifies_rule_b_fails_no_evidence():
    fields = {"grade": "B"}
    assert _qualifies_rule_b(fields) is False


# ---------------------------------------------------------------------------
# Integration tests using process_file
# ---------------------------------------------------------------------------

def test_rule_a_apply(tmp_path):
    page = _make_page(tmp_path, "p1", claims=["Claim1"], apis=[])
    result = process_file(page, apply=True)
    assert result == "inferred"
    prov = read_provenance(page)
    assert prov["content_origin"] == "skill-generated"


def test_rule_b_apply(tmp_path):
    page = _make_page(tmp_path, "p2", claims=[], apis=["Foo.bar"])
    result = process_file(page, apply=True)
    assert result == "inferred"
    prov = read_provenance(page)
    assert prov["content_origin"] == "skill-generated"


def test_rule_b_dry_run_no_write(tmp_path):
    page = _make_page(tmp_path, "p3", claims=[], apis=["Foo.bar"])
    result = process_file(page, apply=False)
    assert result == "inferred"
    prov = read_provenance(page)
    assert prov["content_origin"] == "unknown"  # dry-run: no write


def test_rule_b_low_grade_no_qualify(tmp_path):
    page = _make_page(tmp_path, "p4", grade="C", claims=[], apis=["Foo.bar"])
    result = process_file(page, apply=True)
    assert result == "no-qualify"
    prov = read_provenance(page)
    assert prov["content_origin"] == "unknown"  # unchanged


def test_locale_file_skipped(tmp_path):
    page = _make_page(tmp_path, "p5", translation_origin="translator-batch",
                      claims=[], apis=["Foo.bar"])
    result = process_file(page, apply=True)
    assert result == "not-unknown"
    # content_origin should not be set on locale file
    prov = read_provenance(page)
    assert "content_origin" not in prov


def test_already_set_not_unknown(tmp_path):
    page = _make_page(tmp_path, "p6", content_origin="human-authored",
                      claims=[], apis=["Foo.bar"])
    result = process_file(page, apply=True)
    assert result == "not-unknown"
    prov = read_provenance(page)
    assert prov["content_origin"] == "human-authored"  # unchanged


def test_idempotent_rule_b(tmp_path):
    page = _make_page(tmp_path, "p7", claims=[], apis=["Foo.bar"])
    r1 = process_file(page, apply=True)
    r2 = process_file(page, apply=True)
    assert r1 == "inferred"
    assert r2 == "not-unknown"
