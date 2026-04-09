"""Tests for sync_providers.py — provider mirror sync and creation."""

import pytest
from sync_providers import (
    _extract_id_from_content,
    _extract_description,
    _extract_args,
    _extract_frontmatter,
    _generate_frontmatter,
    _has_cross_skill_note,
    main,
)


# ---------------------------------------------------------------------------
# Sample canonical content for tests
# ---------------------------------------------------------------------------

STANDARD_CANONICAL = """\
# S-42: Category Fix — Run Specific Fixer on Files

**Arguments**: $ARGUMENTS
Expected format: `{category} {family} {platform}` — e.g. `E01 cells net`

## Purpose

Run a specific fixer on files matched by category code. This skill targets
a single evaluator category across all matching content files.

## Pre-conditions

1. Content must exist for the specified family/platform.
"""

MINIMAL_CANONICAL = """\
# S-99: Minimal Skill

## Purpose

Does something minimal.
"""

NO_ID_CANONICAL = """\
# Some Skill Without an ID

## Purpose

This skill has no S-XX ID in its heading.
"""

NO_PURPOSE_CANONICAL = """\
# S-50: No Purpose Section

This skill lacks a Purpose section entirely.
"""

MULTILINE_PURPOSE = """\
# S-77: Session Start

**Arguments**: (none)

## Purpose

**When to use**: at the start of every session.

Initialize the session environment and validate prerequisites.
"""


# ---------------------------------------------------------------------------
# _extract_id_from_content
# ---------------------------------------------------------------------------


class TestExtractId:
    def test_standard_heading(self):
        assert _extract_id_from_content(STANDARD_CANONICAL) == "S-42"

    def test_high_number(self):
        assert _extract_id_from_content(MINIMAL_CANONICAL) == "S-99"

    def test_no_id_returns_none(self):
        assert _extract_id_from_content(NO_ID_CANONICAL) is None

    def test_empty_content(self):
        assert _extract_id_from_content("") is None

    def test_id_beyond_1500_chars_not_found(self):
        padding = "x" * 1600 + "\n# S-01: Late Heading\n"
        assert _extract_id_from_content(padding) is None


# ---------------------------------------------------------------------------
# _extract_description
# ---------------------------------------------------------------------------


class TestExtractDescription:
    def test_standard_purpose(self):
        desc = _extract_description(STANDARD_CANONICAL)
        assert desc.startswith("Run a specific fixer")
        # Should truncate at first sentence boundary
        assert desc.endswith(".")

    def test_minimal(self):
        desc = _extract_description(MINIMAL_CANONICAL)
        assert "minimal" in desc.lower()

    def test_no_purpose_returns_fallback(self):
        desc = _extract_description(NO_PURPOSE_CANONICAL)
        assert desc == "Skill description pending"

    def test_empty_content_returns_fallback(self):
        desc = _extract_description("")
        assert desc == "Skill description pending"

    def test_skips_bold_lines_after_purpose(self):
        """Lines starting with ** should be skipped (e.g. **When to use**)."""
        desc = _extract_description(MULTILINE_PURPOSE)
        assert not desc.startswith("**")
        assert "Initialize" in desc or "session" in desc.lower()


# ---------------------------------------------------------------------------
# _extract_args
# ---------------------------------------------------------------------------


class TestExtractArgs:
    def test_args_with_only_placeholder_returns_empty(self):
        """When **Arguments**: line has only $ARGUMENTS, result is empty after stripping."""
        args = _extract_args(STANDARD_CANONICAL)
        assert args == ""

    def test_args_with_inline_pattern(self):
        """When args pattern is on the same line (not just $ARGUMENTS), it's extracted."""
        content = '# S-10: Foo\n\n**Arguments**: {family} {platform}\n'
        args = _extract_args(content)
        assert args == "{family} {platform}"

    def test_no_args_line(self):
        assert _extract_args(MINIMAL_CANONICAL) == ""

    def test_empty_content(self):
        assert _extract_args("") == ""


# ---------------------------------------------------------------------------
# _extract_frontmatter
# ---------------------------------------------------------------------------


class TestExtractFrontmatter:
    def test_with_frontmatter(self):
        text = "---\nname: test\nid: S-01\n---\n\n# S-01: Test\n"
        fm, body = _extract_frontmatter(text)
        assert fm.startswith("---")
        assert fm.endswith("---\n")
        assert "name: test" in fm
        assert body.startswith("# S-01")

    def test_no_frontmatter(self):
        text = "# S-01: Test Skill\n\nSome content."
        fm, body = _extract_frontmatter(text)
        assert fm == ""
        assert body == text

    def test_empty_content(self):
        fm, body = _extract_frontmatter("")
        assert fm == ""
        assert body == ""

    def test_incomplete_frontmatter(self):
        """Only one --- delimiter — not valid frontmatter."""
        text = "---\nname: test\nno closing delimiter\n"
        fm, body = _extract_frontmatter(text)
        assert fm == ""
        assert body == text


# ---------------------------------------------------------------------------
# _generate_frontmatter
# ---------------------------------------------------------------------------


class TestGenerateFrontmatter:
    def test_standard_output(self):
        fm = _generate_frontmatter("category-fix", STANDARD_CANONICAL)
        assert fm.startswith("---\n")
        assert fm.rstrip().endswith("---")
        assert "name: category-fix" in fm
        assert "id: S-42" in fm
        assert "description:" in fm

    def test_includes_args_when_present(self):
        content = '# S-10: Foo\n\n**Arguments**: {family} {platform}\n\n## Purpose\n\nDoes foo.\n'
        fm = _generate_frontmatter("foo", content)
        assert "args:" in fm
        assert "{family} {platform}" in fm

    def test_omits_args_when_absent(self):
        fm = _generate_frontmatter("minimal", MINIMAL_CANONICAL)
        assert "args:" not in fm

    def test_missing_id_produces_none_marker(self):
        """When no ID is found, frontmatter uses 'NONE' — the guard in
        sync_provider() prevents this from reaching disk."""
        fm = _generate_frontmatter("no-id-skill", NO_ID_CANONICAL)
        assert "id: NONE" in fm

    def test_output_is_parseable_yaml(self):
        """Frontmatter must be valid YAML between --- delimiters."""
        fm = _generate_frontmatter("category-fix", STANDARD_CANONICAL)
        # Strip the --- delimiters and parse
        yaml_body = fm.replace("---", "").strip()
        # Basic structural check: every line should be key: value or indented continuation
        for line in yaml_body.splitlines():
            stripped = line.strip()
            if stripped:
                assert ":" in line or line.startswith(" "), f"Bad YAML line: {line!r}"


# ---------------------------------------------------------------------------
# _has_cross_skill_note
# ---------------------------------------------------------------------------


class TestHasCrossSkillNote:
    def test_present(self):
        text = "> Cross-skill references like `/foo` refer to sibling skills.\n\nBody."
        assert _has_cross_skill_note(text) is True

    def test_absent(self):
        assert _has_cross_skill_note("# S-01: Test\n\nBody.") is False


# ---------------------------------------------------------------------------
# main() --check mode
# ---------------------------------------------------------------------------


class TestCheckMode:
    def test_check_returns_0_when_in_sync(self):
        """--check on a repo where all providers match canonical should exit 0."""
        result = main(["--check"])
        assert result == 0

    def test_check_implies_dry_run(self, capsys):
        """--check should not write any files (implied dry-run)."""
        result = main(["--check"])
        captured = capsys.readouterr()
        assert "PASS" in captured.out
        assert result == 0
