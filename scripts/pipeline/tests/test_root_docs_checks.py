"""Tests for root_docs_checks.py — deterministic checks for /root-docs-refresh (S-121).

Golden-fixture tests are built directly from this repo's real, independently-diagnosed
defects (see plan: moonlit-strolling-sunset.md) so the test suite encodes the sprint's
findings as regression cases, not synthetic examples. Idempotency tests assert the property
that actually defines "consistent across reruns" for the mechanical layer: identical input
must produce byte-identical output.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import root_docs_checks as rdc


# ---------------------------------------------------------------------------
# check_dead_path_references
# ---------------------------------------------------------------------------


def test_dead_path_references_flags_deleted_translator_script(tmp_path):
    # Golden fixture: the real defect found in OPERATOR_GUIDE.md/RUNBOOK.md — the
    # scripts/translator/ package was deleted 2026-07-02 but still invoked in prose.
    text = (
        "### translate\n"
        "```bash\n"
        ".venv/Scripts/python scripts/translator/cli.py batch {family} {platform} --locales all\n"
        "```\n"
    )
    findings = rdc.check_dead_path_references(text, tmp_path)
    assert len(findings) == 1
    assert findings[0]["tier"] == rdc.HARD_GATE
    assert findings[0]["path"] == "scripts/translator/cli.py"


def test_dead_path_references_passes_existing_path(tmp_path):
    real = tmp_path / "scripts" / "pipeline" / "commands" / "content"
    real.mkdir(parents=True)
    (real / "audit.py").write_text("", encoding="utf-8")
    text = (
        "```bash\n"
        ".venv/Scripts/python scripts/pipeline/commands/content/audit.py {family} {platform}\n"
        "```\n"
    )
    assert rdc.check_dead_path_references(text, tmp_path) == []


def test_dead_path_references_ignores_placeholder_braces(tmp_path):
    # {family}/{platform}-style illustrative paths must not be flagged — this is the
    # deliberate conservatism the docstring calls out.
    text = "```bash\npython scripts/pipeline/{family}/{platform}/run.py\n```\n"
    assert rdc.check_dead_path_references(text, tmp_path) == []


def test_dead_path_references_ignores_prose_outside_fences(tmp_path):
    text = "See scripts/translator/cli.py for details (not a code block).\n"
    assert rdc.check_dead_path_references(text, tmp_path) == []


def test_dead_path_references_is_idempotent(tmp_path):
    text = "```bash\npython scripts/translator/cli.py batch\n```\n"
    first = rdc.check_dead_path_references(text, tmp_path)
    second = rdc.check_dead_path_references(text, tmp_path)
    assert first == second


# ---------------------------------------------------------------------------
# check_skill_id_references
# ---------------------------------------------------------------------------

_REGISTRY_FIXTURE = (
    "| Skill | ID | Purpose |\n"
    "|-------|----|--------|\n"
    "| content-check | S-23 | Deterministic API accuracy audit |\n"
    "| content-audit | S-32 | Semantic knowledge verification |\n"
)


def test_skill_id_references_flags_real_defect():
    # Golden fixture: OPERATOR_GUIDE.md:116 labels content-check as S-32; registry says S-23.
    text = "### content-check (S-32)\n```bash\n.venv/Scripts/python scripts/pipeline/commands/content/audit.py\n```\n"
    findings = rdc.check_skill_id_references(text, _REGISTRY_FIXTURE)
    assert len(findings) == 1
    f = findings[0]
    assert f["tier"] == rdc.HARD_GATE
    assert f["skill"] == "content-check"
    assert f["cited_id"] == "S-32"
    assert f["real_id"] == "S-23"


def test_skill_id_references_passes_correct_id():
    text = "### content-check (S-23)\n"
    assert rdc.check_skill_id_references(text, _REGISTRY_FIXTURE) == []


def test_skill_id_references_ignores_unregistered_names():
    text = "### some-future-skill (S-999)\n"
    assert rdc.check_skill_id_references(text, _REGISTRY_FIXTURE) == []


def test_skill_id_references_ignores_last_word_of_longer_heading():
    # Regression test for a real false positive found live against RUNBOOK.md:370:
    # "### 10c. Triage findings to backlog (S-95)" is NOT citing "backlog" as S-95 --
    # it's a section title ending near an unrelated skill's parenthetical ID
    # (discovery-triage, S-95). "backlog" is a real registered skill (S-88), so a
    # loose mid-line search would wrongly flag this as a mismatch.
    registry = _REGISTRY_FIXTURE + "| backlog | S-88 | Unified backlog management |\n"
    text = "### 10c. Triage findings to backlog (S-95)\n"
    assert rdc.check_skill_id_references(text, registry) == []


def test_skill_id_references_is_idempotent():
    text = "### content-check (S-32)\n### content-audit (S-32)\n"
    first = rdc.check_skill_id_references(text, _REGISTRY_FIXTURE)
    second = rdc.check_skill_id_references(text, _REGISTRY_FIXTURE)
    assert first == second


# ---------------------------------------------------------------------------
# check_grade_contract_sync
# ---------------------------------------------------------------------------


def test_grade_contract_sync_flags_freeze_version_mismatch():
    # Golden fixture: real defect — doc says 17, code says 18 (evidence_depth graduation,
    # 2026-07-14, never logged in GRADE_CONTRACT.md's changelog).
    grade_contract_text = (
        "### v1.1 amendment (2026-04-24)\n"
        "ELV bumped 16->17. Current frozen baseline: EVALUATOR_FREEZE_VERSION = 17.\n"
    )
    init_text = 'EVALUATOR_FREEZE_VERSION: str | None = "18"\n'
    findings = rdc.check_grade_contract_sync(grade_contract_text, init_text, "")
    version_findings = [f for f in findings if f["field"] == "EVALUATOR_FREEZE_VERSION"]
    assert len(version_findings) == 1
    assert version_findings[0]["doc_value"] == "17"
    assert version_findings[0]["code_value"] == "18"
    assert version_findings[0]["tier"] == rdc.HARD_GATE


def test_grade_contract_sync_passes_matching_version():
    grade_contract_text = "Current frozen baseline: EVALUATOR_FREEZE_VERSION = 18.\n"
    init_text = 'EVALUATOR_FREEZE_VERSION = "18"\n'
    findings = rdc.check_grade_contract_sync(grade_contract_text, init_text, "")
    assert [f for f in findings if f["field"] == "EVALUATOR_FREEZE_VERSION"] == []


def test_grade_contract_sync_flags_missing_category_row():
    # Golden fixture: real defect — grade_config.yaml defines EG_GROUNDING with no
    # corresponding row in GRADE_CONTRACT.md's §3 table.
    grade_contract_text = (
        "| Category | Levels | Ceiling | Evaluator |\n"
        "|----------|--------|---------|-----------|\n"
        "| TA | WARN, FAIL | C | type_accuracy |\n"
    )
    grade_config_text = "EG_GROUNDING:\n  ceiling: B\nTA:\n  ceiling: C\n"
    findings = rdc.check_grade_contract_sync(grade_contract_text, "", grade_config_text)
    category_findings = [f for f in findings if f["field"] == "category_ceiling_table"]
    assert len(category_findings) == 1
    assert category_findings[0]["missing_category"] == "EG"


def test_grade_contract_sync_ignores_stale_historical_mentions():
    # Regression test for a real bug found live 2026-08-07 while writing GRADE_CONTRACT.md's
    # own v1.2 changelog entry: the doc's changelog is reverse-chronological (newest first),
    # and every past ELV-bump entry ALSO mentions "EVALUATOR_FREEZE_VERSION = N" as historical
    # record. A loose "last EVALUATOR_FREEZE_VERSION = N mention in the document" extraction
    # resolves to a stale historical value, not the current one. Only the phrase "Current
    # frozen baseline: EVALUATOR_FREEZE_VERSION = N" is the document's deliberate, singular
    # "this is current" marker.
    grade_contract_text = (
        "### v1.2 (2026-08-07)\n"
        "- Current frozen baseline: EVALUATOR_FREEZE_VERSION = 18.\n\n"
        "### v1.1 (2026-04-24)\n"
        "- Hard-freeze governance declared. `EVALUATOR_FREEZE_VERSION = \"16\"` activated.\n\n"
        "### v1.1 amendment (2026-04-24)\n"
        "- EVALUATOR_FREEZE_VERSION updated to \"17\" (superseded, historical record only).\n"
    )
    init_text = 'EVALUATOR_FREEZE_VERSION = "18"\n'
    findings = rdc.check_grade_contract_sync(grade_contract_text, init_text, "")
    version_findings = [f for f in findings if f["field"] == "EVALUATOR_FREEZE_VERSION"]
    assert version_findings == [], f"expected no mismatch (doc correctly states 18); got: {version_findings}"


def test_grade_contract_sync_is_idempotent():
    grade_contract_text = "Current frozen baseline: EVALUATOR_FREEZE_VERSION = 17.\n"
    init_text = 'EVALUATOR_FREEZE_VERSION = "18"\n'
    first = rdc.check_grade_contract_sync(grade_contract_text, init_text, "")
    second = rdc.check_grade_contract_sync(grade_contract_text, init_text, "")
    assert first == second


# ---------------------------------------------------------------------------
# check_volatile_count_hardcoding
# ---------------------------------------------------------------------------


def test_volatile_count_flags_bare_product_count():
    # Golden fixture: real defect — "0 FAILs across all 13 products" in OPERATOR_GUIDE.md.
    text = "Running audit.py all currently shows 0 FAILs across all 13 products.\n"
    findings = rdc.check_volatile_count_hardcoding(text)
    assert len(findings) == 1
    assert findings[0]["tier"] == rdc.HEURISTIC


def test_volatile_count_ignores_dated_snapshot_prose():
    text = "Review compiled from repository inspection on 2026-06-27: 16 products and 4 platforms, as of 2026-06-27.\n"
    assert rdc.check_volatile_count_hardcoding(text) == []


def test_volatile_count_ignores_live_source_pointer():
    text = "See data/products.json for the current active-product count.\n"
    assert rdc.check_volatile_count_hardcoding(text) == []


def test_volatile_count_is_idempotent():
    text = "batch SHA comparison across all 15 active products\n"
    first = rdc.check_volatile_count_hardcoding(text)
    second = rdc.check_volatile_count_hardcoding(text)
    assert first == second


# ---------------------------------------------------------------------------
# check_dead_snapshot_file
# ---------------------------------------------------------------------------


def _fake_git_log(dates: list[str]):
    def _fn(path: Path, repo_root: Path) -> list[str]:
        return dates
    return _fn


def test_dead_snapshot_file_flags_old_single_commit(tmp_path):
    # Golden fixture: TASK_BACKLOG_20260521.md shape — one commit, long ago.
    old_date = (datetime.now(tz=timezone.utc) - timedelta(days=78)).isoformat()
    finding = rdc.check_dead_snapshot_file(
        tmp_path / "TASK_BACKLOG_20260521.md",
        tmp_path,
        git_log_fn=_fake_git_log([old_date]),
    )
    assert finding is not None
    assert finding["tier"] == rdc.HEURISTIC
    assert finding["commit_count"] == 1


def test_dead_snapshot_file_ignores_recent_single_commit(tmp_path):
    recent_date = (datetime.now(tz=timezone.utc) - timedelta(days=3)).isoformat()
    finding = rdc.check_dead_snapshot_file(
        tmp_path / "NEW_FILE.md",
        tmp_path,
        git_log_fn=_fake_git_log([recent_date]),
    )
    assert finding is None


def test_dead_snapshot_file_ignores_actively_revised_file(tmp_path):
    d1 = (datetime.now(tz=timezone.utc) - timedelta(days=90)).isoformat()
    d2 = (datetime.now(tz=timezone.utc) - timedelta(days=1)).isoformat()
    finding = rdc.check_dead_snapshot_file(
        tmp_path / "RUNBOOK.md",
        tmp_path,
        git_log_fn=_fake_git_log([d2, d1]),
    )
    assert finding is None


def test_dead_snapshot_file_ignores_untracked_file(tmp_path):
    finding = rdc.check_dead_snapshot_file(
        tmp_path / "TASK_BACKLOG.md",
        tmp_path,
        git_log_fn=_fake_git_log([]),
    )
    assert finding is None


def test_dead_snapshot_file_is_idempotent(tmp_path):
    old_date = (datetime.now(tz=timezone.utc) - timedelta(days=78)).isoformat()
    fixed_now = datetime.now(tz=timezone.utc)
    kwargs = dict(
        path=tmp_path / "TASK_BACKLOG_20260521.md",
        repo_root=tmp_path,
        git_log_fn=_fake_git_log([old_date]),
        now=fixed_now,
    )
    first = rdc.check_dead_snapshot_file(**kwargs)
    second = rdc.check_dead_snapshot_file(**kwargs)
    assert first == second
