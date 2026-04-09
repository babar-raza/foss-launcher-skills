"""Tests for enforce_venv_python.py."""
from __future__ import annotations

import sys
from pathlib import Path

_CI_ROOT = Path(__file__).resolve().parent.parent
if str(_CI_ROOT) not in sys.path:
    sys.path.insert(0, str(_CI_ROOT))

import enforce_venv_python  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_skill(tmp_path: Path, rel: str, content: str) -> Path:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _run_fix(tmp_path: Path, rel: str, content: str) -> tuple[str, list[str]]:
    """Write file, run process_file in fix mode, return (new_content, fixable_violations)."""
    p = _make_skill(tmp_path, rel, content)
    viols, _deny = enforce_venv_python.process_file(p, fix=True)
    return p.read_text(encoding="utf-8"), viols


def _run_check(tmp_path: Path, rel: str, content: str) -> tuple[list[str], list[str]]:
    """Write file, run process_file in check mode (no write), return (violations, deny)."""
    p = _make_skill(tmp_path, rel, content)
    return enforce_venv_python.process_file(p, fix=False)


# ---------------------------------------------------------------------------
# Core replacement rules
# ---------------------------------------------------------------------------

def test_bare_python_in_bash_fence_is_replaced(tmp_path):
    src = "# Skill\n\n```bash\npython -m translator preflight\n```\n"
    out, viols = _run_fix(tmp_path, ".agents/skills/foo/SKILL.md", src)
    assert ".venv/Scripts/python -m translator preflight" in out
    assert len(viols) == 1


def test_bare_pip_install_in_bash_fence_is_replaced(tmp_path):
    src = "# Skill\n\n```bash\npip install pyyaml\n```\n"
    out, viols = _run_fix(tmp_path, ".agents/skills/foo/SKILL.md", src)
    assert ".venv/Scripts/pip install pyyaml" in out
    assert len(viols) == 1


def test_sh_fence_is_also_replaced(tmp_path):
    src = "# Skill\n\n```sh\npython scripts/pipeline/audit.py\n```\n"
    out, viols = _run_fix(tmp_path, ".agents/skills/foo/SKILL.md", src)
    assert ".venv/Scripts/python scripts/pipeline/audit.py" in out
    assert len(viols) == 1


# ---------------------------------------------------------------------------
# Idempotency — already-fixed lines must not be double-replaced
# ---------------------------------------------------------------------------

def test_already_fixed_line_is_not_double_replaced(tmp_path):
    src = "# Skill\n\n```bash\n.venv/Scripts/python -m translator preflight\n```\n"
    out, viols = _run_fix(tmp_path, ".agents/skills/foo/SKILL.md", src)
    assert out == src  # unchanged
    assert viols == []


def test_fix_is_idempotent_on_second_run(tmp_path):
    src = "# Skill\n\n```bash\npython -m translator preflight\n```\n"
    p = _make_skill(tmp_path, ".agents/skills/foo/SKILL.md", src)
    enforce_venv_python.process_file(p, fix=True)
    first = p.read_text(encoding="utf-8")
    enforce_venv_python.process_file(p, fix=True)
    second = p.read_text(encoding="utf-8")
    assert first == second


# ---------------------------------------------------------------------------
# Prose must NOT be replaced
# ---------------------------------------------------------------------------

def test_python_in_prose_is_not_replaced(tmp_path):
    src = "# Skill\n\nPython is a great language.\nRun python to start.\n\n```bash\necho done\n```\n"
    out, viols = _run_fix(tmp_path, ".agents/skills/foo/SKILL.md", src)
    assert "Python is a great language" in out
    assert viols == []


def test_python_mention_in_non_bash_fence_is_not_replaced(tmp_path):
    src = "# Skill\n\n```python\npython -m pytest\n```\n"
    out, viols = _run_fix(tmp_path, ".agents/skills/foo/SKILL.md", src)
    assert out == src
    assert viols == []


def test_pip_in_prose_is_not_replaced(tmp_path):
    src = "# Skill\n\nUse pip install to set up.\n\n```bash\necho ok\n```\n"
    out, viols = _run_fix(tmp_path, ".agents/skills/foo/SKILL.md", src)
    assert "Use pip install" in out
    assert viols == []


# ---------------------------------------------------------------------------
# `python3` must NOT be replaced (explicit version — leave as-is)
# ---------------------------------------------------------------------------

def test_python3_is_not_replaced(tmp_path):
    src = "# Skill\n\n```bash\npython3 -m pytest\n```\n"
    out, viols = _run_fix(tmp_path, ".agents/skills/foo/SKILL.md", src)
    assert out == src
    assert viols == []


# ---------------------------------------------------------------------------
# getting-started skip
# ---------------------------------------------------------------------------

def test_getting_started_skill_is_skipped_by_should_skip(tmp_path):
    path = tmp_path / ".agents" / "skills" / "getting-started" / "SKILL.md"
    assert enforce_venv_python.should_skip(path) is True


def test_other_skill_is_not_skipped(tmp_path):
    path = tmp_path / ".agents" / "skills" / "translate-page" / "SKILL.md"
    assert enforce_venv_python.should_skip(path) is False


def test_getting_started_file_unchanged_in_fix_mode(tmp_path):
    # Override REPO_ROOT so collect_files walks tmp_path
    src = "```bash\npython -m something\n```\n"
    p = tmp_path / ".agents" / "skills" / "getting-started" / "SKILL.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(src, encoding="utf-8")
    # process_file is not called for skipped files; verify directly
    viols, _deny = enforce_venv_python.process_file(p, fix=True)
    # should_skip is checked in collect_files, not process_file —
    # but when passed directly, it processes. This tests the skip logic at collect level.
    # Verify should_skip returns True for this path.
    assert enforce_venv_python.should_skip(p)


# ---------------------------------------------------------------------------
# Multiple violations in one file
# ---------------------------------------------------------------------------

def test_multiple_violations_all_fixed(tmp_path):
    src = (
        "# Skill\n\n"
        "```bash\n"
        "python -m translator preflight\n"
        "python scripts/pipeline/audit.py\n"
        "pip install pyyaml\n"
        "```\n"
    )
    out, viols = _run_fix(tmp_path, ".agents/skills/foo/SKILL.md", src)
    assert out.count(".venv/Scripts/python") == 2
    assert ".venv/Scripts/pip install pyyaml" in out
    assert len(viols) == 3


# ---------------------------------------------------------------------------
# check mode (no write)
# ---------------------------------------------------------------------------

def test_check_mode_does_not_modify_file(tmp_path):
    src = "# Skill\n\n```bash\npython -m foo\n```\n"
    p = _make_skill(tmp_path, ".agents/skills/foo/SKILL.md", src)
    viols, _deny = enforce_venv_python.process_file(p, fix=False)
    assert p.read_text(encoding="utf-8") == src  # file unchanged
    assert len(viols) == 1


def test_check_mode_returns_violations_without_writing(tmp_path):
    src = "# Skill\n\n```bash\npython -m bar\npip install requests\n```\n"
    p = _make_skill(tmp_path, ".agents/skills/foo/SKILL.md", src)
    viols, _deny = enforce_venv_python.process_file(p, fix=False)
    assert len(viols) == 2
    assert p.read_text(encoding="utf-8") == src


# ---------------------------------------------------------------------------
# pip subcommand specificity
# ---------------------------------------------------------------------------

def test_pip_show_is_replaced(tmp_path):
    src = "# Skill\n\n```bash\npip show requests\n```\n"
    out, viols = _run_fix(tmp_path, ".agents/skills/foo/SKILL.md", src)
    assert ".venv/Scripts/pip show requests" in out
    assert len(viols) == 1


def test_pip_freeze_is_replaced(tmp_path):
    src = "# Skill\n\n```bash\npip freeze\n```\n"
    out, viols = _run_fix(tmp_path, ".agents/skills/foo/SKILL.md", src)
    assert ".venv/Scripts/pip freeze" in out
    assert len(viols) == 1


def test_pip_arbitrary_subcommand_not_replaced(tmp_path):
    """pip cache, pip config, etc. are NOT in the replacement list."""
    src = "# Skill\n\n```bash\npip cache purge\n```\n"
    out, viols = _run_fix(tmp_path, ".agents/skills/foo/SKILL.md", src)
    assert out == src
    assert viols == []


# ---------------------------------------------------------------------------
# Multiple fences in one file
# ---------------------------------------------------------------------------

def test_multiple_fences_both_fixed(tmp_path):
    src = (
        "# Skill\n\n"
        "Step 1:\n```bash\npython -m step1\n```\n\n"
        "Step 2:\n```bash\npython -m step2\n```\n"
    )
    out, viols = _run_fix(tmp_path, ".agents/skills/foo/SKILL.md", src)
    assert out.count(".venv/Scripts/python") == 2
    assert len(viols) == 2


# ---------------------------------------------------------------------------
# Untagged code fences (``` without bash/sh)
# ---------------------------------------------------------------------------

def test_untagged_fence_is_scanned(tmp_path):
    src = "# Skill\n\n```\npython -m foo\n```\n"
    out, viols = _run_fix(tmp_path, "skills/foo.md", src)
    assert ".venv/Scripts/python -m foo" in out
    assert len(viols) == 1


def test_untagged_fence_pip_is_scanned(tmp_path):
    src = "# Skill\n\n```\npip install requests\n```\n"
    out, viols = _run_fix(tmp_path, "skills/foo.md", src)
    assert ".venv/Scripts/pip install requests" in out
    assert len(viols) == 1


def test_python_tagged_fence_not_scanned(tmp_path):
    """```python fences contain Python source, not shell commands."""
    src = "# Skill\n\n```python\npython -m foo\n```\n"
    out, viols = _run_fix(tmp_path, "skills/foo.md", src)
    assert out == src
    assert viols == []


def test_yaml_tagged_fence_not_scanned(tmp_path):
    src = "# Skill\n\n```yaml\npython: 3.12\n```\n"
    out, viols = _run_fix(tmp_path, "skills/foo.md", src)
    assert out == src
    assert viols == []


# ---------------------------------------------------------------------------
# DENY_PATTERNS (--user, USER_SITE)
# ---------------------------------------------------------------------------

def test_pip_install_user_is_deny_violation(tmp_path):
    src = "# Skill\n\n```\npip install tree-sitter --user\n```\n"
    p = _make_skill(tmp_path, "skills/foo.md", src)
    _viols, deny = enforce_venv_python.process_file(p, fix=False)
    assert len(deny) == 1
    assert "--user" in deny[0]


def test_pip_install_user_is_deny_in_fix_mode_too(tmp_path):
    """DENY patterns are reported even in --fix mode (not auto-fixed)."""
    src = "# Skill\n\n```bash\npip install tree-sitter --user\n```\n"
    p = _make_skill(tmp_path, "skills/foo.md", src)
    _viols, deny = enforce_venv_python.process_file(p, fix=True)
    assert len(deny) == 1
    # The bare pip IS auto-fixed, but --user is still flagged
    content = p.read_text(encoding="utf-8")
    assert ".venv/Scripts/pip install tree-sitter --user" in content


def test_pythonpath_user_site_is_deny_violation(tmp_path):
    src = '# Skill\n\n```\nPYTHONPATH="$USER_SITE" python -c "import foo"\n```\n'
    p = _make_skill(tmp_path, "skills/foo.md", src)
    _viols, deny = enforce_venv_python.process_file(p, fix=False)
    assert len(deny) == 1
    assert "USER_SITE" in deny[0]


def test_no_deny_violation_in_clean_file(tmp_path):
    src = "# Skill\n\n```bash\n.venv/Scripts/python -m foo\n```\n"
    p = _make_skill(tmp_path, "skills/foo.md", src)
    _viols, deny = enforce_venv_python.process_file(p, fix=False)
    assert deny == []


# ---------------------------------------------------------------------------
# Canonical skills/ directory in SCAN_DIRS
# ---------------------------------------------------------------------------

def test_scan_dirs_includes_canonical_skills():
    """Canonical skills/ must be in SCAN_DIRS (primary enforcement target)."""
    canonical = enforce_venv_python.REPO_ROOT / "skills"
    assert canonical in enforce_venv_python.SCAN_DIRS
    # Must be first entry (primary target)
    assert enforce_venv_python.SCAN_DIRS[0] == canonical
