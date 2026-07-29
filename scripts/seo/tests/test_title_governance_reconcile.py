"""SEO-TITLE-GOVERNANCE-RECONCILE-SKILLS: pin S-22/S-59's documented FAQ
title pattern to the canonical kb_faq skeleton (Finding #22's "3-way
S-22/S-59/production-reality conflict").

Before this fix: S-22 (faq-generate.md) documented
'"Frequently Asked Questions — Aspose.{Family} for {Platform}"' and S-59
(new-kb-faq.md) documented the bare literal 'Frequently Asked Questions'
with no variables at all -- neither matched the other, and neither matched
what the mission decided (product-first: 'Aspose.{Family} FOSS for
{Platform} FAQ'). Both are now reconciled to the same pattern, which this
test locks in against regression (a future skill edit that silently
reintroduces drift would fail this test, not just a manual read-through).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[2]
_REPO_ROOT = _SCRIPTS.parents[0]
_PIPELINE = _SCRIPTS / "pipeline"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
if str(_PIPELINE) not in sys.path:
    sys.path.insert(0, str(_PIPELINE))

import seo.pipeline.title_templates as tt  # noqa: E402

_CANONICAL_KB_FAQ_TITLE_PATTERN = re.compile(
    r'title:\s*"?Aspose\.\{Family\}\s+FOSS\s+for\s+\{Platform\}\s+FAQ"?'
)


def _skill_text(name: str) -> str:
    return (_REPO_ROOT / "skills" / name).read_text(encoding="utf-8")


def test_faq_generate_documents_canonical_title_pattern():
    text = _skill_text("faq-generate.md")
    assert _CANONICAL_KB_FAQ_TITLE_PATTERN.search(text), (
        "skills/faq-generate.md (S-22) no longer documents the canonical "
        "kb_faq title skeleton -- check for reintroduced drift"
    )
    assert "Frequently Asked Questions — Aspose" not in text, (
        "the old, non-canonical S-22 title pattern reappeared"
    )


def test_new_kb_faq_documents_canonical_title_pattern():
    text = _skill_text("new-kb-faq.md")
    assert _CANONICAL_KB_FAQ_TITLE_PATTERN.search(text), (
        "skills/new-kb-faq.md (S-59) no longer documents the canonical "
        "kb_faq title skeleton -- check for reintroduced drift"
    )
    assert "title: Frequently Asked Questions\n" not in text, (
        "the old, bare-literal S-59 title pattern reappeared"
    )


def test_s22_and_s59_documented_patterns_agree_with_each_other():
    s22 = _CANONICAL_KB_FAQ_TITLE_PATTERN.search(_skill_text("faq-generate.md"))
    s59 = _CANONICAL_KB_FAQ_TITLE_PATTERN.search(_skill_text("new-kb-faq.md"))
    assert s22 and s59
    assert s22.group().replace('"', "") == s59.group().replace('"', "")


def test_documented_pattern_resolves_via_the_real_registry():
    """The skill docs' pattern isn't just textually similar to the registry
    -- plugging real values through title_templates.py's resolver must
    produce a title that fits the same shape the skills document."""
    resolved = tt.resolve_title("kb_faq", family="Page", platform="Python")
    assert resolved == "Aspose.Page FOSS for Python FAQ"
    assert tt.check_conformance(resolved, "kb_faq", family="Page", platform="Python")


def test_provider_mirrors_are_in_sync_for_both_reconciled_skills():
    """sync_providers.py must have already propagated these edits -- a
    canonical-only edit that never reached .agents/.claude/.kilocode would
    leave 3 of 4 skill surfaces silently stale."""
    canonical_faq = _skill_text("faq-generate.md")
    agents_faq = (_REPO_ROOT / ".agents" / "skills" / "faq-generate" / "SKILL.md").read_text(encoding="utf-8")
    claude_faq = (_REPO_ROOT / ".claude" / "commands" / "faq-generate.md").read_text(encoding="utf-8")
    kilocode_faq = (_REPO_ROOT / ".kilocode" / "skills" / "faq-generate" / "SKILL.md").read_text(encoding="utf-8")

    for mirror_name, mirror_text in [("agents", agents_faq), ("claude", claude_faq), ("kilocode", kilocode_faq)]:
        assert _CANONICAL_KB_FAQ_TITLE_PATTERN.search(mirror_text), f"{mirror_name} mirror is stale for faq-generate"
