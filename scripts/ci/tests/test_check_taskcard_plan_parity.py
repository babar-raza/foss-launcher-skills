"""test_check_taskcard_plan_parity.py — Regression tests for check_taskcard_plan_parity.py (RPR-G-04).

Covers the taskcard-store-vs-plan-markdown parity check: silence is not a
contradiction, an explicit markdown tag that disagrees with the store IS
(the TC-W11-001.C7 shape), and the real mission's own store passes.
"""
import json
import sys
from pathlib import Path

# Bootstrap: add scripts/ci/ to sys.path so `from checks.X import ...` works.
_HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HERE))

from checks import check_taskcard_plan_parity as parity  # noqa: E402


def _write_store(tmp_path, rows):
    p = tmp_path / "taskcards.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return p


def _row(task_id, status, evidence=None):
    return {
        "task_id": task_id, "mission_id": "m", "status": status,
        "recorded_at": "2026-07-17T00:00:00Z",
        "evidence_refs": evidence or [], "recorded_by": "t",
    }


# ── bucket classifiers ────────────────────────────────────────────────────

def test_markdown_bucket_done():
    assert parity.markdown_status_bucket("DONE") == parity.DONE
    assert parity.markdown_status_bucket("DONE, session 3") == parity.DONE


def test_markdown_bucket_partial_from_qualifier():
    assert parity.markdown_status_bucket("DAR-table portion DONE; ADR still open") == parity.PARTIAL
    assert parity.markdown_status_bucket("PARTIAL — 12/74 classified") == parity.PARTIAL


def test_store_bucket_mapping():
    assert parity.store_status_bucket("FOCUSED_VERIFIED") == parity.DONE
    assert parity.store_status_bucket("IN_PROGRESS") == parity.PARTIAL
    assert parity.store_status_bucket("TODO") == parity.NOT_STARTED
    assert parity.store_status_bucket("SUPERSEDED") is None  # excluded


# ── tag extraction ────────────────────────────────────────────────────────

def test_extract_only_status_tags_not_new_tags():
    md = (
        "**RPR-A-01 — Classify [STATUS: PARTIAL — 12/74]**\n"
        "**RPR-A-05 — File incident [NEW, session 1]**\n"
        "**RPR-B-01/02/03 — Schemas [STATUS: DONE]**\n"
    )
    tags = parity.extract_plan_tags(md)
    assert tags["RPR-A-01"].startswith("PARTIAL")
    assert "RPR-A-05" not in tags  # [NEW, ...] is not a status tag
    assert tags["RPR-B-01"] == "DONE"  # first id on a shared-card line wins


def test_extract_supports_lanes_after_i():
    tags = parity.extract_plan_tags(
        "**RPR-J-05 — verifier [STATUS: DONE]**\n"
    )
    assert tags["RPR-J-05"] == "DONE"


# ── parity logic ──────────────────────────────────────────────────────────

def test_silence_is_not_contradiction(tmp_path):
    """A store task the markdown never tags produces no problem (default mode)."""
    store = _write_store(tmp_path, [_row("RPR-D-01", "FOCUSED_VERIFIED", ["x.py"])])
    md = tmp_path / "plan.md"
    md.write_text("no task tags here at all\n", encoding="utf-8")
    plan_tags = parity.extract_plan_tags(md.read_text(encoding="utf-8"))
    problems = parity.find_contradictions(plan_tags, parity.load_taskcards(store))
    assert problems == []


def test_markdown_done_but_store_todo_is_contradiction(tmp_path):
    """The literal TC-W11-001.C7 failure shape: prose claims done, store says not."""
    store = _write_store(tmp_path, [_row("RPR-A-01", "TODO")])
    md = tmp_path / "plan.md"
    md.write_text("**RPR-A-01 — thing [STATUS: DONE]**\n", encoding="utf-8")
    plan_tags = parity.extract_plan_tags(md.read_text(encoding="utf-8"))
    problems = parity.find_contradictions(plan_tags, parity.load_taskcards(store))
    assert len(problems) == 1
    assert problems[0]["kind"] == "contradiction"


def test_store_done_but_markdown_todo_is_contradiction(tmp_path):
    store = _write_store(tmp_path, [_row("RPR-A-01", "CLOSED", ["x.py"])])
    md = tmp_path / "plan.md"
    md.write_text("**RPR-A-01 — thing [STATUS: TODO not started]**\n", encoding="utf-8")
    plan_tags = parity.extract_plan_tags(md.read_text(encoding="utf-8"))
    problems = parity.find_contradictions(plan_tags, parity.load_taskcards(store))
    assert len(problems) == 1


def test_matching_buckets_pass(tmp_path):
    store = _write_store(tmp_path, [_row("RPR-B-01", "FOCUSED_VERIFIED", ["x.py"])])
    md = tmp_path / "plan.md"
    md.write_text("**RPR-B-01 — schemas [STATUS: DONE]**\n", encoding="utf-8")
    plan_tags = parity.extract_plan_tags(md.read_text(encoding="utf-8"))
    assert parity.find_contradictions(plan_tags, parity.load_taskcards(store)) == []


def test_tagged_but_missing_from_store_fails(tmp_path):
    # RPR-H-09 is a valid-lane id (H is in A-I) that is absent from the store.
    store = _write_store(tmp_path, [_row("RPR-A-01", "TODO")])
    md = tmp_path / "plan.md"
    md.write_text("**RPR-H-09 — ghost [STATUS: DONE]**\n", encoding="utf-8")
    plan_tags = parity.extract_plan_tags(md.read_text(encoding="utf-8"))
    problems = parity.find_contradictions(plan_tags, parity.load_taskcards(store))
    assert any(p["kind"] == "tagged_but_missing_from_store" for p in problems)


def test_strict_coverage_flags_untagged_store_tasks(tmp_path):
    store = _write_store(tmp_path, [_row("RPR-D-01", "FOCUSED_VERIFIED", ["x.py"])])
    md = tmp_path / "plan.md"
    md.write_text("no tags\n", encoding="utf-8")
    plan_tags = parity.extract_plan_tags(md.read_text(encoding="utf-8"))
    problems = parity.find_contradictions(plan_tags, parity.load_taskcards(store), strict_coverage=True)
    assert any(p["kind"] == "untagged_under_strict_coverage" for p in problems)


def test_execution_authority_marker_makes_coverage_strict(tmp_path):
    store = _write_store(tmp_path, [_row("RPR-D-01", "TODO")])
    plan = tmp_path / "plan.md"
    plan.write_text(
        "<!-- TASKCARD_EXECUTION_AUTHORITY -->\nNo task tags.\n",
        encoding="utf-8",
    )
    assert parity.main([
        "--plan-file", str(plan),
        "--taskcards", str(store),
    ]) == 1


def test_execution_authority_flag_makes_coverage_strict(tmp_path):
    store = _write_store(tmp_path, [_row("RPR-D-01", "TODO")])
    plan = tmp_path / "plan.md"
    plan.write_text("No task tags.\n", encoding="utf-8")
    assert parity.main([
        "--plan-file", str(plan),
        "--taskcards", str(store),
        "--execution-authority",
    ]) == 1


# ── id-pattern inference (regression: was hardcoded to RPR-[A-Z]-NN only) ──

def test_infer_pattern_matches_non_rpr_ids():
    """TC-MEDIA-01-style ids (used by every real mission except one legacy
    plan) previously went completely unmatched by the hardcoded _TASK_ID
    regex -- this locks in that they're now derived correctly."""
    pattern = parity.infer_task_id_pattern(["TC-MEDIA-01", "TC-MEDIA-02"])
    assert pattern.findall("**TC-MEDIA-03 — new step [STATUS: DONE]**") == ["TC-MEDIA-03"]


def test_infer_pattern_still_matches_rpr_ids():
    pattern = parity.infer_task_id_pattern(["RPR-A-01", "RPR-B-02"])
    assert pattern.findall("**RPR-A-05 — thing [STATUS: DONE]**") == ["RPR-A-05"]


def test_infer_pattern_empty_store_matches_nothing():
    pattern = parity.infer_task_id_pattern([])
    assert pattern.findall("RPR-A-01 TC-MEDIA-01 anything") == []


def test_end_to_end_non_rpr_ids_previously_silently_passed_now_detected(tmp_path):
    """Before the fix: a TC-MEDIA-* plan/store pair produced 'OK: 0 tagged
    task(s)... no contradictions' regardless of real content, because the
    hardcoded RPR-only regex matched nothing. Same shape, but now a real
    contradiction (plan says DONE, store says TODO) must be caught."""
    store = _write_store(tmp_path, [_row("TC-MEDIA-01", "TODO")])
    md = tmp_path / "plan.md"
    md.write_text("**TC-MEDIA-01 — write gap report [STATUS: DONE]**\n", encoding="utf-8")
    assert parity.main(["--plan-file", str(md), "--taskcards", str(store)]) == 1


# ── real mission artifact ─────────────────────────────────────────────────

def test_real_mission_store_passes_against_real_plan():
    """The mission's own taskcards.jsonl must not contradict the plan markdown.
    Skips gracefully if the plan file (outside the repo) is unavailable in CI."""
    repo_root = Path(__file__).resolve().parents[3]
    store = repo_root / "reports" / "plan_state" / "aspose-org-foss-refresh-tidy-lightning" / "taskcards.jsonl"
    plan = Path.home() / ".claude" / "plans" / "aspose-org-foss-refresh-tidy-lightning.md"
    if not store.is_file() or not plan.is_file():
        import pytest
        pytest.skip("mission store or external plan file unavailable")
    plan_tags = parity.extract_plan_tags(plan.read_text(encoding="utf-8"))
    problems = parity.find_contradictions(plan_tags, parity.load_taskcards(store))
    assert problems == [], f"real plan/store parity drift: {problems}"
