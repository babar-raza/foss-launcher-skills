"""Tests for commands/ops/st054_seed_taskcards.py (ST-054 TC-19,
plans/from_backlog/2026-08-16-st-054-inline-install-command-remediation.md).
"""
import sys
from pathlib import Path

import pytest

_PIPELINE_ROOT = Path(__file__).resolve().parents[1]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

import commands.ops.st054_seed_taskcards as sut  # noqa: E402
from taskcard_store import TaskcardStore  # noqa: E402


@pytest.fixture(autouse=True)
def isolate_repo(tmp_path):
    sut.configure(repo_root=tmp_path)
    yield
    sut.configure(repo_root=None)


def test_build_rows_for_product_chains_dependencies_in_wave_order():
    rows = sut.build_rows_for_product("note", "python")
    assert [r["step"] for r in rows] == ["block_migrate", "inline_migrate", "verify", "commit"]
    assert rows[0]["dependencies"] == []
    assert rows[1]["dependencies"] == ["TC-note-python-block_migrate"]
    assert rows[2]["dependencies"] == ["TC-note-python-inline_migrate"]
    assert rows[3]["dependencies"] == ["TC-note-python-verify"]
    assert [r["wave"] for r in rows] == [1, 2, 3, 4]
    assert all(r["status"] == "TODO" for r in rows)
    assert all("needs_manual_review" not in r for r in rows)


def test_build_rows_for_product_tags_needs_manual_review():
    rows = sut.build_rows_for_product("cells", "net", needs_manual_review=True)
    assert all(r["needs_manual_review"] is True for r in rows)


def test_seed_products_writes_rows_readable_via_taskcard_store(tmp_path):
    result = sut.seed_products([("note", "python")], recorded_by="test-session")
    assert len(result["seeded"]) == 4
    assert result["skipped_existing"] == []

    store = TaskcardStore(sut.DEFAULT_MISSION_ID, repo_root=tmp_path)
    latest = store.read_latest()
    assert "TC-note-python-block_migrate" in latest
    assert latest["TC-note-python-block_migrate"]["status"] == "TODO"
    assert latest["TC-note-python-commit"]["dependencies"] == ["TC-note-python-verify"]


def test_seed_products_is_idempotent_without_force(tmp_path):
    sut.seed_products([("note", "python")], recorded_by="s1")
    result2 = sut.seed_products([("note", "python")], recorded_by="s2")
    assert result2["seeded"] == []
    assert len(result2["skipped_existing"]) == 4


def test_seed_products_force_re_appends(tmp_path):
    sut.seed_products([("note", "python")], recorded_by="s1")
    result2 = sut.seed_products([("note", "python")], recorded_by="s2", force=True)
    assert len(result2["seeded"]) == 4
    assert result2["skipped_existing"] == []


def test_seed_products_multiple_products_independent(tmp_path):
    result = sut.seed_products([("note", "python"), ("cells", "python")], recorded_by="s1")
    assert len(result["seeded"]) == 8
    store = TaskcardStore(sut.DEFAULT_MISSION_ID, repo_root=tmp_path)
    latest = store.read_latest()
    assert "TC-note-python-block_migrate" in latest
    assert "TC-cells-python-block_migrate" in latest


def test_seed_products_needs_manual_review_only_applies_to_named_products(tmp_path):
    result = sut.seed_products(
        [("cells", "net"), ("note", "python")],
        needs_manual_review_products={("cells", "net")},
        recorded_by="s1",
    )
    assert len(result["seeded"]) == 8
    store = TaskcardStore(sut.DEFAULT_MISSION_ID, repo_root=tmp_path)
    latest = store.read_latest()
    assert latest["TC-cells-net-commit"].get("needs_manual_review") is True
    assert "needs_manual_review" not in latest["TC-note-python-commit"]


def test_parse_product_requires_slash():
    with pytest.raises(ValueError):
        sut._parse_product("note-python")
    assert sut._parse_product("note/python") == ("note", "python")


def test_main_seeds_and_prints_summary(tmp_path, capsys):
    exit_code = sut.main(["--products", "note/python", "--mission", "ST-054-REMEDIATION"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "seeded=4" in out
    assert "skipped_existing=0" in out


def test_main_needs_manual_review_flag(tmp_path):
    sut.main(["--products", "cells/net", "--needs-manual-review"])
    store = TaskcardStore(sut.DEFAULT_MISSION_ID, repo_root=tmp_path)
    latest = store.read_latest()
    assert latest["TC-cells-net-verify"].get("needs_manual_review") is True
