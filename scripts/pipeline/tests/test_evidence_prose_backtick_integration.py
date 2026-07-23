"""Integration test for EVID-PROSE-001: full attach_files() run, end to end.

Proves the actual production bug is fixed — not just the isolated matching
function. Root cause: content pages that are entirely prose (no fenced code
blocks) got evidence.claims/evidence.apis == [] forever, because the only
evidence source was code-block token extraction. This test builds a
prose-only fixture page (mirroring the real shape of the affected pages:
backtick-quoted class/method mentions, no code fences) and runs it through
evidence.runner.attach_files() with token/code-block extraction genuinely
returning nothing (as it would for a real prose-only page), verifying the
written evidence block is populated by the new prose fallback alone.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

_PIPELINE_DIR = Path(__file__).resolve().parent.parent
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))


class _FakeKnowledge:
    """Duck-type Knowledge with a small, realistic words/net-shaped API surface."""

    def __init__(self, repo_sha="sha-prose-001", version="", family="words", platform="net"):
        self.available = True
        self.repo_sha = repo_sha
        self.version = version
        self.family = family
        self.platform = platform
        self.claim_ids = {"ERC-words-doc", "ERC-words-db", "CLM-words-save"}
        self.classes = {"Document": {}, "DocumentBuilder": {}}
        self.api_to_claim = {
            "Document": "ERC-words-doc",
            "DocumentBuilder": "ERC-words-db",
            "Document.Save": "CLM-words-save",
        }
        self._methods = {"Document": {"Save"}}
        self._properties = {}
        self._enum_members = {}

    def has_method(self, cls, member):
        return member in self._methods.get(cls, set())

    def has_property(self, cls, member):
        return member in self._properties.get(cls, set())

    def has_enum_member(self, cls, member):
        return member in self._enum_members.get(cls, set())


@pytest.fixture(autouse=True)
def reset_runner_config():
    import evidence.runner as er
    yield
    er.configure()


def _write_prose_only_page(path: Path) -> Path:
    """A page shaped exactly like the real affected pages: prose-only, backtick
    identifiers, zero fenced code blocks."""
    body = (
        "---\ntitle: Working with Documents\nweight: 10\n---\n\n"
        "## Working with Documents\n\n"
        "Construct a `Document` and wrap it in a `DocumentBuilder` to insert content. "
        "Call `Document.Save` to persist the result to disk.\n"
    )
    path.write_text(body, encoding="utf-8")
    return path


class TestProseOnlyPageGetsEvidenceEndToEnd:
    """The actual production bug, reproduced and verified fixed end-to-end."""

    def test_prose_only_page_evidence_no_longer_empty(self, tmp_path):
        import evidence.runner as er

        f = _write_prose_only_page(tmp_path / "document.md")
        fk = _FakeKnowledge()

        # extract_tokens/verify_tokens/map_tokens all return nothing — this is
        # the REAL shape of a prose-only page: there are no code blocks, so
        # code-block token extraction has nothing to find. This reproduces the
        # exact bug (before this fix, evidence.claims/apis would stay []).
        er.configure(
            infer_product_fn=lambda fp: ("words", "net"),
            knowledge_fn=lambda fam, plat: fk,
            extract_tokens_fn=lambda *a, **kw: [],
            verify_tokens_fn=lambda *a, **kw: [],
            map_tokens_fn=lambda *a, **kw: ([], []),
            detect_formats_fn=lambda *a, **kw: [],
            build_sections_fn=lambda *a, **kw: [],
            write_grade_fn=lambda *a, **kw: None,
            compute_grade_fn=lambda f, w: "A",
            evaluator_logic_version="v1",
        )

        counts = er.attach_files([f])
        assert counts.get("UPDATED") == 1, f"Expected UPDATED, got {counts}"

        text = f.read_text(encoding="utf-8")
        fm = yaml.safe_load(text.split("---")[1])
        ev = fm.get("evidence", {})

        # This is the actual fix under test: apis/claims must be non-empty,
        # sourced entirely from the prose backtick fallback (code path mocked empty).
        assert ev["apis"], f"evidence.apis is still empty — bug not fixed: {ev}"
        assert ev["claims"], f"evidence.claims is still empty — bug not fixed: {ev}"
        assert "Document" in ev["apis"]
        assert "DocumentBuilder" in ev["apis"]
        assert "Document.Save" in ev["apis"]
        assert set(ev["claims"]) == {"ERC-words-doc", "ERC-words-db", "CLM-words-save"}

    def test_code_block_evidence_and_prose_evidence_do_not_double_count(self, tmp_path):
        """A page with BOTH a code-block token AND a prose-only mention of a
        different class must get both, with no duplicate refs."""
        import evidence.runner as er

        body = (
            "---\ntitle: Mixed Page\nweight: 10\n---\n\n"
            "Use `DocumentBuilder` to author content, then see the example below.\n\n"
            "```csharp\nDocument doc = new Document();\n```\n"
        )
        f = tmp_path / "mixed.md"
        f.write_text(body, encoding="utf-8")
        fk = _FakeKnowledge()

        # Simulate code-block extraction having already found "Document" (as the
        # real token_ops.extract_tokens + _map_tokens_to_evidence would for the
        # code fence above) — map_tokens_fn returns it directly so the test
        # doesn't depend on the real C# tokenizer's exact behavior.
        er.configure(
            infer_product_fn=lambda fp: ("words", "net"),
            knowledge_fn=lambda fam, plat: fk,
            extract_tokens_fn=lambda *a, **kw: ["stub-token"],
            verify_tokens_fn=lambda *a, **kw: [],
            map_tokens_fn=lambda *a, **kw: (["ERC-words-doc"], ["Document"]),
            detect_formats_fn=lambda *a, **kw: [],
            build_sections_fn=lambda *a, **kw: [],
            write_grade_fn=lambda *a, **kw: None,
            compute_grade_fn=lambda f, w: "A",
            evaluator_logic_version="v1",
        )

        counts = er.attach_files([f])
        assert counts.get("UPDATED") == 1

        text = f.read_text(encoding="utf-8")
        fm = yaml.safe_load(text.split("---")[1])
        ev = fm.get("evidence", {})

        assert ev["apis"].count("Document") == 1, f"Document must not be duplicated: {ev['apis']}"
        assert "DocumentBuilder" in ev["apis"], "prose-only mention must still be captured"
        assert set(ev["claims"]) == {"ERC-words-doc", "ERC-words-db"}

    def test_page_with_no_backtick_mentions_still_empty(self, tmp_path):
        """Sanity check: a page that genuinely has no verifiable API mentions
        must still get an honest empty evidence block, not fabricated matches."""
        import evidence.runner as er

        body = "---\ntitle: Generic Page\nweight: 10\n---\n\nThis page has no API mentions at all.\n"
        f = tmp_path / "generic.md"
        f.write_text(body, encoding="utf-8")
        fk = _FakeKnowledge()

        er.configure(
            infer_product_fn=lambda fp: ("words", "net"),
            knowledge_fn=lambda fam, plat: fk,
            extract_tokens_fn=lambda *a, **kw: [],
            verify_tokens_fn=lambda *a, **kw: [],
            map_tokens_fn=lambda *a, **kw: ([], []),
            detect_formats_fn=lambda *a, **kw: [],
            build_sections_fn=lambda *a, **kw: [],
            write_grade_fn=lambda *a, **kw: None,
            compute_grade_fn=lambda f, w: "A",
            evaluator_logic_version="v1",
        )

        counts = er.attach_files([f])
        assert counts.get("UPDATED") == 1

        text = f.read_text(encoding="utf-8")
        fm = yaml.safe_load(text.split("---")[1])
        ev = fm.get("evidence", {})
        assert ev["apis"] == []
        assert ev["claims"] == []

    def test_rerun_determinism(self, tmp_path):
        """Same input, fresh run (different tmp file) → identical evidence output."""
        import evidence.runner as er

        fk = _FakeKnowledge()
        er.configure(
            infer_product_fn=lambda fp: ("words", "net"),
            knowledge_fn=lambda fam, plat: fk,
            extract_tokens_fn=lambda *a, **kw: [],
            verify_tokens_fn=lambda *a, **kw: [],
            map_tokens_fn=lambda *a, **kw: ([], []),
            detect_formats_fn=lambda *a, **kw: [],
            build_sections_fn=lambda *a, **kw: [],
            write_grade_fn=lambda *a, **kw: None,
            compute_grade_fn=lambda f, w: "A",
            evaluator_logic_version="v1",
        )

        f1 = _write_prose_only_page(tmp_path / "run1_document.md")
        f2 = _write_prose_only_page(tmp_path / "run2_document.md")

        er.attach_files([f1])
        er.attach_files([f2])

        fm1 = yaml.safe_load(f1.read_text(encoding="utf-8").split("---")[1])
        fm2 = yaml.safe_load(f2.read_text(encoding="utf-8").split("---")[1])
        assert fm1["evidence"]["apis"] == fm2["evidence"]["apis"]
        assert fm1["evidence"]["claims"] == fm2["evidence"]["claims"]
