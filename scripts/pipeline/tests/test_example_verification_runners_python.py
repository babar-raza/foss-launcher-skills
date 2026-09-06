"""Tests for lib/example_verification/runners/python.py (rollout step C3):
a faithful port of S-120's real Python verification runner
(readme_refresh_run.py:4725-5115). Real acquire->execute->classify is the
check (never mocked) -- but the network-dependent half (a real `pip
install` from PyPI) is deliberately NOT exercised here, matching this
repo's own established test convention for the original functions.

Includes direct parity checks against the real, unmodified S-120 functions
(imported as `rr`) for identical inputs -- the "legacy-adapter equality"
this stage's own promotion gate calls for.
"""
from __future__ import annotations

import sys
from pathlib import Path

import readme_refresh_run as rr

from lib.example_verification.runners.python import (
    acquire_python_environment,
    classify_bash_failure,
    classify_python_failure,
    pip_installed_version,
    product_console_scripts,
    python_block_starts_chain,
    python_verification_runner,
    run_bash_block,
    run_single_python_block,
    venv_script_path,
)


# --- Direct behavior (mirrors test_readme_refresh_run.py's own TC-HARDEN-01 tests) ------------

def test_run_single_python_block_clean_execution(tmp_path):
    result = run_single_python_block(sys.executable, "print('hello')", tmp_path, 0)
    assert result == {"index": 0, "status": "COMPILED+RAN CLEAN"}


def test_run_single_python_block_runtime_error_captured(tmp_path):
    result = run_single_python_block(
        sys.executable, "raise ValueError('boom, real traceback')", tmp_path, 1,
    )
    assert result["index"] == 1
    assert result["status"] == "BLOCKED-WITH-REASON"
    assert result["reason"] == "RUNTIME-ERROR"
    assert "boom, real traceback" in result["detail"]


def test_classify_python_failure_upstream_broken_real_syntax_error_in_dependency(tmp_path):
    script_path = tmp_path / "block_0.py"
    traceback_text = (
        'Traceback (most recent call last):\n'
        f'  File "{script_path}", line 1, in <module>\n'
        '    import broken_pkg\n'
        '  File "C:\\clone_cache\\broken_pkg\\__init__.py", line 3, in <module>\n'
        '    from broken_pkg.inner import thing\n'
        '  File "C:\\clone_cache\\broken_pkg\\inner.py", line 66\n'
        '    table[c] = X\n'
        '    ^^^^^\n'
        "IndentationError: expected an indented block after 'for' statement on line 65\n"
    )
    reason, detail = classify_python_failure(traceback_text, script_path)
    assert reason == "UPSTREAM-BROKEN"
    assert "inner.py" in detail
    assert "IndentationError" in detail


def test_classify_python_failure_stays_runtime_error_for_the_blocks_own_defect(tmp_path):
    script_path = tmp_path / "block_0.py"
    traceback_text = (
        'Traceback (most recent call last):\n'
        f'  File "{script_path}", line 3, in <module>\n'
        '    workbook.doesnt_exist()\n'
        "AttributeError: 'Workbook' object has no attribute 'doesnt_exist'\n"
    )
    reason, detail = classify_python_failure(traceback_text, script_path)
    assert reason == "RUNTIME-ERROR"
    assert "doesnt_exist" in detail


def test_python_block_starts_chain_import_starts_new_chain():
    assert python_block_starts_chain("import os\nprint(os.getcwd())") is True


def test_python_block_starts_chain_continuation_does_not():
    assert python_block_starts_chain("print(existing_var)") is False


def test_product_console_scripts_reads_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project.scripts]\nmytool = "mytool.cli:main"\n', encoding="utf-8",
    )
    scripts = product_console_scripts(tmp_path)
    assert scripts == {"mytool": "mytool.cli:main"}


def test_venv_script_path_finds_exe_on_windows(tmp_path):
    venv_python = tmp_path / "Scripts" / "python.exe"
    venv_python.parent.mkdir(parents=True)
    (tmp_path / "Scripts" / "mytool.exe").write_bytes(b"")
    result = venv_script_path(str(venv_python), "mytool")
    assert result is not None
    assert result.name == "mytool.exe"


def test_venv_script_path_returns_none_when_absent(tmp_path):
    venv_python = tmp_path / "Scripts" / "python.exe"
    venv_python.parent.mkdir(parents=True)
    assert venv_script_path(str(venv_python), "nonexistent") is None


def test_classify_bash_failure_fixture_unavailable():
    reason, _ = classify_bash_failure("Error: input.pdf: No such file or directory", ["input.pdf"])
    assert reason == "FIXTURE-UNAVAILABLE"


def test_classify_bash_failure_runtime_error_when_no_fixture_match():
    reason, _ = classify_bash_failure("some unrelated crash", ["input.pdf"])
    assert reason == "RUNTIME-ERROR"


def test_run_bash_block_reports_not_a_product_command(tmp_path):
    result = run_bash_block(sys.executable, "pip install foo\n", tmp_path, 0, {}, [])
    assert result["status"] == "BLOCKED-WITH-REASON"
    assert result["reason"] == "NOT-A-PRODUCT-COMMAND"


def test_run_bash_block_acquire_failed_when_script_not_installed(tmp_path):
    result = run_bash_block(
        sys.executable, "mytool convert a.pdf b.pdf\n", tmp_path, 0,
        {"mytool": "mytool.cli:main"}, [],
    )
    assert result["status"] == "BLOCKED-WITH-REASON"
    assert result["reason"] == "ACQUIRE-FAILED"


def test_pip_installed_version_returns_none_for_bogus_python(tmp_path):
    assert pip_installed_version(str(tmp_path / "nonexistent-python"), "somepkg") is None


def test_acquire_python_environment_real_venv_unpublished_no_clone_cache(tmp_path):
    # Real venv creation (no network -- python -m venv is purely local),
    # then the real, honest failure when unpublished and no clone cache
    # exists to editable-install from (mirrors S-120's own test of the
    # same name).
    result = acquire_python_environment(
        tmp_path, {"published": False, "candidate": {"name": "doesnt-matter"}},
        tmp_path / "no-such-clone-cache",
    )
    assert result["ok"] is False
    assert "no clone cache directory" in result["detail"]


def test_acquire_python_environment_parity_with_s120_unpublished_no_clone_cache(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    ours = acquire_python_environment(
        tmp_path / "a", {"published": False, "candidate": {"name": "x"}}, tmp_path / "no-clone-a",
    )
    theirs = rr._acquire_python_environment(
        tmp_path / "b", {"published": False, "candidate": {"name": "x"}}, tmp_path / "no-clone-b",
    )
    assert ours == theirs


# --- Parity against the real, unmodified S-120 functions --------------------------------------

def test_run_single_python_block_parity_with_s120(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    ours = run_single_python_block(sys.executable, "print('parity check')", tmp_path / "a", 0)
    theirs = rr._run_single_python_block(sys.executable, "print('parity check')", tmp_path / "b", 0)
    assert ours == theirs


def test_run_single_python_block_runtime_error_parity_with_s120(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    ours = run_single_python_block(sys.executable, "raise ValueError('x')", tmp_path / "a", 2)
    theirs = rr._run_single_python_block(sys.executable, "raise ValueError('x')", tmp_path / "b", 2)
    assert ours["status"] == theirs["status"] == "BLOCKED-WITH-REASON"
    assert ours["reason"] == theirs["reason"]
    assert ours["index"] == theirs["index"]


def test_classify_python_failure_parity_with_s120(tmp_path):
    script_path = tmp_path / "block_0.py"
    traceback_text = (
        'Traceback (most recent call last):\n'
        f'  File "{script_path}", line 1, in <module>\n'
        '    import broken_pkg\n'
        '  File "C:\\clone_cache\\broken_pkg\\inner.py", line 66\n'
        "IndentationError: expected an indented block\n"
    )
    assert classify_python_failure(traceback_text, script_path) == rr._classify_python_failure(traceback_text, script_path)


def test_python_block_starts_chain_parity_with_s120():
    for code in ("import os\nx = 1", "print(x)", "# comment\nfrom a import b", "   \nimport os"):
        assert python_block_starts_chain(code) == rr._python_block_starts_chain(code)


def test_product_console_scripts_parity_with_s120(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project.scripts]\nfoo = "foo.cli:main"\nbar = "bar.cli:run"\n', encoding="utf-8",
    )
    assert product_console_scripts(tmp_path) == rr._product_console_scripts(tmp_path)


def test_classify_bash_failure_parity_with_s120():
    cases = [
        ("Error: input.pdf: No such file or directory", ["input.pdf"]),
        ("some unrelated crash", ["input.pdf"]),
        ("FileNotFoundError: missing.docx", ["missing.docx", "other.pdf"]),
    ]
    for output, unresolved in cases:
        assert classify_bash_failure(output, unresolved) == rr._classify_bash_failure(output, unresolved)


def test_venv_script_path_parity_with_s120(tmp_path):
    venv_python = tmp_path / "Scripts" / "python.exe"
    venv_python.parent.mkdir(parents=True)
    (tmp_path / "Scripts" / "mytool.exe").write_bytes(b"")
    ours = venv_script_path(str(venv_python), "mytool")
    theirs = rr._venv_script_path(str(venv_python), "mytool")
    assert ours == theirs


# --- python_verification_runner: real, local, no-network end-to-end -----------------------------

def test_python_verification_runner_non_python_blocks_stay_stub(tmp_path):
    candidate = tmp_path / "candidate.md"
    candidate.write_text(
        "```java\nSystem.out.println(1);\n```\n\n```csharp\nConsole.WriteLine(1);\n```\n",
        encoding="utf-8",
    )
    result = python_verification_runner(candidate, {"family": "testfam", "platform": "testplat"})
    assert result["blocks_found"] == 2
    assert result["all_named"] is True
    assert all(b["status"] == "BLOCKED-WITH-REASON" and b["reason"] == "TOOLCHAIN-UNAVAILABLE"
               for b in result["block_statuses"])


def test_python_verification_runner_no_family_platform_stays_stub(tmp_path):
    candidate = tmp_path / "candidate.md"
    candidate.write_text("```python\nprint(1)\n```\n", encoding="utf-8")
    result = python_verification_runner(candidate, {})
    assert result["block_statuses"][0]["reason"] == "TOOLCHAIN-UNAVAILABLE"


def test_python_verification_runner_byte_identical_rerun(tmp_path):
    # Same candidate, run twice -- must produce an identical report (no
    # timing fields exist in this legacy dict shape to exclude).
    candidate = tmp_path / "candidate.md"
    candidate.write_text(
        "```java\nSystem.out.println(1);\n```\n", encoding="utf-8",
    )
    r1 = python_verification_runner(candidate, {"family": "testfam", "platform": "testplat"})
    r2 = python_verification_runner(candidate, {"family": "testfam", "platform": "testplat"})
    assert r1 == r2


def test_python_verification_runner_parity_with_s120_stub_case(tmp_path):
    candidate = tmp_path / "candidate.md"
    candidate.write_text(
        "```java\nSystem.out.println(1);\n```\n\n```typescript\nconsole.log(1);\n```\n",
        encoding="utf-8",
    )
    ours = python_verification_runner(candidate, {"family": "testfam", "platform": "testplat"})
    theirs = rr.python_verification_runner(candidate, {"family": "testfam", "platform": "testplat"})
    assert ours == theirs
