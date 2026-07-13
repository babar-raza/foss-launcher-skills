"""Tests for co-author validation logic in scripts/commit-msg-skills.sh.

The commit-msg hook validates that agent commits (those containing "Skills invoked:")
carry exactly one Co-authored-by trailer.  It no longer injects any trailer itself —
injection caused double attribution across agents (RC-1 in shiny-rolling-petal plan).

Covered scenarios:
  CA-01  Agent commit, 1 co-author                    → allowed  (exit 0)
  CA-02  Agent commit, 0 co-authors                   → blocked  (exit 1)
  CA-03  Agent commit, 2 co-authors (double attr)     → blocked  (exit 1)
  CA-04  Human commit, 0 co-authors                   → allowed  (exit 0, hook exits early)
  CA-05  Human commit, 1 co-author                    → allowed  (exit 0, hook exits early)
  CA-06  Agent commit, Codex co-author (correct form) → allowed  (exit 0)
  CA-07  Agent commit, 3 co-authors                   → blocked  (exit 1)
  CA-08  Operator bypass SKIP_SKILL_COMMIT_CHECK=1    → allowed  (exit 0, full bypass)

Note: the co-author checks run BEFORE the hook's staged-file gate, so blocked
cases (CA-02/03/07) are staging-independent. Allowed cases exit 0 at the
staged-file gate. _run_hook isolates the hook from the developer's real repo
state (temp GIT_INDEX_FILE seeded from HEAD + empty SKILL_RUN_RECORDS_DIR) so
live staged content or pending skill-run records cannot fail these tests
(TC-W3H-007).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_HOOK = _REPO_ROOT / "scripts" / "commit-msg-skills.sh"


def _find_bash() -> str:
    if sys.platform == "win32":
        git_bash = os.path.join("C:", os.sep, "Program Files", "Git", "usr", "bin", "bash.exe")
        if os.path.exists(git_bash):
            return git_bash
    return "bash"


_BASH = _find_bash()


def _run_hook(msg: str, env_overrides: dict | None = None) -> int:
    """Write msg to a temp file, invoke the hook, return its exit code.

    The hook has two relevant exit paths for co-author tests:

    EXIT-BLOCK (exit 1): co-author count is 0 or >1 — fires before the staged-file
    check, so no git interaction is needed for blocked cases.

    EXIT-ALLOW (exit 0): co-author count == 1 (valid) — hook proceeds to
    ``content_staged`` check.  In the test environment no content files are
    staged, so ``git diff --cached`` returns empty → hook exits 0 early.
    Steps 2+3 (skill ID + run-record) are never reached.

    This design means the test exercises the real hook binary with real git,
    without requiring any test-environment staging shenanigans.
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False,
                                     encoding="utf-8") as f:
        f.write(msg)
        tmp_path = f.name

    # Isolation (TC-W3H-007): the hook consults the REAL repo state, so
    # without these overrides the tests fail spuriously whenever the
    # developer has content staged or a live pending skill-run record.
    #  - GIT_INDEX_FILE: temp index seeded from HEAD -> `git diff --cached`
    #    is deterministically empty for the hook subprocess. The co-author
    #    checks (CA-02/03/07) fire BEFORE the staged-file check, so blocked
    #    cases are unaffected; allowed cases exit 0 at the staged-file gate.
    #  - SKILL_RUN_RECORDS_DIR: empty temp dir -> find-pending sees nothing.
    tmp_index = tempfile.NamedTemporaryFile(suffix=".index", delete=False)
    tmp_index.close()
    tmp_records = tempfile.mkdtemp(prefix="skillruns-")

    try:
        env = dict(os.environ)
        env.pop("SKIP_SKILL_COMMIT_CHECK", None)
        env.pop("GOV_BYPASS_TASKCARD", None)
        env.pop("GOV_BYPASS_REASON", None)
        env["GIT_INDEX_FILE"] = tmp_index.name
        env["SKILL_RUN_RECORDS_DIR"] = tmp_records
        subprocess.run(
            ["git", "read-tree", "HEAD"],
            env=env, cwd=str(_REPO_ROOT), capture_output=True, check=True,
        )
        if env_overrides:
            env.update(env_overrides)

        result = subprocess.run(
            [_BASH, str(_HOOK), tmp_path],
            env=env,
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
        )
        return result.returncode
    finally:
        os.unlink(tmp_path)
        os.unlink(tmp_index.name)
        shutil.rmtree(tmp_records, ignore_errors=True)


# ---------------------------------------------------------------------------
# CA-01: Agent commit with exactly 1 co-author → allowed
# ---------------------------------------------------------------------------
def test_ca01_agent_one_coauthor_allowed():
    msg = (
        "feat(content): update test page\n\n"
        "- Updated test page\n"
        "- Verification: audit.py → 0 FAIL\n\n"
        "Skills invoked: [S-73]\n\n"
        "Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>\n"
    )
    assert _run_hook(msg) == 0, "Agent commit with 1 co-author should be allowed"


# ---------------------------------------------------------------------------
# CA-02: Agent commit with 0 co-authors → blocked
# ---------------------------------------------------------------------------
def test_ca02_agent_zero_coauthors_blocked():
    msg = (
        "feat(content): update test page\n\n"
        "- Updated test page\n\n"
        "Skills invoked: [S-73]\n"
    )
    assert _run_hook(msg) == 1, "Agent commit with 0 co-authors should be blocked"


# ---------------------------------------------------------------------------
# CA-03: Agent commit with 2 co-authors (double attribution bug) → blocked
# ---------------------------------------------------------------------------
def test_ca03_agent_double_coauthor_blocked():
    msg = (
        "feat(content): update test page\n\n"
        "- Updated test page\n\n"
        "Skills invoked: [S-73]\n\n"
        "Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>\n"
        "Co-authored-by: Codex <codex@openai.com>\n"
    )
    assert _run_hook(msg) == 1, "Agent commit with 2 co-authors should be blocked"


# ---------------------------------------------------------------------------
# CA-04: Human commit, no co-author → allowed (hook exits early, no check)
# ---------------------------------------------------------------------------
def test_ca04_human_commit_no_coauthor_allowed():
    msg = (
        "docs: update readme\n\n"
        "- Minor grammar fix\n"
    )
    # Human commits have no "Skills invoked:" line; co-author block is skipped
    assert _run_hook(msg) == 0, "Human commit (no Skills invoked:) should be allowed"


# ---------------------------------------------------------------------------
# CA-05: Human commit, 1 co-author → allowed (hook exits early, no check)
# ---------------------------------------------------------------------------
def test_ca05_human_commit_one_coauthor_allowed():
    msg = (
        "docs: update readme\n\n"
        "- Minor grammar fix\n\n"
        "Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>\n"
    )
    assert _run_hook(msg) == 0, "Human commit with 1 co-author should be allowed"


# ---------------------------------------------------------------------------
# CA-06: Agent commit with Codex co-author → allowed
# ---------------------------------------------------------------------------
def test_ca06_agent_codex_coauthor_allowed():
    msg = (
        "feat(content): update test page\n\n"
        "- Updated test page\n\n"
        "Skills invoked: [S-73]\n\n"
        "Co-authored-by: Codex <codex@openai.com>\n"
    )
    assert _run_hook(msg) == 0, "Agent commit with Codex co-author should be allowed"


# ---------------------------------------------------------------------------
# CA-07: Agent commit with 3 co-authors → blocked
# ---------------------------------------------------------------------------
def test_ca07_agent_triple_coauthor_blocked():
    msg = (
        "feat(content): update test page\n\n"
        "Skills invoked: [S-73]\n\n"
        "Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>\n"
        "Co-authored-by: Codex <codex@openai.com>\n"
        "Co-authored-by: Kilo Code <kilocode@kilocode.ai>\n"
    )
    assert _run_hook(msg) == 1, "Agent commit with 3 co-authors should be blocked"


# ---------------------------------------------------------------------------
# CA-08: Operator bypass + valid co-author → allowed
# The bypass (SKIP_SKILL_COMMIT_CHECK=1) covers the skill-ID and run-record
# checks (Steps 2 and 3), NOT the co-author validation, which fires earlier
# in the hook before the bypass check is reached.  Agents using the bypass
# must still include their co-author trailer.
# ---------------------------------------------------------------------------
def test_ca08_operator_bypass_with_valid_coauthor_allowed():
    msg = (
        "feat(content): emergency fix\n\n"
        "- Emergency content fix\n\n"
        "Skills invoked: [S-73]\n\n"
        "Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>\n"
    )
    # Bypass lets through skill-record check; co-author count (1) is valid.
    assert _run_hook(msg, env_overrides={
        "SKIP_SKILL_COMMIT_CHECK": "1",
        "GOV_BYPASS_TASKCARD": "TC-GOV-TEST-001",
        "GOV_BYPASS_REASON": "test of operator bypass path",
    }) == 0, "Bypass with valid co-author should be allowed"


# ---------------------------------------------------------------------------
# CA-09: Operator bypass + missing co-author → blocked
# The bypass does NOT cover co-author validation; attribution is required
# regardless of bypass mode.
# ---------------------------------------------------------------------------
def test_ca09_operator_bypass_without_coauthor_blocked():
    msg = (
        "feat(content): emergency fix\n\n"
        "- Emergency content fix\n\n"
        "Skills invoked: [S-73]\n"
        # deliberately no co-author — bypass does NOT cover co-author check
    )
    assert _run_hook(msg, env_overrides={
        "SKIP_SKILL_COMMIT_CHECK": "1",
        "GOV_BYPASS_TASKCARD": "TC-GOV-TEST-001",
        "GOV_BYPASS_REASON": "test of operator bypass path",
    }) == 1, "Bypass with missing co-author should still be blocked"
