"""Tests for .github/workflows/content-governance-checks.yml (TC-CIA-06 / TC-CIR-02,
2026-08-14 CI reliability reassessment).

content-audit.yml is pull_request-only and never fires under this repo's real
direct-to-main push model. A systematic re-audit of its ~40 steps found 18 blocking
checks with zero other enforcement anywhere. This workflow gives them a live,
push-triggered home. These are read-only YAML/text assertions — no subprocess
execution of the workflow itself (that's covered by direct smoke-test runs during
implementation, recorded in the commit message and plan evidence).
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "content-governance-checks.yml"


@pytest.fixture(scope="module")
def workflow_text() -> str:
    return _WORKFLOW.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def workflow_body_only(workflow_text) -> str:
    """The `jobs:` section onward — excludes the file-level header comment block,
    which deliberately quotes several NOT-migrated script/pattern names in its own
    explanatory prose and would false-positive a naive substring search."""
    return workflow_text[workflow_text.index("jobs:"):]


@pytest.fixture(scope="module")
def workflow_yaml() -> dict:
    return yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))


def test_workflow_file_exists():
    assert _WORKFLOW.exists()


def test_yaml_parses(workflow_yaml):
    assert "jobs" in workflow_yaml
    assert "governance-checks" in workflow_yaml["jobs"]


def test_triggers_on_push_to_main_not_pull_request_only(workflow_yaml):
    """The whole point of this workflow: content-audit.yml is pull_request-only
    and never fires. This one must trigger on push."""
    on = workflow_yaml[True] if True in workflow_yaml else workflow_yaml.get("on", {})
    assert "push" in on, "must trigger on push — pull_request-only repeats content-audit.yml's mistake"
    assert on["push"].get("branches") == ["main"]
    assert "workflow_dispatch" in on


def test_installs_real_hugo_not_silent_skip(workflow_text, workflow_body_only):
    """TC-CIR-02: content-audit.yml's Hugo check is `hugo version || exit 0` with no
    install step anywhere — a near-certain silent no-op. This workflow must actually
    install Hugo before running the build check."""
    assert "peaceiris/actions-hugo" in workflow_text or "hugo-version" in workflow_text, (
        "must install Hugo via a real setup action, not rely on hugo already being on PATH"
    )
    assert 'hugo version || { echo "SKIP' not in workflow_body_only, (
        "must not carry over content-audit.yml's exact silent-skip guard now that Hugo is installed"
    )


def test_computes_diff_base_correctly_for_multi_commit_pushes(workflow_text):
    """HEAD~1 is wrong for a push carrying more than one commit — must use
    github.event.before (the actual pre-push SHA), with a workflow_dispatch fallback."""
    assert "github.event.before" in workflow_text
    assert "DIFF_BASE" in workflow_text
    assert "HEAD~1...HEAD" not in workflow_text, "must not use the multi-commit-unsafe HEAD~1 form"


@pytest.mark.parametrize("script_name", [
    "check-blog-slugs.py",
    "check_blog_family_routes.py",
    "check_blog_platform_indexes.py",
    "check_family_icon_uniqueness.py",
    "check_audit_regression.py",
    "check_grade_presence.py",
    "check_grade_integrity.py",
    "check_manifest_consistency.py",
    "check_evaluator_freeze.py",
    "validate_frontmatter.py",
    "check_skill_readme_coverage.py",
    "check_skill_registry.py",
    "check_dar_coverage.py",
    "check_dar_table_accuracy.py",
    "check_pipeline_path_integrity.py",
    "check_clone_cache_refs.py",
    "check_pipeline_registration.py",
    "check_hugo_build.sh",
])
def test_confirmed_uncovered_check_is_migrated(workflow_text, script_name):
    """Each of the 18 checks confirmed (via direct smoke test during implementation)
    to have zero other live enforcement must appear in this workflow."""
    assert script_name in workflow_text, f"{script_name} must be migrated here"


@pytest.mark.parametrize("step_name_fragment", [
    "Check blog platform indexes",
    "Check for audit regressions",
    "Check grade block integrity",
    "Check evaluator freeze",
    "Check DAR coverage alignment",
    "Check pipeline script registration",
])
def test_landing_state_failures_are_continue_on_error(workflow_yaml, step_name_fragment):
    """Real, pre-existing failures found during this workflow's own first smoke test
    (2026-08-14) must land as continue-on-error, not immediately red the whole
    workflow on day one — matches this repo's own established
    "graduated to blocking" precedent. Each must have a comment naming why."""
    steps = workflow_yaml["jobs"]["governance-checks"]["steps"]
    matching = [s for s in steps if step_name_fragment in s.get("name", "")]
    assert matching, f"no step found matching {step_name_fragment!r}"
    assert matching[0].get("continue-on-error") is True, (
        f"{step_name_fragment!r} found a real failure during smoke test — "
        "must land as continue-on-error, not blocking, until the underlying issue is fixed"
    )


@pytest.mark.parametrize("step_name_fragment", [
    "Check blog slug hygiene",
    "Check family icon uniqueness",
    "Check grade presence",
    "Check manifest/frontmatter consistency",
    "Check skill documentation coverage",
    "Check skill registry completeness",
    "Check DAR-table skill-ID accuracy",
    "Check pipeline path integrity",
    "Check clone cache refs",
    "Hugo build verification",
])
def test_passing_checks_stay_blocking(workflow_yaml, step_name_fragment):
    """Checks confirmed passing cleanly during the smoke test must stay fully
    blocking — no unnecessary softening of a check that already works."""
    steps = workflow_yaml["jobs"]["governance-checks"]["steps"]
    matching = [s for s in steps if step_name_fragment in s.get("name", "")]
    assert matching, f"no step found matching {step_name_fragment!r}"
    assert matching[0].get("continue-on-error") is not True, (
        f"{step_name_fragment!r} passed cleanly during smoke test — should stay blocking"
    )


def test_does_not_duplicate_checks_already_live_elsewhere(workflow_body_only):
    """Checks with a genuine, live, push-triggered or local equivalent must not be
    re-implemented here — would create a 3rd (or 4th) source of truth. Checked
    against the workflow body only (excludes the header comment's own explanatory
    listing of these same NOT-migrated names)."""
    # sync_skills.py --check is already push-live in skill-governance.yml
    assert "sync_skills.py --check" not in workflow_body_only
    # deletion-approval PR compliance is redundant with pre-commit Step 0b's DGR gate
    assert "check_pr_deletion_approvals" not in workflow_body_only
    assert "check_pr_override_compliance" not in workflow_body_only
