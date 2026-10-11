"""Tests for check_subprocess_encoding_parity.py (2026-08-30 stale-guard plan,
T7 / TC-SG-06): call-SHAPE linting (aliases included), the hook-heredoc stdin
scan, and the ratchet-baseline semantics."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from checks import check_subprocess_encoding_parity as parity  # noqa: E402


@pytest.fixture(autouse=True)
def _reset():
    yield
    parity.configure()


def _fixture_scripts(tmp_path: Path) -> Path:
    root = tmp_path / "root"
    (root / "scripts").mkdir(parents=True)
    parity.configure(repo_root=root)
    return root / "scripts"


def test_bare_text_true_is_flagged(tmp_path):
    scripts = _fixture_scripts(tmp_path)
    (scripts / "a.py").write_text(
        "import subprocess\nsubprocess.run(['git'], capture_output=True, text=True)\n",
        encoding="utf-8")
    assert parity.scan() == {"scripts/a.py": 1}


def test_alias_call_shape_is_flagged(tmp_path):
    """~35 sites hid behind runner aliases at plan time -- the lint must be
    callee-agnostic."""
    scripts = _fixture_scripts(tmp_path)
    (scripts / "b.py").write_text(
        "_COMMAND_RUNNER = None\n"
        "def f(runner):\n"
        "    _COMMAND_RUNNER(['git'], capture_output=True, text=True)\n"
        "    runner(['gh'], universal_newlines=True)\n",
        encoding="utf-8")
    assert parity.scan() == {"scripts/b.py": 2}


def test_explicit_encoding_and_binary_mode_are_clean(tmp_path):
    scripts = _fixture_scripts(tmp_path)
    (scripts / "c.py").write_text(
        "import subprocess\n"
        "subprocess.run(['git'], text=True, encoding='utf-8', errors='replace')\n"
        "subprocess.run(['git', 'check-ignore', '--stdin', '-z'], input=b'x', text=False)\n"
        "subprocess.run(['git'], capture_output=True)\n",
        encoding="utf-8")
    assert parity.scan() == {}


def test_hook_heredoc_stdin_read_is_flagged_buffer_is_not(tmp_path):
    scripts = _fixture_scripts(tmp_path)
    (scripts / "hook.sh").write_text(
        '#!/bin/bash\n"$PYTHON" -c "\nimport json, sys\ndata = json.load(sys.stdin)\n"\n'
        '"$PYTHON" -c "\nimport sys\ntext = sys.stdin.buffer.read().decode(\'utf-8\')\n"\n',
        encoding="utf-8")
    assert parity.scan() == {"scripts/hook.sh": 1}


def test_ratchet_passes_at_baseline_and_fails_on_increase(tmp_path, capsys):
    scripts = _fixture_scripts(tmp_path)
    target = scripts / "d.py"
    target.write_text(
        "import subprocess\nsubprocess.run(['git'], text=True)\n", encoding="utf-8")
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"files": {"scripts/d.py": 1}}), encoding="utf-8")

    rc_equal = parity.main(["--files", "scripts/d.py",
                            "--compare-baseline", str(baseline)])
    assert rc_equal == 0

    target.write_text(
        "import subprocess\nsubprocess.run(['git'], text=True)\n"
        "subprocess.run(['gh'], text=True)\n", encoding="utf-8")
    rc_regress = parity.main(["--files", "scripts/d.py",
                              "--compare-baseline", str(baseline)])
    out = capsys.readouterr().out
    assert rc_regress == 1
    assert "scripts/d.py: 2 (baseline 1)" in out


def test_new_file_with_violation_fails_against_baseline(tmp_path):
    scripts = _fixture_scripts(tmp_path)
    (scripts / "new.py").write_text(
        "import subprocess\nsubprocess.run(['git'], text=True)\n", encoding="utf-8")
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"files": {}}), encoding="utf-8")
    rc = parity.main(["--files", "scripts/new.py", "--compare-baseline", str(baseline)])
    assert rc == 1


def test_decrease_is_always_allowed(tmp_path):
    scripts = _fixture_scripts(tmp_path)
    (scripts / "e.py").write_text("x = 1\n", encoding="utf-8")
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"files": {"scripts/e.py": 3}}), encoding="utf-8")
    rc = parity.main(["--files", "scripts/e.py", "--compare-baseline", str(baseline)])
    assert rc == 0


def test_real_repo_baseline_is_current():
    """The committed baseline must cover the real tree: the same invocation the
    pre-commit Step 38 and the CI step use has to pass against HEAD's code."""
    parity.configure()  # real repo
    baseline_path = Path(parity.__file__).resolve().parent.parent / "subprocess_encoding_baseline.json"
    assert baseline_path.exists(), "scripts/ci/subprocess_encoding_baseline.json missing"
    rc = parity.main(["--all-files", "--compare-baseline", str(baseline_path)])
    assert rc == 0, "regenerate the baseline deliberately if a legitimate decrease happened"
