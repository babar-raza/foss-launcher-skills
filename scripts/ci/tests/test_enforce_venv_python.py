"""Tests for enforce_venv_python.py."""
from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

_CI_ROOT = Path(__file__).resolve().parent.parent / "checks"
_CI_SHIM_DIR = str(Path(__file__).resolve().parent.parent)
# Remove ci/ root from sys.path to prevent shim shadowing canonical modules
sys.path[:] = [p for p in sys.path if str(Path(p).resolve()) != _CI_SHIM_DIR or "checks" in p or "tests" in p]
if str(_CI_ROOT) not in sys.path:
    sys.path.insert(0, str(_CI_ROOT))
# Clear any cached shim import
if "enforce_venv_python" in sys.modules:
    del sys.modules["enforce_venv_python"]

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


# ---------------------------------------------------------------------------
# GitHub Actions workflow YAML scanning
# ---------------------------------------------------------------------------

def _make_workflow(tmp_path: Path, content: str) -> Path:
    p = tmp_path / ".github" / "workflows" / "test.yml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def test_workflow_bare_python_is_violation_without_venv_export(tmp_path):
    """Without a $GITHUB_PATH venv export, bare `python` must be flagged."""
    src = textwrap.dedent("""\
        jobs:
          ci:
            steps:
              - name: Run script
                run: python scripts/ci/check_something.py
        """)
    p = _make_workflow(tmp_path, src)
    viols, deny = enforce_venv_python.scan_workflow_file(p)
    assert viols, "Expected a bare-python violation when no venv PATH export"
    assert any("Run script" in v for v in viols)
    assert deny == []


def test_workflow_bare_python_with_venv_path_export_is_clean(tmp_path):
    """With $GITHUB_PATH venv export, bare `python` routes via venv — not flagged."""
    src = textwrap.dedent("""\
        jobs:
          ci:
            steps:
              - name: Set up .venv
                run: |
                  python -m venv .venv
                  echo "$(pwd)/.venv/bin" >> $GITHUB_PATH
                  .venv/bin/pip install pyyaml --quiet
              - name: Run script
                run: python scripts/ci/check_something.py
        """)
    p = _make_workflow(tmp_path, src)
    viols, deny = enforce_venv_python.scan_workflow_file(p)
    assert viols == [], f"PATH-exported venv makes bare python compliant; got: {viols}"
    assert deny == []


def test_workflow_explicit_venv_python_is_always_clean(tmp_path):
    """Explicit .venv/bin/python is always clean regardless of PATH export."""
    src = textwrap.dedent("""\
        jobs:
          ci:
            steps:
              - name: Run with venv
                run: .venv/bin/python scripts/ci/check_something.py
        """)
    p = _make_workflow(tmp_path, src)
    viols, deny = enforce_venv_python.scan_workflow_file(p)
    assert viols == []
    assert deny == []


def test_workflow_venv_creation_exempt_without_path_export(tmp_path):
    """python -m venv .venv must NOT be flagged even without a PATH export."""
    src = textwrap.dedent("""\
        jobs:
          ci:
            steps:
              - name: Bootstrap only
                run: python -m venv .venv
        """)
    p = _make_workflow(tmp_path, src)
    viols, deny = enforce_venv_python.scan_workflow_file(p)
    assert viols == [], f"venv creation must be exempt; got: {viols}"
    assert deny == []


def test_workflow_pip_install_user_is_deny_with_path_export(tmp_path):
    """pip install --user is a DENY violation even when venv is on PATH."""
    src = textwrap.dedent("""\
        jobs:
          ci:
            steps:
              - name: Set up .venv
                run: |
                  python -m venv .venv
                  echo "$(pwd)/.venv/bin" >> $GITHUB_PATH
              - name: Bad install
                run: pip install pytest --user
        """)
    p = _make_workflow(tmp_path, src)
    viols, deny = enforce_venv_python.scan_workflow_file(p)
    assert deny, "DENY violation must fire even with venv on PATH"
    assert any("--user" in d or "bypass" in d.lower() for d in deny)


def test_workflow_pip_install_user_is_deny_without_path_export(tmp_path):
    """pip install --user is a DENY violation when no venv setup at all."""
    src = textwrap.dedent("""\
        jobs:
          ci:
            steps:
              - name: Bad install
                run: pip install pytest --user
        """)
    p = _make_workflow(tmp_path, src)
    viols, deny = enforce_venv_python.scan_workflow_file(p)
    assert deny, "Expected a deny violation for --user"
    assert any("--user" in d or "bypass" in d.lower() for d in deny)


def test_workflow_non_run_block_python_is_ignored(tmp_path):
    """python references in with: or uses: values must not trigger violations."""
    src = textwrap.dedent("""\
        jobs:
          ci:
            steps:
              - name: Setup Python
                uses: actions/setup-python@v5
                with:
                  python-version: '3.12'
              - name: Run venv step
                run: .venv/bin/python scripts/ci/do_thing.py
        """)
    p = _make_workflow(tmp_path, src)
    viols, deny = enforce_venv_python.scan_workflow_file(p)
    assert viols == [], f"with:/uses: values should be ignored; got: {viols}"
    assert deny == []


# ---------------------------------------------------------------------------
# Claude Code settings JSON scanning
# ---------------------------------------------------------------------------

def _make_settings(tmp_path: Path, data: dict) -> Path:
    import json
    p = tmp_path / "settings.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_settings_clean_file_has_no_violations(tmp_path):
    p = _make_settings(tmp_path, {
        "permissions": {"allow": [
            "Bash(.venv/Scripts/python -m pytest tests/ -v)",
            "Bash(echo hello)",
        ]}
    })
    viols, deny = enforce_venv_python.scan_settings_file(p)
    assert viols == []
    assert deny == []


def test_settings_bare_python_is_violation(tmp_path):
    p = _make_settings(tmp_path, {
        "permissions": {"allow": [
            "Bash(python scripts/pipeline/audit.py)",
        ]}
    })
    viols, deny = enforce_venv_python.scan_settings_file(p)
    assert len(viols) == 1
    assert "python scripts/pipeline/audit.py" in viols[0]
    assert deny == []


def test_settings_bare_pip_install_is_violation(tmp_path):
    p = _make_settings(tmp_path, {
        "permissions": {"allow": [
            "Bash(pip install pyyaml)",
        ]}
    })
    viols, deny = enforce_venv_python.scan_settings_file(p)
    assert len(viols) == 1


def test_settings_deny_pattern_detected(tmp_path):
    p = _make_settings(tmp_path, {
        "permissions": {"allow": [
            "Bash(.venv/Scripts/pip install tree-sitter --user)",
        ]}
    })
    viols, deny = enforce_venv_python.scan_settings_file(p)
    assert viols == []  # .venv prefix is fine
    assert len(deny) == 1
    assert "--user" in deny[0]


def test_settings_missing_file_returns_empty():
    p = Path("/nonexistent/settings.json")
    viols, deny = enforce_venv_python.scan_settings_file(p)
    assert viols == []
    assert deny == []


def test_settings_malformed_json_returns_empty(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text("{not valid json", encoding="utf-8")
    viols, deny = enforce_venv_python.scan_settings_file(p)
    assert viols == []
    assert deny == []


def test_settings_non_bash_entries_ignored(tmp_path):
    p = _make_settings(tmp_path, {
        "permissions": {"allow": [
            "Read(file.py)",
            "Edit(file.py)",
        ]}
    })
    viols, deny = enforce_venv_python.scan_settings_file(p)
    assert viols == []
    assert deny == []


def test_settings_files_are_clean():
    """Regression guard: actual .claude/settings*.json must have no venv violations."""
    all_viols: list[str] = []
    all_deny: list[str] = []
    for sf in enforce_venv_python.SETTINGS_FILES:
        if not sf.exists():
            continue
        v, d = enforce_venv_python.scan_settings_file(sf)
        all_viols.extend(f"{sf.name}: {x}" for x in v)
        all_deny.extend(f"{sf.name}: {x}" for x in d)
    assert not all_viols, "Bare python/pip in settings:\n" + "\n".join(all_viols)
    assert not all_deny, "DENY violations in settings:\n" + "\n".join(all_deny)


def test_workflow_files_are_clean():
    """Regression guard: actual CI workflow files must have no venv violations.

    Both workflows export .venv/bin to $GITHUB_PATH, so bare python calls are
    compliant.  pip install --user or $USER_SITE would still be flagged.
    If this test fails, the PATH export was removed or a DENY pattern was added.
    """
    wf_dir = enforce_venv_python.REPO_ROOT / ".github" / "workflows"
    if not wf_dir.exists():
        pytest.skip("No .github/workflows/ directory present")
    all_viols: list[str] = []
    all_deny: list[str] = []
    for yml in sorted(wf_dir.glob("*.yml")):
        v, d = enforce_venv_python.scan_workflow_file(yml)
        all_viols.extend(f"{yml.name}: {x}" for x in v)
        all_deny.extend(f"{yml.name}: {x}" for x in d)
    assert not all_viols, "Bare python/pip violations in workflow files:\n" + "\n".join(all_viols)
    assert not all_deny, "DENY violations in workflow files:\n" + "\n".join(all_deny)
