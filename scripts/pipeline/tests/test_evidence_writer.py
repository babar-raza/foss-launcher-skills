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


def _strip_evidence(text: str) -> str:
    """Remove the evidence block from frontmatter for comparison."""
    # Match between --- fences
    fm_match = re.match(r"^(---\s*\n)(.*?)(\n---\s*\n)", text, re.DOTALL)
    if not fm_match:
        return text
    open_f, fm, close_f = fm_match.group(1), fm_match.group(2), fm_match.group(3)
    body = text[fm_match.end():]
    fm_clean = _EVIDENCE_BLOCK_RE.sub("", fm).rstrip("\n") + "\n"
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
        plugin_name: Aspose.Cells FOSS
        weight: 1
        ---

        Body.
    """)
    result = _apply_evidence(original)
    assert "plugin_name: Aspose.Cells FOSS" in result
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
    assert evidence_pos > layout_pos, "evidence should come after layout"
