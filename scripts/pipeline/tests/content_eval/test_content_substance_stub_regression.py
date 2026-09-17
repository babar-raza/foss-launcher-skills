"""Regression fixtures pinning the 2026-09-16 fabricated-KB-page defect class.

CE-01 (plans/healing/2026-09-17-content-eval-hardening-gaps.md): the 4 pages
retired in commit 820d2c7e8e (content(kb,data): retire 5 fabricated-capability
KB stub pages...) shared one placeholder-stub template that evaded
content_substance.py and evidence_depth.py entirely. Their self-review cited
an ESTIMATED word count ("~63 words"); this file captures the REAL, measured
numbers via the live evaluators, replacing the estimate.

BEFORE CE-03 (thresholds unhardened), all 4 fixtures had raw prose_words of
70-72 (> the 50-word FAIL threshold, correcting the self-review's "~63"
estimate upward), exactly 1 API-eligible code block each (< evidence_depth's
old `>= 2` EG_GROUNDING gate), and 1-2 factual (backtick-bearing) prose lines
(< its old `> 5` INFO gate). Net result: content_substance.py found NOTHING;
evidence_depth.py found only one INFO ("Evidence binding tier: weak") --
never FAIL, never WARN.

AFTER CE-03 (landed 2026-09-17, same commit as this file's update): excluding
the "Tips and Best Practices"/"Related Resources"/"See Also" boilerplate
sections (none contain a backtick-identifier in any of the 4 fixtures) drops
the counted prose-word total from 70-72 to 30 -- below the 50-word FAIL
threshold on its own. Lowering EG_GROUNDING's gate to `>= 1` and the
factual-line INFO gate to `> 0` additionally makes evidence_depth.py emit a
WARN + INFO on every fixture. Real, captured post-CE-03 findings:
  content_substance: 1 FAIL ("Stub page: only 30 prose words") on all 4.
  evidence_depth: 1 WARN ("...1 API-eligible code blocks but 0 evidence
    APIs") + 2 INFO per page (factual-line count differs: 1 for 3 fixtures,
    2 for compound-file-cpp, which has 2 backtick prose lines).

NOTE (self-correction during CE-01 execution): the retirement commit's own
message said "5 fabricated-capability KB stub pages"; `git show --stat
820d2c7e8e` shows only 4 distinct slugs (86 files = 4 slugs x ~21-22 locales).
This file's 4 fixtures are the complete, correct set.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from content_eval.evaluators.content_substance import (
    ContentSubstanceEvaluator,
    _count_prose_words,
    _has_real_code,
)
from content_eval.evaluators.evidence_depth import (
    EvidenceDepthEvaluator,
    _api_eligible_blocks,
)
from content_eval.models import Page

FIXTURES_ROOT = Path(__file__).parent / "fixtures" / "kb.aspose.org" / "en"

# (path, counted_prose_words_after_boilerplate_exclusion, raw_code_blocks,
#  api_eligible_blocks, expected_factual_lines)
FIXTURES = [
    pytest.param(
        FIXTURES_ROOT / "note" / "python" / "how-to-convert-onestore-format-python.md",
        30, 1, 1, 1,
        id="onestore-convert",
    ),
    pytest.param(
        FIXTURES_ROOT / "note" / "python" / "how-to-build-scene-entities-python.md",
        30, 1, 1, 1,
        id="scene-entities",
    ),
    pytest.param(
        FIXTURES_ROOT / "email" / "cpp" / "how-to-load-compound-file-cpp.md",
        30, 2, 1, 2,
        id="compound-file-cpp",
    ),
    pytest.param(
        FIXTURES_ROOT / "email" / "net" / "how-to-load-compound-file-dotnet.md",
        30, 1, 1, 1,
        id="compound-file-dotnet",
    ),
]


@pytest.mark.parametrize(
    "fixture_path,expected_words,expected_code_blocks,expected_api_eligible,expected_factual_lines",
    FIXTURES,
)
def test_fixture_metadata_matches_captured_evidence(
    fixture_path, expected_words, expected_code_blocks, expected_api_eligible, expected_factual_lines,
):
    """Pin the exact measured metadata so a future evaluator change is visible."""
    page = Page.load(fixture_path)
    assert page.subdomain == "kb"
    assert page.page_role == "howto"
    assert _count_prose_words(page) == expected_words
    assert len(page.code_blocks) == expected_code_blocks
    assert len(_api_eligible_blocks(page.code_blocks, page.platform)) == expected_api_eligible
    factual_lines = sum(1 for _, text in page.prose_lines if "`" in text)
    assert factual_lines == expected_factual_lines


@pytest.mark.parametrize(
    "fixture_path,expected_words,expected_code_blocks,expected_api_eligible,expected_factual_lines",
    FIXTURES,
)
def test_content_substance_flags_every_retired_page_as_stub(
    fixture_path, expected_words, expected_code_blocks, expected_api_eligible, expected_factual_lines,
):
    """Post-CE-03: content_substance.py now FAILs every fixture as a stub page.

    Regression guard for CE-03's fix: if this evaluator goes silent again on
    these fixtures, the exact 2026-09-16 defect class has come back
    undetected.
    """
    page = Page.load(fixture_path)
    findings = ContentSubstanceEvaluator().evaluate(page, knowledge=None)
    assert len(findings) == 1, f"expected exactly 1 finding for {fixture_path.name}, got {findings}"
    finding = findings[0]
    assert finding.level == "FAIL"
    assert finding.category == "CS"
    assert finding.message == f"Stub page: only {expected_words} prose words"


@pytest.mark.parametrize(
    "fixture_path,expected_words,expected_code_blocks,expected_api_eligible,expected_factual_lines",
    FIXTURES,
)
def test_evidence_depth_now_warns_on_every_retired_page(
    fixture_path, expected_words, expected_code_blocks, expected_api_eligible, expected_factual_lines,
):
    """Post-CE-03: evidence_depth.py now emits an EG_GROUNDING WARN, not just INFO.

    Regression guard for CE-03's lowered `code_block_count >= 1` /
    `factual_lines > 0` gates.
    """
    page = Page.load(fixture_path)
    findings = EvidenceDepthEvaluator().evaluate(page, knowledge=None)
    levels = sorted(f.level for f in findings)
    assert levels == ["INFO", "INFO", "WARN"], (
        f"evidence_depth.py findings for {fixture_path.name} changed from "
        f"the CE-03 baseline ({levels})."
    )
    grounding = [f for f in findings if f.category == "EG_GROUNDING"]
    assert len(grounding) == 1
    assert grounding[0].level == "WARN"
    assert grounding[0].message == (
        f"Page has {expected_api_eligible} API-eligible code blocks but 0 evidence APIs"
    )
    factual_info = [f for f in findings if "factual lines" in f.message]
    assert len(factual_info) == 1
    assert factual_info[0].message == (
        f"Page has {expected_factual_lines} factual lines but empty evidence block"
    )


def test_has_real_code_rejects_placeholder_comment_blocks():
    """Unit-level guard for CE-03's placeholder-code detector, independent of fixtures."""
    from content_eval.models import CodeBlock

    placeholder = [CodeBlock(lang="python", content="// See API reference for usage details", start_line=1, end_line=1)]
    assert _has_real_code(placeholder) is False

    real = [CodeBlock(lang="python", content="doc = Document('a.one')\ndoc.save('out.pdf')", start_line=1, end_line=2)]
    assert _has_real_code(real) is True

    empty = [CodeBlock(lang="python", content="", start_line=1, end_line=1)]
    assert _has_real_code(empty) is False
