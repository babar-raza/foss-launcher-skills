"""Tests for locale_code_block_equivalence.py (TC-14,
MT072-2026-09-23-EXAMPLE-VERIFICATION-PRODUCTIONIZATION).
"""
from __future__ import annotations

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

import locale_code_block_equivalence as lce  # noqa: E402


# ---------------------------------------------------------------------------
# _is_locale_suffixed
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,expected", [
    ("index.md", None),
    ("index.fr.md", "fr"),
    ("index.pt-br.md", "pt-br"),
    ("index.zh-cn.md", "zh-cn"),
    ("_index.md", None),
    ("faq.ar.md", "ar"),
])
def test_is_locale_suffixed(name, expected):
    assert lce._is_locale_suffixed(name) == expected


# ---------------------------------------------------------------------------
# _classify_page
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("site,rel_path,expected", [
    ("blog.aspose.org", "content/blog.aspose.org/pdf/go/some-post/index.md",
     ("en", "content/blog.aspose.org/pdf/go/some-post/index.md")),
    ("blog.aspose.org", "content/blog.aspose.org/pdf/go/some-post/index.fr.md",
     ("fr", "content/blog.aspose.org/pdf/go/some-post/index.md")),
    ("blog.aspose.org", "content/blog.aspose.org/pdf/go/some-post/index.pt-br.md",
     ("pt-br", "content/blog.aspose.org/pdf/go/some-post/index.md")),
    ("docs.aspose.org", "content/docs.aspose.org/en/pdf/go/getting-started/installation.md",
     ("en", "content/docs.aspose.org/en/pdf/go/getting-started/installation.md")),
    ("docs.aspose.org", "content/docs.aspose.org/ar/pdf/go/getting-started/installation.md",
     ("ar", "content/docs.aspose.org/en/pdf/go/getting-started/installation.md")),
])
def test_classify_page(site, rel_path, expected):
    assert lce._classify_page(site, rel_path) == expected


def test_classify_page_rejects_wrong_site():
    assert lce._classify_page("blog.aspose.org", "content/docs.aspose.org/en/pdf/go/x.md") is None


def test_classify_page_rejects_unknown_locale_directory():
    # "notalocale" is neither "en" nor a known LOCALE_CODES entry.
    assert lce._classify_page("docs.aspose.org", "content/docs.aspose.org/notalocale/pdf/go/x.md") is None


def test_classify_page_products_excluded():
    # products.aspose.org isn't in _SWEPT_SITES at all.
    assert lce._classify_page("products.aspose.org", "content/products.aspose.org/en/pdf/_index.md") is None


# ---------------------------------------------------------------------------
# compare_group — synthetic on-disk fixtures, no live repo dependency
# ---------------------------------------------------------------------------

def _write(path: Path, text: str) -> None:
    # newline="" -- do NOT let text-mode translate "\n" to os.linesep on
    # Windows; several fixtures below embed literal "\r\n" on purpose to
    # test CRLF normalization, and a second translation pass would
    # corrupt them into "\r\r\n".
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="")


def test_compare_group_identical_blocks_no_findings(tmp_path):
    en = tmp_path / "en.md"
    fr = tmp_path / "fr.md"
    body = "# Title\n\n```python\nprint('hi')\n```\n"
    _write(en, body)
    _write(fr, body)
    findings = lce.compare_group(tmp_path, "group", "en.md", {"fr": "fr.md"})
    assert findings == []


def test_compare_group_count_mismatch(tmp_path):
    en = tmp_path / "en.md"
    fr = tmp_path / "fr.md"
    _write(en, "```python\nprint(1)\n```\n\n```python\nprint(2)\n```\n")
    _write(fr, "```python\nprint(1)\n```\n")
    findings = lce.compare_group(tmp_path, "group", "en.md", {"fr": "fr.md"})
    assert len(findings) == 1
    assert findings[0].kind == "COUNT_MISMATCH"
    assert findings[0].locale == "fr"


def test_compare_group_lang_mismatch(tmp_path):
    en = tmp_path / "en.md"
    th = tmp_path / "th.md"
    _write(en, "```python\nprint(1)\n```\n")
    _write(th, "```\nprint(1)\n```\n")  # info string stripped -- blank lang
    findings = lce.compare_group(tmp_path, "group", "en.md", {"th": "th.md"})
    assert len(findings) == 1
    assert findings[0].kind == "LANG_MISMATCH"


def test_compare_group_content_drift(tmp_path):
    en = tmp_path / "en.md"
    de = tmp_path / "de.md"
    _write(en, "```java\nopts.setPrettyPrint(true);\n```\n")
    _write(de, "```java\nopts.setFlipCoordinateSystem(true);\nopts.setPrettyPrint(true);\n```\n")
    findings = lce.compare_group(tmp_path, "group", "en.md", {"de": "de.md"})
    assert len(findings) == 1
    assert findings[0].kind == "CONTENT_DRIFT"


def test_compare_group_normalization_absorbs_cosmetic_diffs(tmp_path):
    """CRLF vs LF and trailing whitespace must NOT be flagged -- that's
    exactly what sha256_norm (code_fences.py) already absorbs."""
    en = tmp_path / "en.md"
    de = tmp_path / "de.md"
    _write(en, "```python\nprint(1)  \nprint(2)\n```\n")
    _write(de, "```python\r\nprint(1)\r\nprint(2)   \r\n```\r\n")
    findings = lce.compare_group(tmp_path, "group", "en.md", {"de": "de.md"})
    assert findings == []


def test_compare_group_no_english_blocks_short_circuits(tmp_path):
    en = tmp_path / "en.md"
    de = tmp_path / "de.md"
    _write(en, "# just prose, no code\n")
    _write(de, "```python\nprint(1)\n```\n")
    en_blocks = lce._blocks_for(en)
    assert en_blocks == []
    findings = lce.compare_group(tmp_path, "group", "en.md", {"de": "de.md"})
    assert findings == []


# ---------------------------------------------------------------------------
# run_check / main — live-repo smoke test + CLI exit code contract
# ---------------------------------------------------------------------------

def test_run_check_against_live_repo_finds_real_pages():
    """Bounded live-repo smoke test (not a synthetic fixture): the real
    portfolio has thousands of English pages-with-code and locale
    counterparts, so this must return a non-trivial, internally consistent
    report without raising."""
    report = lce.run_check()
    assert report["pages_seen"] > 1000
    assert report["page_groups_with_english_code"] > 0
    assert report["locale_page_comparisons"] >= report["page_groups_with_english_code"]
    assert report["finding_count"] == len(report["findings"])
    assert sum(report["finding_kind_counts"].values()) == report["finding_count"]
    for f in report["findings"]:
        assert f["kind"] in ("COUNT_MISMATCH", "LANG_MISMATCH", "CONTENT_DRIFT")


def test_main_exit_code_reflects_findings(tmp_path, monkeypatch):
    """A synthetic repo_root with one deliberate drift must exit 1; an
    all-clean one must exit 0. Exercises main() end-to-end via subprocess
    so the CLI contract (not just run_check()) is proven."""
    clean_root = tmp_path / "clean"
    (clean_root / "content" / "blog.aspose.org" / "pdf" / "go" / "post").mkdir(parents=True)
    body = "```go\nfmt.Println(1)\n```\n"
    _write(clean_root / "content/blog.aspose.org/pdf/go/post/index.md", body)
    _write(clean_root / "content/blog.aspose.org/pdf/go/post/index.fr.md", body)
    subprocess.run(["git", "init", "-q"], cwd=clean_root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=clean_root, check=True)

    module_path = str(Path(lce.__file__).resolve())
    result = subprocess.run(
        [sys.executable, module_path, "--repo-root", str(clean_root)],
        cwd=clean_root, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert result.returncode == 0, result.stdout + result.stderr

    dirty_root = tmp_path / "dirty"
    (dirty_root / "content" / "blog.aspose.org" / "pdf" / "go" / "post").mkdir(parents=True)
    _write(dirty_root / "content/blog.aspose.org/pdf/go/post/index.md", "```go\nfmt.Println(1)\n```\n")
    _write(dirty_root / "content/blog.aspose.org/pdf/go/post/index.fr.md", "```go\nfmt.Println(2)\n```\n")
    subprocess.run(["git", "init", "-q"], cwd=dirty_root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=dirty_root, check=True)

    result = subprocess.run(
        [sys.executable, module_path, "--repo-root", str(dirty_root)],
        cwd=dirty_root, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "CONTENT_DRIFT" in result.stdout
