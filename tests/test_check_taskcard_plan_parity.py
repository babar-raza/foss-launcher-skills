"""Tests for scripts/ci/checks/check_taskcard_plan_parity.py.

Rewritten 2026-08-30 alongside the module itself: the original
done/not-done-word heuristic is gone, replaced by source's real
[STATUS: ...]-tag design (see the module's own docstring for why)."""
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci" / "checks"))

import check_taskcard_plan_parity as ctpp  # noqa: E402


def _write_taskcards(tmp_path, rows):
    path = tmp_path / "taskcards.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return path


def test_load_taskcards_latest_last_occurrence_wins(tmp_path):
    rows = [
        {"task_id": "T-1", "status": "TODO"},
        {"task_id": "T-1", "status": "CLOSED"},
    ]
    path = _write_taskcards(tmp_path, rows)
    latest = ctpp.load_taskcards_latest(path)
    assert latest["T-1"]["status"] == "CLOSED"


def test_load_taskcards_latest_missing_file_returns_empty(tmp_path):
    assert ctpp.load_taskcards_latest(tmp_path / "nonexistent.jsonl") == {}


def test_infer_task_id_pattern_derives_prefix_from_numeric_suffix_ids():
    pattern = ctpp.infer_task_id_pattern(["SYNC-1", "SYNC-5"])
    assert pattern.findall("mentions SYNC-1 and SYNC-9 here") == ["SYNC-1", "SYNC-9"]


def test_infer_task_id_pattern_falls_back_to_literal_for_non_numeric_ids():
    pattern = ctpp.infer_task_id_pattern(["SYNC-8-full", "SYNC-1-git-plumb-commit"])
    assert pattern.findall("about SYNC-8-full today") == ["SYNC-8-full"]
    assert pattern.findall("no mention of SYNC-8 alone") == []


def test_infer_task_id_pattern_empty_input_matches_nothing():
    pattern = ctpp.infer_task_id_pattern([])
    assert pattern.findall("SYNC-1 SYNC-2 anything") == []


def test_extract_plan_tags_only_matches_lines_with_explicit_status_tag():
    pattern = ctpp.infer_task_id_pattern(["SYNC-5"])
    text = "SYNC-5 -- Java cluster [STATUS: CLOSED]\nSYNC-5 mentioned again with no tag\n"
    tags = ctpp.extract_plan_tags(text, pattern)
    assert tags == {"SYNC-5": "CLOSED"}


def test_extract_plan_tags_ignores_bare_mention_without_tag():
    """The exact false-positive regression this rewrite fixes: a line that
    merely mentions a task id near done/not-done vocabulary, with no
    [STATUS: ...] tag, must never be treated as a claim."""
    pattern = ctpp.infer_task_id_pattern(["SYNC-5"])
    text = "SYNC-5's closeout rules: closes when the scoping assessment is done.\n"
    tags = ctpp.extract_plan_tags(text, pattern)
    assert tags == {}


def test_extract_plan_tags_first_tag_per_id_wins():
    pattern = ctpp.infer_task_id_pattern(["SYNC-5"])
    text = "SYNC-5 [STATUS: CLOSED]\nlater SYNC-5 [STATUS: PAUSED]\n"
    tags = ctpp.extract_plan_tags(text, pattern)
    assert tags == {"SYNC-5": "CLOSED"}


def test_markdown_status_bucket_done():
    assert ctpp.markdown_status_bucket("DONE") == ctpp.DONE
    assert ctpp.markdown_status_bucket("closed") == ctpp.DONE


def test_markdown_status_bucket_partial_qualifier_downgrades_done():
    assert ctpp.markdown_status_bucket("DONE -- steps 1-2 only, not yet complete") == ctpp.PARTIAL


def test_markdown_status_bucket_defaults_to_not_started():
    assert ctpp.markdown_status_bucket("TODO") == ctpp.NOT_STARTED
    assert ctpp.markdown_status_bucket("something unrecognized") == ctpp.NOT_STARTED


def test_store_status_bucket_excluded_status_returns_none():
    assert ctpp.store_status_bucket("OUT_OF_SCOPE") is None
    assert ctpp.store_status_bucket("BLOCKED_EXTERNAL") is None


def test_store_status_bucket_maps_known_statuses():
    assert ctpp.store_status_bucket("CLOSED") == ctpp.DONE
    assert ctpp.store_status_bucket("PAUSED") == ctpp.PARTIAL
    assert ctpp.store_status_bucket("TODO") == ctpp.NOT_STARTED


def test_find_contradictions_flags_done_tag_against_nonterminal_store():
    plan_tags = {"T-1": "DONE"}
    taskcards = {"T-1": {"task_id": "T-1", "status": "TODO"}}
    problems = ctpp.find_contradictions(plan_tags, taskcards)
    assert len(problems) == 1
    assert problems[0]["kind"] == "contradiction"


def test_find_contradictions_no_issue_when_tag_matches_store():
    plan_tags = {"T-1": "DONE"}
    taskcards = {"T-1": {"task_id": "T-1", "status": "CLOSED"}}
    assert ctpp.find_contradictions(plan_tags, taskcards) == []


def test_find_contradictions_flags_tagged_but_missing_from_store():
    plan_tags = {"GHOST": "DONE"}
    problems = ctpp.find_contradictions(plan_tags, {})
    assert len(problems) == 1
    assert problems[0]["kind"] == "tagged_but_missing_from_store"


def test_find_contradictions_excluded_store_status_never_flagged():
    plan_tags = {"T-1": "TODO"}
    taskcards = {"T-1": {"task_id": "T-1", "status": "OUT_OF_SCOPE"}}
    assert ctpp.find_contradictions(plan_tags, taskcards) == []


def test_find_contradictions_strict_coverage_flags_untagged_store_task():
    taskcards = {"T-1": {"task_id": "T-1", "status": "TODO"}}
    problems = ctpp.find_contradictions({}, taskcards, strict_coverage=True)
    assert len(problems) == 1
    assert problems[0]["kind"] == "untagged_under_strict_coverage"


def test_main_exit_0_when_no_contradictions(tmp_path):
    taskcards_path = _write_taskcards(tmp_path, [{"task_id": "T-1", "status": "CLOSED"}])
    plan_path = tmp_path / "plan.md"
    plan_path.write_text("T-1 [STATUS: DONE]\n", encoding="utf-8")
    code = ctpp.main(["--plan-file", str(plan_path), "--taskcards", str(taskcards_path)])
    assert code == 0


def test_main_exit_1_when_contradiction_found(tmp_path):
    taskcards_path = _write_taskcards(tmp_path, [{"task_id": "T-1", "status": "TODO"}])
    plan_path = tmp_path / "plan.md"
    plan_path.write_text("T-1 [STATUS: DONE]\n", encoding="utf-8")
    code = ctpp.main(["--plan-file", str(plan_path), "--taskcards", str(taskcards_path)])
    assert code == 1


def test_main_ignores_bare_mention_without_status_tag(tmp_path):
    """End-to-end confirmation of the false-positive fix: T-1 appears near
    done-language but carries no [STATUS: ...] tag -- store says TODO, and
    main() must still exit 0."""
    taskcards_path = _write_taskcards(tmp_path, [{"task_id": "T-1", "status": "TODO"}])
    plan_path = tmp_path / "plan.md"
    plan_path.write_text("T-1's closeout rule: closes when review is done.\n", encoding="utf-8")
    code = ctpp.main(["--plan-file", str(plan_path), "--taskcards", str(taskcards_path)])
    assert code == 0


def test_main_exit_2_when_plan_file_missing(tmp_path):
    taskcards_path = _write_taskcards(tmp_path, [{"task_id": "T-1", "status": "TODO"}])
    code = ctpp.main(["--plan-file", str(tmp_path / "nope.md"), "--taskcards", str(taskcards_path)])
    assert code == 2


def test_main_exit_0_when_taskcards_file_missing(tmp_path):
    plan_path = tmp_path / "plan.md"
    plan_path.write_text("T-1 [STATUS: DONE]\n", encoding="utf-8")
    code = ctpp.main(["--plan-file", str(plan_path), "--taskcards", str(tmp_path / "nope.jsonl")])
    assert code == 0
