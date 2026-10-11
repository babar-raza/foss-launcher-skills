"""Tests for check_evaluator_version_bump.py (PKGINSTALL-VERSION-BUMP-AND-LINT).

Added 2026-09-17 (TC-15, MT069-2026-09-16-GHA-MINUTES-REARCHITECTURE) -- this
checker had ZERO test coverage before this file, discovered while root-causing
content-governance-checks.yml's 49% real failure rate (TC-05). Exercises
check()'s pure, injectable logic directly (changed_files/init_head_text/
init_base_text/exemption_diff_lines) rather than the CLI's hardcoded repo-root
reads, so these tests never touch this checkout's real
scripts/pipeline/content_eval/__init__.py.

Coverage:
- an evaluator file changed with no corresponding version bump -> BLOCKED
- the same change with EVALUATOR_VERSIONS[name] bumped -> clean
- the same change with EVALUATOR_LOGIC_VERSION (cross-cutting) bumped instead -> clean
- an EVALUATOR-VERSION-BUMP-EXEMPT marker in the diff -> clean even without a bump
- no evaluator files changed -> clean, trivially

2026-09-17 followup (independent review of TC-15): the tests above all inject
init_head_text, bypassing check()'s real disk/index read entirely -- so none of
them could have caught the fail-open gap where a pre-commit invocation read the
WORKING TREE copy of __init__.py instead of the git INDEX (what will actually
be committed). test_staged_mode_reads_index_not_working_tree and its companion
below monkeypatch _file_at_ref/_INIT_PATH directly to exercise that exact read
path and prove the staged=True fix closes it.
"""
from __future__ import annotations

import sys
from pathlib import Path

_CHECKS_DIR = Path(__file__).resolve().parents[1] / "checks"
if str(_CHECKS_DIR) not in sys.path:
    sys.path.insert(0, str(_CHECKS_DIR))

import check_evaluator_version_bump as cevb  # noqa: E402

_EVALUATOR_PATH = "scripts/pipeline/content_eval/evaluators/description_completeness.py"

_BASE_INIT = """EVALUATOR_VERSIONS = {
    \"description_completeness\": \"3\",
}
EVALUATOR_LOGIC_VERSION = \"19\"
"""


def _check(head_init: str, *, exemption_lines: "list[str] | None" = None):
    return cevb.check(
        "HEAD",
        changed_files=[_EVALUATOR_PATH],
        init_head_text=head_init,
        init_base_text=_BASE_INIT,
        exemption_diff_lines={_EVALUATOR_PATH: exemption_lines or []},
    )


def test_changed_evaluator_without_bump_is_blocked():
    exit_code, problems = _check(_BASE_INIT)  # identical to base -- no bump happened
    assert exit_code == 1
    assert problems == [("description_completeness", None)]


def test_changed_evaluator_with_own_version_bumped_is_clean():
    head = _BASE_INIT.replace('"3"', '"4"')
    exit_code, problems = _check(head)
    assert exit_code == 0
    assert problems == []


def test_cross_cutting_logic_version_bump_covers_every_changed_evaluator():
    head = _BASE_INIT.replace('"19"', '"20"')  # per-evaluator entry untouched
    exit_code, problems = _check(head)
    assert exit_code == 0
    assert problems == []


def test_exemption_marker_allows_an_unbumped_change():
    exit_code, problems = _check(
        _BASE_INIT,
        exemption_lines=["+# EVALUATOR-VERSION-BUMP-EXEMPT: docstring only"],
    )
    assert exit_code == 0
    assert problems == []


def test_no_evaluator_files_changed_is_trivially_clean():
    exit_code, problems = cevb.check(
        "HEAD",
        changed_files=["scripts/pipeline/content_eval/__init__.py"],  # not an evaluators/*.py path
        init_head_text=_BASE_INIT,
        init_base_text=_BASE_INIT,
        exemption_diff_lines={},
    )
    assert exit_code == 0
    assert problems == []


def test_changed_evaluator_names_matches_only_the_evaluators_directory():
    assert cevb.changed_evaluator_names([_EVALUATOR_PATH]) == {"description_completeness"}
    assert cevb.changed_evaluator_names(["scripts/pipeline/content_eval/__init__.py"]) == set()
    assert cevb.changed_evaluator_names(["scripts/pipeline/content_eval/evaluators/sub/nested.py"]) == set()


def test_staged_mode_reads_index_not_working_tree():
    """The disk copy of __init__.py has the version bump, but it was never
    `git add`-ed -- the INDEX (what `git commit` will actually record) still
    holds the un-bumped text. A pre-commit invocation (staged=True) must judge
    the index, so this must still BLOCK even though the working tree looks
    fixed. This is the exact fail-open scenario the independent review found:
    before this fix, staged=True didn't exist and check() always read disk,
    so this same setup would have incorrectly passed.

    Uses check()'s read_head_text_fn parameter (a plain keyword argument) to
    exercise the real staged-vs-disk branching in _read_init_head_text() --
    init_head_text alone can't do this, since providing it skips that branch
    entirely. This is an explicit DI seam, not monkeypatching (AGENTS.md 16
    classifies patching _file_at_ref/_INIT_PATH directly as banned T2)."""
    def fake_read_head_text(staged):
        assert staged is True
        return _BASE_INIT  # the INDEX is still un-bumped, unlike disk (never staged)

    exit_code, problems = cevb.check(
        "HEAD",
        changed_files=[_EVALUATOR_PATH],
        staged=True,
        read_head_text_fn=fake_read_head_text,
        init_base_text=_BASE_INIT,
        exemption_diff_lines={_EVALUATOR_PATH: []},
    )
    assert exit_code == 1
    assert problems == [("description_completeness", None)]


def test_non_staged_mode_still_reads_working_tree_disk_copy():
    """Companion case: the real push-triggered CI invocation (staged=False,
    the default) diffs the already-committed working tree against a base
    branch, so it must keep reading disk -- proving the staged=True change
    is additive and doesn't disturb the existing CI code path."""
    disk_text = _BASE_INIT.replace('"3"', '"4"')  # bumped, and this IS what gets read

    def fake_read_head_text(staged):
        assert staged is False
        return disk_text

    exit_code, problems = cevb.check(
        "main",
        changed_files=[_EVALUATOR_PATH],
        staged=False,
        read_head_text_fn=fake_read_head_text,
        init_base_text=_BASE_INIT,
        exemption_diff_lines={_EVALUATOR_PATH: []},
    )
    assert exit_code == 0
    assert problems == []
