"""test_check_dar_table_accuracy.py — Regression tests for check_dar_table_accuracy.py (RPR-G-02).

Covers the DAR-table-vs-skills.md skill-ID comparison that catches the 8 mislabels
found and fixed in RPR-A-04 (session 1), and asserts the real repo passes today.
"""
import sys
from pathlib import Path

# Bootstrap: add scripts/ci/ to sys.path so `from checks.X import ...` works.
_HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HERE))

from checks import check_dar_table_accuracy as dar  # noqa: E402

_SKILLS = """\
# Skills registry

| skill | id | purpose |
|-------|----|---------|
| refresh-product | S-84 | maintenance chain |
| heal-page | S-26 | repair a page |
| page-update | S-20 | body edit |
"""


def _write(tmp_path, skills_md, dar_md):
    (tmp_path / "docs" / "registries").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "governance").mkdir(parents=True, exist_ok=True)
    sp = tmp_path / "docs" / "registries" / "skills.md"
    dp = tmp_path / "docs" / "governance" / "dar-table.md"
    sp.write_text(skills_md, encoding="utf-8")
    dp.write_text(dar_md, encoding="utf-8")
    return sp, dp


def test_load_skills_map_parses_ids(tmp_path):
    sp, _ = _write(tmp_path, _SKILLS, "")
    m = dar.load_skills_map(sp)
    assert m["refresh-product"] == "S-84"
    assert m["heal-page"] == "S-26"
    assert "skill" not in m  # header row skipped


def test_matching_dar_table_no_mismatches(tmp_path):
    sp, dp = _write(
        tmp_path, _SKILLS,
        "| Action | Skill |\n|--|--|\n| `/refresh-product` (S-84) | refresh |\n"
        "| `/heal-page` (S-26) | heal |\n",
    )
    assert dar.find_mismatches(dp, dar.load_skills_map(sp)) == []


def test_detects_mislabel(tmp_path):
    """The RPR-A-04 failure shape: /refresh-product labeled S-80, actual S-84."""
    sp, dp = _write(
        tmp_path, _SKILLS,
        "| `/refresh-product` (S-80) | refresh |\n",
    )
    mismatches = dar.find_mismatches(dp, dar.load_skills_map(sp))
    assert len(mismatches) == 1
    assert mismatches[0]["name"] == "refresh-product"
    assert mismatches[0]["dar_id"] == "S-80"
    assert mismatches[0]["canonical_id"] == "S-84"


def test_unknown_skill_name_skipped(tmp_path):
    """A command in the DAR table with no skills.md row is skipped, not a mismatch."""
    sp, dp = _write(
        tmp_path, _SKILLS,
        "| `/change-guard` (S-99) | governance |\n",
    )
    assert dar.find_mismatches(dp, dar.load_skills_map(sp)) == []


def test_real_repo_dar_table_passes():
    """The real repo must PASS — RPR-A-04 fixed all 8 mislabels in session 1."""
    assert dar.DAR_TABLE.is_file(), "dar-table.md missing"
    assert dar.SKILLS_MD.is_file(), "skills.md missing"
    skills_map = dar.load_skills_map(dar.SKILLS_MD)
    mismatches = dar.find_mismatches(dar.DAR_TABLE, skills_map)
    assert mismatches == [], f"DAR-table drift resurfaced: {mismatches}"


def test_main_returns_zero_on_real_repo():
    assert dar.main([]) == 0
