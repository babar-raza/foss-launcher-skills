"""Tests for example_verification_sweep.py (TC-09,
MT072-2026-09-23-EXAMPLE-VERIFICATION-PRODUCTIONIZATION).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
_LIB_DIR = str(_HERE / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
_GOV_DIR = str(_HERE / "commands" / "governance")
if _GOV_DIR not in sys.path:
    sys.path.insert(0, _GOV_DIR)

import example_verification_sweep as sweep  # noqa: E402


# ---------------------------------------------------------------------------
# Path classification helpers
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path,expected", [
    ("content/docs.aspose.org/en/pdf/go/getting-started/installation.md", "docs.aspose.org"),
    ("content/docs.aspose.org/de/pdf/go/getting-started/installation.md", None),
    ("content/kb.aspose.org/en/pdf/go/faq.md", "kb.aspose.org"),
    ("content/kb.aspose.org/fr/pdf/go/faq.md", None),
    ("content/reference.aspose.org/en/pdf/go/Foo.md", "reference.aspose.org"),
    ("content/reference.aspose.org/zh/pdf/go/Foo.md", None),
    ("content/blog.aspose.org/pdf/go/some-post/index.md", "blog.aspose.org"),
    ("content/blog.aspose.org/pdf/go/some-post/index.fr.md", None),
    ("content/blog.aspose.org/pdf/go/some-post/index.pt-br.md", None),
    ("content/products.aspose.org/en/pdf/_index.md", "products.aspose.org"),
    ("content/products.aspose.org/de/pdf/_index.md", None),
    ("content/mcp.aspose.org/en/pdf/_index.md", None),
    ("not-content/foo.md", None),
    ("content/docs.aspose.org/en/pdf/go/readme.txt", None),
])
def test_is_english_public_page(path, expected):
    assert sweep._is_english_public_page(path) == expected


def test_family_platform_from_path_docs():
    assert sweep._family_platform_from_path(
        "docs.aspose.org", "content/docs.aspose.org/en/pdf/go/getting-started/installation.md",
    ) == ("pdf", "go")


def test_family_platform_from_path_blog():
    assert sweep._family_platform_from_path(
        "blog.aspose.org", "content/blog.aspose.org/cells/net/some-post/index.md",
    ) == ("cells", "net")


# ---------------------------------------------------------------------------
# _classify_block -- every input must land in exactly one of the 7 buckets
# ---------------------------------------------------------------------------

def test_classify_empty_block():
    status, reason, tier, detail = sweep._classify_block("python", "   \n\n")
    assert status == "EMPTY"


def test_classify_shell_not_checked():
    status, reason, tier, detail = sweep._classify_block("bash", "pip install foo")
    assert status == "SHELL-NOT-CHECKED"


def test_classify_non_executable_lang():
    status, reason, tier, detail = sweep._classify_block("json", '{"a": 1}')
    assert status == "NOT-EXECUTABLE-LANG"


def test_classify_blank_lang_unchecked():
    """TC-20/ST-212: a blank info string is split out of NOT-EXECUTABLE-LANG
    (which also legitimately contains "") into its own bucket, so it's
    never indistinguishable from a deliberately-tagged yaml/json/css block."""
    status, reason, tier, detail = sweep._classify_block("", "root.addChildNode(detached);")
    assert status == "BLANK-LANG-UNCHECKED"
    assert tier == 0
    assert detail


def test_classify_blank_lang_takes_priority_over_empty_check_order():
    """Blank lang + non-blank content must not be swallowed by EMPTY (the
    content check runs first and correctly doesn't fire here)."""
    status, _, _, _ = sweep._classify_block("", "real code, just untagged")
    assert status == "BLANK-LANG-UNCHECKED"


def test_classify_pass():
    status, reason, tier, detail = sweep._classify_block("python", "print('hi')\n")
    assert status == "PASS"
    assert tier == 1


def test_classify_syntax_error():
    # NOT "def f(:" -- confirmed in the original portfolio audit that
    # tree-sitter's Python grammar tolerates that specific malformed
    # signature (a real, disclosed tier-1 weakness vs ast.parse). An
    # unclosed paren is a genuine tree-sitter ERROR node.
    status, reason, tier, detail = sweep._classify_block("python", "x = (1,\n")
    assert status == "SYNTAX-ERROR"
    assert reason == "SYNTAX-ERROR"
    assert tier == 1
    assert detail


def test_classify_grammar_unavailable():
    status, reason, tier, detail = sweep._classify_block("cobol", "IDENTIFICATION DIVISION.\n")
    assert status == "GRAMMAR-UNAVAILABLE"


# ---------------------------------------------------------------------------
# run_sweep() -- real, small, isolated fixture repo (never the real content/)
# ---------------------------------------------------------------------------

def _init_fixture_repo(tmp_path: Path) -> Path:
    """A tiny real git repo (run_sweep() shells out to `git ls-files`, so it
    needs one) with a handful of English + locale content pages spanning
    the classification buckets, and one products.aspose.org page to prove
    the disclosed-exclusion counting."""
    (tmp_path / "content" / "docs.aspose.org" / "en" / "pdf" / "go").mkdir(parents=True)
    (tmp_path / "content" / "docs.aspose.org" / "de" / "pdf" / "go").mkdir(parents=True)
    (tmp_path / "content" / "products.aspose.org" / "en" / "pdf").mkdir(parents=True)

    good = tmp_path / "content/docs.aspose.org/en/pdf/go/clean.md"
    good.write_text("---\ntitle: x\n---\n\n```go\npackage main\nfunc main() {}\n```\n", encoding="utf-8")

    bad = tmp_path / "content/docs.aspose.org/en/pdf/go/broken.md"
    bad.write_text("---\ntitle: x\n---\n\n```go\npackage main\nfunc main( {\n```\n", encoding="utf-8")

    mixed = tmp_path / "content/docs.aspose.org/en/pdf/go/mixed.md"
    mixed.write_text(
        "---\ntitle: x\n---\n\n"
        "```bash\ngo get example\n```\n\n"
        "```json\n{\"a\": 1}\n```\n\n"
        "```go\npackage main\nfunc main() {}\n```\n",
        encoding="utf-8",
    )

    locale = tmp_path / "content/docs.aspose.org/de/pdf/go/clean.md"
    locale.write_text("---\ntitle: x\n---\n\n```go\npackage main\nfunc main( {\n```\n", encoding="utf-8")

    products_page = tmp_path / "content/products.aspose.org/en/pdf/_index.md"
    products_page.write_text("---\ntitle: x\n---\n\nNo fenced blocks here.\n", encoding="utf-8")

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=T", "commit", "-q", "-m", "init"],
        cwd=tmp_path, check=True,
    )
    return tmp_path


def test_run_sweep_classifies_every_block_in_the_fixture(tmp_path):
    repo = _init_fixture_repo(tmp_path)
    report = sweep.run_sweep(repo_root=repo)

    assert report["unclassified_blocks"] == 0
    # clean.md (1 PASS) + broken.md (1 SYNTAX-ERROR) + mixed.md (1 SHELL-NOT-CHECKED
    # + 1 NOT-EXECUTABLE-LANG + 1 PASS) = 5 English blocks; the /de/ locale page
    # and the products.aspose.org page (no fences) never enter the count.
    assert report["total_blocks_classified"] == 5
    assert report["status_counts"]["PASS"] == 2
    assert report["status_counts"]["SYNTAX-ERROR"] == 1
    assert report["status_counts"]["SHELL-NOT-CHECKED"] == 1
    assert report["status_counts"]["NOT-EXECUTABLE-LANG"] == 1
    assert report["pages_by_site"]["docs.aspose.org"] == 3  # locale page excluded from this count too
    assert report["pages_by_site"]["products.aspose.org"] == 1
    assert report["excluded_products_aspose_org_pages"] == 1


def test_run_sweep_blank_lang_block_is_its_own_bucket_not_unclassified(tmp_path):
    """TC-20/ST-212: a fence with no language tag at all must land in
    BLANK-LANG-UNCHECKED, not silently merge into NOT-EXECUTABLE-LANG's
    combined total (which also holds deliberately-tagged yaml/json/css)."""
    (tmp_path / "content" / "docs.aspose.org" / "en" / "pdf" / "go").mkdir(parents=True)
    (tmp_path / "content" / "docs.aspose.org").mkdir(parents=True, exist_ok=True)
    page = tmp_path / "content/docs.aspose.org/en/pdf/go/untagged.md"
    page.write_text(
        "---\ntitle: x\n---\n\n```\nroot.addChildNode(detached);\n```\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=T", "commit", "-q", "-m", "init"],
        cwd=tmp_path, check=True,
    )
    report = sweep.run_sweep(repo_root=tmp_path)
    assert report["unclassified_blocks"] == 0
    assert report["status_counts"]["BLANK-LANG-UNCHECKED"] == 1
    assert "NOT-EXECUTABLE-LANG" not in report["status_counts"]


def test_run_sweep_writes_ledger_eligible_results(tmp_path):
    import example_verification_ledger as ledger_mod

    repo = _init_fixture_repo(tmp_path)
    report = sweep.run_sweep(repo_root=repo)

    # PASS in clean.md + SYNTAX-ERROR in broken.md + the PASS go block in
    # mixed.md (its bash/json blocks are SHELL-NOT-CHECKED/NOT-EXECUTABLE-LANG,
    # neither ledger-eligible).
    assert report["ledger_writes"] == 3
    assert report["ledger_errors"] == []

    ledger = ledger_mod.ExecutionProofLedger("pdf", "go", repo_root=repo)
    history = ledger.read_history()
    assert len(history) == 3
    statuses = sorted(r["status"] for r in history)
    assert statuses == ["BLOCKED-WITH-REASON", "PASS", "PASS"]


def test_run_sweep_is_idempotent_on_ledger_append_count(tmp_path):
    """Running the sweep twice appends twice (append-only, by design --
    the ledger's OWN staleness/history model handles repeats; this sweep
    does not deduplicate). Documents the real behavior rather than
    asserting a false idempotency claim."""
    repo = _init_fixture_repo(tmp_path)
    sweep.run_sweep(repo_root=repo)
    sweep.run_sweep(repo_root=repo)

    import example_verification_ledger as ledger_mod
    ledger = ledger_mod.ExecutionProofLedger("pdf", "go", repo_root=repo)
    assert len(ledger.read_history()) == 6  # 3 ledger-eligible blocks x 2 runs


def test_main_writes_a_dated_report_file(tmp_path, capsys):
    repo = _init_fixture_repo(tmp_path)
    out_dir = tmp_path / "out"
    rc = sweep.main(["--output-dir", str(out_dir)], repo_root=repo)
    assert rc == 0
    files = list(out_dir.glob("*-full-sweep.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert data["unclassified_blocks"] == 0
