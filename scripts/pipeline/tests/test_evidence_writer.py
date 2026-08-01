"""test_evidence_writer.py — Regression tests for evidence/writer.py.

Critical invariant: _write_evidence_to_frontmatter must preserve all non-evidence
YAML scalar styles (| literal block, > folded, quoted, unquoted) byte-for-byte.

Background: The writer previously called yaml.safe_load + yaml.dump on the full
frontmatter, which silently converted | literal block scalars (the correct style
for code-containing content fields) to PyYAML-chosen double-quoted or single-quoted
flow scalars. This caused code fences to render with indentation artifacts or
incorrect blank lines in Hugo's goldmark renderer.
"""
import re
import textwrap
import tempfile
from pathlib import Path

import pytest

# conftest.py adds scripts/pipeline/ to sys.path
from evidence.writer import _write_evidence_to_frontmatter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EVIDENCE_BLOCK_RE = re.compile(
    r"^evidence:[ \t]*(?:\n[ \t]+[^\n]*)*",
    re.MULTILINE,
)

_PROVENANCE_BLOCK_RE = re.compile(
    r"^provenance:[ \t]*(?:\n[ \t]+[^\n]*)*",
    re.MULTILINE,
)

_SAMPLE_EVIDENCE = {
    "model_sha": "abc123def456",
    "model_version": "1.0.0",
    "claims": ["CLM-001", "CLM-002"],
    "apis": ["Foo.bar", "Foo.baz"],
}


def _apply_evidence(content: str, evidence: dict | None = None) -> str:
    """Write evidence to a temp file and return the new content."""
    if evidence is None:
        evidence = dict(_SAMPLE_EVIDENCE)
    with tempfile.NamedTemporaryFile(
        suffix=".md", mode="w", encoding="utf-8", delete=False
    ) as f:
        f.write(content)
        tmp = Path(f.name)
    try:
        _write_evidence_to_frontmatter(tmp, dict(evidence))
        return tmp.read_text(encoding="utf-8")
    finally:
        tmp.unlink(missing_ok=True)


def _apply_evidence_raw_bytes(raw: bytes, evidence: dict | None = None) -> bytes:
    """Write raw bytes (e.g. BOM-prefixed) to a temp file, run the writer, return
    the raw output bytes. Needed because _apply_evidence's text-mode write can
    never itself produce a BOM."""
    if evidence is None:
        evidence = dict(_SAMPLE_EVIDENCE)
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f:
        f.write(raw)
        tmp = Path(f.name)
    try:
        _write_evidence_to_frontmatter(tmp, dict(evidence))
        return tmp.read_bytes()
    finally:
        tmp.unlink(missing_ok=True)


def _strip_evidence(text: str) -> str:
    """Remove the evidence block from frontmatter for comparison."""
    # Match between --- fences
    fm_match = re.match(r"^(---\s*\n)(.*?)(\n---\s*\n)", text, re.DOTALL)
    if not fm_match:
        return text
    open_f, fm, close_f = fm_match.group(1), fm_match.group(2), fm_match.group(3)
    body = text[fm_match.end():]
    fm_clean = _EVIDENCE_BLOCK_RE.sub("", fm)
    fm_clean = _PROVENANCE_BLOCK_RE.sub("", fm_clean).rstrip("\n") + "\n"
    return f"{open_f}{fm_clean}{close_f}{body}"


# ---------------------------------------------------------------------------
# Core invariant: scalar styles preserved
# ---------------------------------------------------------------------------

def test_preserves_literal_block_scalar():
    """| scalar style for content fields must survive evidence write exactly."""
    original = textwrap.dedent("""\
        ---
        title: My Page
        single:
          block:
          - title: Example
            content: |
              Install with pip:

              ```python
              from lib import Foo

              obj = Foo()
              obj.run()
              ```
        ---

        Body content here.
    """)
    result = _apply_evidence(original)

    assert "content: |" in result, "| scalar style was lost"
    assert "```python" in result, "code fence was lost"
    assert "from lib import Foo" in result, "code content was lost"
    # Must NOT be re-serialized as double-quoted or single-quoted
    assert 'content: "' not in result, "| was converted to double-quoted"
    assert "content: '" not in result, "| was converted to single-quoted"


def test_preserves_folded_block_scalar():
    """> scalar style must survive evidence write."""
    original = textwrap.dedent("""\
        ---
        title: Page
        description: >
          This is a folded
          scalar value that
          should stay folded.
        ---

        Body.
    """)
    result = _apply_evidence(original)
    assert "description: >" in result, "> folded scalar was lost"


def test_preserves_unquoted_scalar():
    """Unquoted scalars must stay unquoted after evidence write."""
    original = textwrap.dedent("""\
        ---
        layout: plugin
        family_name: Aspose.Cells FOSS
        weight: 1
        ---

        Body.
    """)
    result = _apply_evidence(original)
    assert "family_name: Aspose.Cells FOSS" in result
    assert "weight: 1" in result


def test_preserves_all_non_evidence_bytes():
    """Byte-for-byte: all content outside the evidence block must be identical."""
    original = textwrap.dedent("""\
        ---
        layout: plugin
        title: "My Title"
        description: A description with: colon in it
        overview:
          content: |
            Paragraph one.

            Paragraph two with `code`.
        single:
          block:
          - title: Step one
            content: |
              Do the thing:

              ```bash
              pip install foo
              ```
        ---

        Body content here.
    """)
    result = _apply_evidence(original)
    # Strip evidence from both and compare everything else exactly
    assert _strip_evidence(original) == _strip_evidence(result), (
        "Non-evidence frontmatter bytes changed"
    )


def test_preserves_yaml_comments():
    """YAML comments in frontmatter must be preserved."""
    original = textwrap.dedent("""\
        ---
        # Head
        title: Page Title
        # SubMenu
        submenu:
          enable: true
        ---

        Body.
    """)
    result = _apply_evidence(original)
    assert "# Head" in result
    assert "# SubMenu" in result


# ---------------------------------------------------------------------------
# Functional: evidence block is correct
# ---------------------------------------------------------------------------

def test_evidence_block_inserted_when_absent():
    """evidence: block must appear in output when file had none."""
    original = textwrap.dedent("""\
        ---
        title: Page
        layout: plugin
        ---

        Body.
    """)
    result = _apply_evidence(original)
    assert "evidence:" in result
    assert "model_sha: abc123def456" in result
    assert "CLM-001" in result
    assert "CLM-002" in result


def test_evidence_block_replaces_existing():
    """Running the writer on a file that already has evidence must replace it."""
    original = textwrap.dedent("""\
        ---
        title: Page
        evidence:
          model_sha: old_sha
          model_version: '0.9'
          claims:
          - CLM-OLD
          apis:
          - Old.method
        ---

        Body.
    """)
    result = _apply_evidence(original, {
        "model_sha": "new_sha",
        "model_version": "2.0",
        "claims": ["CLM-NEW"],
        "apis": ["New.method"],
    })
    assert "model_sha: new_sha" in result
    assert "old_sha" not in result
    # Claims are merged
    assert "CLM-OLD" in result
    assert "CLM-NEW" in result


def test_existing_claims_are_merged():
    """Claims in existing evidence must be merged (not replaced) with new claims."""
    original = textwrap.dedent("""\
        ---
        title: Page
        evidence:
          model_sha: sha1
          model_version: '1.0'
          claims:
          - CLM-KEEP-1
          - CLM-KEEP-2
          apis: []
        ---

        Body.
    """)
    result = _apply_evidence(original, {
        "model_sha": "sha2",
        "model_version": "1.1",
        "claims": ["CLM-NEW"],
        "apis": [],
    })
    assert "CLM-KEEP-1" in result
    assert "CLM-KEEP-2" in result
    assert "CLM-NEW" in result


def test_existing_claims_pruned_when_not_in_current_knowledge():
    """Stale evidence claims must not survive a refreshed knowledge model."""
    original = textwrap.dedent("""\
        ---
        title: Page
        evidence:
          model_sha: old_sha
          model_version: '1.0'
          claims:
          - CLM-KEEP
          - CLM-STALE
          apis: []
        ---

        Body.
    """)
    result = _apply_evidence(original, {
        "model_sha": "new_sha",
        "model_version": "1.1",
        "claims": ["CLM-NEW"],
        "apis": [],
        "_valid_claim_ids": {"CLM-KEEP", "CLM-NEW"},
    })

    assert "CLM-KEEP" in result
    assert "CLM-NEW" in result
    assert "CLM-STALE" not in result
    assert "_valid_claim_ids" not in result


def test_existing_apis_pruned_when_class_removed_from_current_knowledge():
    """Stale evidence apis must not survive forever (found live on 3d/python's
    reference _index.md: Token/TokenType kept citing a removed class because
    the pre-fix merge was a plain union with no validity check, unlike claims
    which already had one via _valid_claim_ids)."""
    original = textwrap.dedent("""\
        ---
        title: Page
        evidence:
          model_sha: old_sha
          model_version: '1.0'
          claims: []
          apis:
          - Token
          - Token.type
          - KeepMe
        ---

        Body.
    """)
    result = _apply_evidence(original, {
        "model_sha": "new_sha",
        "model_version": "1.1",
        "claims": [],
        "apis": ["NewClass"],
        "_valid_api_class_names": {"KeepMe", "NewClass"},
    })

    assert "KeepMe" in result
    assert "NewClass" in result
    assert "- Token\n" not in result
    assert "Token.type" not in result
    assert "_valid_api_class_names" not in result


def test_apis_not_pruned_when_no_valid_set_supplied():
    """Backward compatibility: omitting _valid_api_class_names keeps the old
    union-only behaviour (e.g. callers that never populate knowledge.classes)."""
    original = textwrap.dedent("""\
        ---
        title: Page
        evidence:
          model_sha: old_sha
          model_version: '1.0'
          claims: []
          apis:
          - SomeClass
        ---

        Body.
    """)
    result = _apply_evidence(original, {
        "model_sha": "new_sha",
        "model_version": "1.1",
        "claims": [],
        "apis": [],
    })

    assert "SomeClass" in result


def test_idempotent_on_second_run():
    """Running writer twice must not duplicate the evidence block."""
    original = textwrap.dedent("""\
        ---
        title: Page
        ---

        Body.
    """)
    result1 = _apply_evidence(original)
    result2 = _apply_evidence(result1)

    assert result2.count("evidence:") == 1, "evidence block was duplicated"


def test_no_frontmatter_creates_one():
    """Files without frontmatter get a new --- block with evidence only."""
    original = "Just some body content.\n"
    result = _apply_evidence(original)

    assert result.startswith("---\n"), "frontmatter not prepended"
    assert "evidence:" in result
    assert "Just some body content." in result


def test_evidence_is_last_key_by_convention():
    """evidence: block should appear after all other keys."""
    original = textwrap.dedent("""\
        ---
        title: Page
        layout: plugin
        ---

        Body.
    """)
    result = _apply_evidence(original)
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", result, re.DOTALL)
    assert fm_match, "no frontmatter in result"
    fm = fm_match.group(1)
    evidence_pos = fm.rfind("evidence:")
    title_pos = fm.rfind("title:")
    layout_pos = fm.rfind("layout:")
    assert evidence_pos > title_pos, "evidence should come after title"


# ---------------------------------------------------------------------------
# TC-04 acceptance test: evidence writer MUST NOT update last_mechanism
# ---------------------------------------------------------------------------

class TestEvidenceWriterPreservesLastMechanism:
    """write_evidence must not touch last_mechanism in the provenance block."""

    def _make_file(self, tmp_path, extra_fm: str = "") -> Path:
        """Write a temp .md with a provenance block containing last_mechanism."""
        p = tmp_path / "index.md"
        p.write_text(
            "---\n"
            "title: Test Page\n"
            "type: docs\n"
            + extra_fm +
            "provenance:\n"
            "  content_origin: human-authored\n"
            "  last_mechanism: human-edit\n"
            "  auto_updatable: false\n"
            "---\n\nBody content.\n",
            encoding="utf-8",
        )
        return p

    def test_write_evidence_does_not_change_last_mechanism(self, tmp_path):
        """After attaching evidence, last_mechanism must still be 'human-edit'."""
        p = self._make_file(tmp_path)
        evidence = {
            "model_sha": "abc123",
            "model_version": "1.0.0",
            "claims": ["CLM-test-001"],
            "apis": ["SomeClass.method"],
        }
        ok = _write_evidence_to_frontmatter(p, evidence)
        assert ok, "write_evidence returned False unexpectedly"

        text = p.read_text(encoding="utf-8")
        # The provenance block must still contain last_mechanism: human-edit
        assert "last_mechanism: human-edit" in text, (
            f"last_mechanism was mutated by evidence writer:\n{text}"
        )
        # Evidence should be present
        assert "model_sha: abc123" in text

    def test_write_evidence_does_not_create_provenance_if_absent(self, tmp_path):
        """If no provenance block exists, evidence write must NOT create one."""
        p = tmp_path / "no_prov.md"
        p.write_text(
            "---\ntitle: No Provenance\ntype: docs\n---\n\nBody.\n",
            encoding="utf-8",
        )
        evidence = {
            "model_sha": "abc123",
            "model_version": "1.0.0",
            "claims": ["CLM-test-001"],
            "apis": ["SomeClass.method"],
        }
        _write_evidence_to_frontmatter(p, evidence)

        text = p.read_text(encoding="utf-8")
        # No provenance block should have been created
        assert "provenance:" not in text, (
            f"evidence writer created a provenance block unexpectedly:\n{text}"
        )


# ---------------------------------------------------------------------------
# G-16: BOM handling + _valid_claim_ids leak in the no-frontmatter branch
# ---------------------------------------------------------------------------

def test_bom_prefixed_file_frontmatter_matched_not_prepended():
    """A BOM'd file with otherwise-valid frontmatter must be matched and merged
    in place, not misdetected as frontmatter-less and double-prepended."""
    original = textwrap.dedent("""\
        ---
        title: My Page
        layout: plugin
        ---

        Body content here.
    """)
    raw = b"\xef\xbb\xbf" + original.encode("utf-8")
    result = _apply_evidence_raw_bytes(raw).decode("utf-8")

    fence_lines = [line for line in result.splitlines() if line == "---"]
    assert len(fence_lines) == 2, (
        f"expected exactly one frontmatter fence pair, found fences: {fence_lines}\n{result}"
    )
    assert result.count("evidence:") == 1
    assert "title: My Page" in result
    assert "Body content here." in result


def test_bom_stripped_from_output():
    """atomic_write always emits plain utf-8 — any input BOM must not survive."""
    original = "---\ntitle: Page\n---\n\nBody.\n"
    raw = b"\xef\xbb\xbf" + original.encode("utf-8")
    result = _apply_evidence_raw_bytes(raw)

    assert not result.startswith(b"\xef\xbb\xbf"), "BOM leaked into output bytes"
    assert not result.decode("utf-8").startswith("﻿")


def test_no_frontmatter_prepend_branch_prunes_valid_claim_ids():
    """The no-frontmatter-yet branch must pop _valid_claim_ids before serializing,
    same as the matched branch already does — it is an internal validation set,
    never meant to reach the file."""
    original = "Just some body content.\n"
    result = _apply_evidence(original, {
        "model_sha": "abc123",
        "model_version": "1.0.0",
        "claims": ["CLM-SMALL"],
        "apis": [],
        "_valid_claim_ids": {"CLM-SMALL", "CLM-HUGE-1", "CLM-HUGE-2", "CLM-HUGE-3"},
    })
    assert "CLM-SMALL" in result
    assert "_valid_claim_ids" not in result
    assert "CLM-HUGE" not in result


def test_guard_still_raises_on_malformed_non_bom_frontmatter():
    """Regression lock: the pre-existing malformed-frontmatter guard must still
    raise on a plain (non-BOM) file whose closing fence is malformed, rather than
    silently falling through to double-frontmatter corruption."""
    malformed = "---\ntitle: Page\n---no newline after fence\nBody.\n"
    with tempfile.NamedTemporaryFile(
        suffix=".md", mode="w", encoding="utf-8", delete=False
    ) as f:
        f.write(malformed)
        tmp = Path(f.name)
    try:
        with pytest.raises(ValueError):
            _write_evidence_to_frontmatter(tmp, dict(_SAMPLE_EVIDENCE))
    finally:
        tmp.unlink(missing_ok=True)
