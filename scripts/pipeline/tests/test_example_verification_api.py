"""Tests for lib/example_verification/api.py (TC-01, MT072-2026-09-23-
EXAMPLE-VERIFICATION-PRODUCTIONIZATION).

Proves the two real dispatch paths (BaseRunner-driven for go/net/java/
rust/cpp, whole-candidate-function-driven for python/typescript) and the
honest-degradation path for a platform this package doesn't run at all.
Never acquires a real environment (allow_acquire stays False throughout --
these are tier-0/1 structural tests, not toolchain-dependent ones).
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
_LIB_DIR = str(_HERE / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from example_verification import api  # noqa: E402
from example_verification.policy import Policy  # noqa: E402
from example_verification.result import VerificationReport  # noqa: E402

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_api_configure():
    yield
    api.configure()


def _write(tmp_path: Path, name: str, text: str) -> Path:
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# verify_markdown -- BaseRunner-driven platforms (go/net/java/rust/cpp)
# ---------------------------------------------------------------------------

def test_verify_markdown_go_tier1_pass():
    text = "```go\npackage main\n\nfunc main() {}\n```\n"
    report = api.verify_markdown(text, platform="go", policy=Policy(max_tier=1, allow_acquire=False))
    assert isinstance(report, VerificationReport)
    assert len(report.blocks) == 1
    assert report.blocks[0].status == "PASS"
    assert report.blocks[0].proof_tier == 1


def test_verify_markdown_go_syntax_error_detected():
    text = "```go\npackage main\nfunc main( {\n```\n"
    report = api.verify_markdown(text, platform="go", policy=Policy(max_tier=1, allow_acquire=False))
    assert report.blocks[0].status == "BLOCKED-WITH-REASON"
    assert report.blocks[0].reason == "SYNTAX-ERROR"


def test_verify_markdown_ignores_other_language_blocks():
    text = "```python\nprint('not go')\n```\n\n```go\npackage main\nfunc main() {}\n```\n"
    report = api.verify_markdown(text, platform="go", policy=Policy(max_tier=1, allow_acquire=False))
    assert len(report.blocks) == 1
    assert report.blocks[0].identity.lang == "go"


def test_verify_markdown_cpp_dotnet_java_rust_all_dispatch(tmp_path):
    for platform, fence, code in [
        ("net", "csharp", "class A { void F() {} }"),
        ("java", "java", "class A { void f() {} }"),
        ("rust", "rust", "fn main() {}"),
        ("cpp", "cpp", "int main() { return 0; }"),
    ]:
        text = f"```{fence}\n{code}\n```\n"
        report = api.verify_markdown(text, platform=platform, policy=Policy(max_tier=1, allow_acquire=False))
        assert len(report.blocks) == 1, f"platform={platform}"
        assert report.blocks[0].status == "PASS", f"platform={platform}: {report.blocks[0].detail}"
        assert report.runner == platform


# ---------------------------------------------------------------------------
# verify_markdown -- unrunnable / non-code platforms degrade honestly
# ---------------------------------------------------------------------------

def test_verify_markdown_unrunnable_platform_is_not_verified_not_silent_pass():
    text = "```kotlin\nfun main() {}\n```\n"
    report = api.verify_markdown(text, platform="kotlin", policy=Policy(max_tier=1, allow_acquire=False))
    assert len(report.blocks) == 1
    assert report.blocks[0].status == "NOT-VERIFIED"
    assert report.blocks[0].proof_tier == 0


def test_verify_markdown_non_executable_lang_is_labeled_not_executable():
    text = "```json\n{\"a\": 1}\n```\n"
    report = api.verify_markdown(text, platform="json", policy=Policy(max_tier=1, allow_acquire=False))
    assert report.blocks[0].status == "NOT-EXECUTABLE-LANG"


def test_verify_markdown_python_typescript_raise_not_implemented():
    for platform in ("python", "typescript"):
        try:
            api.verify_markdown("```python\nprint(1)\n```\n", platform=platform)
        except NotImplementedError:
            continue
        raise AssertionError(f"expected NotImplementedError for platform={platform}")


# ---------------------------------------------------------------------------
# verify_page -- python/typescript whole-candidate dispatch path
# ---------------------------------------------------------------------------

def test_verify_page_python_whole_candidate_dispatch(tmp_path):
    """Proves verify_page() for python calls python_verification_runner
    and adapts its dict into a VerificationReport -- without actually
    acquiring a real venv. Uses api.configure()'s own test seam rather than
    monkeypatching the runner module's internal function reference (T2,
    banned by AGENTS.md §16)."""
    page = _write(tmp_path, "page.md", "```python\nprint('hi')\n```\n")

    def fake_runner(candidate_path, factpack):
        assert candidate_path == page
        return {
            "runner": "python_verification_runner_v2",
            "blocks_found": 1,
            "block_statuses": [{"index": 0, "status": "COMPILED+RAN CLEAN"}],
            "environment": {"install_source": "pypi", "package": "aspose-pdf-foss", "version": "1.0.0"},
            "all_named": True,
        }

    api.configure(python_runner=fake_runner)

    report = api.verify_page(page, family="pdf", platform="python")
    assert report.blocks[0].status == "PASS"
    assert report.blocks[0].proof_tier == 3
    assert report.package == "aspose-pdf-foss"
    assert report.install_source == "pypi"


def test_verify_page_missing_file_returns_empty_report_not_crash(tmp_path):
    missing = tmp_path / "does-not-exist.md"
    report = api.verify_markdown("", platform="go")
    assert report.blocks == []
    # verify_page on a real missing file for a BaseRunner platform should
    # not raise either -- text defaults to "" and yields zero blocks.
    report2 = api.verify_page(missing, platform="go")
    assert report2.blocks == []


# ---------------------------------------------------------------------------
# Registry consistency (TC-01's own dispatch table)
# ---------------------------------------------------------------------------

def test_language_runner_classes_all_importable():
    """Every platform api.py claims to dispatch through BaseRunner must
    have a real, importable LanguageRunner class -- catching a typo in
    the dispatch table itself before any caller hits it at runtime."""
    for platform in api._LANGUAGE_RUNNER_CLASSES:
        runner = api._load_language_runner(platform, family="pdf")
        assert runner.canonical_lang
        assert runner.ceiling_tier >= 1


# ---------------------------------------------------------------------------
# cli.py -- thin argparse wrapper over api.py
# ---------------------------------------------------------------------------

def test_cli_verify_exit_0_on_pass(tmp_path, capsys):
    from example_verification import cli
    page = _write(tmp_path, "page.md", "```go\npackage main\nfunc main() {}\n```\n")
    rc = cli.main(["verify", "--file", str(page), "--platform", "go"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "1/1 PASS" in out


def test_cli_verify_exit_1_on_syntax_error(tmp_path):
    from example_verification import cli
    page = _write(tmp_path, "page.md", "```go\npackage main\nfunc main( {\n```\n")
    rc = cli.main(["verify", "--file", str(page), "--platform", "go"])
    assert rc == 1


def test_cli_verify_json_output_matches_legacy_shape(tmp_path, capsys):
    import json
    from example_verification import cli
    page = _write(tmp_path, "page.md", "```go\npackage main\nfunc main() {}\n```\n")
    rc = cli.main(["verify", "--file", str(page), "--platform", "go", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["runner"] == "go"
    assert payload["blocks_found"] == 1
    assert payload["all_named"] is True
