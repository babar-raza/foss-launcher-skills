"""Portability/registration tests for skills/workflow-harden.md (S-121,
ported 2026-08-29 from aspose.org's S-115)."""
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
BANNED_STRINGS_FILE = REPO_ROOT / "tests" / "fixtures" / "portability" / "banned_strings.txt"


def _load_banned_strings():
    lines = BANNED_STRINGS_FILE.read_text(encoding="utf-8").splitlines()
    return [ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")]


def _split_frontmatter(text):
    if not text.startswith("---"):
        return "", text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return "", text
    return parts[1], parts[2]


def test_workflow_harden_exists():
    assert (SKILLS_DIR / "workflow-harden.md").exists()


def test_workflow_harden_frontmatter_valid():
    text = (SKILLS_DIR / "workflow-harden.md").read_text(encoding="utf-8")
    fm_text, _ = _split_frontmatter(text)
    parsed = yaml.safe_load(fm_text)
    assert parsed["name"] == "workflow-harden"
    assert parsed["id"] == "S-121"


def test_workflow_harden_no_banned_strings():
    text = (SKILLS_DIR / "workflow-harden.md").read_text(encoding="utf-8")
    _, body = _split_frontmatter(text)
    banned = _load_banned_strings()
    violations = [b for b in banned if b.lower() in body.lower()]
    assert not violations, f"contains banned strings: {violations}"


def test_workflow_harden_mirrored_to_all_three_adapters():
    assert (REPO_ROOT / ".claude" / "commands" / "workflow-harden.md").is_file()
    assert (REPO_ROOT / ".agents" / "skills" / "workflow-harden" / "SKILL.md").is_file()
    assert (REPO_ROOT / ".kilocode" / "skills" / "workflow-harden" / "SKILL.md").is_file()


def test_workflow_harden_registered_as_agent_executed():
    registry = yaml.safe_load((SKILLS_DIR / "registry.yaml").read_text(encoding="utf-8"))
    entries = [s for s in registry["skills"] if s["name"] == "workflow-harden"]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["internal"] is False
    assert entry["script"] is None  # agent-executed, matching source's own contract shape


def test_workflow_harden_does_not_assume_github_only():
    """The whole point of the generalization: source assumes GitHub Actions
    only ("this repo has no GitLab CI"); this port must not carry that
    assumption forward, since this repo actually runs both."""
    text = (SKILLS_DIR / "workflow-harden.md").read_text(encoding="utf-8")
    assert "gitlab" in text.lower()
    assert "no gitlab ci" not in text.lower()
