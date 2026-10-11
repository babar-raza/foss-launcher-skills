"""Tests for EVID-PROSE-001: _prose_backtick_fallback_match / _scan_backtick_tokens.

Root cause covered: most content pages in this repo are prose-only (no fenced
code blocks) because verified code snippets are scarce or narrow for some
products (see G-26, backlog/BACKLOG.md), so the code-block-only evidence miner
(_map_tokens_to_evidence) has nothing to mine and leaves evidence.claims/
evidence.apis empty. This fallback scans prose for backtick-quoted
`ClassName` / `ClassName.member` tokens and verifies each against the real
knowledge model — the same exact-match confidence tier as code-block mining,
just fed from prose, using this repo's own backtick-quoting authoring
convention as the anchor signal.

Covers:
  - Bare `ClassName` in prose → matched (class exists in knowledge.classes)
  - `ClassName.method` / `.property` / `.enum_member` → matched only when the
    member independently verifies via has_method/has_property/has_enum_member
  - `ClassName.method()` with call parens → matched (parens stripped)
  - Unqualified class in backticks not in knowledge.classes → skipped
  - Qualified reference where the member does NOT resolve → skipped entirely
    (not silently downgraded to a bare-class credit)
  - Lowercase-leading backtick token (e.g. `` `getName` ``) → never matched
    (conservative: bare member mentions without a class qualifier are ambiguous)
  - Token inside a fenced code block → excluded (prose-only scanning)
  - Already-matched dedup (both bare class and qualified forms)
  - Claim-id fallback: class-level claim used when method-level key misses
  - Deterministic, sorted output
  - Multiple distinct tokens in one page
  - No knowledge.classes / no api_to_claim entries → empty result, no crash
  - Nonexistent filepath → empty result, no crash
  - Markdown table cell / multi-line prose → matched (not just single-sentence)
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evidence.mapper import _prose_backtick_fallback_match, _scan_backtick_tokens


# ---------------------------------------------------------------------------
# Minimal Knowledge stub
# ---------------------------------------------------------------------------

class FakeKnowledge:
    """Duck-type stub for Knowledge — no disk access.

    methods/properties/enum_members are dicts of {ClassName: set(member names)}.
    """

    def __init__(self, classes=None, api_to_claim=None,
                 methods=None, properties=None, enum_members=None):
        self.classes = classes or {}
        self.api_to_claim = api_to_claim or {}
        self._methods = methods or {}
        self._properties = properties or {}
        self._enum_members = enum_members or {}

    def has_method(self, cls, member):
        return member in self._methods.get(cls, set())

    def has_property(self, cls, member):
        return member in self._properties.get(cls, set())

    def has_enum_member(self, cls, member):
        return member in self._enum_members.get(cls, set())


def _write_page(page_dir, body, frontmatter=None):
    fm = frontmatter or "title: Test\nauthor: Aspose\n"
    content = f"---\n{fm}---\n\n{body}"
    page_dir.mkdir(parents=True, exist_ok=True)
    page = page_dir / "index.md"
    page.write_text(content, encoding="utf-8")
    return page


# ---------------------------------------------------------------------------
# _scan_backtick_tokens (pure text-in, no file I/O) — the shared core
# ---------------------------------------------------------------------------

class TestScanBacktickTokens:

    def test_bare_class_matched(self):
        kb = FakeKnowledge(classes={"Document": {}}, api_to_claim={"Document": "ERC-words-doc"})
        cids, refs = _scan_backtick_tokens("Construct a `Document` instance.", kb, set())
        assert cids == ["ERC-words-doc"]
        assert refs == ["Document"]

    def test_qualified_method_matched_when_valid(self):
        kb = FakeKnowledge(
            classes={"Document": {}},
            api_to_claim={"Document.Save": "CLM-words-save"},
            methods={"Document": {"Save"}},
        )
        cids, refs = _scan_backtick_tokens("Call `Document.Save` to persist changes.", kb, set())
        assert cids == ["CLM-words-save"]
        assert refs == ["Document.Save"]

    def test_qualified_method_with_call_parens_matched(self):
        kb = FakeKnowledge(
            classes={"Document": {}},
            api_to_claim={"Document.Save": "CLM-words-save"},
            methods={"Document": {"Save"}},
        )
        cids, refs = _scan_backtick_tokens("Call `Document.Save()` to persist changes.", kb, set())
        assert cids == ["CLM-words-save"]
        assert refs == ["Document.Save"]

    def test_qualified_property_matched(self):
        kb = FakeKnowledge(
            classes={"Style": {}},
            api_to_claim={"Style.Name": "CLM-words-stylename"},
            properties={"Style": {"Name"}},
        )
        cids, refs = _scan_backtick_tokens("Read `Style.Name` for the display name.", kb, set())
        assert cids == ["CLM-words-stylename"]
        assert refs == ["Style.Name"]

    def test_qualified_enum_member_matched(self):
        kb = FakeKnowledge(
            classes={"StyleType": {}},
            api_to_claim={"StyleType.Paragraph": "ERC-words-styletype"},
            enum_members={"StyleType": {"Paragraph"}},
        )
        cids, refs = _scan_backtick_tokens("Use `StyleType.Paragraph` for paragraph styles.", kb, set())
        assert cids == ["ERC-words-styletype"]
        assert refs == ["StyleType.Paragraph"]

    def test_class_not_in_knowledge_skipped(self):
        kb = FakeKnowledge(classes={}, api_to_claim={})
        cids, refs = _scan_backtick_tokens("The `FakeClass` does not exist.", kb, set())
        assert cids == []
        assert refs == []

    def test_qualified_member_that_does_not_resolve_is_skipped_entirely(self):
        """A wrong/hallucinated member must not be silently downgraded to a bare-class credit."""
        kb = FakeKnowledge(
            classes={"Document": {}},
            api_to_claim={"Document": "ERC-words-doc"},
            methods={"Document": {"Save"}},  # "NotAMethod" is NOT in this set
        )
        cids, refs = _scan_backtick_tokens("Call `Document.NotAMethod` for nonsense.", kb, set())
        assert cids == []
        assert refs == []

    def test_lowercase_leading_token_never_matched(self):
        """Bare member mentions without a class qualifier are ambiguous — never resolved."""
        kb = FakeKnowledge(
            classes={"Document": {}},
            api_to_claim={"Document": "ERC-words-doc"},
            methods={"Document": {"save"}},
        )
        cids, refs = _scan_backtick_tokens("Call `save()` to persist changes.", kb, set())
        assert cids == []
        assert refs == []

    def test_token_inside_code_fence_excluded_when_caller_strips_it(self):
        """Caller is responsible for stripping code fences before calling; verify a
        pre-stripped string yields no match for content that would have been in a fence."""
        kb = FakeKnowledge(classes={"Document": {}}, api_to_claim={"Document": "ERC-words-doc"})
        # Simulate what _prose_backtick_fallback_match does: strip fences first.
        raw = "No prose mention.\n\n```csharp\nDocument doc = new Document();\n```"
        import re
        prose = re.sub(r"```[\s\S]*?```", " ", raw)
        cids, refs = _scan_backtick_tokens(prose, kb, set())
        assert cids == []
        assert refs == []

    def test_already_matched_bare_class_skipped(self):
        kb = FakeKnowledge(classes={"Document": {}}, api_to_claim={"Document": "ERC-words-doc"})
        cids, refs = _scan_backtick_tokens("The `Document` class.", kb, already_matched={"Document"})
        assert cids == []
        assert refs == []

    def test_already_matched_qualified_skipped(self):
        kb = FakeKnowledge(
            classes={"Document": {}},
            api_to_claim={"Document.Save": "CLM-words-save"},
            methods={"Document": {"Save"}},
        )
        cids, refs = _scan_backtick_tokens(
            "Call `Document.Save` again.", kb, already_matched={"Document.Save"}
        )
        assert cids == []
        assert refs == []

    def test_claim_falls_back_to_class_level_when_method_key_missing(self):
        kb = FakeKnowledge(
            classes={"Document": {}},
            api_to_claim={"Document": "ERC-words-doc"},  # no Document.Save key
            methods={"Document": {"Save"}},
        )
        cids, refs = _scan_backtick_tokens("Call `Document.Save` to persist.", kb, set())
        assert cids == ["ERC-words-doc"]
        assert refs == ["Document.Save"]

    def test_no_claim_id_still_returns_api_ref(self):
        """A verified class/member with no matching claim_id at all still credits api_refs."""
        kb = FakeKnowledge(classes={"Document": {}}, api_to_claim={})
        cids, refs = _scan_backtick_tokens("The `Document` class.", kb, set())
        assert cids == []
        assert refs == ["Document"]

    def test_multiple_distinct_tokens(self):
        kb = FakeKnowledge(
            classes={"Document": {}, "DocumentBuilder": {}},
            api_to_claim={"Document": "ERC-doc", "DocumentBuilder": "ERC-db"},
        )
        cids, refs = _scan_backtick_tokens(
            "Construct a `Document` and wrap it in a `DocumentBuilder`.", kb, set()
        )
        assert set(cids) == {"ERC-doc", "ERC-db"}
        assert set(refs) == {"Document", "DocumentBuilder"}

    def test_deterministic_sorted_output(self):
        kb = FakeKnowledge(
            classes={"Zebra": {}, "Apple": {}},
            api_to_claim={"Zebra": "CLM-z", "Apple": "CLM-a"},
        )
        cids, refs = _scan_backtick_tokens("`Zebra` and `Apple` are both mentioned.", kb, set())
        assert refs == sorted(refs)
        assert cids == sorted(cids)

    def test_dedup_repeated_mention(self):
        kb = FakeKnowledge(classes={"Document": {}}, api_to_claim={"Document": "ERC-doc"})
        cids, refs = _scan_backtick_tokens(
            "`Document` first mention. `Document` second mention.", kb, set()
        )
        assert cids == ["ERC-doc"]
        assert refs == ["Document"]

    def test_markdown_table_cell_prose(self):
        kb = FakeKnowledge(classes={"Document": {}}, api_to_claim={"Document": "ERC-doc"})
        body = "| Class | Description |\n|---|---|\n| `Document` | Root document object |"
        cids, refs = _scan_backtick_tokens(body, kb, set())
        assert cids == ["ERC-doc"]

    def test_empty_text_no_crash(self):
        kb = FakeKnowledge(classes={"Document": {}}, api_to_claim={"Document": "ERC-doc"})
        cids, refs = _scan_backtick_tokens("", kb, set())
        assert cids == []
        assert refs == []


# ---------------------------------------------------------------------------
# _prose_backtick_fallback_match (file-level: reads, strips frontmatter+fences)
# ---------------------------------------------------------------------------

class TestProseBacktickFallbackMatch:

    def test_matches_from_real_file(self, tmp_path):
        kb = FakeKnowledge(classes={"Document": {}}, api_to_claim={"Document": "ERC-doc"})
        page = _write_page(tmp_path / "page", body="Construct a `Document` instance.")
        cids, refs = _prose_backtick_fallback_match(page, kb, already_matched=set())
        assert cids == ["ERC-doc"]
        assert refs == ["Document"]

    def test_code_block_content_excluded(self, tmp_path):
        kb = FakeKnowledge(classes={"Document": {}}, api_to_claim={"Document": "ERC-doc"})
        body = "No prose mention.\n\n```csharp\nDocument doc = new Document();\n```"
        page = _write_page(tmp_path / "page", body=body)
        cids, refs = _prose_backtick_fallback_match(page, kb, already_matched=set())
        assert cids == []
        assert refs == []

    def test_frontmatter_stripped_before_scan(self, tmp_path):
        """A class name appearing only in frontmatter (e.g. in a title) must not
        be scanned as if it were body prose evidence."""
        kb = FakeKnowledge(classes={"Document": {}}, api_to_claim={"Document": "ERC-doc"})
        page = _write_page(
            tmp_path / "page",
            body="Nothing relevant here.",
            frontmatter="title: Document\nauthor: Aspose\n",
        )
        cids, refs = _prose_backtick_fallback_match(page, kb, already_matched=set())
        assert cids == []
        assert refs == []

    def test_nonexistent_filepath_returns_empty(self, tmp_path):
        kb = FakeKnowledge(classes={"Document": {}}, api_to_claim={"Document": "ERC-doc"})
        missing = tmp_path / "no-such-file.md"
        cids, refs = _prose_backtick_fallback_match(missing, kb, already_matched=set())
        assert cids == []
        assert refs == []

    def test_already_matched_from_code_block_path_not_double_counted(self, tmp_path):
        """Simulates the runner's already_matched, built from code-block token
        extraction results, being passed in to avoid double-counting the same ref."""
        kb = FakeKnowledge(
            classes={"Document": {}},
            api_to_claim={"Document.Save": "CLM-save"},
            methods={"Document": {"Save"}},
        )
        body = "The example calls `Document.Save` to write the file."
        page = _write_page(tmp_path / "page", body=body)
        cids, refs = _prose_backtick_fallback_match(
            page, kb, already_matched={"Document.Save", "Document"}
        )
        assert cids == []
        assert refs == []

    def test_page_without_frontmatter_separator(self, tmp_path):
        kb = FakeKnowledge(classes={"Document": {}}, api_to_claim={"Document": "ERC-doc"})
        page = tmp_path / "page" / "index.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text("Discusses `Document` without frontmatter.", encoding="utf-8")
        cids, refs = _prose_backtick_fallback_match(page, kb, already_matched=set())
        assert cids == ["ERC-doc"]
