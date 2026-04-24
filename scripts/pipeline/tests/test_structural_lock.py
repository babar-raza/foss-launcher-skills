"""test_structural_lock.py — Unit tests for structural_lock.py (KR-2).

Covers:
- Happy path: Class 3 row, file exists → auto_updatable: false + note set
- Already locked: file already has auto_updatable: false + note → skipped (0 updates)
- Missing file: logged as error, not crash
- Dry-run: prints WOULD LOCK, no write
- Idempotency: second apply → 0 updates, all skipped
- Non-class-3 row: not processed (CSV filter)
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
from structural_lock import run
import structural_lock as _sl


@pytest.fixture(autouse=True)
def _reset_sl():
    yield
    _sl.configure()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_page(tmp_path: Path, subdir: str = "page", auto_updatable: bool = True,
               recovery_note: str | None = None) -> Path:
    d = tmp_path / subdir
    d.mkdir(parents=True, exist_ok=True)
    p = d / "index.md"
    p.write_text("---\ntitle: Test\n---\nBody.\n", encoding="utf-8")
    prov: dict = {
        "content_origin": "unknown",
        "last_mechanism": "unknown",
        "auto_updatable": auto_updatable,
        "content_hash": "abc123",
    }
    if recovery_note is not None:
        prov["provenance_recovery_note"] = recovery_note
    write_provenance(p, prov)
    return p


def _make_csv(tmp_path: Path, rows: list[dict], name: str = "queue.csv") -> Path:
    csv_path = tmp_path / name
    fields = ["site", "filepath", "family", "platform", "grade", "last_mechanism",
              "has_evidence", "claims_present", "claims_empty", "claims_non_empty",
              "has_code_blocks", "content_created_at", "assigned_class", "assigned_strategy"]
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

def test_class3_file_locked(tmp_path):
    page = _make_page(tmp_path, subdir="page1")
    rel = page.relative_to(tmp_path).as_posix()
    csv_path = _make_csv(tmp_path, [{"filepath": rel, "assigned_class": "3"}])

    _sl.configure(repo_root=tmp_path)
    stats = run(csv_path=csv_path, dry_run=False)

    assert stats["updated"] == 1
    assert stats["skipped"] == 0
    prov = read_provenance(page)
    assert prov["auto_updatable"] is False
    assert prov["provenance_recovery_note"] == "structural-page"
    assert prov["content_origin"] == "unknown"  # content_origin must not change


def test_already_locked_skipped(tmp_path):
    page = _make_page(tmp_path, subdir="page2", auto_updatable=False,
                      recovery_note="structural-page")
    rel = page.relative_to(tmp_path).as_posix()
    csv_path = _make_csv(tmp_path, [{"filepath": rel, "assigned_class": "3"}])

    _sl.configure(repo_root=tmp_path)
    stats = run(csv_path=csv_path, dry_run=False)

    assert stats["skipped"] == 1
    assert stats["updated"] == 0


def test_missing_file_counted_as_error(tmp_path):
    csv_path = _make_csv(tmp_path, [{"filepath": "no/such/file.md", "assigned_class": "3"}])

    _sl.configure(repo_root=tmp_path)
    stats = run(csv_path=csv_path, dry_run=False)

    assert stats["errors"] == 1
    assert stats["updated"] == 0


def test_dry_run_no_writes(tmp_path):
    page = _make_page(tmp_path, subdir="page4")
    rel = page.relative_to(tmp_path).as_posix()
    csv_path = _make_csv(tmp_path, [{"filepath": rel, "assigned_class": "3"}])

    _sl.configure(repo_root=tmp_path)
    stats = run(csv_path=csv_path, dry_run=True)

    assert stats["updated"] == 1
    prov = read_provenance(page)
    # dry-run: should NOT have written auto_updatable: false
    assert prov["auto_updatable"] is True


def test_idempotent(tmp_path):
    page = _make_page(tmp_path, subdir="page5")
    rel = page.relative_to(tmp_path).as_posix()
    csv_path = _make_csv(tmp_path, [{"filepath": rel, "assigned_class": "3"}])

    _sl.configure(repo_root=tmp_path)
    stats1 = run(csv_path=csv_path, dry_run=False)
    stats2 = run(csv_path=csv_path, dry_run=False)

    assert stats1["updated"] == 1
    assert stats2["updated"] == 0
    assert stats2["skipped"] == 1


def test_non_class3_rows_ignored(tmp_path):
    page = _make_page(tmp_path, subdir="page6")
    rel = page.relative_to(tmp_path).as_posix()
    # Row with assigned_class="1" — should be ignored
    csv_path = _make_csv(tmp_path, [{"filepath": rel, "assigned_class": "1"}])

    _sl.configure(repo_root=tmp_path)
    stats = run(csv_path=csv_path, dry_run=False)

    # File should be untouched
    assert stats["updated"] == 0
    prov = read_provenance(page)
    assert prov["auto_updatable"] is True  # unchanged
