"""
Tests for the real CLI added to scripts/pipeline/lib/triage_confirm.py and
scripts/pipeline/lib/reconcile_triage.py (RPR-F-03).

Regression context: prior to this fix, both files had zero CLI (no argparse,
no __main__). The skill's own documented invocation, run literally as written,
would execute the module top-to-bottom (define functions, no-op), print
nothing, and exit 0 -- a silent, contentless "success" indistinguishable from
a real clean run. These tests exercise the real `main()` entrypoints via
`run()` (the testable core, `main()` just wraps it + argparse + file I/O).
"""

import json
from pathlib import Path

import lib.triage_confirm as tc
import lib.reconcile_triage as rt


def _make_knowledge_tree(tmp_path: Path, family: str, platform: str, *, delta: dict | None = None, stale_since: str | None = None) -> Path:
    merged = tmp_path / "knowledge" / family / platform / "merged"
    merged.mkdir(parents=True)
    (merged / "api_surface.json").write_text(json.dumps([{"name": "OldDocument"}]), encoding="utf-8")
    (merged / "claims.json").write_text(json.dumps([{"claim_id": "CLM-001", "text": "old text"}]), encoding="utf-8")
    (merged / "knowledge_delta.json").write_text(json.dumps(delta or {}), encoding="utf-8")
    stale_since_repr = repr(stale_since) if stale_since else "null"
    model_yaml = f"repo_sha: abc123\nstale_since: {stale_since_repr}\n"
    (merged / "model.yaml").write_text(model_yaml, encoding="utf-8")
    return tmp_path


def _make_page(tmp_path: Path, rel: str, content: str) -> Path:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


# ── triage_confirm.py CLI ────────────────────────────────────────────────────

def test_run_raises_when_merged_dir_missing(tmp_path):
    import pytest
    with pytest.raises(FileNotFoundError):
        tc.run("pdf", "net", repo_root=tmp_path)


def test_run_confirms_clean_page(tmp_path):
    root = _make_knowledge_tree(tmp_path, "pdf", "net", delta={"removed_apis": ["GoneClass"]})
    page = _make_page(tmp_path, "content/page.md", "This page mentions nothing stale.\n")
    summary = tc.run("pdf", "net", repo_root=root, files=[str(page)])
    assert summary["pages_checked"] == 1
    assert summary["stale_count"] == 0


def test_run_detects_stale_page(tmp_path):
    root = _make_knowledge_tree(tmp_path, "pdf", "net", delta={"removed_apis": ["GoneClass"]})
    page = _make_page(tmp_path, "content/page.md", "Use `GoneClass` to do things.\n")
    summary = tc.run("pdf", "net", repo_root=root, files=[str(page)])
    assert summary["pages_checked"] == 1
    assert summary["stale_count"] == 1
    assert summary["results"][0]["stale"] is True


def test_main_exit_code_0_on_confirmed(tmp_path, capsys):
    root = _make_knowledge_tree(tmp_path, "pdf", "net")
    page = _make_page(tmp_path, "content/page.md", "Nothing stale here.\n")
    tc.configure(repo_root=root)
    code = tc.main(["pdf", "net", "--files", str(page)])
    assert code == 0


def test_main_exit_code_1_on_unresolved(tmp_path):
    root = _make_knowledge_tree(tmp_path, "pdf", "net", delta={"removed_apis": ["GoneClass"]})
    page = _make_page(tmp_path, "content/page.md", "Use `GoneClass`.\n")
    tc.configure(repo_root=root)
    code = tc.main(["pdf", "net", "--files", str(page)])
    assert code == 1


def test_main_exit_code_2_on_missing_knowledge(tmp_path):
    tc.configure(repo_root=tmp_path)
    code = tc.main(["pdf", "net"])
    assert code == 2


def test_main_writes_verdict_artifact(tmp_path):
    root = _make_knowledge_tree(tmp_path, "pdf", "net")
    page = _make_page(tmp_path, "content/page.md", "Clean page.\n")
    tc.configure(repo_root=root)
    tc.main(["pdf", "net", "--files", str(page)])
    out_dir = root / "reports" / "refresh_review" / "pdf" / "net"
    assert (out_dir / "triage_verdict.yaml").exists() or (out_dir / "triage_verdict.json").exists()


# ── reconcile_triage.py CLI ──────────────────────────────────────────────────

def test_reconcile_run_raises_when_merged_dir_missing(tmp_path):
    import pytest
    with pytest.raises(FileNotFoundError):
        rt.run("pdf", "net", repo_root=tmp_path)


def test_reconcile_run_sources_layer1_from_stale_since(tmp_path):
    root = _make_knowledge_tree(tmp_path, "pdf", "net", stale_since="2026-07-16T00:00:00Z")
    page = _make_page(tmp_path, "content/page.md", "Clean body.\n")
    summary = rt.run("pdf", "net", repo_root=root, files=[str(page)])
    assert summary["needs_update_count"] == 1
    assert summary["results"][0]["sources"]["layer1_triage"]["verdict"] == "needs_update"


def test_reconcile_run_all_current_when_no_stale_signals(tmp_path):
    root = _make_knowledge_tree(tmp_path, "pdf", "net")
    page = _make_page(tmp_path, "content/page.md", "Clean body.\n")
    summary = rt.run("pdf", "net", repo_root=root, files=[str(page)])
    assert summary["needs_update_count"] == 0
    assert summary["missing_count"] == 0


def test_reconcile_main_exit_code_1_when_layer1_stale(tmp_path):
    root = _make_knowledge_tree(tmp_path, "pdf", "net", stale_since="2026-07-16T00:00:00Z")
    page = _make_page(tmp_path, "content/page.md", "Clean body.\n")
    rt.configure(repo_root=root)
    code = rt.main(["pdf", "net", "--files", str(page)])
    assert code == 1


def test_reconcile_main_exit_code_0_when_all_current(tmp_path):
    root = _make_knowledge_tree(tmp_path, "pdf", "net")
    page = _make_page(tmp_path, "content/page.md", "Clean body.\n")
    rt.configure(repo_root=root)
    code = rt.main(["pdf", "net", "--files", str(page)])
    assert code == 0


def test_reconcile_main_exit_code_2_on_missing_knowledge(tmp_path):
    rt.configure(repo_root=tmp_path)
    code = rt.main(["pdf", "net"])
    assert code == 2
