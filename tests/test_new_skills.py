"""
Tests for the 19 new/upgraded skill files added in the foss-launcher-skills sync.

Covers:
- File existence
- YAML frontmatter validity and required fields
- No banned (Aspose-specific) strings in skill bodies
- Correct distribution to all 3 provider targets
"""
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools.distribute import distribute, parse_skill  # noqa: E402
from scripts.skill_constants import INTERNAL_SKILLS  # noqa: E402

SKILLS_DIR = REPO_ROOT / "skills"
BANNED_STRINGS_FILE = REPO_ROOT / "tests" / "fixtures" / "portability" / "banned_strings.txt"

# ---------------------------------------------------------------------------
# New skills that should exist after the sync
# ---------------------------------------------------------------------------

NEW_SKILL_NAMES = [
    "heal-page",            # Phase B: upgraded
    "code-smoke",           # Phase C1
    "page-retire",          # Phase C2
    "session-start",        # Phase C3
    "diagnose-skill-failure",  # Phase C4
    "register-human-content",  # Phase C5
    "evidence-repair",      # Phase C6
    "evidence-enhance",     # Phase C7
    "link-validate",        # Phase C8
    "batch-eval-fix",       # Phase C9
    "commit",               # Phase D
    "backlog",              # Phase D
    "manual-edit",          # Phase D
    "truth-audit",          # Phase D (S-90)
    "truth-audit-content",  # Phase D
    "coverage-reconcile",   # Phase D
    "knowledge-coverage-audit",  # Phase D
]


def load_banned_strings():
    """Load banned strings from fixtures file (skip blank lines and comments)."""
    lines = BANNED_STRINGS_FILE.read_text(encoding="utf-8").splitlines()
    return [ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")]


# ---------------------------------------------------------------------------
# Existence tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("skill_name", NEW_SKILL_NAMES)
def test_new_skill_file_exists(skill_name):
    """Each new skill file must exist in skills/."""
    skill_file = SKILLS_DIR / f"{skill_name}.md"
    assert skill_file.exists(), f"Missing skill file: skills/{skill_name}.md"


# ---------------------------------------------------------------------------
# Frontmatter structure tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("skill_name", NEW_SKILL_NAMES)
def test_new_skill_frontmatter_parses(skill_name):
    """Each skill must have valid YAML frontmatter."""
    skill_file = SKILLS_DIR / f"{skill_name}.md"
    if not skill_file.exists():
        pytest.skip(f"skills/{skill_name}.md not found")
    content = skill_file.read_text(encoding="utf-8")
    fm, _ = parse_skill(content)
    if fm:
        try:
            parsed = yaml.safe_load(fm.strip("---\n"))
            assert parsed is not None, f"Frontmatter parsed as None in {skill_name}.md"
        except yaml.YAMLError as e:
            pytest.fail(f"Invalid YAML frontmatter in {skill_name}.md: {e}")


@pytest.mark.parametrize("skill_name", NEW_SKILL_NAMES)
def test_new_skill_frontmatter_required_fields(skill_name):
    """Each skill frontmatter must contain name, id, description."""
    skill_file = SKILLS_DIR / f"{skill_name}.md"
    if not skill_file.exists():
        pytest.skip(f"skills/{skill_name}.md not found")
    content = skill_file.read_text(encoding="utf-8")
    fm, _ = parse_skill(content)
    if not fm:
        pytest.skip(f"{skill_name}.md has no frontmatter (acceptable for legacy skills)")
    parsed = yaml.safe_load(fm.strip("---\n"))
    assert parsed is not None
    for field in ("name", "id", "description"):
        assert field in parsed, f"skills/{skill_name}.md frontmatter missing required field: '{field}'"


@pytest.mark.parametrize("skill_name", NEW_SKILL_NAMES)
def test_new_skill_name_matches_filename(skill_name):
    """Frontmatter 'name' must match the filename (without .md)."""
    skill_file = SKILLS_DIR / f"{skill_name}.md"
    if not skill_file.exists():
        pytest.skip(f"skills/{skill_name}.md not found")
    content = skill_file.read_text(encoding="utf-8")
    fm, _ = parse_skill(content)
    if not fm:
        pytest.skip(f"{skill_name}.md has no frontmatter")
    parsed = yaml.safe_load(fm.strip("---\n"))
    if parsed and "name" in parsed:
        assert parsed["name"] == skill_name, (
            f"skills/{skill_name}.md: frontmatter name='{parsed['name']}' "
            f"does not match filename '{skill_name}'"
        )


# ---------------------------------------------------------------------------
# Portability tests — no banned strings
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("skill_name", NEW_SKILL_NAMES)
def test_new_skill_no_banned_strings(skill_name):
    """New skill files must not contain Aspose-specific strings in their body."""
    skill_file = SKILLS_DIR / f"{skill_name}.md"
    if not skill_file.exists():
        pytest.skip(f"skills/{skill_name}.md not found")

    banned = load_banned_strings()
    content = skill_file.read_text(encoding="utf-8")

    # Strip frontmatter before checking
    _, body = parse_skill(content)

    violations = []
    for banned_str in banned:
        if banned_str.lower() in body.lower():
            violations.append(banned_str)

    assert not violations, (
        f"skills/{skill_name}.md contains banned (source-specific) strings: {violations}\n"
        f"These strings must be replaced with config-driven or generic equivalents."
    )


# ---------------------------------------------------------------------------
# Distribution tests
# ---------------------------------------------------------------------------

def test_new_skill_distributed_to_codex(tmp_path):
    """Every new skill must be distributed to .agents/skills/{name}/SKILL.md."""
    distribute(SKILLS_DIR, tmp_path)
    for name in NEW_SKILL_NAMES:
        skill_file = tmp_path / ".agents" / "skills" / name / "SKILL.md"
        assert skill_file.exists(), (
            f"Skill '{name}' not found in .agents/skills/{name}/SKILL.md after distribution"
        )


def test_new_skill_distributed_to_kilocode(tmp_path):
    """Every new skill must be distributed to .kilocode/skills/{name}/SKILL.md."""
    distribute(SKILLS_DIR, tmp_path)
    for name in NEW_SKILL_NAMES:
        skill_file = tmp_path / ".kilocode" / "skills" / name / "SKILL.md"
        assert skill_file.exists(), (
            f"Skill '{name}' not found in .kilocode/skills/{name}/SKILL.md after distribution"
        )


def test_new_public_skills_distributed_to_claude(tmp_path):
    """Non-internal new skills must appear in .claude/commands/ after distribution."""
    distribute(SKILLS_DIR, tmp_path)
    public_new_skills = [n for n in NEW_SKILL_NAMES if n not in INTERNAL_SKILLS]
    for name in public_new_skills:
        claude_file = tmp_path / ".claude" / "commands" / f"{name}.md"
        assert claude_file.exists(), (
            f"Public skill '{name}' not found in .claude/commands/{name}.md after distribution"
        )


def test_new_internal_skills_not_in_claude(tmp_path):
    """Internal new skills must NOT appear in .claude/commands/ after distribution."""
    distribute(SKILLS_DIR, tmp_path)
    internal_new_skills = [n for n in NEW_SKILL_NAMES if n in INTERNAL_SKILLS]
    for name in internal_new_skills:
        claude_file = tmp_path / ".claude" / "commands" / f"{name}.md"
        assert not claude_file.exists(), (
            f"Internal skill '{name}' should NOT be in .claude/commands/ but was found there"
        )
