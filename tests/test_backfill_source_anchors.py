"""Tests for scripts/pipeline/commands/ops/backfill_source_anchors.py
(new 2026-08-29, TASK_BACKLOG.md SYNC-8). Synthetic fixtures, not the real
aspose.org checkout or the real docs/id-mapping.md."""
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline" / "commands" / "ops"))

import backfill_source_anchors as bsa  # noqa: E402

_SAMPLE_TABLE = """# id-mapping.md fixture

## Mapping Table

| foss-launcher ID | foss-launcher name | aspose.org ID | aspose.org name | Notes |
|---|---|---|---|---|
| S-01 | alpha | S-01 | alpha | Same |
| S-02 | beta | S-02 | different-beta | DIVERGE -- different skills |
| S-03 | *(unassigned)* | S-03 | *(varies)* | Gap |
| S-04 | gamma | S-04 | gamma | Ported 2026-04-27 |
| S-05 | delta | *(none)* | *(none)* | foss-only dispatcher skill |
| S-06 | epsilon | S-06 | epsilon | Same |

## Skills Unique to foss-launcher (no aspose.org counterpart)
"""


def test_parse_mapping_table_extracts_all_rows_including_ineligible():
    """parse_mapping_table parses every row verbatim, including placeholder
    ones -- filtering is is_eligible's job, a separate concern."""
    rows = bsa.parse_mapping_table(_SAMPLE_TABLE)
    names = [r["foss_name"] for r in rows]
    assert names == ["alpha", "beta", "*(unassigned)*", "gamma", "delta", "epsilon"]


def test_parse_mapping_table_then_filter_matches_eligible_only():
    rows = bsa.parse_mapping_table(_SAMPLE_TABLE)
    eligible_names = [r["foss_name"] for r in rows if bsa.is_eligible(r)]
    assert eligible_names == ["alpha", "gamma", "epsilon"]


def test_parse_mapping_table_stops_at_next_section():
    rows = bsa.parse_mapping_table(_SAMPLE_TABLE)
    assert all("Skills Unique" not in r["notes"] for r in rows)


@pytest.mark.parametrize("notes,expected", [
    ("Same", True),
    ("Ported 2026-04-27", True),
    ("DIVERGE -- different skills", False),
    ("Gap", False),
    ("Reserved", False),
    ("foss-only dispatcher skill", False),
])
def test_is_eligible_filters_by_notes(notes, expected):
    row = {"foss_name": "x", "aspose_name": "y", "notes": notes}
    assert bsa.is_eligible(row) == expected


def test_is_eligible_rejects_placeholder_names():
    row = {"foss_name": "*(unassigned)*", "aspose_name": "y", "notes": "Same"}
    assert bsa.is_eligible(row) is False


def test_parse_mapping_table_strips_markdown_bold_from_names():
    table = """## Mapping Table

| foss-launcher ID | foss-launcher name | aspose.org ID | aspose.org name | Notes |
|---|---|---|---|---|
| S-56 | **renamed-skill** | *(same aspose S-55)* | renamed-skill | Foss-new ID |
"""
    rows = bsa.parse_mapping_table(table)
    assert rows[0]["foss_name"] == "renamed-skill"
    assert "*" not in rows[0]["foss_name"]
