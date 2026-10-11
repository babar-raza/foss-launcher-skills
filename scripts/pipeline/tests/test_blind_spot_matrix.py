"""Golden-fixture replay test for scripts/pipeline/lib/forensic_heal/blind_spot_matrix.py.

_V2_COMPARISON_MATRIX_CSV below is a verbatim copy of the real, already-produced output
from the 2026-06-17 hand-run of this mission's original ungoverned execution:
.local/evidences/foss-manual-system-heal-v2-20260617/06-comparison/
manual-vs-system-comparison-matrix.csv -- embedded directly (not read from that path at
test time) because `.local/` is git-ignored and would not exist on a fresh clone or in CI.

The test reconstructs synthetic dual-list input (separate unaided-pass and system-pass
finding lists) that -- when joined by build_comparison_matrix() -- must reproduce this real
run's own per-row classifications. This is the strongest available correctness check for
the classifier: it is not a fixture invented to make the code look right, it is real prior
output from the exact mission this module formalizes.
"""
from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib" / "forensic_heal"))

import blind_spot_matrix as bsm  # noqa: E402

_V2_COMPARISON_MATRIX_CSV = """\
finding_id,family,platform,page,issue_type,manual_found,system_found,system_tool,classification
FND-font-python-001,font,python,brotli-font-compression-python/index.md,private_import_notice,Y,N,,human-found/system-missed
FND-font-python-002,font,python,font-cff-in-python/index.md,private_import_notice,Y,N,,human-found/system-missed
FND-font-python-003,font,python,font-core-management-python/index.md,wrong_import_path,Y,N,,human-found/system-missed
FND-font-python-004,font,python,cff.md,private_import_notice,Y,N,,human-found/system-missed
FND-font-python-005,font,python,how-to-work-with-brotli-python.md,private_import_notice,Y,N,,human-found/system-missed
FND-font-python-006,font,python,h01+h02 H-gates,hgate_conditional,Y,N,,human-found/system-missed
SFND-001,font,python,134 reference pages,empty_description_cells,Y,Y,content_eval DC,system-found/human-agreed
SFND-003,font,python,AfmData.md etc,property_access_wrong,N,Y,content_eval TA,system-found/human-missed
FND-tex-python-001,tex,python,_index.md,wrong_import_path,Y,N,,human-found/system-missed
FND-email-python-001,email,python,MapiMessage.md,empty_description_cells,Y,Y,content_eval DC,system-found/human-agreed
SFND-004,email,python,introducing-email-foss-python/index.md,unknown_class_stdlib,N,Y,content_audit WARN,system-found/human-missed
SFND-005,email,python,python-outlook-msg-library/index.md,broken_internal_link,N,Y,content_audit WARN,system-found/human-missed
FND-pdf-go-001,pdf,go,248 pages,clean_regen,Y,Y,content_eval,system-found/human-agreed
FND-pdf-net-001,pdf,net,110 pages,empty_description_cells,Y,Y,content_eval DC,system-found/human-agreed
FND-pdf-java-001,pdf,java,342 pages,clean_regen,Y,Y,content_eval,system-found/human-agreed
FND-slides-net-001,slides,net,Image.md+SlideCollection.md,empty_description_cells,Y,Y,content_eval DC,system-found/human-agreed
SFND-002,pdf,go,~124 pages,stale_evidence,N,Y,content_audit WARN,system-found/human-missed
TC-P4-001-03-B,pdf,go,H-gate files,hgate_format_mismatch,Y,N,,human-found/system-missed
"""

_CLASSIFICATION_MAP = {
    "human-found/system-missed": "UNAIDED_ONLY",
    "system-found/human-agreed": "BOTH",
    "system-found/human-missed": "SYSTEM_ONLY",
}


def _load_v2_rows() -> "list[dict]":
    return list(csv.DictReader(io.StringIO(_V2_COMPARISON_MATRIX_CSV)))


def _build_synthetic_inputs(rows: "list[dict]") -> "tuple[list[dict], list[dict]]":
    unaided: "list[dict]" = []
    system: "list[dict]" = []
    for row in rows:
        base = {"family": row["family"], "platform": row["platform"], "page": row["page"], "issue_type": row["issue_type"]}
        if row["manual_found"] == "Y":
            unaided.append({"finding_id": row["finding_id"], **base})
        if row["system_found"] == "Y":
            fid = row["finding_id"] if row["manual_found"] != "Y" else f"{row['finding_id']}-sys"
            system.append({"finding_id": fid, **base})
    return unaided, system


def test_golden_fixture_reproduces_v2_run_per_row_classification():
    rows = _load_v2_rows()
    assert len(rows) == 18  # sanity: the embedded copy must match the real file's row count

    unaided, system = _build_synthetic_inputs(rows)
    result = bsm.build_comparison_matrix(unaided, system)

    assert result["orphan_finding_ids"] == []
    assert result["unclassified_issue_types"] == []

    actual_by_key = {tuple(r["key"].values()): r["classification"] for r in result["rows"]}
    for row in rows:
        key = (row["family"], row["platform"], row["page"], row["issue_type"])
        expected = _CLASSIFICATION_MAP[row["classification"]]
        assert actual_by_key[key] == expected, f"{row['finding_id']}: expected {expected}, got {actual_by_key[key]}"


def test_golden_fixture_counts_match_hand_tally():
    # Hand-tallied directly from the embedded CSV's own classification column:
    # 8 human-found/system-missed, 6 system-found/human-agreed, 4 system-found/human-missed.
    rows = _load_v2_rows()
    unaided, system = _build_synthetic_inputs(rows)
    result = bsm.build_comparison_matrix(unaided, system)

    assert result["counts"] == {"BOTH": 6, "UNAIDED_ONLY": 8, "SYSTEM_ONLY": 4, "CONTRADICTORY": 0}
    assert result["system_recall"] == 6 / 14


# ---------------------------------------------------------------------------
# Unit-level behavior not exercised by the golden fixture (no CONTRADICTORY,
# no unclassified issue_type, no malformed input, in the real v2 data)
# ---------------------------------------------------------------------------


def _f(finding_id, **kw):
    base = {"family": "pdf", "platform": "net", "page": "x.md", "issue_type": "clean_regen"}
    base.update(kw)
    return {"finding_id": finding_id, **base}


def test_contradictory_when_verdicts_disagree_on_same_key():
    unaided = [_f("FND-1", verdict="FAIL")]
    system = [_f("SFND-1", verdict="PASS")]
    result = bsm.build_comparison_matrix(unaided, system)
    assert result["counts"]["CONTRADICTORY"] == 1


def test_unclassified_issue_type_is_reported_not_dropped():
    unaided = [_f("FND-1", issue_type="totally_novel_issue_type")]
    result = bsm.build_comparison_matrix(unaided, [])
    assert result["rows"] == []
    assert len(result["unclassified_issue_types"]) == 1
    assert result["counts"] == {"BOTH": 0, "UNAIDED_ONLY": 0, "SYSTEM_ONLY": 0, "CONTRADICTORY": 0}


def test_missing_required_field_raises_not_silently_drops():
    bad = {"finding_id": "FND-1", "family": "pdf", "platform": "net", "issue_type": "clean_regen"}  # no page
    with pytest.raises(ValueError, match="page"):
        bsm.build_comparison_matrix([bad], [])


def test_system_recall_is_none_when_denominator_is_zero():
    result = bsm.build_comparison_matrix([], [_f("SFND-1")])
    assert result["counts"]["BOTH"] == 0
    assert result["counts"]["UNAIDED_ONLY"] == 0
    assert result["system_recall"] is None


def test_orphan_finding_ids_empty_by_construction_across_random_inputs():
    unaided = [_f(f"FND-{i}", page=f"p{i}.md") for i in range(5)]
    system = [_f(f"SFND-{i}", page=f"p{i}.md") for i in range(3, 8)]
    result = bsm.build_comparison_matrix(unaided, system)
    assert result["orphan_finding_ids"] == []
