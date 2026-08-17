"""test_check_plan_taskcard_completeness.py — regression tests for
check_plan_taskcard_completeness.py.

Includes an end-to-end ground-truth test against the real artifacts from the
incident that motivated this check (magical-inventing-book.md's 9-step
Execution order section vs. the real media-icon-generation-2026-08-06
taskcards.jsonl, which only has 6 distinct task_ids) -- a rare case where the
correct answer is independently already known, not just asserted.
"""
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HERE))

from checks import check_plan_taskcard_completeness as completeness  # noqa: E402


def _write_store(tmp_path, task_ids):
    p = tmp_path / "taskcards.jsonl"
    rows = [
        {
            "task_id": tid, "mission_id": "m", "status": "TODO",
            "recorded_at": "2026-08-06T00:00:00Z", "evidence_refs": [], "recorded_by": "t",
        }
        for tid in task_ids
    ]
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return p


# ── extract_execution_steps ─────────────────────────────────────────────────

def test_no_execution_order_section_returns_none():
    assert completeness.extract_execution_steps("# Plan\n\nSome prose, no step list.\n") is None


def test_extracts_numbered_steps_under_heading():
    md = (
        "# Plan\n\n"
        "## Execution order\n\n"
        "1. Do the first thing\n"
        "2. Do the second thing\n"
        "3. Do the third thing\n"
    )
    steps = completeness.extract_execution_steps(md)
    assert steps == ["Do the first thing", "Do the second thing", "Do the third thing"]


def test_stops_at_next_heading():
    md = (
        "## Execution order\n\n"
        "1. Step one\n"
        "2. Step two\n\n"
        "## Risks\n\n"
        "1. This is not an execution step\n"
    )
    steps = completeness.extract_execution_steps(md)
    assert steps == ["Step one", "Step two"]


def test_not_tracked_tag_excludes_step():
    md = (
        "## Execution order\n\n"
        "1. Real tracked step\n"
        "2. Prose-only guidance <!-- NOT-TRACKED: not a discrete work item -->\n"
    )
    steps = completeness.extract_execution_steps(md)
    assert steps == ["Real tracked step"]


def test_heading_matching_is_case_insensitive_and_flexible_level():
    md = "### EXECUTION ORDER\n\n1. thing\n"
    assert completeness.extract_execution_steps(md) == ["thing"]


# ── load_distinct_task_ids ──────────────────────────────────────────────────

def test_distinct_task_ids_counts_each_id_once_regardless_of_status_history(tmp_path):
    p = tmp_path / "taskcards.jsonl"
    rows = [
        {"task_id": "TC-01", "mission_id": "m", "status": "TODO", "recorded_at": "x",
         "evidence_refs": [], "recorded_by": "t"},
        {"task_id": "TC-01", "mission_id": "m", "status": "IN_PROGRESS", "recorded_at": "x",
         "evidence_refs": [], "recorded_by": "t"},
        {"task_id": "TC-02", "mission_id": "m", "status": "TODO", "recorded_at": "x",
         "evidence_refs": [], "recorded_by": "t"},
    ]
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    assert completeness.load_distinct_task_ids(p) == {"TC-01", "TC-02"}


# ── main() / CLI ─────────────────────────────────────────────────────────────

def test_main_passes_when_no_execution_order_section(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text("no execution order section\n", encoding="utf-8")
    store = _write_store(tmp_path, ["TC-01"])
    assert completeness.main(["--plan-file", str(plan), "--taskcards", str(store)]) == 0


def test_main_passes_when_steps_fully_covered(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text("## Execution order\n\n1. a\n2. b\n", encoding="utf-8")
    store = _write_store(tmp_path, ["TC-01", "TC-02"])
    assert completeness.main(["--plan-file", str(plan), "--taskcards", str(store)]) == 0


def test_main_fails_when_steps_exceed_taskcards_reproduces_the_real_incident_shape(tmp_path):
    """Same shape as the real incident: 9 steps, 6 taskcards -- step 9 (and
    others) have no durable record. This is a synthetic fixture reproducing
    that exact ratio, not the real external plan file (see the real-artifact
    test below for that)."""
    plan = tmp_path / "plan.md"
    steps_md = "\n".join(f"{i}. step {i}" for i in range(1, 10))
    plan.write_text(f"## Execution order\n\n{steps_md}\n", encoding="utf-8")
    store = _write_store(tmp_path, [f"TC-MEDIA-{i:02d}" for i in range(1, 7)])
    assert completeness.main(["--plan-file", str(plan), "--taskcards", str(store)]) == 1


def test_main_missing_plan_file_exits_2(tmp_path):
    store = _write_store(tmp_path, ["TC-01"])
    assert completeness.main(["--plan-file", str(tmp_path / "nope.md"), "--taskcards", str(store)]) == 2


def test_main_missing_taskcards_file_exits_2(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text("## Execution order\n\n1. a\n", encoding="utf-8")
    assert completeness.main(["--plan-file", str(plan), "--taskcards", str(tmp_path / "nope.jsonl")]) == 2


# ── real-artifact ground truth ──────────────────────────────────────────────

def test_real_incident_taskcards_file_is_still_readable_and_undercounts_nine_steps(tmp_path):
    """Ground truth for the STABLE half of the incident's artifacts: the
    real, repo-tracked reports/plan_state/media-icon-generation-2026-08-06/
    taskcards.jsonl (6 distinct task_ids, TC-MEDIA-01..06) is exactly what
    was live at the time of the investigation and is not expected to change
    retroactively. We pair it with a frozen COPY of the real plan's original
    9-step "Execution order" text (not the live external ~/.claude/plans/
    file, which is mutable, outside the repo, and has since evolved past
    this specific plan -- confirmed live: it now tracks unrelated
    later-dated content under the same filename. Depending on that live
    external file for a hard regression assertion would itself reproduce
    RC1 from the assessment this check exists to act on -- "plan lives
    outside the repo, no stable content-hash mechanism" -- so this test
    deliberately does not do that; see the synthetic-fixture test above for
    the always-reliable regression coverage of the same 9-vs-6 shape."""
    repo_root = Path(__file__).resolve().parents[3]
    store = repo_root / "reports" / "plan_state" / "media-icon-generation-2026-08-06" / "taskcards.jsonl"
    if not store.is_file():
        import pytest
        pytest.skip("real incident taskcards.jsonl unavailable in this environment")

    task_ids = completeness.load_distinct_task_ids(store)
    assert task_ids == {f"TC-MEDIA-{i:02d}" for i in range(1, 7)}

    frozen_plan_text = (
        "## Execution order\n\n"
        "1. Rewrite `scripts/pipeline/commands/ops/optimize_media_assets.py`\n"
        "2. Rewrite `scripts/pipeline/tests/test_optimize_media_assets.py`\n"
        "3. Update `skills/media-optimize.md`\n"
        "4. Re-fetch the `oxipng` binary\n"
        "5. Run full test suite; commit\n"
        "6. Run `--dry-run` then `--apply`\n"
        "7. Visual review of the 72 new PNG files only\n"
        "8. `--confirm-reviewed`; commit the added PNG files\n"
        "9. Resume the paused `.supervisor` MT023 convergence audit\n"
    )
    steps = completeness.extract_execution_steps(frozen_plan_text)
    assert len(steps) == 9
    assert len(task_ids) == 6

    plan_path = tmp_path / "frozen-plan.md"
    plan_path.write_text(frozen_plan_text, encoding="utf-8")
    assert completeness.main(["--plan-file", str(plan_path), "--taskcards", str(store)]) == 1
