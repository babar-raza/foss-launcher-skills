"""TC-SG-11 (2026-08-31 stale-guard plan): full end-to-end runs of the real,
unmodified scripts/pre-commit-audit.sh via precommit_full_run_harness.py.

Complements (does not replace) the existing per-step block harnesses
(test_precommit_audit_step5_step10.py, _step34.py, _step_numbering.py),
which extract and stub-wrap ONE step's logic in isolation. What only a
full-script run can prove:
  - real sequencing: does an early step's mutation (e.g. Step 9's
    content_hash correction) survive correctly into a later step's view
    of the same file, in the SAME process, through the SAME script?
  - real short-circuit: does a blocking step's `_pc_exit` genuinely stop
    every later step from running at all (not just report failure while
    continuing) -- the exact "fake 3-line Tier-1 scripts were why five
    defects shipped unseen" blind spot the 2026-08-20 report named
    (Root Cause 3), reproduced here against the REAL script instead of a
    stand-in.
  - real step-tracking integrity end-to-end: the printed summary table's
    row count/order across a genuine full run, not a synthetic scenario.
"""
from __future__ import annotations

from precommit_full_run_harness import full_run_fixture  # noqa: F401  (fixture import)


def test_clean_run_passes_every_applicable_step(full_run_fixture):
    """No staged changes at all: every step must resolve to PASS or SKIP,
    never FAIL, and the script must exit 0 -- the baseline every other
    scenario in this file is a deliberate deviation from."""
    fixture = full_run_fixture
    fixture.reset()

    result = fixture.run_precommit()

    assert result.returncode == 0, result.stdout + result.stderr
    assert "FAIL" not in result.stdout, result.stdout
    summary_start = result.stdout.index("=== Pre-commit Summary ===")
    summary = result.stdout[summary_start:]
    # Asserted by step NAME, not ordinal number -- the ordinal shifts by one
    # every time a new step is inserted earlier in the script (found live,
    # 2026-09-17 HOOK-01: adding Step 5b pushed every later step's printed
    # number up by one and silently broke this exact assertion until this
    # test was actually re-run against the real script).
    assert "stale file regression" in summary
    assert "subprocess encoding parity" in summary
    # MT069 HC-23: when _PC_NAMES and _PC_RESULTS drift apart the hook prints an
    # "INTERNAL ERROR ... desynchronized" banner. An evaluator gate that closed
    # another step's slot printed it on EVERY full run from 2026-09-17, and this
    # test kept passing -- so assert its absence, and that the gate has its own row.
    assert "INTERNAL ERROR" not in result.stderr, result.stderr
    assert "evaluator version bump" in summary
    # A genuinely complete run reaches deep into the step list -- proves
    # the whole chain executed, not just the first few steps.
    assert summary.count("PASS") + summary.count("SKIP") >= 30


def test_real_violation_short_circuits_and_blocks(full_run_fixture):
    """A genuine filename-convention violation (Step 4) must BLOCK the
    real script -- and, critically, no step after Step 4 may appear in
    the summary at all, proving `_pc_exit` genuinely terminated the
    script rather than merely recording a failure and continuing."""
    fixture = full_run_fixture
    fixture.reset()
    fixture.stage_file(
        "content/kb.aspose.org/en/pdf/cpp/Bad_File_Name.md",
        "---\ntitle: Test\n---\n\nBody.\n",
    )

    result = fixture.run_precommit()

    assert result.returncode == 1, result.stdout + result.stderr
    assert "BLOCKED" in result.stdout
    assert "VIOLATION" in result.stdout
    summary_start = result.stdout.index("=== Pre-commit Summary ===")
    summary = result.stdout[summary_start:]
    assert "Step 4 filename conventions" in summary
    assert "FAIL" in summary
    # Nothing past the blocking step ever ran -- the real short-circuit
    # proof this file exists for.
    assert "Step 5" not in summary
    assert "Step 34" not in summary
    assert "Step 38" not in summary


def test_gate5b_locale_alias_leak_blocks_the_real_commit(full_run_fixture):
    """HOOK-01 (ASPOSE-BLOG-DEPLOY-ALIAS-RECURRENCE-001, 2026-09-17): Step 5b
    (locale frontmatter contamination) must fire under a REAL run of the
    real, unmodified script -- not just the standalone check_locale_
    frontmatter_contamination.py script in isolation (already covered by
    scripts/ci/tests/test_check_locale_frontmatter_contamination.py) and
    not just a hand-simulated snippet. This is the one gap those two could
    not close: proof against the actual hook mechanism a real `git commit`
    would invoke, including Step 5's English-only filter correctly SKIPping
    (this fixture is a non-English locale file) rather than masking Step 5b.
    """
    fixture = full_run_fixture
    fixture.reset()
    fixture.stage_file(
        "content/kb.aspose.org/de/pdf/cpp/sample-page.md",
        "---\ntitle: Test\naliases: [/old-slug/]\n---\n\nBody.\n",
        force=True,
    )

    result = fixture.run_precommit()

    assert result.returncode == 1, result.stdout + result.stderr
    assert "BLOCKED: Locale frontmatter contamination" in result.stdout
    assert "aliases" in result.stdout
    summary_start = result.stdout.index("=== Pre-commit Summary ===")
    summary = result.stdout[summary_start:]
    assert "locale frontmatter contamination" in summary
    assert "FAIL" in summary
    # Confirms Step 5's own English-only filter correctly SKIPped (this
    # fixture is a "de" file, not English) rather than accidentally
    # catching -- and therefore masking -- this defect itself.
    assert "API accuracy audit" in summary


def test_gate5b_allows_commit_once_leaked_alias_is_removed(full_run_fixture):
    """Companion to the block test above: the same fixture, fixed the same
    way the real incident was fixed (strip the aliases: key from the
    non-English copy), must pass Step 5b and reach the end of the script
    cleanly -- proving this is a real, working gate, not a permanently
    blocking one."""
    fixture = full_run_fixture
    fixture.reset()
    fixture.stage_file(
        "content/kb.aspose.org/de/pdf/cpp/sample-page.md",
        "---\ntitle: Test\n---\n\nBody.\n",
        force=True,
    )

    result = fixture.run_precommit()

    assert result.returncode == 0, result.stdout + result.stderr
    assert "BLOCKED: Locale frontmatter contamination" not in result.stdout
    summary_start = result.stdout.index("=== Pre-commit Summary ===")
    summary = result.stdout[summary_start:]
    assert "locale frontmatter contamination" in summary
    # Asserted by name, not ordinal number -- see the same note on
    # test_clean_run_passes_every_applicable_step above.
    assert "stale file regression" in summary


def test_wrong_author_identity_blocks_at_the_identity_step(full_run_fixture):
    """2026-08-31 "Harness" identity incident regression test: a wrong git
    author identity (forced here via extra_env, the same seam a real stale
    .git/config override would produce via ambient config instead) must
    BLOCK at the author-identity step, with no staged changes needed at all
    -- this check is unconditional, unlike most other steps."""
    fixture = full_run_fixture
    fixture.reset()

    result = fixture.run_precommit(extra_env={
        "GIT_AUTHOR_NAME": "Harness",
        "GIT_AUTHOR_EMAIL": "harness@test.local",
        "GIT_COMMITTER_NAME": "Harness",
        "GIT_COMMITTER_EMAIL": "harness@test.local",
    })

    assert result.returncode == 1, result.stdout + result.stderr
    assert "BLOCKED: Commit author identity is wrong." in result.stdout
    assert "Harness <harness@test.local>" in result.stdout
    summary_start = result.stdout.index("=== Pre-commit Summary ===")
    summary = result.stdout[summary_start:]
    assert "author identity" in summary
    assert "FAIL" in summary


def test_reports_boundary_violation_blocks_at_step1_not_step4(full_run_fixture):
    """A DIFFERENT real violation (a staged reports/ file, Step 1) must
    block at ITS OWN step, not Step 4 -- proving the harness distinguishes
    genuinely different failure sites, not just "something failed"."""
    fixture = full_run_fixture
    fixture.reset()
    fixture.stage_file("reports/should-not-be-staged.json", "{}\n", force=True)

    result = fixture.run_precommit()

    assert result.returncode == 1, result.stdout + result.stderr
    assert "BLOCKED" in result.stdout
    assert "reports/" in result.stdout
    summary_start = result.stdout.index("=== Pre-commit Summary ===")
    summary = result.stdout[summary_start:]
    assert "Step 1 reports/ boundary" in summary
    assert "Step 4" not in summary
