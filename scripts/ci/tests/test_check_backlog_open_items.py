"""Tests for check_backlog_open_items.py — backlog carry-forward hygiene validator.

Covers:
  CF-01  OPEN/CONDITIONALLY_ACCEPTED row missing Blocker
  CF-02  INV-* CONDITIONALLY_ACCEPTED row missing review date
  CF-03  INV-* CLOSED row missing evidence keyword

Tests also verify clean-pass behaviour (no findings) for correctly formed entries.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "checks"))

from check_backlog_open_items import check_backlog, _parse_table_rows  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TABLE_HEADER = (
    "| ID | Cat | Effect | Title | Status | Priority | Size | Wave | Score | Plan | Blocker | Updated |\n"
    "|----|-----|--------|-------|--------|----------|------|------|-------|------|---------|---------|"
)


def _make_backlog(active_rows: list[str] = (), queued_rows: list[str] = ()) -> Path:
    """Write a temporary BACKLOG.md with given row strings."""
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8")
    lines = ["# Backlog\n", "\n", "## Active (P0-P1)\n", "\n", _TABLE_HEADER + "\n"]
    for r in active_rows:
        lines.append(r + "\n")
    lines += ["\n", "## Queued (P2-P3)\n", "\n", _TABLE_HEADER + "\n"]
    for r in queued_rows:
        lines.append(r + "\n")
    tmp.write("".join(lines))
    tmp.flush()
    tmp.close()
    return Path(tmp.name)


def _row(
    id="TEST-001",
    cat="ops",
    effect="LOW",
    title="Some title with no date",
    status="OPEN",
    priority="P3",
    size="S",
    wave="0",
    score="0",
    plan="some-plan",
    blocker="some blocker",
    updated="2026-06-08",
):
    return f"| {id} | {cat} | {effect} | {title} | {status} | {priority} | {size} | {wave} | {score} | {plan} | {blocker} | {updated} |"


# ---------------------------------------------------------------------------
# CF-01: OPEN rows must have non-empty Blocker
# ---------------------------------------------------------------------------

class TestCF01MissingBlocker:

    def test_open_row_without_blocker_triggers_cf01(self):
        path = _make_backlog(queued_rows=[_row(status="OPEN", blocker="-")])
        findings = check_backlog(path)
        rules = [f["rule"] for f in findings]
        assert "CF-01" in rules

    def test_open_row_with_em_dash_triggers_cf01(self):
        path = _make_backlog(queued_rows=[_row(status="OPEN", blocker="—")])
        findings = check_backlog(path)
        rules = [f["rule"] for f in findings]
        assert "CF-01" in rules

    def test_open_row_with_blocker_is_clean(self):
        path = _make_backlog(queued_rows=[_row(status="OPEN", blocker="formats.json stale")])
        findings = check_backlog(path)
        cf01 = [f for f in findings if f["rule"] == "CF-01"]
        assert cf01 == []

    def test_conditionally_accepted_without_blocker_triggers_cf01(self):
        path = _make_backlog(active_rows=[_row(
            id="INV-999", status="CONDITIONALLY_ACCEPTED",
            title="Upstream PR open; Next review: 2026-09-01", blocker="-"
        )])
        findings = check_backlog(path)
        cf01 = [f for f in findings if f["rule"] == "CF-01"]
        assert len(cf01) == 1

    def test_closed_row_without_blocker_is_clean(self):
        """CLOSED rows do not need a Blocker."""
        path = _make_backlog(queued_rows=[_row(status="CLOSED", blocker="-")])
        findings = check_backlog(path)
        cf01 = [f for f in findings if f["rule"] == "CF-01"]
        assert cf01 == []

    def test_accepted_ceiling_without_blocker_is_clean(self):
        path = _make_backlog(queued_rows=[_row(status="ACCEPTED_CEILING", blocker="-")])
        findings = check_backlog(path)
        cf01 = [f for f in findings if f["rule"] == "CF-01"]
        assert cf01 == []


# ---------------------------------------------------------------------------
# CF-02: INV-* CONDITIONALLY_ACCEPTED must have a review date
# ---------------------------------------------------------------------------

class TestCF02MissingReviewDate:

    def test_inv_conditionally_accepted_without_date_triggers_cf02(self):
        path = _make_backlog(active_rows=[_row(
            id="INV-001", status="CONDITIONALLY_ACCEPTED",
            title="Upstream PR open, no date in description",
            blocker="PR#1 open",
        )])
        findings = check_backlog(path)
        cf02 = [f for f in findings if f["rule"] == "CF-02"]
        assert len(cf02) == 1
        assert "INV-001" in cf02[0]["message"]

    def test_inv_conditionally_accepted_with_date_is_clean(self):
        path = _make_backlog(active_rows=[_row(
            id="INV-004", status="CONDITIONALLY_ACCEPTED",
            title="PR open; Next review: 2026-07-20 or sooner if merged",
            blocker="PR#1 open",
        )])
        findings = check_backlog(path)
        cf02 = [f for f in findings if f["rule"] == "CF-02"]
        assert cf02 == []

    def test_non_inv_open_row_does_not_trigger_cf02(self):
        """CF-02 is only for INV-* IDs."""
        path = _make_backlog(queued_rows=[_row(
            id="CELLS-NET-001", status="OPEN",
            title="Some description without date",
            blocker="formats.json stale",
        )])
        findings = check_backlog(path)
        cf02 = [f for f in findings if f["rule"] == "CF-02"]
        assert cf02 == []


# ---------------------------------------------------------------------------
# CF-03: INV-* CLOSED must have evidence keyword
# ---------------------------------------------------------------------------

class TestCF03FalseClosure:

    def test_inv_closed_without_evidence_triggers_cf03(self):
        path = _make_backlog(active_rows=[_row(
            id="INV-002", status="CLOSED",
            title="some description with no evidence word",
            blocker="-",
        )])
        findings = check_backlog(path)
        cf03 = [f for f in findings if f["rule"] == "CF-03"]
        assert len(cf03) == 1
        assert "INV-002" in cf03[0]["message"]

    def test_inv_closed_with_verified_is_clean(self):
        path = _make_backlog(active_rows=[_row(
            id="INV-003", status="CLOSED",
            title="CLOSED verified 2026-06-08 — PR merged upstream",
            blocker="-",
        )])
        findings = check_backlog(path)
        cf03 = [f for f in findings if f["rule"] == "CF-03"]
        assert cf03 == []

    def test_inv_closed_with_resolved_is_clean(self):
        path = _make_backlog(active_rows=[_row(
            id="INV-005", status="CLOSED",
            title="resolved 2026-05-17 — active:false set",
            blocker="-",
        )])
        findings = check_backlog(path)
        cf03 = [f for f in findings if f["rule"] == "CF-03"]
        assert cf03 == []

    def test_non_inv_closed_without_evidence_is_clean(self):
        """CF-03 only applies to INV-* IDs."""
        path = _make_backlog(queued_rows=[_row(
            id="CELLS-CPP-001", status="CLOSED",
            title="some closed item",
            blocker="-",
        )])
        findings = check_backlog(path)
        cf03 = [f for f in findings if f["rule"] == "CF-03"]
        assert cf03 == []


# ---------------------------------------------------------------------------
# Production BACKLOG.md clean pass
# ---------------------------------------------------------------------------

class TestProductionBacklog:

    def test_current_backlog_has_zero_findings(self):
        """The actual repo BACKLOG.md must pass all CF-* checks."""
        repo_root = Path(__file__).resolve().parents[3]
        backlog_path = repo_root / "backlog" / "BACKLOG.md"
        if not backlog_path.exists():
            pytest.skip("BACKLOG.md not found in repo root")
        findings = check_backlog(backlog_path)
        assert findings == [], (
            f"Production BACKLOG.md has {len(findings)} carry-forward hygiene finding(s): "
            + str(findings)
        )
