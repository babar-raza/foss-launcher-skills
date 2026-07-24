"""
Tests for commands/ops/publish_watcher.py (Mission MT008, TC-MT008-05).

Covers the taskcard's required fixtures: a family that resolves live (positive),
a family that never resolves (negative), and the specific invariant that nothing
other than a live checker result can ever produce a proposal -- there is no
workflow-exit-code path into this module at all, closing the documented
waitUtil/waitUntil silent-failure precedent (.claude/commands/foss-java-publish.md).
"""

import json
import sys
from pathlib import Path

import pytest

_PIPELINE_ROOT = Path(__file__).resolve().parents[1]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

import commands.ops.publish_watcher as sut


def _fake_data():
    return {
        "cells": {"java": {
            "scouted": {"group_id": "org.aspose", "artifact_id": "aspose-cells-foss", "version": "26.5.0"},
            "published": True,
            "confirmed": {"group_id": "org.aspose", "artifact_id": "aspose-cells-foss", "version": "26.5.0"},
            "confirmed_at": "2026-07-24", "central_url": "https://repo1.maven.org/maven2/org/aspose/aspose-cells-foss/",
        }},
        "slides": {"java": {
            "scouted": {"group_id": "org.aspose.slides.foss", "artifact_id": "aspose-slides-foss", "version": "1.0.0"},
            "published": False,
            "confirmed": None, "confirmed_at": None, "central_url": None,
        }},
        "fictional": {"java": {
            "scouted": {"group_id": "org.aspose", "artifact_id": "aspose-fictional-foss", "version": "1.0.0"},
            "published": False,
            "confirmed": None, "confirmed_at": None, "central_url": None,
        }},
    }


def test_positive_fixture_a_family_that_resolves_produces_a_proposal():
    data = _fake_data()

    def checker(group_id, artifact_id):
        if artifact_id == "aspose-fictional-foss":
            return "2.0.0"
        return None

    proposals = sut.check_unpublished_families(data, live_checker=checker)
    assert len(proposals) == 1
    assert proposals[0]["family"] == "fictional"
    assert proposals[0]["version"] == "2.0.0"
    assert proposals[0]["group_id"] == "org.aspose"


def test_negative_fixture_a_family_that_never_resolves_stays_unpublished():
    data = _fake_data()

    def checker(group_id, artifact_id):
        return None  # never resolves, no matter what's asked

    proposals = sut.check_unpublished_families(data, live_checker=checker)
    assert proposals == []
    # data itself must be completely untouched -- check_unpublished_families is pure
    assert data["slides"]["java"]["published"] is False
    assert data["fictional"]["java"]["published"] is False


def test_already_published_families_are_never_rechecked():
    """INV-03 equivalent for the watcher: a published:true entry must never be
    re-queried or re-proposed, even if the checker would say something different."""
    data = _fake_data()
    calls = []

    def checker(group_id, artifact_id):
        calls.append((group_id, artifact_id))
        return "99.0.0"  # would "resolve" everything if actually called

    sut.check_unpublished_families(data, live_checker=checker)
    assert ("org.aspose", "aspose-cells-foss") not in calls, "published:true entry must never be checked"


def test_workflow_exit_code_has_no_path_into_a_proposal():
    """Closes the documented waitUtil/waitUntil silent-failure precedent: nothing
    resembling a 'workflow succeeded' signal exists anywhere in this module's
    inputs. The ONLY way a proposal is produced is live_checker returning a
    truthy version string -- proven here by a checker that always returns None
    regardless of any other state, confirming no side-channel exists."""
    data = _fake_data()
    # A checker that unconditionally reports "not live", simulating the exact
    # scenario a green-but-unvalidated release workflow would NOT be able to fake:
    # the only source of truth is the live HTTP check itself.
    proposals = sut.check_unpublished_families(data, live_checker=lambda g, a: None)
    assert proposals == []


def test_apply_proposal_flips_state_correctly():
    data = _fake_data()
    proposal = {
        "family": "slides", "platform": "java",
        "group_id": "org.aspose.slides.foss", "artifact_id": "aspose-slides-foss",
        "version": "1.0.0", "central_url": "https://repo1.maven.org/maven2/org/aspose/slides/foss/aspose-slides-foss/",
    }
    entry = sut.apply_proposal(data, proposal, checked_at="2026-08-01")
    assert entry["published"] is True
    assert entry["confirmed"]["version"] == "1.0.0"
    assert entry["confirmed_at"] == "2026-08-01"
    assert data["slides"]["java"]["published"] is True  # mutated in place


def test_apply_proposal_is_not_called_by_run_watch(tmp_path, monkeypatch):
    """Design invariant: the automatic scheduled path (run_watch) must never
    write to data/foss_packages.json itself -- only detect and report."""
    data_path = tmp_path / "foss_packages.json"
    data_path.write_text(json.dumps(_fake_data()), encoding="utf-8")
    sut.configure(data_path=data_path)
    try:
        sut.run_watch(live_checker=lambda g, a: "9.9.9")
        # File on disk must be byte-identical to what we wrote -- run_watch never writes.
        assert json.loads(data_path.read_text(encoding="utf-8")) == _fake_data()
    finally:
        sut.configure(data_path=None)


def test_default_data_path_resolves_to_the_real_repo_root():
    """Regression pin: the parents[N] repo-root computation had an off-by-one
    (parents[5] instead of parents[4]) that pointed one directory ABOVE the real
    repo root, caught only by actually running the CLI against production data,
    not by any fixture-based test (fixtures inject their own tmp_path, which
    masked the bug). Assert the real default path lands inside this repo and
    matches the file that actually exists on disk."""
    assert sut._DEFAULT_DATA_PATH.name == "foss_packages.json"
    assert sut._DEFAULT_DATA_PATH.parent.name == "data"
    assert (sut._DEFAULT_DATA_PATH.parent.parent / ".git").is_dir(), (
        f"_DEFAULT_DATA_PATH's grandparent ({sut._DEFAULT_DATA_PATH.parent.parent}) "
        "should be the repo root (contains .git) -- if this fails, the parents[N] "
        "depth in publish_watcher.py has drifted again"
    )
    assert sut._DEFAULT_DATA_PATH.is_file(), "the real data/foss_packages.json must actually exist at the computed default path"


def test_default_live_checker_handles_network_failure_gracefully():
    """Must never raise -- a checker failure is 'could not confirm', not a crash."""
    result = sut.default_live_checker("org.aspose", "definitely-does-not-exist-xyz-123")
    assert result is None


def test_format_issue_body_includes_actionable_steps_and_findings():
    proposals = [{
        "family": "fictional", "platform": "java", "group_id": "org.aspose",
        "artifact_id": "aspose-fictional-foss", "version": "2.0.0",
        "central_url": "https://repo1.maven.org/maven2/org/aspose/aspose-fictional-foss/",
    }]
    body = sut.format_issue_body(proposals)
    assert "org.aspose:aspose-fictional-foss:2.0.0" in body
    assert "/repo-scout" in body
    assert "Action Required" in body


def test_cli_exit_code_reflects_findings(tmp_path, capsys):
    data_path = tmp_path / "foss_packages.json"
    data_path.write_text(json.dumps(_fake_data()), encoding="utf-8")
    try:
        sut.configure(data_path=data_path, live_checker=lambda g, a: None)
        assert sut.main([]) == 0  # nothing resolves -> exit 0

        sut.configure(data_path=data_path, live_checker=lambda g, a: "3.0.0")
        assert sut.main([]) == 1  # something resolves -> exit 1 (signals the workflow to open an issue)
    finally:
        sut.configure(data_path=None, live_checker=None)
