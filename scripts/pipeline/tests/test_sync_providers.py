"""Tests for sync_providers.py — provider mirror sync and creation."""

import pytest
from sync_providers import (
    _extract_id_from_content,
    _extract_description,
    _extract_args,
    _extract_frontmatter,
    _generate_frontmatter,
    _has_cross_skill_note,
    sync_provider,
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


# ---------------------------------------------------------------------------
# sync_provider() with create_missing=True — integration tests
# ---------------------------------------------------------------------------


import sync_providers  # for configure() seam


@pytest.fixture(autouse=True)
def _reset_sp():
    yield
    sync_providers.configure()


class TestCreateMissingIntegration:
    """Integration tests for the --create-missing file creation path."""

    def _setup(self, tmp_path, monkeypatch, slug, content):
        """Create canonical dir + empty provider dirs, monkeypatch module constants."""
        canonical_dir = tmp_path / "skills"
        canonical_dir.mkdir()
        (canonical_dir / f"{slug}.md").write_text(content, encoding="utf-8")

        providers = {
            "agents": tmp_path / "agents",
            "claude": tmp_path / "claude",
            "kilocode": tmp_path / "kilocode",
        }
        for p in providers.values():
            p.mkdir()

        sync_providers.configure(canonical_dir=canonical_dir, providers=providers, skip_slugs={})
        return providers

    def test_agents_creates_dir_and_skill_file(self, tmp_path, monkeypatch):
        """agents provider creates {slug}/SKILL.md with frontmatter + cross-skill note."""
        providers = self._setup(tmp_path, monkeypatch, "test-skill", STANDARD_CANONICAL)

        changed, created = sync_provider("agents", create_missing=True)

        assert "test-skill" in created
        skill_path = providers["agents"] / "test-skill" / "SKILL.md"
        assert skill_path.exists()
        content = skill_path.read_text(encoding="utf-8")
        assert content.startswith("---\n")
        assert "id: S-42" in content
        assert "name: test-skill" in content
        assert "Cross-skill references" in content
        assert "## Purpose" in content

    def test_claude_creates_flat_file_no_cross_note(self, tmp_path, monkeypatch):
        """claude provider creates {slug}.md with frontmatter but NO cross-skill note."""
        providers = self._setup(tmp_path, monkeypatch, "test-skill", STANDARD_CANONICAL)

        changed, created = sync_provider("claude", create_missing=True)

        assert "test-skill" in created
        skill_path = providers["claude"] / "test-skill.md"
        assert skill_path.exists()
        content = skill_path.read_text(encoding="utf-8")
        assert content.startswith("---\n")
        assert "id: S-42" in content
        assert "Cross-skill references" not in content

    def test_kilocode_matches_agents_format(self, tmp_path, monkeypatch):
        """kilocode uses the same nested {slug}/SKILL.md format as agents."""
        providers = self._setup(tmp_path, monkeypatch, "test-skill", STANDARD_CANONICAL)

        changed, created = sync_provider("kilocode", create_missing=True)

        assert "test-skill" in created
        skill_path = providers["kilocode"] / "test-skill" / "SKILL.md"
        assert skill_path.exists()
        content = skill_path.read_text(encoding="utf-8")
        assert "Cross-skill references" in content
        assert "id: S-42" in content

    def test_internal_skill_skipped_for_claude(self, tmp_path, monkeypatch):
        """Internal skills (sub-routines) must NOT be created in the Claude tree."""
        providers = self._setup(tmp_path, monkeypatch, "knowledge-bootstrap", MINIMAL_CANONICAL)
        monkeypatch.setattr(
            sync_providers, "INTERNAL_SKILLS", frozenset({"knowledge-bootstrap"})
        )

        changed, created = sync_provider("claude", create_missing=True)

        assert "knowledge-bootstrap" not in created
        assert not (providers["claude"] / "knowledge-bootstrap.md").exists()

    def test_internal_skill_created_for_agents(self, tmp_path, monkeypatch):
        """Internal skills ARE created in agents/kilocode (they invoke them directly)."""
        providers = self._setup(tmp_path, monkeypatch, "knowledge-bootstrap", MINIMAL_CANONICAL)
        monkeypatch.setattr(
            sync_providers, "INTERNAL_SKILLS", frozenset({"knowledge-bootstrap"})
        )

        changed, created = sync_provider("agents", create_missing=True)

        assert "knowledge-bootstrap" in created
        assert (providers["agents"] / "knowledge-bootstrap" / "SKILL.md").exists()

    def test_no_id_guard_prevents_creation(self, tmp_path, monkeypatch):
        """Canonical without S-XX heading must NOT generate a provider file."""
        providers = self._setup(tmp_path, monkeypatch, "bad-skill", NO_ID_CANONICAL)

        changed, created = sync_provider("agents", create_missing=True)

        assert "bad-skill" not in created
        assert not (providers["agents"] / "bad-skill" / "SKILL.md").exists()

    def test_skip_slugs_respected(self, tmp_path, monkeypatch):
        """Skills listed in SKIP_SLUGS must not be created."""
        providers = self._setup(tmp_path, monkeypatch, "translate-batch", STANDARD_CANONICAL)
        monkeypatch.setattr(
            sync_providers, "SKIP_SLUGS", {"claude": {"translate-batch"}}
        )

        changed, created = sync_provider("claude", create_missing=True)

        assert "translate-batch" not in created
        assert not (providers["claude"] / "translate-batch.md").exists()

    def test_dry_run_does_not_write(self, tmp_path, monkeypatch):
        """dry_run=True must report the file but NOT create it on disk."""
        providers = self._setup(tmp_path, monkeypatch, "test-skill", STANDARD_CANONICAL)

        changed, created = sync_provider("agents", dry_run=True, create_missing=True)

        assert "test-skill" in created
        assert not (providers["agents"] / "test-skill" / "SKILL.md").exists()
