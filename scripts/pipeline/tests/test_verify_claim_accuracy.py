"""Tests for verify_claim_accuracy.py (TC-11)."""
import pytest

from commands.ops.verify_claim_accuracy import (
    ClaimAccuracyResult,
    check,
    configure,
)


@pytest.fixture(autouse=True)
def reset_config():
    configure(repo_root=None)
    yield
    configure(repo_root=None)


class TestClaimAccuracyResult:
    def test_pass_is_truthy(self):
        r = ClaimAccuracyResult(verdict="PASS")
        assert bool(r) is True

    def test_warning_is_falsy(self):
        r = ClaimAccuracyResult(verdict="WARNING", findings=["something"])
        assert bool(r) is False


class TestCheckWithInjectedKnowledge:
    """Use injected knowledge sets to avoid filesystem dependencies."""

    KNOWN_APIS = frozenset({"Document", "PdfSaveOptions", "WatermarkAnnotation"})
    KNOWN_FORMATS = frozenset({"PDF", "DOCX", "PNG"})
    KNOWN_SYMBOLS = frozenset({"Document.Save", "Document.Load"})

    def _run(self, section_text: str) -> ClaimAccuracyResult:
        return check(
            section_text,
            family="pdf",
            platform="net",
            known_api_names=self.KNOWN_APIS,
            known_format_names=self.KNOWN_FORMATS,
            known_claim_symbols=self.KNOWN_SYMBOLS,
        )

    def test_known_api_no_unknown_findings(self):
        # "Document" is in known APIs; any unverified claims should not include "Document"
        result = self._run("The Document class supports PDF export.")
        document_findings = [f for f in result.findings if "Document" in f]
        assert document_findings == []

    def test_unknown_api_produces_finding(self):
        # Unknown CamelCase API name appearing AFTER a capability verb
        # "PhantomRenderer" must appear AFTER the verb in the window for detection
        result = self._run("The library supports PhantomRenderer output.")
        assert result.verdict == "WARNING"
        assert any("PhantomRenderer" in f for f in result.findings)

    def test_code_blocks_skipped(self):
        # "FantasyClass" in a code block should NOT trigger a warning
        section = (
            "The API is easy to use.\n"
            "```csharp\n"
            "var x = new FantasyClass();\n"
            "x.supports(format);\n"
            "```\n"
            "See the documentation."
        )
        result = self._run(section)
        assert not any("FantasyClass" in f for f in result.findings)

    def test_empty_knowledge_does_not_warn(self):
        # When knowledge is empty, checker must not emit false positives
        result = check(
            "The UnknownThing supports UnknownFormat output.",
            family="pdf",
            platform="net",
            known_api_names=frozenset(),
            known_format_names=frozenset(),
            known_claim_symbols=frozenset(),
        )
        assert result.verdict == "PASS"

    def test_no_capability_verb_passes(self):
        # Text without capability verbs should always PASS
        result = self._run("This is a general overview of the documentation.")
        assert result.verdict == "PASS"

    def test_findings_deduplicated(self):
        # Repeating the same unverified claim should not produce many duplicates
        result = self._run(
            "PhantomRenderer supports WebM. PhantomRenderer supports WebM."
        )
        phantom_findings = [f for f in result.findings if "PhantomRenderer" in f]
        # Should be deduplicated by dict.fromkeys -- at most 1-2 entries
        assert len(phantom_findings) <= 2

    def test_verdict_only_warning_never_fail(self):
        # Verify the checker never returns FAIL -- only PASS or WARNING
        result = self._run("FakeClass supports FakeFormat.")
        assert result.verdict in {"PASS", "WARNING"}


class TestCheckNoFilesystemDependency:
    """When knowledge files are absent, check should degrade gracefully."""

    def test_absent_knowledge_returns_pass(self, tmp_path):
        configure(repo_root=tmp_path)
        result = check(
            "The Document class supports PDF export.",
            family="nonexistent",
            platform="net",
        )
        # No knowledge artifacts exist, so all_known is empty -> PASS
        assert result.verdict == "PASS"
