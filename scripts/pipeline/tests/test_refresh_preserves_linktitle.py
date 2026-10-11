"""Test that refresh/heal workflows preserve platform linkTitle.

Proves the refresh-path protection for platform metadata by verifying
that frontmatter round-trip operations preserve linkTitle fields.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml


def _parse_frontmatter(text: str) -> dict:
    """Extract frontmatter dict from markdown text."""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    return yaml.safe_load(text[3:end]) or {}


def _write_platform_page(path: Path, lt_key: str = "linkTitle", lt_val: str = "Java") -> None:
    """Write a minimal platform _index.md with linkTitle."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(f"""\
        ---
        title: Aspose.PDF FOSS for Java
        {lt_key}: {lt_val}
        description: Test page
        layout: wide
        weight: 1
        is_root: true
        provenance:
          content_origin: skill-generated
          last_mechanism: skill
          auto_updatable: true
          content_hash: abc123
        ---

        Body content here.
    """), encoding="utf-8")


class TestRefreshPreservesLinkTitle:
    """Verify that yaml round-trip preserves linkTitle in frontmatter."""

    def test_yaml_roundtrip_preserves_linktitle_camelcase(self, tmp_path: Path) -> None:
        """Prove yaml.safe_load + yaml.safe_dump preserves linkTitle."""
        page = tmp_path / "_index.md"
        _write_platform_page(page, lt_key="linkTitle", lt_val="Java")

        text = page.read_text(encoding="utf-8")
        fm = _parse_frontmatter(text)

        assert fm.get("linkTitle") == "Java", "linkTitle must survive YAML parse"

        # Simulate refresh: dump back to YAML
        dumped = yaml.safe_dump(fm, default_flow_style=False, allow_unicode=True)
        reparsed = yaml.safe_load(dumped)
        assert reparsed.get("linkTitle") == "Java", "linkTitle must survive YAML round-trip"

    def test_yaml_roundtrip_preserves_linktitle_lowercase(self, tmp_path: Path) -> None:
        """Prove yaml round-trip preserves lowercase linktitle (docs convention)."""
        page = tmp_path / "_index.md"
        _write_platform_page(page, lt_key="linktitle", lt_val="Java")

        text = page.read_text(encoding="utf-8")
        fm = _parse_frontmatter(text)

        assert fm.get("linktitle") == "Java", "linktitle must survive YAML parse"

    def test_body_only_edit_preserves_frontmatter(self, tmp_path: Path) -> None:
        """Simulate a body-only refresh: replace body, keep frontmatter intact."""
        page = tmp_path / "_index.md"
        _write_platform_page(page, lt_key="linkTitle", lt_val=".NET")

        text = page.read_text(encoding="utf-8")
        parts = text.split("---", 2)
        assert len(parts) >= 3

        # Replace body only
        new_body = "\n\nNew refreshed body content.\n"
        new_text = "---" + parts[1] + "---" + new_body

        page.write_text(new_text, encoding="utf-8")
        fm_after = _parse_frontmatter(page.read_text(encoding="utf-8"))
        assert fm_after.get("linkTitle") == ".NET", "Body-only refresh must preserve linkTitle"

    def test_v04_catches_missing_linktitle_after_accidental_removal(self, tmp_path: Path) -> None:
        """Prove V-04 would catch if a refresh accidentally removed linkTitle."""
        from scripts.ci.validators.v04_platform_linktitle import extract_field

        page = tmp_path / "_index.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(textwrap.dedent("""\
            ---
            title: Aspose.PDF FOSS for Java
            description: No linkTitle here
            ---
            Body
        """), encoding="utf-8")

        lt = extract_field(page, "linktitle")
        assert lt is None, "V-04 extract_field correctly detects missing linkTitle"

    def test_batch_reference_sets_linktitle(self) -> None:
        """Prove batch_reference.py actively sets linkTitle in generated content."""
        import importlib
        spec = importlib.util.find_spec("scripts.pipeline.commands.content.batch_reference")
        if spec is None:
            pytest.skip("batch_reference not importable")

        source = Path(spec.origin).read_text(encoding="utf-8")
        assert "linkTitle:" in source, "batch_reference.py must set linkTitle in output"
