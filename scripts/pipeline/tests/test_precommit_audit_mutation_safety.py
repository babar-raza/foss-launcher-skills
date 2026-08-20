"""Tests for check_precommit_audit_mutation_safety.py -- the best-effort
static half of the mutation-safety control (2026-08-20 production
assessment, reports/skill-gaps/2026-08-20-git-plumb-commit-tier1-mutation-
safety.md). The authoritative control is git_plumb_commit.py's own runtime
postcondition (see test_git_plumb_commit.py::TestPostconditionSafetyNet) --
these tests only cover this script's own, narrower promise: registered
guards stay present.
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[2]
sys.path.insert(0, str(_REPO_ROOT / "scripts" / "ci" / "checks"))

import check_precommit_audit_mutation_safety as checker  # noqa: E402


def test_passes_against_the_real_script_today():
    """Regression gate: the two known-registered guards (Step 5, Step 10)
    must actually be present in the real, current script."""
    ok, messages = checker.check(checker._DEFAULT_SCRIPT, checker._DEFAULT_REGISTRY)
    assert ok, messages


def test_fails_when_a_registered_guard_is_removed(tmp_path):
    """Proves the check has teeth -- not just silent because nothing's
    wrong."""
    registry = tmp_path / "registry.yaml"
    registry.write_text(
        'steps:\n  - name: "fake step"\n    guard: "PC_AUDIT_NO_MUTATE"\n',
        encoding="utf-8",
    )
    script = tmp_path / "fake-precommit-audit.sh"
    script.write_text(
        '_pc_step_start "fake step"\n'
        "echo hello\n"  # no PC_AUDIT_NO_MUTATE anywhere in this block
        '_pc_step_start "next step"\n'
        "echo world\n",
        encoding="utf-8",
    )
    ok, messages = checker.check(script, registry)
    assert ok is False
    assert any("REQUIRED FAIL" in m and "fake step" in m for m in messages)


def test_passes_when_the_registered_guard_is_present(tmp_path):
    registry = tmp_path / "registry.yaml"
    registry.write_text(
        'steps:\n  - name: "fake step"\n    guard: "PC_AUDIT_NO_MUTATE"\n',
        encoding="utf-8",
    )
    script = tmp_path / "fake-precommit-audit.sh"
    script.write_text(
        '_pc_step_start "fake step"\n'
        'if [ -n "${PC_AUDIT_NO_MUTATE:-}" ]; then echo skip; else git add -f x; fi\n'
        '_pc_step_start "next step"\n'
        "echo world\n",
        encoding="utf-8",
    )
    ok, messages = checker.check(script, registry)
    assert ok is True


def test_fails_when_a_registered_step_is_renamed_or_missing(tmp_path):
    registry = tmp_path / "registry.yaml"
    registry.write_text(
        'steps:\n  - name: "renamed away"\n    guard: "PC_AUDIT_NO_MUTATE"\n',
        encoding="utf-8",
    )
    script = tmp_path / "fake-precommit-audit.sh"
    script.write_text('_pc_step_start "something else"\necho hi\n', encoding="utf-8")
    ok, messages = checker.check(script, registry)
    assert ok is False
    assert any("not found" in m for m in messages)


def test_advisory_flags_an_unregistered_mutation_signature_without_failing(tmp_path):
    registry = tmp_path / "registry.yaml"
    registry.write_text("steps: []\n", encoding="utf-8")
    script = tmp_path / "fake-precommit-audit.sh"
    script.write_text(
        '_pc_step_start "unregistered mutator"\n'
        "git checkout HEAD -- somefile.txt\n",
        encoding="utf-8",
    )
    ok, messages = checker.check(script, registry)
    assert ok is True  # advisory only -- never blocks
    assert any("ADVISORY" in m and "unregistered mutator" in m for m in messages)


def test_advisory_does_not_flag_a_genuinely_read_only_step(tmp_path):
    registry = tmp_path / "registry.yaml"
    registry.write_text("steps: []\n", encoding="utf-8")
    script = tmp_path / "fake-precommit-audit.sh"
    script.write_text(
        '_pc_step_start "read only step"\n'
        "git diff --cached --name-only\n",
        encoding="utf-8",
    )
    ok, messages = checker.check(script, registry)
    assert ok is True
    assert not any("ADVISORY" in m for m in messages)


def test_cli_exits_nonzero_on_required_failure(tmp_path, capsys):
    registry = tmp_path / "registry.yaml"
    registry.write_text(
        'steps:\n  - name: "fake step"\n    guard: "PC_AUDIT_NO_MUTATE"\n',
        encoding="utf-8",
    )
    script = tmp_path / "fake-precommit-audit.sh"
    script.write_text('_pc_step_start "fake step"\necho hi\n', encoding="utf-8")

    rc = checker.main(["--script", str(script), "--registry", str(registry)])

    assert rc == 1
    assert "FAIL" in capsys.readouterr().err
