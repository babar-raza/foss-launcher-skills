"""test_check_skill_command_parity.py — Regression tests for check_skill_command_parity.py (RPR-G-02).

Covers 3-mirror parity detection (.agents / .claude / .kilocode), normalized
comparison, co-change enforcement with the SKILL-COMMAND-DIVERGENCE-ACK trailer,
and the specific class of drift a 2-way check would miss (only .kilocode diverges).
"""
import sys
from pathlib import Path

# Bootstrap: add scripts/ci/ to sys.path so `from checks.X import ...` works.
_HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HERE))

from checks import check_skill_command_parity as parity  # noqa: E402


def _make_skill(tmp_path, name, agents, claude=None, kilo=None):
    (tmp_path / ".agents" / "skills" / name).mkdir(parents=True, exist_ok=True)
    (tmp_path / ".agents" / "skills" / name / "SKILL.md").write_text(agents, encoding="utf-8")
    if claude is not None:
        (tmp_path / ".claude" / "commands").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".claude" / "commands" / f"{name}.md").write_text(claude, encoding="utf-8")
    if kilo is not None:
        (tmp_path / ".kilocode" / "skills" / name).mkdir(parents=True, exist_ok=True)
        (tmp_path / ".kilocode" / "skills" / name / "SKILL.md").write_text(kilo, encoding="utf-8")


def _point_at(monkeypatch, tmp_path):
    monkeypatch.setattr(parity, "_AGENTS_DIR", tmp_path / ".agents" / "skills")
    monkeypatch.setattr(parity, "_CLAUDE_DIR", tmp_path / ".claude" / "commands")
    monkeypatch.setattr(parity, "_KILO_DIR", tmp_path / ".kilocode" / "skills")


def test_matching_triple_not_divergent(tmp_path, monkeypatch):
    _point_at(monkeypatch, tmp_path)
    body = "# S-10\n\nStep 1\nStep 2\n"
    _make_skill(tmp_path, "foo", body, body, body)
    result = parity.compare_skill("foo")
    assert result["divergent"] is False
    assert set(result["present"]) == {"agents", "claude", "kilocode"}


def test_divergent_claude_mirror_flagged(tmp_path, monkeypatch):
    _point_at(monkeypatch, tmp_path)
    _make_skill(tmp_path, "foo", "# S-10\n\ncanonical body\n",
                "# S-10\n\nDIVERGED body\n", "# S-10\n\ncanonical body\n")
    result = parity.compare_skill("foo")
    assert result["divergent"] is True
    assert "claude" in result["divergent_mirrors"]


def test_only_kilocode_diverges_still_flagged(tmp_path, monkeypatch):
    """The exact drift class a 2-way (.agents vs .claude) check would miss."""
    _point_at(monkeypatch, tmp_path)
    _make_skill(tmp_path, "foo", "# S-10\n\ncanonical body\n",
                "# S-10\n\ncanonical body\n", "# S-10\n\nDIVERGED kilo body\n")
    result = parity.compare_skill("foo")
    assert result["divergent"] is True
    assert result["divergent_mirrors"] == ["kilocode"]


def test_whitespace_only_difference_not_divergent(tmp_path, monkeypatch):
    _point_at(monkeypatch, tmp_path)
    # Create the skill, then overwrite the kilocode mirror as bytes with real CRLF
    # line endings so the on-disk content is exactly LF-vs-CRLF of the same text
    # (write_text in Windows text mode would double-translate embedded \r\n).
    _make_skill(tmp_path, "foo", "# S-10\nbody\n", "# S-10\nbody   \n", "placeholder\n")
    (tmp_path / ".kilocode" / "skills" / "foo" / "SKILL.md").write_bytes(b"# S-10\r\nbody\r\n")
    assert parity.compare_skill("foo")["divergent"] is False


def test_single_mirror_not_divergent(tmp_path, monkeypatch):
    """A skill with only the canonical file (no mirrors) is not divergent."""
    _point_at(monkeypatch, tmp_path)
    _make_skill(tmp_path, "foo", "# S-10\nbody\n")
    assert parity.compare_skill("foo")["divergent"] is False


def test_cochange_flags_divergent_touched_skill(tmp_path, monkeypatch):
    _point_at(monkeypatch, tmp_path)
    _make_skill(tmp_path, "foo", "# S-10\ncanonical\n", "# S-10\nDIVERGED\n")
    problems = parity.check_cochange([".claude/commands/foo.md"])
    assert len(problems) == 1
    assert "foo" in problems[0]


def test_cochange_ack_trailer_overrides(tmp_path, monkeypatch):
    _point_at(monkeypatch, tmp_path)
    _make_skill(tmp_path, "foo", "# S-10\ncanonical\n", "# S-10\nDIVERGED\n")
    problems = parity.check_cochange(
        [".claude/commands/foo.md"],
        commit_msg="fix: cosmetic\n\nSKILL-COMMAND-DIVERGENCE-ACK: intentional command-only rename",
    )
    assert problems == []


def test_cochange_clean_when_mirrors_match(tmp_path, monkeypatch):
    _point_at(monkeypatch, tmp_path)
    body = "# S-10\nbody\n"
    _make_skill(tmp_path, "foo", body, body, body)
    assert parity.check_cochange([".agents/skills/foo/SKILL.md"]) == []


def test_reproduces_2026_06_27_divergence_pattern(tmp_path, monkeypatch):
    """The literal failure: only .claude mirror wired, canonical never touched."""
    _point_at(monkeypatch, tmp_path)
    canonical = "# S-105 body-refresh\n\nStep 1\nStep 2\n"
    wired_mirror = "# S-105 body-refresh\n\nStep 1\nStep 2\nStep 3.6 dispatch\n"
    _make_skill(tmp_path, "body-refresh", canonical, wired_mirror, canonical)
    problems = parity.check_cochange([".claude/commands/body-refresh.md"])
    assert len(problems) == 1


def test_skill_name_for_file():
    assert parity._skill_name_for_file(".agents/skills/foo/SKILL.md") == "foo"
    assert parity._skill_name_for_file(".claude/commands/foo.md") == "foo"
    assert parity._skill_name_for_file(".kilocode/skills/foo/SKILL.md") == "foo"
    assert parity._skill_name_for_file("scripts/pipeline/x.py") is None
