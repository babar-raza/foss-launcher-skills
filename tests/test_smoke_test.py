import subprocess
import sys
import textwrap
from pathlib import Path

from scripts.pipeline.commands.diagnostics.smoke_test import BlockResult, SmokeResult, check_file, print_report

REPO_ROOT = Path(__file__).resolve().parent.parent


def _write_md(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "page.md"
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    return path


def test_valid_python_block_passes(tmp_path):
    page = _write_md(tmp_path, "```python\nx = 1 + 2\nprint(x)\n```\n")

    result = check_file(page)

    assert result.blocks_checked == 1
    assert result.fail_count == 0


def test_python_syntax_error_fails(tmp_path):
    page = _write_md(tmp_path, "```python\ndef bad(\n```\n")

    result = check_file(page)

    assert result.fail_count == 1
    assert result.results[0].status == "FAIL"
    assert "SyntaxError" in result.results[0].message


def test_non_matching_language_is_ignored(tmp_path):
    page = _write_md(tmp_path, "```java\nclass X {}\n```\n")

    result = check_file(page)

    assert result.blocks_checked == 0


def test_canonical_import_is_prepended(tmp_path):
    page = _write_md(tmp_path, "```python\nx = 1\n```\n")

    result = check_file(page, canonical_import="import os")

    assert result.blocks_checked == 1
    assert result.fail_count == 0


def test_print_report_exit_codes():
    pass_result = SmokeResult(
        file="page.md",
        blocks_checked=1,
        pass_count=1,
        warn_count=0,
        fail_count=0,
        results=[BlockResult("page.md", 1, 1, "PASS", "")],
    )
    fail_result = SmokeResult(
        file="page.md",
        blocks_checked=1,
        pass_count=0,
        warn_count=0,
        fail_count=1,
        results=[BlockResult("page.md", 1, 1, "FAIL", "SyntaxError")],
    )

    assert print_report([pass_result]) == 0
    assert print_report([fail_result]) == 2


def test_cli_files_path_passes(tmp_path):
    page = _write_md(tmp_path, "```python\nx = 1\n```\n")

    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "pipeline" / "commands" / "diagnostics" / "smoke_test.py"),
            "--files",
            str(page),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "SMOKE TEST REPORT" in result.stdout


def test_legacy_wrapper_path_passes(tmp_path):
    page = _write_md(tmp_path, "```python\nx = 1\n```\n")

    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "pipeline" / "smoke_test.py"), "--files", str(page)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "SMOKE TEST REPORT" in result.stdout


def test_product_scan_uses_redirected_content_root(tmp_path):
    page = tmp_path / "content" / "docs.aspose.org" / "en" / "sample" / "python" / "intro.md"
    page.parent.mkdir(parents=True)
    page.write_text("```python\nx = 1\n```\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "pipeline" / "commands" / "diagnostics" / "smoke_test.py"),
            "sample",
            "python",
            "--content-root",
            str(tmp_path / "content"),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Blocks checked: 1" in result.stdout
