"""Tests for the evaluator-version-bump CI gate (PKGINSTALL-VERSION-BUMP-AND-LINT).

DI-over-monkeypatch: check() accepts changed_files/init_head_text/init_base_text/
exemption_diff_lines directly, so these tests never shell out to real git or
touch the real __init__.py -- matching this repo's own testing-seams convention.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "ci" / "checks"))
from check_evaluator_version_bump import (  # noqa: E402
    changed_evaluator_names,
    check,
    parse_versions,
    _exemption_from_lines,
)

_INIT_BASE = '''\
EVALUATOR_LOGIC_VERSION = "18"
EVALUATOR_FREEZE_VERSION: str | None = "18"
EVALUATOR_VERSIONS: dict[str, str] = {
    "api_accuracy": "2",
    "install_recipe": "1",
    "prose_truth": "2",
}
'''

_INIT_HEAD_BUMPED = '''\
EVALUATOR_LOGIC_VERSION = "18"
EVALUATOR_FREEZE_VERSION: str | None = "18"
EVALUATOR_VERSIONS: dict[str, str] = {
    "api_accuracy": "2",
    "install_recipe": "2",  # v2: added a new safety check
    "prose_truth": "2",
}
'''

_INIT_HEAD_UNBUMPED = _INIT_BASE  # identical -- simulates "forgot to bump"

_INIT_HEAD_ELV_BUMPED = '''\
EVALUATOR_LOGIC_VERSION = "19"
EVALUATOR_FREEZE_VERSION: str | None = "18"
EVALUATOR_VERSIONS: dict[str, str] = {
    "api_accuracy": "2",
    "install_recipe": "1",
    "prose_truth": "2",
}
'''


class TestChangedEvaluatorNames:
    def test_extracts_evaluator_files_only(self):
        names = changed_evaluator_names([
            "scripts/pipeline/content_eval/evaluators/install_recipe.py",
            "scripts/pipeline/content_eval/evaluators/api_accuracy.py",
            "scripts/pipeline/content_eval/models.py",  # not an evaluator file
            "content/docs.aspose.org/en/foo/bar.md",
        ])
        assert names == {"install_recipe", "api_accuracy"}

    def test_no_evaluator_files_changed(self):
        assert changed_evaluator_names(["scripts/pipeline/content_eval/config.py"]) == set()


class TestParseVersions:
    def test_parses_dict_and_logic_version(self):
        versions, logic = parse_versions(_INIT_BASE)
        assert versions["install_recipe"] == "1"
        assert versions["api_accuracy"] == "2"
        assert logic == "18"

    def test_parses_trailing_comment_correctly(self):
        versions, _ = parse_versions(_INIT_HEAD_BUMPED)
        assert versions["install_recipe"] == "2"


class TestExemptionFromLines:
    def test_marker_present(self):
        reason = _exemption_from_lines([
            "    # some cosmetic change",
            "    # EVALUATOR-VERSION-BUMP-EXEMPT: docstring typo fix only",
        ])
        assert reason == "docstring typo fix only"

    def test_marker_absent(self):
        assert _exemption_from_lines(["    # just a normal comment"]) is None


class TestCheck:
    _CHANGED = ["scripts/pipeline/content_eval/evaluators/install_recipe.py"]
    _PATH = "scripts/pipeline/content_eval/evaluators/install_recipe.py"

    def test_no_evaluator_changed_passes(self):
        exit_code, problems = check(
            "main",
            changed_files=["scripts/pipeline/content_eval/models.py"],
            init_head_text=_INIT_HEAD_UNBUMPED,
            init_base_text=_INIT_BASE,
        )
        assert exit_code == 0
        assert problems == []

    def test_bumped_evaluator_passes(self):
        exit_code, problems = check(
            "main",
            changed_files=self._CHANGED,
            init_head_text=_INIT_HEAD_BUMPED,
            init_base_text=_INIT_BASE,
        )
        assert exit_code == 0
        assert problems == []

    def test_unbumped_evaluator_fails(self):
        exit_code, problems = check(
            "main",
            changed_files=self._CHANGED,
            init_head_text=_INIT_HEAD_UNBUMPED,
            init_base_text=_INIT_BASE,
            exemption_diff_lines={self._PATH: []},
        )
        assert exit_code == 1
        assert problems == [("install_recipe", None)]

    def test_cross_cutting_elv_bump_covers_every_changed_evaluator(self):
        exit_code, problems = check(
            "main",
            changed_files=self._CHANGED,
            init_head_text=_INIT_HEAD_ELV_BUMPED,
            init_base_text=_INIT_BASE,
        )
        assert exit_code == 0
        assert problems == []

    def test_exemption_marker_covers_unbumped_evaluator(self):
        exit_code, problems = check(
            "main",
            changed_files=self._CHANGED,
            init_head_text=_INIT_HEAD_UNBUMPED,
            init_base_text=_INIT_BASE,
            exemption_diff_lines={
                self._PATH: ["+    # EVALUATOR-VERSION-BUMP-EXEMPT: comment-only fix"],
            },
        )
        assert exit_code == 0
        assert problems == []

    def test_multiple_evaluators_only_unbumped_one_reported(self):
        init_head = '''\
EVALUATOR_LOGIC_VERSION = "18"
EVALUATOR_FREEZE_VERSION: str | None = "18"
EVALUATOR_VERSIONS: dict[str, str] = {
    "api_accuracy": "3",
    "install_recipe": "1",
}
'''
        init_base = '''\
EVALUATOR_LOGIC_VERSION = "18"
EVALUATOR_FREEZE_VERSION: str | None = "18"
EVALUATOR_VERSIONS: dict[str, str] = {
    "api_accuracy": "2",
    "install_recipe": "1",
}
'''
        exit_code, problems = check(
            "main",
            changed_files=[
                "scripts/pipeline/content_eval/evaluators/api_accuracy.py",
                "scripts/pipeline/content_eval/evaluators/install_recipe.py",
            ],
            init_head_text=init_head,
            init_base_text=init_base,
            exemption_diff_lines={
                "scripts/pipeline/content_eval/evaluators/api_accuracy.py": [],
                "scripts/pipeline/content_eval/evaluators/install_recipe.py": [],
            },
        )
        assert exit_code == 1
        assert problems == [("install_recipe", None)]
