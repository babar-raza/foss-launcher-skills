"""Tests for scripts/ci/checks/check_stale_refresh_gate.py (HARDEN-A8, R1).

R1: the gate is scoped PER STAGED FILE against triage_confirm's per-page
`results` list, not per-{family,platform} aggregate counts — the aggregate
version would have hard-blocked every future commit to any of this repo's 4
products with pre-existing nonzero historical stale counts, with no override.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import yaml

_CHECKS_DIR = Path(__file__).resolve().parent.parent / "checks"
if str(_CHECKS_DIR) not in sys.path:
    sys.path.insert(0, str(_CHECKS_DIR))

import check_stale_refresh_gate as gate  # noqa: E402


def _write_verdict(repo_root: Path, family: str, platform: str, results: list[dict],
                   stale_count: int | None = None, error_count: int | None = None) -> Path:
    out_dir = repo_root / "reports" / "refresh_review" / family / platform
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "family": family,
        "platform": platform,
        "pages_checked": len(results),
        "stale_count": stale_count if stale_count is not None
                       else sum(1 for r in results if r.get("stale")),
        "error_count": error_count if error_count is not None
                       else sum(1 for r in results if r.get("verdict") == "read_error"),
        "results": results,
    }
    out_path = out_dir / "triage_verdict.yaml"
    out_path.write_text(yaml.dump(summary, sort_keys=False), encoding="utf-8")
    return out_path


def test_no_verdict_file_passes(tmp_path):
    blocked = gate.check_pair("words", "net", ["content/docs.aspose.org/en/words/net/x.md"],
                              repo_root=tmp_path)
    assert blocked == []


def test_staged_file_not_in_results_passes(tmp_path):
    """A brand-new page (or one triage never checked) has nothing on record."""
    page = "content/docs.aspose.org/en/pdf/net/getting-started/installation.md"
    _write_verdict(tmp_path, "pdf", "net", [
        {"page_path": "content/docs.aspose.org/en/pdf/net/other-page.md", "stale": True,
         "verdict": "stale", "reasons": ["r1"]},
    ])
    blocked = gate.check_pair("pdf", "net", [page], repo_root=tmp_path)
    assert blocked == []


def test_staged_stale_page_blocks(tmp_path):
    page = "content/docs.aspose.org/en/pdf/net/getting-started/installation.md"
    _write_verdict(tmp_path, "pdf", "net", [
        {"page_path": page, "stale": True, "verdict": "stale", "reasons": ["claim drift"]},
    ])
    with mock.patch.object(gate, "_has_override", return_value=False):
        blocked = gate.check_pair("pdf", "net", [page], repo_root=tmp_path)
    assert len(blocked) == 1
    assert blocked[0][0] == page
    assert "claim drift" in blocked[0][1]


def test_staged_non_stale_page_in_results_passes(tmp_path):
    page = "content/docs.aspose.org/en/pdf/net/getting-started/installation.md"
    _write_verdict(tmp_path, "pdf", "net", [
        {"page_path": page, "stale": False, "verdict": "current", "reasons": []},
    ])
    blocked = gate.check_pair("pdf", "net", [page], repo_root=tmp_path)
    assert blocked == []


def test_unrelated_file_under_stale_product_not_blocked(tmp_path):
    """R1's core fix: a product with MANY other stale pages must not block a
    staged file that isn't itself one of them."""
    stale_page = "content/docs.aspose.org/en/pdf/net/some-other-page.md"
    unrelated_page = "content/docs.aspose.org/en/pdf/net/getting-started/typo-fix.md"
    results = [{"page_path": stale_page, "stale": True, "verdict": "stale", "reasons": ["r"]}]
    # Simulate a product with hundreds of historical stale pages (like real pdf/net)
    results += [{"page_path": f"content/docs.aspose.org/en/pdf/net/page-{i}.md",
                 "stale": True, "verdict": "stale", "reasons": ["r"]} for i in range(50)]
    _write_verdict(tmp_path, "pdf", "net", results, stale_count=479)
    blocked = gate.check_pair("pdf", "net", [unrelated_page], repo_root=tmp_path)
    assert blocked == []


def test_read_error_page_blocks(tmp_path):
    page = "content/docs.aspose.org/en/pdf/net/broken.md"
    _write_verdict(tmp_path, "pdf", "net", [
        {"page_path": page, "stale": False, "verdict": "read_error",
         "reasons": ["could not read page"]},
    ])
    with mock.patch.object(gate, "_has_override", return_value=False):
        blocked = gate.check_pair("pdf", "net", [page], repo_root=tmp_path)
    assert len(blocked) == 1


def test_override_token_unblocks(tmp_path):
    page = "content/docs.aspose.org/en/pdf/net/installation.md"
    _write_verdict(tmp_path, "pdf", "net", [
        {"page_path": page, "stale": True, "verdict": "stale", "reasons": ["r"]},
    ])
    with mock.patch.object(gate, "_has_override", return_value=True):
        blocked = gate.check_pair("pdf", "net", [page], repo_root=tmp_path)
    assert blocked == []


def test_unreadable_verdict_blocks_all_staged_for_pair(tmp_path):
    out_dir = tmp_path / "reports" / "refresh_review" / "pdf" / "net"
    out_dir.mkdir(parents=True)
    (out_dir / "triage_verdict.yaml").write_text("{not: valid: yaml: [", encoding="utf-8")
    blocked = gate.check_pair("pdf", "net", ["content/docs.aspose.org/en/pdf/net/x.md"],
                              repo_root=tmp_path)
    assert len(blocked) == 1


def test_pairs_from_paths_extracts_docs_kb_products_reference():
    paths = [
        "content/docs.aspose.org/en/pdf/net/getting-started/installation.md",
        "content/kb.aspose.org/en/pdf/net/faq.md",
        "content/products.aspose.org/en/cells/net/_index.md",
        "content/reference.aspose.org/en/words/python/Document.md",
    ]
    pairs = gate.pairs_from_paths(paths)
    assert set(pairs.keys()) == {("pdf", "net"), ("cells", "net"), ("words", "python")}
    assert pairs[("pdf", "net")] == [paths[0], paths[1]]


def test_pairs_from_paths_extracts_blog_without_en():
    paths = ["content/blog.aspose.org/words/python/some-slug/index.md"]
    pairs = gate.pairs_from_paths(paths)
    assert pairs == {("words", "python"): paths}


def test_pairs_from_paths_ignores_platform_less_paths():
    paths = ["content/products.aspose.org/en/cells/_index.md", "content/docs.aspose.org/en/words/_index.md"]
    pairs = gate.pairs_from_paths(paths)
    assert pairs == {}


def test_main_exits_zero_on_clean_stdin(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", __import__("io").StringIO(""))
    assert gate.main() == 0


def test_main_blocks_via_stdin(tmp_path, monkeypatch, capsys):
    page = "content/docs.aspose.org/en/pdf/net/installation.md"
    _write_verdict(tmp_path, "pdf", "net", [
        {"page_path": page, "stale": True, "verdict": "stale", "reasons": ["r"]},
    ])
    monkeypatch.setattr(gate, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(sys, "stdin", __import__("io").StringIO(page + "\n"))
    with mock.patch.object(gate, "_has_override", return_value=False):
        rc = gate.main()
    assert rc == 1
    err = capsys.readouterr().err
    assert "BLOCKED" in err and page in err
