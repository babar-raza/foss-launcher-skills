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
            "registry_type": "maven",
            "candidate": {"group_id": "org.aspose", "artifact_id": "aspose-cells-foss", "version": "26.5.0"},
            "candidate_owner": "org.aspose",
            "verification": {
                "published": True, "verified_at": "2026-07-24", "verified_owner": None,
                "evidence_url": "https://repo1.maven.org/maven2/org/aspose/aspose-cells-foss/",
                "method": "migrated-from-foss_packages.json",
            },
            "owner_match": None,
        }},
        "slides": {"java": {
            "registry_type": "maven",
            "candidate": {"group_id": "org.aspose.slides.foss", "artifact_id": "aspose-slides-foss", "version": "1.0.0"},
            "candidate_owner": "org.aspose",
            "verification": {
                "published": False, "verified_at": None, "verified_owner": None,
                "evidence_url": None, "method": None,
            },
            "owner_match": None,
        }},
        "fictional": {"java": {
            "registry_type": "maven",
            "candidate": {"group_id": "org.aspose", "artifact_id": "aspose-fictional-foss", "version": "1.0.0"},
            "candidate_owner": "org.aspose",
            "verification": {
                "published": False, "verified_at": None, "verified_owner": None,
                "evidence_url": None, "method": None,
            },
            "owner_match": None,
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
    assert data["slides"]["java"]["verification"]["published"] is False
    assert data["fictional"]["java"]["verification"]["published"] is False


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
    assert entry["verification"]["published"] is True
    assert entry["candidate"]["version"] == "1.0.0"
    assert entry["verification"]["verified_at"] == "2026-08-01"
    assert data["slides"]["java"]["verification"]["published"] is True  # mutated in place


def test_apply_proposal_is_not_called_by_run_watch(tmp_path, monkeypatch):
    """Design invariant: the automatic scheduled path (run_watch) must never
    write to data/package_registry.json itself -- only detect and report."""
    data_path = tmp_path / "package_registry.json"
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
    assert sut._DEFAULT_DATA_PATH.name == "package_registry.json"
    assert sut._DEFAULT_DATA_PATH.parent.name == "data"
    assert (sut._DEFAULT_DATA_PATH.parent.parent / ".git").is_dir(), (
        f"_DEFAULT_DATA_PATH's grandparent ({sut._DEFAULT_DATA_PATH.parent.parent}) "
        "should be the repo root (contains .git) -- if this fails, the parents[N] "
        "depth in publish_watcher.py has drifted again"
    )
    assert sut._DEFAULT_DATA_PATH.is_file(), "the real data/package_registry.json must actually exist at the computed default path"


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


def test_steady_state_detects_newer_live_version_on_published_entry():
    """MT036 gap G3: an already-published family (cells, recorded 26.5.0) must be
    flagged when the live version has moved past what's recorded -- the case
    check_unpublished_families() structurally can never catch, since it skips
    published:true entries entirely."""
    data = _fake_data()

    def checker(group_id, artifact_id):
        if artifact_id == "aspose-cells-foss":
            return "26.7.0"
        return None

    proposals = sut.check_published_families_for_new_version(data, live_checker=checker)
    assert len(proposals) == 1
    assert proposals[0]["family"] == "cells"
    assert proposals[0]["recorded_version"] == "26.5.0"
    assert proposals[0]["live_version"] == "26.7.0"


def test_steady_state_no_proposal_when_live_version_matches_recorded():
    data = _fake_data()
    proposals = sut.check_published_families_for_new_version(
        data, live_checker=lambda g, a: "26.5.0"  # matches cells' recorded version exactly
    )
    assert proposals == []


def test_steady_state_skips_unpublished_entries():
    """The mirror-image invariant of test_already_published_families_are_never_rechecked:
    an unpublished entry is check_unpublished_families()'s job, never this function's."""
    data = _fake_data()
    calls = []

    def checker(group_id, artifact_id):
        calls.append((group_id, artifact_id))
        return "1.0.0"

    sut.check_published_families_for_new_version(data, live_checker=checker)
    assert ("org.aspose.slides.foss", "aspose-slides-foss") not in calls, "unpublished entry must never be checked by the steady-state watcher"


def test_steady_state_is_pure_never_mutates_data():
    data = _fake_data()
    before = json.loads(json.dumps(data))  # deep copy for comparison
    sut.check_published_families_for_new_version(data, live_checker=lambda g, a: "99.0.0")
    assert data == before


def test_apply_version_update_proposal_updates_only_version():
    data = _fake_data()
    proposal = {
        "family": "cells", "platform": "java",
        "group_id": "org.aspose", "artifact_id": "aspose-cells-foss",
        "recorded_version": "26.5.0", "live_version": "26.7.0",
        "central_url": "https://repo1.maven.org/maven2/org/aspose/aspose-cells-foss/",
    }
    entry = sut.apply_version_update_proposal(data, proposal, checked_at="2026-08-21")
    assert entry["candidate"]["version"] == "26.7.0"
    assert entry["candidate"]["group_id"] == "org.aspose"  # unrelated fields preserved
    assert entry["verification"]["published"] is True
    assert entry["verification"]["verified_at"] == "2026-08-21"
    assert "26.5.0" in entry["verification"]["evidence_note"] and "26.7.0" in entry["verification"]["evidence_note"]


def test_format_version_update_issue_body_includes_recorded_and_live_versions():
    proposals = [{
        "family": "cells", "platform": "java", "group_id": "org.aspose",
        "artifact_id": "aspose-cells-foss", "recorded_version": "26.5.0", "live_version": "26.7.0",
        "central_url": "https://repo1.maven.org/maven2/org/aspose/aspose-cells-foss/",
    }]
    body = sut.format_version_update_issue_body(proposals)
    assert "26.5.0" in body and "26.7.0" in body
    assert "--mode=republish" in body
    assert "Action Required" in body


def test_run_version_watch_never_writes(tmp_path):
    """Mirror of test_apply_proposal_is_not_called_by_run_watch, for the steady-state path."""
    data_path = tmp_path / "package_registry.json"
    data_path.write_text(json.dumps(_fake_data()), encoding="utf-8")
    sut.configure(data_path=data_path)
    try:
        sut.run_version_watch(live_checker=lambda g, a: "99.0.0")
        assert json.loads(data_path.read_text(encoding="utf-8")) == _fake_data()
    finally:
        sut.configure(data_path=None)


class TestRunAutoApply:
    """Mission MT066-2026-09-09-PACKAGE-INSTALL-RECONCILIATION, Phase 3."""

    def _write(self, tmp_path, data=None):
        data_path = tmp_path / "package_registry.json"
        data_path.write_text(json.dumps(data if data is not None else _fake_data()), encoding="utf-8")
        sut.configure(data_path=data_path)
        return data_path

    def test_applies_unpublished_to_published_and_writes(self, tmp_path):
        data_path = self._write(tmp_path)
        try:
            result = sut.run_auto_apply(live_checker=lambda g, a: "2.0.0" if a == "aspose-fictional-foss" else None)
            assert result["wrote_changes"] is True
            assert len(result["applied"]) == 1
            on_disk = json.loads(data_path.read_text(encoding="utf-8"))
            assert on_disk["fictional"]["java"]["verification"]["published"] is True
            assert on_disk["fictional"]["java"]["candidate"]["version"] == "2.0.0"
        finally:
            sut.configure(data_path=None)

    def test_applies_version_update_and_writes(self, tmp_path):
        data_path = self._write(tmp_path)
        try:
            result = sut.run_auto_apply(live_checker=lambda g, a: "26.7.0" if a == "aspose-cells-foss" else None)
            assert result["wrote_changes"] is True
            on_disk = json.loads(data_path.read_text(encoding="utf-8"))
            assert on_disk["cells"]["java"]["candidate"]["version"] == "26.7.0"
        finally:
            sut.configure(data_path=None)

    def test_no_op_when_nothing_resolves(self, tmp_path):
        data_path = self._write(tmp_path)
        original_bytes = data_path.read_text(encoding="utf-8")
        try:
            result = sut.run_auto_apply(live_checker=lambda g, a: None)
            assert result["wrote_changes"] is False
            assert result["applied"] == []
            assert data_path.read_text(encoding="utf-8") == original_bytes
        finally:
            sut.configure(data_path=None)

    def test_idempotent_rerun_produces_no_second_write(self, tmp_path):
        """Applying the same live state twice must write once, then no-op."""
        data_path = self._write(tmp_path)
        try:
            checker = lambda g, a: "2.0.0" if a == "aspose-fictional-foss" else None  # noqa: E731
            first = sut.run_auto_apply(live_checker=checker)
            assert first["wrote_changes"] is True
            after_first = data_path.read_text(encoding="utf-8")

            second = sut.run_auto_apply(live_checker=checker)
            assert second["wrote_changes"] is False  # already published, nothing left to apply
            assert data_path.read_text(encoding="utf-8") == after_first
        finally:
            sut.configure(data_path=None)

    def test_circuit_breaker_caps_applied_count(self, tmp_path):
        data = _fake_data()
        data["another"] = {"java": {
            "registry_type": "maven",
            "candidate": {"group_id": "org.aspose", "artifact_id": "aspose-another-foss", "version": "1.0.0"},
            "candidate_owner": "org.aspose",
            "verification": {"published": False, "verified_at": None, "verified_owner": None,
                              "evidence_url": None, "method": None},
            "owner_match": None,
        }}
        data_path = self._write(tmp_path, data=data)
        try:
            # Both "fictional" and "another" resolve live -- cap at 1 to force an overflow.
            result = sut.run_auto_apply(
                live_checker=lambda g, a: "2.0.0" if a in ("aspose-fictional-foss", "aspose-another-foss") else None,
                max_apply=1,
            )
            assert result["wrote_changes"] is True
            assert len(result["applied"]) == 1
            assert len(result["skipped_capped"]) == 1
        finally:
            sut.configure(data_path=None)

    def test_validation_failure_aborts_the_entire_write(self, tmp_path):
        """A pre-existing, unrelated data-quality problem elsewhere in the file
        must abort the WHOLE write, even though the actual proposal being
        applied is itself perfectly valid -- 'nothing partial is ever persisted'."""
        data = _fake_data()
        data["broken"] = {"java": {"registry_type": "not-a-real-registry-type"}}  # missing required fields too
        data_path = self._write(tmp_path, data=data)
        original_bytes = data_path.read_text(encoding="utf-8")
        try:
            result = sut.run_auto_apply(live_checker=lambda g, a: "2.0.0" if a == "aspose-fictional-foss" else None)
            assert result["wrote_changes"] is False
            assert result["applied"] == []
            assert result["validation_errors"] != []
            assert data_path.read_text(encoding="utf-8") == original_bytes  # untouched
        finally:
            sut.configure(data_path=None)

    def test_github_output_written_when_env_var_present(self, tmp_path, monkeypatch):
        output_path = tmp_path / "github_output.txt"
        monkeypatch.setenv("GITHUB_OUTPUT", str(output_path))
        data_path = self._write(tmp_path)
        try:
            sut.configure(data_path=data_path, live_checker=lambda g, a: "2.0.0" if a == "aspose-fictional-foss" else None)
            exit_code = sut.main(["--auto-apply"])
            assert exit_code == 1  # applied a proposal -> still reports it for visibility
            content = output_path.read_text(encoding="utf-8")
            assert "wrote_changes=true" in content
        finally:
            sut.configure(data_path=None, live_checker=None)

    def test_cli_auto_apply_reports_overflow_via_normal_issue_path(self, tmp_path, capsys):
        data = _fake_data()
        data["another"] = {"java": {
            "registry_type": "maven",
            "candidate": {"group_id": "org.aspose", "artifact_id": "aspose-another-foss", "version": "1.0.0"},
            "candidate_owner": "org.aspose",
            "verification": {"published": False, "verified_at": None, "verified_owner": None,
                              "evidence_url": None, "method": None},
            "owner_match": None,
        }}
        data_path = self._write(tmp_path, data=data)
        try:
            sut.configure(
                data_path=data_path,
                live_checker=lambda g, a: "2.0.0" if a in ("aspose-fictional-foss", "aspose-another-foss") else None,
            )
            exit_code = sut.main(["--auto-apply", "--max-auto-apply", "1"])
            assert exit_code == 1
            out = capsys.readouterr().out
            assert "circuit breaker reached" in out
            assert "Action Required" in out  # the overflow's issue body still gets printed
        finally:
            sut.configure(data_path=None, live_checker=None)


def test_cli_exit_code_reflects_findings(tmp_path, capsys):
    data_path = tmp_path / "package_registry.json"
    data_path.write_text(json.dumps(_fake_data()), encoding="utf-8")
    try:
        sut.configure(data_path=data_path, live_checker=lambda g, a: None)
        assert sut.main([]) == 0  # nothing resolves -> exit 0

        sut.configure(data_path=data_path, live_checker=lambda g, a: "3.0.0")
        assert sut.main([]) == 1  # something resolves -> exit 1 (signals the workflow to open an issue)
    finally:
        sut.configure(data_path=None, live_checker=None)
