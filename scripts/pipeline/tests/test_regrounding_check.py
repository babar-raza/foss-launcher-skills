"""
Tests for scripts/pipeline/lib/regrounding_check.py (RPR-E-03).

Reproduces the real 3d/net template-propagation defect (plan §2.4): the same
fabricated code `node.Transform.Scale = new FVector3(2, 2, 2)` recurring VERBATIM
across 6 unrelated pages. The re-grounding cache must allow the first occurrence
and flag the reuse on the other pages when they are not grounded in the same
evidence.
"""

from lib.regrounding_check import (
    RegroundingCache,
    extract_distinctive_spans,
    fingerprint,
)

# The real fabricated snippet from the 3d/net audit.
_BAD_SNIPPET_PAGE = (
    "---\ntitle: {title}\n---\n\n"
    "## Transforms\n\n"
    "```csharp\n"
    "node.Transform.Scale = new FVector3(2, 2, 2);\n"
    "```\n"
)


# ── fingerprint / span extraction ────────────────────────────────────────

def test_fingerprint_whitespace_insensitive():
    assert fingerprint("Transform.Scale  =  x") == fingerprint("Transform.Scale = x")


def test_extract_spans_requires_dotted_symbol():
    # A code block with a dotted symbol is distinctive; generic prose is not.
    body = "```csharp\nnode.Transform.Scale = 1;\n```\n\nJust generic prose here.\n"
    spans = extract_distinctive_spans(body)
    assert any("Transform.Scale" in s for s in spans)
    assert not any("generic prose" in s for s in spans)


def test_generic_boilerplate_produces_no_spans():
    """The canned deterministic-fallback note has no dotted symbol → not fingerprinted,
    so reusing it across pages is never flagged (avoids fighting the fallback path)."""
    boilerplate = "This section has been reviewed against the current source model.\n"
    assert extract_distinctive_spans(boilerplate) == []


# ── RegroundingCache: the 6-page reproduction ────────────────────────────

def test_first_occurrence_allowed():
    cache = RegroundingCache()
    v = cache.check_page("pageA.md", _BAD_SNIPPET_PAGE.format(title="A"), cited_evidence=["Transform"])
    assert v == []


def test_reuse_on_different_page_without_grounding_flagged():
    cache = RegroundingCache()
    cache.check_page("pageA.md", _BAD_SNIPPET_PAGE.format(title="A"), cited_evidence=["Transform"])
    # Page B reuses the identical snippet but cites unrelated evidence.
    v = cache.check_page("pageB.md", _BAD_SNIPPET_PAGE.format(title="B"), cited_evidence=["Mesh"])
    assert len(v) == 1
    assert v[0].reusing_page == "pageB.md"
    assert v[0].first_page == "pageA.md"


def test_six_page_propagation_only_first_survives():
    """The exact 6-page fixture: page 1 registers the snippet; pages 2-6 reusing it
    verbatim without shared grounding are each flagged."""
    cache = RegroundingCache()
    flagged_pages = []
    for i in range(1, 7):
        page_id = f"page{i}.md"
        v = cache.check_page(page_id, _BAD_SNIPPET_PAGE.format(title=str(i)), cited_evidence=[f"Unrelated{i}"])
        if v:
            flagged_pages.append(page_id)
    # page1 registers cleanly; pages 2-6 are flagged.
    assert flagged_pages == ["page2.md", "page3.md", "page4.md", "page5.md", "page6.md"]


def test_shared_grounding_allows_reuse():
    """If two pages genuinely cite the same evidence, reusing the snippet is legitimate."""
    cache = RegroundingCache()
    cache.check_page("pageA.md", _BAD_SNIPPET_PAGE.format(title="A"), cited_evidence=["Transform"])
    v = cache.check_page("pageB.md", _BAD_SNIPPET_PAGE.format(title="B"), cited_evidence=["Transform", "Node"])
    assert v == []  # both grounded in Transform → shared grounding, allowed


def test_same_page_recheck_idempotent():
    """Re-checking the same page (e.g. an idempotent product rerun) does not self-flag."""
    cache = RegroundingCache()
    cache.check_page("pageA.md", _BAD_SNIPPET_PAGE.format(title="A"), cited_evidence=["Transform"])
    v = cache.check_page("pageA.md", _BAD_SNIPPET_PAGE.format(title="A"), cited_evidence=["Transform"])
    assert v == []


def test_distinct_snippets_not_flagged():
    """Different snippets on different pages are never flagged — only verbatim reuse is."""
    cache = RegroundingCache()
    cache.check_page("pageA.md", "```csharp\nDocument.Save(path);\n```\n", cited_evidence=["Document"])
    v = cache.check_page("pageB.md", "```csharp\nMesh.Build();\n```\n", cited_evidence=["Mesh"])
    assert v == []
