"""
Tests for RPR-C-02: promote.py must write baseline SHA history through
baseline_ledger.py instead of relying solely on model.yaml.repo_sha, a single
scalar destroyed on every full-dict rewrite.

Regression context: before this fix, refresh_knowledge.py wrote a
previous_repo_sha field intended to preserve one generation of history, but
promote.py's subsequent full-dict rewrite of model.yaml never included that
field in its output dict, so it was silently dropped on every single promote()
call -- confirmed empirically pre-fix against a live product's model.yaml
(no previous_repo_sha key present despite the code path that should have
written one). This is the mechanical root cause of the 3D-NET-REFRESH-002
backlog conflation (a hand-copied SHA pair in a backlog entry going stale
mid-cycle because nothing durable tracked the transition).
"""

import json
from pathlib import Path

import pytest
import yaml

import promote as promote_mod
from lib.baseline_ledger import BaselineLedger

SCOUT_CLAIMS = [
    {"claim_id": "CLM-test-p1-001", "text": "Scene.open(filename) loads a 3D file.", "kind": "api_method"},
]
API_SURFACE = [
    {"name": "Scene", "methods": [{"name": "open", "return_type": "Scene", "params": ["filename"]}],
     "properties": [], "enum_members": [], "bases": []},
]


def _setup_scout(tmp_path: Path, repo_sha: str) -> Path:
    knowledge_root = tmp_path / "knowledge"
    scout_dir = knowledge_root / "test" / "python" / "scout"
    scout_dir.mkdir(parents=True, exist_ok=True)
    (scout_dir / "claims.json").write_text(json.dumps(SCOUT_CLAIMS, indent=2), encoding="utf-8")
    (scout_dir / "api_surface.json").write_text(json.dumps(API_SURFACE, indent=2), encoding="utf-8")
    (scout_dir / "model.yaml").write_text(
        yaml.dump({"family": "test", "platform": "python", "repo_sha": repo_sha, "stale_since": None}),
        encoding="utf-8",
    )
    return knowledge_root


def test_single_promote_creates_one_accepted_ledger_entry(tmp_path):
    kr = _setup_scout(tmp_path, "sha-v1")
    ok = promote_mod.promote("test", "python", knowledge_root=str(kr))
    assert ok

    merged_dir = kr / "test" / "python" / "merged"
    ledger = BaselineLedger("test", "python", merged_dir=merged_dir)
    history = ledger.history()
    assert len(history) == 1
    assert history[0]["new_repo_sha"] == "sha-v1"
    assert history[0]["status"] == "accepted"
    assert history[0]["prior_repo_sha"] is None  # first-ever promotion for this product


def test_two_sequential_promotes_produce_two_ledger_entries(tmp_path):
    """The literal regression guard: model.yaml shows only the latest SHA
    (unchanged, correct behavior), but the ledger must retain BOTH transitions
    -- this is exactly what was silently lost before RPR-C-02."""
    kr = _setup_scout(tmp_path, "sha-v1")
    assert promote_mod.promote("test", "python", knowledge_root=str(kr))

    _setup_scout(tmp_path, "sha-v2")  # simulate a fresh scout run with an updated upstream SHA
    assert promote_mod.promote("test", "python", knowledge_root=str(kr))

    merged_dir = kr / "test" / "python" / "merged"

    # model.yaml (by design) shows only the latest -- this is NOT the bug, it's
    # the documented current-value cache behavior; the ledger is what must retain history.
    model = yaml.safe_load((merged_dir / "model.yaml").read_text(encoding="utf-8"))
    assert model["repo_sha"] == "sha-v2"

    ledger = BaselineLedger("test", "python", merged_dir=merged_dir)
    history = ledger.history()
    assert len(history) == 2, (
        "expected 2 ledger entries after 2 promote() calls with different SHAs -- "
        "if this is 1, the RPR-C-02 fix has regressed and history is being lost again"
    )
    assert history[0]["new_repo_sha"] == "sha-v1"
    assert history[1]["new_repo_sha"] == "sha-v2"
    assert history[1]["prior_repo_sha"] == "sha-v1", (
        "second entry must record sha-v1 as its prior_repo_sha -- this is the exact "
        "value that was silently destroyed pre-fix (previous_repo_sha written by "
        "refresh_knowledge.py, then dropped by promote.py's full-dict rewrite)"
    )


def test_3d_net_refresh_002_scenario_resolves(tmp_path):
    """Reproduces the exact backlog-documented conflation: a refresh cycle lands
    (sha-A -> sha-B) that a human/agent never observes directly (e.g. a backlog
    entry was written referencing an older pair), then a SECOND, later refresh
    lands (sha-B -> sha-C) before anyone reconciles the first. Pre-fix, only
    sha-C would ever be recoverable from model.yaml, with no durable trail
    explaining how the product got there. Post-fix, the full sha-A -> sha-B ->
    sha-C chain is reconstructable from the ledger alone."""
    kr = _setup_scout(tmp_path, "61580eaa2b")  # the actual pre-conflation SHA from the real backlog entry
    assert promote_mod.promote("test", "python", knowledge_root=str(kr))

    _setup_scout(tmp_path, "76ee798cfb")  # the SHA originally filed as "current" in the backlog item
    assert promote_mod.promote("test", "python", knowledge_root=str(kr))

    _setup_scout(tmp_path, "53cb6be63d")  # the later, uncoordinated refresh the backlog entry never saw
    assert promote_mod.promote("test", "python", knowledge_root=str(kr))

    merged_dir = kr / "test" / "python" / "merged"
    ledger = BaselineLedger("test", "python", merged_dir=merged_dir)
    history = ledger.history()
    shas = [e["new_repo_sha"] for e in history]
    assert shas == ["61580eaa2b", "76ee798cfb", "53cb6be63d"], (
        "the full 3-hop chain must be reconstructable from the ledger alone -- "
        "this is precisely the reconciliation the real 3D-NET-REFRESH-002 backlog "
        "entry could not perform, because no durable ledger existed at the time"
    )


def test_promote_still_succeeds_if_ledger_write_fails(tmp_path, monkeypatch):
    """Knowledge promotion must not become contingent on ledger availability --
    a ledger-write failure is logged, not fatal to promote()."""
    kr = _setup_scout(tmp_path, "sha-v1")

    def _boom(*a, **kw):
        raise RuntimeError("simulated ledger failure")

    monkeypatch.setattr("lib.baseline_ledger.BaselineLedger.append", _boom)
    ok = promote_mod.promote("test", "python", knowledge_root=str(kr))
    assert ok, "promote() must still succeed even when the ledger write fails"

    merged_dir = kr / "test" / "python" / "merged"
    assert (merged_dir / "model.yaml").exists()  # the primary artifact is unaffected
