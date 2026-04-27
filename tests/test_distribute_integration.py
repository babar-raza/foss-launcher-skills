"""Integration test: run distribute.py against output/distributed/ and verify outputs."""
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.skill_constants import INTERNAL_SKILLS  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DISTRIBUTE_SCRIPT = REPO_ROOT / "tools" / "distribute.py"
SKILLS_DIR = REPO_ROOT / "skills"
OUTPUT_DIR = REPO_ROOT / "output" / "distributed"


def _run_distribute(target: Path):
    return subprocess.run(
        [sys.executable, str(DISTRIBUTE_SCRIPT), str(target)],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )


# ---------------------------------------------------------------------------
# Tests against tmp_path (isolated)
# ---------------------------------------------------------------------------

def test_distribute_script_exits_zero(tmp_path):
    result = _run_distribute(tmp_path)
    assert result.returncode == 0, f"distribute.py failed:\n{result.stderr}"


def test_distribute_script_creates_claude_commands(tmp_path):
    _run_distribute(tmp_path)
    assert (tmp_path / ".claude" / "commands").is_dir()


def test_distribute_script_creates_agent_skills(tmp_path):
    _run_distribute(tmp_path)
    assert (tmp_path / ".agents" / "skills").is_dir()


def test_distribute_script_creates_kilocode_skills(tmp_path):
    _run_distribute(tmp_path)
    assert (tmp_path / ".kilocode" / "skills").is_dir()


def test_distribute_script_skill_count(tmp_path):
    _run_distribute(tmp_path)
    skill_count = len(list(SKILLS_DIR.glob("*.md")))
    claude_count = len(list((tmp_path / ".claude" / "commands").glob("*.md")))
    expected = skill_count - len(INTERNAL_SKILLS)
    assert claude_count == expected, (
        f"Claude should have {expected} skills (total={skill_count}, internal={len(INTERNAL_SKILLS)})"
    )


def test_distribute_no_frontmatter_in_claude_commands(tmp_path):
    _run_distribute(tmp_path)
    for f in (tmp_path / ".claude" / "commands").glob("*.md"):
        content = f.read_text(encoding="utf-8")
        assert not content.startswith("---"), f"{f.name} must not have frontmatter"


def test_distribute_frontmatter_in_agents(tmp_path):
    _run_distribute(tmp_path)
    for skill_dir in (tmp_path / ".agents" / "skills").iterdir():
        if (skill_dir / "SKILL.md").exists():
            content = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
            assert content.startswith("---"), f"{skill_dir.name} SKILL.md must have frontmatter"


def test_distribute_repo_scout_in_claude(tmp_path):
    """Spot-check that repo-scout.md is distributed to Claude commands."""
    _run_distribute(tmp_path)
    assert (tmp_path / ".claude" / "commands" / "repo-scout.md").exists()


def test_distribute_repo_scout_skill_in_agents(tmp_path):
    """Spot-check that repo-scout/SKILL.md is distributed to Codex agents."""
    _run_distribute(tmp_path)
    assert (tmp_path / ".agents" / "skills" / "repo-scout" / "SKILL.md").exists()


# ---------------------------------------------------------------------------
# Persistent output to output/distributed/ (for manual inspection)
# ---------------------------------------------------------------------------

def test_distribute_to_output_dir():
    """Run distribute against the canonical output/distributed/ dir."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    result = _run_distribute(OUTPUT_DIR)
    assert result.returncode == 0, f"distribute.py failed:\n{result.stderr}"
    skill_count = len(list(SKILLS_DIR.glob("*.md")))
    claude_count = len(list((OUTPUT_DIR / ".claude" / "commands").glob("*.md")))
    assert claude_count == skill_count
