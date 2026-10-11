"""test_audit_content_origin.py — Unit tests for audit_content_origin.py (KR-0).

Covers:
- File with grade A, claims=[], no code blocks → Class 1, prose_only
- File with grade A, claims=[], has code blocks → Class 1
- File with grade C → Class 2
- File with no grade, has evidence → Class 2
- File with no grade, no evidence → Class 3
- File with content_origin != unknown → excluded from output
- Output CSV has correct columns and row count
"""
import csv
import sys
from pathlib import Path

import pytest

# Ensure scripts/pipeline is on path
_PIPELINE = Path(__file__).resolve().parent.parent
if str(_PIPELINE) not in sys.path:
    sys.path.insert(0, str(_PIPELINE))

from provenance import write_provenance
from audit_content_origin import audit, _classify
import audit_content_origin as _aco


@pytest.fixture(autouse=True)
def _reset_aco():
    yield
    _aco.configure()


# ---------------------------------------------------------------------------
# Unit tests for the _classify() function (pure logic, no I/O)
# ---------------------------------------------------------------------------

def test_classify_class1_grade_a_claims_empty():
    cls, strategy = _classify(grade="A", has_evidence=True, claims_present=True, claims_empty=True)
    assert cls == "1"
    assert strategy == "A"


def test_classify_class1_grade_b_claims_empty():
    cls, strategy = _classify(grade="B", has_evidence=True, claims_present=True, claims_empty=True)
    assert cls == "1"
    assert strategy == "A"


def test_classify_class2_grade_c():
    cls, strategy = _classify(grade="C", has_evidence=True, claims_present=True, claims_empty=True)
    assert cls == "2"
    assert strategy == "B"


def test_classify_class2_grade_d():
    cls, strategy = _classify(grade="D", has_evidence=False, claims_present=False, claims_empty=False)
    assert cls == "2"
    assert strategy == "B"


def test_classify_class2_no_grade_has_evidence():
    cls, strategy = _classify(grade="", has_evidence=True, claims_present=False, claims_empty=False)
    assert cls == "2"
    assert strategy == "B"


def test_classify_class3_no_grade_no_evidence():
    cls, strategy = _classify(grade="", has_evidence=False, claims_present=False, claims_empty=False)
    assert cls == "3"
    assert strategy == "C"


def test_classify_anomaly_grade_a_non_empty_claims():
    # Grade A/B + non-empty claims should have been promoted already → anomaly
    cls, strategy = _classify(grade="A", has_evidence=True, claims_present=True, claims_empty=False)
    assert cls == "anomaly"


# ---------------------------------------------------------------------------
# Integration tests using tmp_path
# ---------------------------------------------------------------------------

def _make_page(tmp_path: Path, subdir: str, content_origin: str = "unknown",
               grade: str = "", evidence: bool = False, claims: str | None = None,
               code_blocks: bool = False) -> Path:
    """Create a minimal .md file with provenance and optional evidence block."""
    site_dir = tmp_path / "blog.aspose.org" / "en" / "slides" / "java" / subdir
    site_dir.mkdir(parents=True, exist_ok=True)
    p = site_dir / "index.md"

    grade_line = f"grade: {grade}\n" if grade else ""
    code_line = "```python\nprint('hello')\n```\n" if code_blocks else ""

    if evidence:
        claims_str = f"  claims: [{claims if claims else ''}]\n"
        evidence_block = f"evidence:\n{claims_str}  apis: []\n"
    else:
        evidence_block = ""

    p.write_text(
        f"---\ntitle: Test\n{grade_line}---\nBody.\n{code_line}{evidence_block}",
        encoding="utf-8",
    )
    write_provenance(p, {
        "content_origin": content_origin,
        "last_mechanism": "unknown",
        "auto_updatable": True,
        "content_hash": "abc123",
    })
    return p


def _read_csv(csv_path: Path) -> list[dict]:
    with open(csv_path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _patch_audit_roots(mod, tmp_path):
    """Configure audit roots so content_root and repo_root both point to tmp_path."""
    mod.configure(repo_root=tmp_path, content_root=tmp_path)
    return ()


def _restore_audit_roots(mod, *_args):
    mod.configure()


def test_audit_grade_a_no_code_class1(tmp_path):
    _make_page(tmp_path, "p1", grade="A", evidence=True, claims="", code_blocks=False)
    csv_path = tmp_path / "out.csv"

    import audit_content_origin as mod
    orig = _patch_audit_roots(mod, tmp_path)
    try:
        audit(site_filter="blog.aspose.org", csv_path=csv_path)
    finally:
        _restore_audit_roots(mod, *orig)

    rows = _read_csv(csv_path)
    assert len(rows) == 1
    assert rows[0]["assigned_class"] == "1"
    assert rows[0]["has_code_blocks"] == "False"


def test_audit_grade_a_with_code_class1(tmp_path):
    _make_page(tmp_path, "p2", grade="A", evidence=True, claims="", code_blocks=True)
    csv_path = tmp_path / "out.csv"

    import audit_content_origin as mod
    orig = _patch_audit_roots(mod, tmp_path)
    try:
        audit(site_filter="blog.aspose.org", csv_path=csv_path)
    finally:
        _restore_audit_roots(mod, *orig)

    rows = _read_csv(csv_path)
    assert len(rows) == 1
    assert rows[0]["assigned_class"] == "1"
    assert rows[0]["has_code_blocks"] == "True"


def test_audit_grade_c_class2(tmp_path):
    _make_page(tmp_path, "p3", grade="C", evidence=True, claims="")
    csv_path = tmp_path / "out.csv"

    import audit_content_origin as mod
    orig = _patch_audit_roots(mod, tmp_path)
    try:
        audit(site_filter="blog.aspose.org", csv_path=csv_path)
    finally:
        _restore_audit_roots(mod, *orig)

    rows = _read_csv(csv_path)
    assert len(rows) == 1
    assert rows[0]["assigned_class"] == "2"


def test_audit_no_grade_has_evidence_class2(tmp_path):
    _make_page(tmp_path, "p4", grade="", evidence=True, claims="")
    csv_path = tmp_path / "out.csv"

    import audit_content_origin as mod
    orig = _patch_audit_roots(mod, tmp_path)
    try:
        audit(site_filter="blog.aspose.org", csv_path=csv_path)
    finally:
        _restore_audit_roots(mod, *orig)

    rows = _read_csv(csv_path)
    assert len(rows) == 1
    assert rows[0]["assigned_class"] == "2"


def test_audit_no_grade_no_evidence_class3(tmp_path):
    _make_page(tmp_path, "p5", grade="", evidence=False)
    csv_path = tmp_path / "out.csv"

    import audit_content_origin as mod
    orig = _patch_audit_roots(mod, tmp_path)
    try:
        audit(site_filter="blog.aspose.org", csv_path=csv_path)
    finally:
        _restore_audit_roots(mod, *orig)

    rows = _read_csv(csv_path)
    assert len(rows) == 1
    assert rows[0]["assigned_class"] == "3"


def test_audit_known_origin_excluded(tmp_path):
    _make_page(tmp_path, "p6", content_origin="skill-generated", grade="A", evidence=True, claims="")
    csv_path = tmp_path / "out.csv"

    import audit_content_origin as mod
    orig = _patch_audit_roots(mod, tmp_path)
    try:
        audit(site_filter="blog.aspose.org", csv_path=csv_path)
    finally:
        _restore_audit_roots(mod, *orig)

    rows = _read_csv(csv_path)
    # skill-generated file must not appear in unknown audit output
    assert len(rows) == 0


def test_audit_csv_has_correct_columns(tmp_path):
    _make_page(tmp_path, "p7", grade="A", evidence=True, claims="")
    csv_path = tmp_path / "out.csv"

    import audit_content_origin as mod
    orig = _patch_audit_roots(mod, tmp_path)
    try:
        audit(site_filter="blog.aspose.org", csv_path=csv_path)
    finally:
        _restore_audit_roots(mod, *orig)

    rows = _read_csv(csv_path)
    assert rows  # at least one row
    required_cols = {"site", "filepath", "grade", "assigned_class", "assigned_strategy",
                     "has_evidence", "claims_present", "claims_empty", "has_code_blocks"}
    assert required_cols.issubset(rows[0].keys())
