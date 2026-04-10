"""Unit tests for evidence/runner.py reference-page class injection.

Covers the code path (lines ~70–81 in runner.py) that injects a class name
into api_refs for reference pages when no code-block tokens yielded API
evidence. Added during the prancy-waddling-mitten healing cycle (SR-01).

Test cases:
  T1 — valid class title, class in knowledge → api_refs populated + claim injected
  T2 — index title (no "—") → api_refs stays empty
  T3 — valid title, class NOT in knowledge → api_refs stays empty
  T4 — non-reference page (docs.aspose.org) → injection code not entered
  T5 — already has api_refs from code-block tokens → guard prevents injection
  T6 — class in knowledge, no claim mapping → api_refs populated, claims empty
  T7 — multi-word title before "—" → only first word extracted as candidate
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_PIPELINE_DIR = Path(__file__).resolve().parent.parent
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

from evidence.runner import attach_evidence  # noqa: E402


# ---------------------------------------------------------------------------
# Fake knowledge model (duck-typed, no disk I/O)
# ---------------------------------------------------------------------------

class _FakeKnowledge:
    """Minimal duck-type substitute for Knowledge; no disk I/O required."""

    def __init__(self, repo_sha="abc12345", version="1.0.0", platform="python"):
        self.available = True
        self.repo_sha = repo_sha
        self.version = version
        self.platform = platform
        self.classes: dict = {}        # {ClassName: anything}
        self.api_to_claim: dict = {}   # {ClassName: claim_id}

    def has_method(self, *_): return False
    def has_property(self, *_): return False
    def has_enum_member(self, *_): return False


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _write_md(path: Path, title: str) -> Path:
    """Write a minimal markdown file with title in frontmatter."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # Use model_sha "old" so the idempotent-skip guard never fires
    path.write_text(
        f"---\ntitle: {title}\nevidence:\n  model_sha: old\n---\n\n# Content\n",
        encoding="utf-8",
    )
    return path


def _run_attach(
    filepath: Path,
    knowledge: _FakeKnowledge,
    *,
    initial_api_refs: list | None = None,
    initial_claim_ids: list | None = None,
) -> dict:
    """
    Run attach_evidence() with all I/O-heavy deps mocked.

    Returns the evidence dict that was passed to _write_evidence_to_frontmatter.
    _write_evidence_to_frontmatter returns False so the auto-grade block is skipped.
    """
    captured: dict = {}

    def fake_map(tokens, _knowledge):
        return list(initial_claim_ids or []), list(initial_api_refs or [])

    def fake_write(fp, evidence):
        captured.update(evidence)
        return False  # skip auto-grade; function returns "ERROR" but we ignore it

    with patch("evidence.runner.extract_tokens", return_value=[]), \
         patch("evidence.runner.verify_tokens", return_value=[]), \
         patch("evidence.runner._map_tokens_to_evidence", side_effect=fake_map), \
         patch("evidence.runner._detect_formats", return_value=[]), \
         patch("evidence.runner._build_sections_evidence", return_value=[]), \
         patch("evidence.runner._write_evidence_to_frontmatter", side_effect=fake_write):
        attach_evidence(filepath, knowledge, force=True)

    return captured


# ---------------------------------------------------------------------------
# T1 — valid class title, class in knowledge → injection fires
# ---------------------------------------------------------------------------

class TestT1ValidClassTitle:
    def test_api_refs_populated_and_claim_injected(self, tmp_path):
        """reference page with 'ClassName — ...' title and class in knowledge.classes
        → api_refs = ['ClassName'], matching claim_id added to claims."""
        knowledge = _FakeKnowledge()
        knowledge.classes["Document"] = True
        knowledge.api_to_claim["Document"] = "CLM-note-abc123"

        fp = _write_md(
            tmp_path / "reference.aspose.org" / "document.md",
            "Document — Aspose.Note FOSS for Python API Reference",
        )
        ev = _run_attach(fp, knowledge)

        assert "Document" in ev.get("apis", []), (
            f"Expected 'Document' in apis; got {ev.get('apis')}"
        )
        assert "CLM-note-abc123" in ev.get("claims", []), (
            f"Expected 'CLM-note-abc123' in claims; got {ev.get('claims')}"
        )


# ---------------------------------------------------------------------------
# T2 — index title (no "—") → injection skipped
# ---------------------------------------------------------------------------

class TestT2IndexTitle:
    def test_api_refs_empty_for_index_title(self, tmp_path):
        """reference page with no '—' separator (index page) → api_refs stays empty."""
        knowledge = _FakeKnowledge()
        knowledge.classes["Document"] = True

        fp = _write_md(
            tmp_path / "reference.aspose.org" / "_index.md",
            "API Reference",
        )
        ev = _run_attach(fp, knowledge)

        assert ev.get("apis", []) == [], (
            f"Expected empty apis for index title; got {ev.get('apis')}"
        )


# ---------------------------------------------------------------------------
# T3 — valid title, class NOT in knowledge.classes → injection skipped
# ---------------------------------------------------------------------------

class TestT3ClassNotInKnowledge:
    def test_api_refs_empty_when_class_unknown(self, tmp_path):
        """class_candidate extracted from title but not present in knowledge.classes
        → api_refs stays empty."""
        knowledge = _FakeKnowledge()
        # knowledge.classes intentionally empty

        fp = _write_md(
            tmp_path / "reference.aspose.org" / "unknownclass.md",
            "UnknownClass — Aspose.Note FOSS for Python API Reference",
        )
        ev = _run_attach(fp, knowledge)

        assert ev.get("apis", []) == [], (
            f"Expected empty apis when class not in knowledge; got {ev.get('apis')}"
        )


# ---------------------------------------------------------------------------
# T4 — non-reference page → injection code path not entered
# ---------------------------------------------------------------------------

class TestT4NonReferencePage:
    def test_injection_skipped_for_docs_path(self, tmp_path):
        """docs.aspose.org path → 'reference.aspose.org' check fails → injection skipped
        even when title and knowledge match."""
        knowledge = _FakeKnowledge()
        knowledge.classes["Document"] = True

        fp = _write_md(
            tmp_path / "docs.aspose.org" / "document.md",
            "Document — Aspose.Note FOSS for Python API Reference",
        )
        ev = _run_attach(fp, knowledge)

        assert ev.get("apis", []) == [], (
            f"Expected empty apis for non-reference page; got {ev.get('apis')}"
        )


# ---------------------------------------------------------------------------
# T5 — already has api_refs from code-block tokens → guard prevents injection
# ---------------------------------------------------------------------------

class TestT5AlreadyPopulated:
    def test_guard_prevents_double_injection(self, tmp_path):
        """_map_tokens_to_evidence already returned api_refs=['Document.Save']
        → 'not api_refs' guard is False → injection block not entered."""
        knowledge = _FakeKnowledge()
        knowledge.classes["Document"] = True
        knowledge.api_to_claim["Document"] = "CLM-note-abc123"

        fp = _write_md(
            tmp_path / "reference.aspose.org" / "document.md",
            "Document — Aspose.Note FOSS for Python API Reference",
        )
        ev = _run_attach(fp, knowledge, initial_api_refs=["Document.Save"])

        assert "Document.Save" in ev.get("apis", []), (
            f"Expected pre-existing 'Document.Save' preserved; got {ev.get('apis')}"
        )
        # Bare "Document" must NOT appear — injection was guarded
        assert "Document" not in ev.get("apis", []), (
            f"'Document' must not be injected when api_refs already set; got {ev.get('apis')}"
        )


# ---------------------------------------------------------------------------
# T6 — class in knowledge, no claim mapping → api_refs populated, claims empty
# ---------------------------------------------------------------------------

class TestT6NoClaimMapping:
    def test_api_refs_populated_but_claims_empty(self, tmp_path):
        """api_to_claim has no entry for the class → api_refs = ['Page']
        but claims stays empty (cid is None, inner if-guard fires)."""
        knowledge = _FakeKnowledge()
        knowledge.classes["Page"] = True
        # api_to_claim intentionally empty — .get("Page") returns None

        fp = _write_md(
            tmp_path / "reference.aspose.org" / "page.md",
            "Page — Aspose.Note FOSS for Python API Reference",
        )
        ev = _run_attach(fp, knowledge)

        assert "Page" in ev.get("apis", []), (
            f"Expected 'Page' in apis; got {ev.get('apis')}"
        )
        assert ev.get("claims", []) == [], (
            f"Expected empty claims when no claim mapping; got {ev.get('claims')}"
        )


# ---------------------------------------------------------------------------
# T7 — multi-word title before "—" → only first word is the class candidate
# ---------------------------------------------------------------------------

class TestT7MultiWordTitle:
    def test_first_word_only_extracted_as_candidate(self, tmp_path):
        """title 'Foo Bar — Aspose...' → class_candidate = 'Foo' via .split()[0];
        'Bar' is also in knowledge but must NOT be matched or injected."""
        knowledge = _FakeKnowledge()
        knowledge.classes["Foo"] = True
        knowledge.api_to_claim["Foo"] = "CLM-note-foo123"
        knowledge.classes["Bar"] = True
        knowledge.api_to_claim["Bar"] = "CLM-note-bar456"

        fp = _write_md(
            tmp_path / "reference.aspose.org" / "foo.md",
            "Foo Bar — Aspose.Note FOSS for Python API Reference",
        )
        ev = _run_attach(fp, knowledge)

        assert "Foo" in ev.get("apis", []), (
            f"Expected 'Foo' (first word) in apis; got {ev.get('apis')}"
        )
        assert "Bar" not in ev.get("apis", []), (
            f"'Bar' must not appear — only first word is extracted; got {ev.get('apis')}"
        )
        assert "CLM-note-foo123" in ev.get("claims", []), (
            f"Expected Foo's claim; got {ev.get('claims')}"
        )
        assert "CLM-note-bar456" not in ev.get("claims", []), (
            f"Bar's claim must not be injected; got {ev.get('claims')}"
        )