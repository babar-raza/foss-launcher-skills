"""Portability tests for the llms-generate/coverage/fidelity skill files
(ported 2026-08-29). Mirrors tests/test_new_skills.py's banned-strings
pattern but scoped to this specific cohort rather than appended to that
file's list (which documents a different, earlier, dated sync)."""
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
BANNED_STRINGS_FILE = REPO_ROOT / "tests" / "fixtures" / "portability" / "banned_strings.txt"

LLMS_SKILL_NAMES = ["llms-generate", "llms-coverage", "llms-fidelity"]


def load_banned_strings():
    lines = BANNED_STRINGS_FILE.read_text(encoding="utf-8").splitlines()
    return [ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")]


def _split_frontmatter(text: str) -> tuple[str, str]:
    if not text.startswith("---"):
        return "", text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return "", text
    return parts[1], parts[2]


@pytest.mark.parametrize("skill_name", LLMS_SKILL_NAMES)
def test_llms_skill_exists(skill_name):
    assert (SKILLS_DIR / f"{skill_name}.md").exists()


@pytest.mark.parametrize("skill_name", LLMS_SKILL_NAMES)
def test_llms_skill_frontmatter_valid(skill_name):
    text = (SKILLS_DIR / f"{skill_name}.md").read_text(encoding="utf-8")
    fm_text, _ = _split_frontmatter(text)
    parsed = yaml.safe_load(fm_text)
    assert parsed["name"] == skill_name
    assert parsed["id"].startswith("S-")
    assert parsed["description"]


@pytest.mark.parametrize("skill_name", LLMS_SKILL_NAMES)
def test_llms_skill_no_banned_strings(skill_name):
    text = (SKILLS_DIR / f"{skill_name}.md").read_text(encoding="utf-8")
    _, body = _split_frontmatter(text)
    banned = load_banned_strings()
    violations = [b for b in banned if b.lower() in body.lower()]
    assert not violations, f"skills/{skill_name}.md contains banned strings: {violations}"


@pytest.mark.parametrize("skill_name", LLMS_SKILL_NAMES)
def test_llms_skill_mirrored_to_all_three_adapters(skill_name):
    claude_path = REPO_ROOT / ".claude" / "commands" / f"{skill_name}.md"
    codex_path = REPO_ROOT / ".agents" / "skills" / skill_name / "SKILL.md"
    kilo_path = REPO_ROOT / ".kilocode" / "skills" / skill_name / "SKILL.md"
    assert claude_path.is_file(), f"missing Claude mirror for {skill_name}"
    assert codex_path.is_file(), f"missing Codex mirror for {skill_name}"
    assert kilo_path.is_file(), f"missing KiloCode mirror for {skill_name}"


@pytest.mark.parametrize("skill_name", LLMS_SKILL_NAMES)
def test_llms_skill_registered_with_backing_script(skill_name):
    registry = yaml.safe_load((SKILLS_DIR / "registry.yaml").read_text(encoding="utf-8"))
    entries = [s for s in registry["skills"] if s["name"] == skill_name]
    assert len(entries) == 1, f"{skill_name} should have exactly one registry.yaml entry"
    entry = entries[0]
    assert entry["internal"] is False
    assert entry["script"] and (REPO_ROOT / entry["script"]).is_file()
