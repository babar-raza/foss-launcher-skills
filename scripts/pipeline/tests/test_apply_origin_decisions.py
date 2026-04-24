"""test_apply_origin_decisions.py — Unit tests for apply_origin_decisions.py (KR-6).

Covers:
- skill-generated-confirmed → content_origin: skill-generated written
- human-authored-confirmed  → content_origin: human-authored written
- mixed-modified            → content_origin: agent-drafted + auto_updatable: false
- deferred                  → no change (file stays unknown)
- blank reviewer_decision   → BLOCKED before any writes
- invalid decision value    → BLOCKED before any writes
- already-set file          → skipped (not unknown)
- missing file              → counted as missing, not error
- idempotency               → double-apply produces 0 updates on second run
"""
import csv
import sys
from pathlib import Path

import pytest

# Ensure scripts/pipeline is on path
_PIPELINE = Path(__file__).resolve().parent.parent
if str(_PIPELINE) not in sys.path:
    sys.path.insert(0, str(_PIPELINE))

from provenance import read_provenance, write_provenance
from apply_origin_decisions import run
import apply_origin_decisions as _aod


@pytest.fixture(autouse=True)
def _reset_aod():
    yield
    _aod.configure()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_page(tmp_path: Path, content_origin: str = "unknown", subdir: str = "page") -> Path:
    d = tmp_path / subdir
    d.mkdir(parents=True, exist_ok=True)
    p = d / "index.md"
    p.write_text("---\ntitle: Test\ngrade: A\n---\nBody.\n", encoding="utf-8")
    prov = {
        "content_origin": content_origin,
        "last_mechanism": "unknown",
        "auto_updatable": True,
        "content_hash": "abc123",
    }
    write_provenance(p, prov)
    return p


def _make_csv(tmp_path: Path, rows: list[dict], name: str = "decisions.csv") -> Path:
    csv_path = tmp_path / name
    fields = ["site", "filepath", "family", "platform", "grade", "last_mechanism",
              "has_evidence", "claims_present", "claims_empty", "claims_non_empty",
              "has_code_blocks", "content_created_at", "assigned_class",
              "assigned_strategy", "outcome", "review_class",
              "reviewer_decision", "reviewer_note"]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            full = {k: "" for k in fields}
            full.update(row)
            writer.writerow(full)
    return csv_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_skill_generated_confirmed(tmp_path):
    page = _make_page(tmp_path, content_origin="unknown", subdir="page1")
    rel = page.relative_to(tmp_path).as_posix()
    csv_path = _make_csv(tmp_path, [{"filepath": rel, "reviewer_decision": "skill-generated-confirmed"}])

    _aod.configure(repo_root=tmp_path)
    stats = run(csv_path=csv_path, dry_run=False)

    assert stats["updated"] == 1
    prov = read_provenance(page)
    assert prov["content_origin"] == "skill-generated"


def test_human_authored_confirmed(tmp_path):
    page = _make_page(tmp_path, content_origin="unknown", subdir="page2")
    rel = page.relative_to(tmp_path).as_posix()
    csv_path = _make_csv(tmp_path, [{"filepath": rel, "reviewer_decision": "human-authored-confirmed"}])

    _aod.configure(repo_root=tmp_path)
    stats = run(csv_path=csv_path, dry_run=False)

    assert stats["updated"] == 1
    prov = read_provenance(page)
    assert prov["content_origin"] == "human-authored"


def test_mixed_modified_sets_agent_drafted_and_locks(tmp_path):
    page = _make_page(tmp_path, content_origin="unknown", subdir="page3")
    rel = page.relative_to(tmp_path).as_posix()
    csv_path = _make_csv(tmp_path, [{"filepath": rel, "reviewer_decision": "mixed-modified"}])

    _aod.configure(repo_root=tmp_path)
    stats = run(csv_path=csv_path, dry_run=False)

    assert stats["updated"] == 1
    prov = read_provenance(page)
    assert prov["content_origin"] == "agent-drafted"
    assert prov["auto_updatable"] is False


def test_deferred_leaves_unknown(tmp_path):
    page = _make_page(tmp_path, content_origin="unknown", subdir="page4")
    rel = page.relative_to(tmp_path).as_posix()
    csv_path = _make_csv(tmp_path, [{"filepath": rel, "reviewer_decision": "deferred"}])

    _aod.configure(repo_root=tmp_path)
    stats = run(csv_path=csv_path, dry_run=False)

    assert stats["deferred"] == 1
    assert stats["updated"] == 0
    prov = read_provenance(page)
    assert prov["content_origin"] == "unknown"


def test_blank_decision_blocks(tmp_path):
    page = _make_page(tmp_path, content_origin="unknown", subdir="page5")
    rel = page.relative_to(tmp_path).as_posix()
    csv_path = _make_csv(tmp_path, [{"filepath": rel, "reviewer_decision": ""}])

    _aod.configure(repo_root=tmp_path)
    with pytest.raises(SystemExit) as exc:
        run(csv_path=csv_path, dry_run=False)
    assert exc.value.code == 1

    # File must NOT have been modified
    prov = read_provenance(page)
    assert prov["content_origin"] == "unknown"


def test_invalid_decision_blocks(tmp_path):
    page = _make_page(tmp_path, content_origin="unknown", subdir="page6")
    rel = page.relative_to(tmp_path).as_posix()
    csv_path = _make_csv(tmp_path, [{"filepath": rel, "reviewer_decision": "unknown-guess"}])

    _aod.configure(repo_root=tmp_path)
    with pytest.raises(SystemExit) as exc:
        run(csv_path=csv_path, dry_run=False)
    assert exc.value.code == 1


def test_already_set_skipped(tmp_path):
    page = _make_page(tmp_path, content_origin="skill-generated", subdir="page7")
    rel = page.relative_to(tmp_path).as_posix()
    csv_path = _make_csv(tmp_path, [{"filepath": rel, "reviewer_decision": "human-authored-confirmed"}])

    _aod.configure(repo_root=tmp_path)
    stats = run(csv_path=csv_path, dry_run=False)

    assert stats["already_set"] == 1
    assert stats["updated"] == 0
    prov = read_provenance(page)
    assert prov["content_origin"] == "skill-generated"  # unchanged


def test_missing_file_counted(tmp_path):
    csv_path = _make_csv(tmp_path, [{"filepath": "no/such/file.md", "reviewer_decision": "skill-generated-confirmed"}])

    _aod.configure(repo_root=tmp_path)
    stats = run(csv_path=csv_path, dry_run=False)

    assert stats["missing"] == 1
    assert stats["updated"] == 0


def test_dry_run_makes_no_writes(tmp_path):
    page = _make_page(tmp_path, content_origin="unknown", subdir="page8")
    rel = page.relative_to(tmp_path).as_posix()
    csv_path = _make_csv(tmp_path, [{"filepath": rel, "reviewer_decision": "skill-generated-confirmed"}])

    _aod.configure(repo_root=tmp_path)
    stats = run(csv_path=csv_path, dry_run=True)

    assert stats["updated"] == 1
    prov = read_provenance(page)
    assert prov["content_origin"] == "unknown"  # dry-run: no write


def test_idempotent(tmp_path):
    page = _make_page(tmp_path, content_origin="unknown", subdir="page9")
    rel = page.relative_to(tmp_path).as_posix()
    csv_path = _make_csv(tmp_path, [{"filepath": rel, "reviewer_decision": "skill-generated-confirmed"}])

    _aod.configure(repo_root=tmp_path)
    stats1 = run(csv_path=csv_path, dry_run=False)
    stats2 = run(csv_path=csv_path, dry_run=False)

    assert stats1["updated"] == 1
    assert stats2["updated"] == 0
    assert stats2["already_set"] == 1
