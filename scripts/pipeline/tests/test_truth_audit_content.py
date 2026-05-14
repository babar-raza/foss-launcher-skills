"""Compatibility test surface for truth-audit-content parity."""

from scripts.pipeline.commands.diagnostics.truth_audit_content import decompose_markdown


def test_truth_audit_content_decomposes_units() -> None:
    units = decompose_markdown("# Title\n\nParagraph supports `Workbook.save()`.\n", "docs/page.md")
    assert [unit["type"] for unit in units] == ["heading", "paragraph"]
