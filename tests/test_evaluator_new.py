"""Unit tests for 17 new evaluators."""

import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
sys.path.insert(0, str(_SCRIPTS / "pipeline"))

from content_eval.models import Page, Finding


def _make_page(body="", filepath="content/ref/en/f/p/T.md", frontmatter=None,
               subdomain="reference", family="f", platform="p", page_role="reference"):
    fm = frontmatter or {}
    raw = chr(45)*3 + chr(10) + "title: Test" + chr(10) + chr(45)*3 + chr(10) + body
    page = Page(filepath=Path(filepath), raw_text=raw, frontmatter=fm,
                body=body, body_offset=3, subdomain=subdomain,
                family=family, platform=platform, page_role=page_role)
    page._parse()
    return page


class TestEncodingCheck:
    def test_detects_mojibake(self):
        from content_eval.evaluators.encoding_check import EncodingCheckEvaluator
        ev = EncodingCheckEvaluator()
        moji = chr(0xe2) + chr(0x20ac) + chr(0x201c)
        page = _make_page(body='Some text with ' + moji + ' bad')
        findings = ev.evaluate(page, None)
        assert len(findings) >= 1
        assert findings[0].category == 'EN'

    def test_clean_text(self):
        from content_eval.evaluators.encoding_check import EncodingCheckEvaluator
        assert EncodingCheckEvaluator().evaluate(_make_page(body='Clean text here.'), None) == []


class TestContentSubstance:
    def test_stub_page_fails(self):
        from content_eval.evaluators.content_substance import ContentSubstanceEvaluator
        page = _make_page(body='Short.', subdomain='docs', page_role='docs')
        assert any(f.level == 'FAIL' for f in ContentSubstanceEvaluator().evaluate(page, None))

    def test_substantial_passes(self):
        from content_eval.evaluators.content_substance import ContentSubstanceEvaluator
        page = _make_page(body=' '.join(['word'] * 200), subdomain='docs', page_role='docs')
        assert ContentSubstanceEvaluator().evaluate(page, None) == []


class TestDeadInternalLink:
    def test_no_links(self):
        from content_eval.evaluators.dead_internal_link import DeadInternalLinkEvaluator
        assert DeadInternalLinkEvaluator().evaluate(_make_page(body='No links.'), None) == []


class TestDescriptionCompleteness:
    def test_non_reference_skipped(self):
        from content_eval.evaluators.description_completeness import DescriptionCompletenessEvaluator
        assert DescriptionCompletenessEvaluator().evaluate(
            _make_page(subdomain='docs', page_role='docs'), None) == []


class TestConsumerUsefulness:
    def test_non_applicable_skipped(self):
        from content_eval.evaluators.consumer_usefulness import ConsumerUsefulnessEvaluator
        assert ConsumerUsefulnessEvaluator().evaluate(
            _make_page(subdomain='reference'), None) == []


class TestCodeSyntaxCheck:
    def test_valid_python(self):
        from content_eval.evaluators.code_syntax_check import CodeSyntaxCheckEvaluator
        body = BT3 + 'python' + chr(10) + 'def hello():' + chr(10) + '    x = 42' + chr(10) + '    return x' + chr(10) + BT3
        page = _make_page(body=body)
        assert not any(f.category == 'SX' for f in CodeSyntaxCheckEvaluator().evaluate(page, None))

    def test_invalid_python(self):
        from content_eval.evaluators.code_syntax_check import CodeSyntaxCheckEvaluator
        body = BT3 + 'python' + chr(10) + 'def hello(' + chr(10) + '    x = 42' + chr(10) + '    return x' + chr(10) + BT3
        page = _make_page(body=body)
        assert any(f.category == 'SX' and f.level == 'FAIL' for f in CodeSyntaxCheckEvaluator().evaluate(page, None))


class TestTypeAccuracy:
    def test_non_ref_skipped(self):
        from content_eval.evaluators.type_accuracy import TypeAccuracyEvaluator
        assert TypeAccuracyEvaluator().evaluate(
            _make_page(subdomain='docs', page_role='docs', platform='python'), None) == []


class TestApiCompleteness:
    def test_skips_non_reference(self):
        from content_eval.evaluators.api_completeness import ApiCompletenessEvaluator
        assert ApiCompletenessEvaluator().evaluate(
            _make_page(subdomain='docs', page_role='docs'), None) == []


class TestCapabilityClaimCheck:
    def test_skips_no_family(self):
        from content_eval.evaluators.capability_claim_check import CapabilityClaimCheckEvaluator
        assert CapabilityClaimCheckEvaluator().evaluate(
            _make_page(family='', platform=''), None) == []


class TestCodeBlockApi:
    def test_skips_without_knowledge(self):
        from content_eval.evaluators.code_block_api import CodeBlockApiEvaluator
        assert CodeBlockApiEvaluator().evaluate(_make_page(), None) == []


class TestMemberValidity:
    def test_skips_non_reference(self):
        from content_eval.evaluators.member_validity import MemberValidityEvaluator
        assert MemberValidityEvaluator().evaluate(
            _make_page(subdomain='docs', page_role='docs'), None) == []


class TestNamespaceCorrectness:
    def test_skips_no_family(self):
        from content_eval.evaluators.namespace_correctness import NamespaceCorrectnessEvaluator
        assert NamespaceCorrectnessEvaluator().evaluate(
            _make_page(family='', platform=''), None) == []


class TestVersionClaimCheck:
    def test_skips_no_family(self):
        from content_eval.evaluators.version_claim_check import VersionClaimCheckEvaluator
        assert VersionClaimCheckEvaluator().evaluate(
            _make_page(family='', platform=''), None) == []


class TestFormatCompleteness:
    def test_skips_no_table(self):
        from content_eval.evaluators.format_completeness import FormatCompletenessEvaluator
        assert FormatCompletenessEvaluator().evaluate(
            _make_page(body='Just prose.'), None) == []


class TestEvidenceCompleteness:
    def test_skips_non_reference(self):
        from content_eval.evaluators.evidence_completeness import EvidenceCompletenessEvaluator
        assert EvidenceCompletenessEvaluator().evaluate(
            _make_page(subdomain='docs', page_role='docs'), None) == []


class TestProseClaimBinding:
    def test_skips_no_family(self):
        from content_eval.evaluators.prose_claim_binding import ProseClaimBindingEvaluator
        assert ProseClaimBindingEvaluator().evaluate(
            _make_page(family='', platform=''), None) == []


class TestProseGrounding:
    def test_skips_no_family(self):
        from content_eval.evaluators.prose_grounding import ProseGroundingEvaluator
        assert ProseGroundingEvaluator().evaluate(
            _make_page(family='', platform=''), None) == []


BT3 = chr(96) * 3


class TestEvaluatorDiscovery:
    def test_all_registered(self):
        from content_eval.evaluators import _ensure_loaded, list_evaluators
        _ensure_loaded()
        assert len(list_evaluators()) >= 32

    def test_new_evaluators_present(self):
        from content_eval.evaluators import _ensure_loaded, list_evaluators
        _ensure_loaded()
        evals = set(list_evaluators())
        new = {
            'encoding_check', 'content_substance', 'dead_internal_link',
            'description_completeness', 'consumer_usefulness', 'code_syntax_check',
            'type_accuracy', 'api_completeness', 'capability_claim_check',
            'code_block_api', 'member_validity', 'namespace_correctness',
            'version_claim_check', 'format_completeness', 'evidence_completeness',
            'prose_claim_binding', 'prose_grounding',
        }
        for name in new:
            assert name in evals, f'{name!r} not registered'
