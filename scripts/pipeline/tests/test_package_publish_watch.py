"""
Tests for commands/ops/package_publish_watch.py (Mission
MT015-2026-07-30-PACKAGE-REGISTRY, TC-MT015-09).

Multi-registry sibling of publish_watcher.py (Maven-only). Covers the
debounce-gated proposal flow for pypi/nuget/npm/go_modules/cargo, the
counter-persists-but-flip-doesn't design (see module docstring), and the
content-healing-needed hint surfaced per proposal.
"""

import json
import sys
from pathlib import Path

import pytest

_PIPELINE_ROOT = Path(__file__).resolve().parents[1]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

import commands.ops.package_publish_watch as sut
import commands.ops.registry_coverage_scan as _rcs
from package_registries import CheckResult


@pytest.fixture(autouse=True)
def isolate_repo(tmp_path):
    data_path = tmp_path / "package_registry.json"
    empty_content_root = tmp_path / "content"
    empty_content_root.mkdir()
    # products_path deliberately points at a nonexistent file by default (Mission
    # MT066-2026-09-09-PACKAGE-INSTALL-RECONCILIATION, Phase 2) -- same isolation
    # discipline as data_path/content_root below: without this, every test would
    # silently read the REAL repo's data/products.json for identity corroboration,
    # making test behavior depend on that file's current, changing contents. A
    # test that needs real products.json content writes its own tmp_path copy and
    # calls sut.configure(products_path=...) itself.
    sut.configure(data_path=data_path, content_root=empty_content_root, products_path=tmp_path / "products.json")
    # TC-MT018-09: main() now also calls check_exclusion_reconciliation(),
    # whose default scan_fn (registry_coverage_scan.scan_coverage) reads from
    # a module-level _REPO_ROOT independent of sut's own configure() seam --
    # without this, every test in this file would silently scan the REAL
    # repo's content/ + data/package_registry.json during main() calls.
    _rcs.configure(repo_root=tmp_path)
    yield data_path
    sut.configure(data_path=None, content_root=None, products_path=None)
    _rcs.configure(repo_root=None)


def _fake_adapter(result: CheckResult):
    class _Adapter:
        @staticmethod
        def check_published(candidate):
            return result
    return _Adapter()


def _entry(registry_type="pypi", published=False, consecutive=0):
    return {
        "registry_type": registry_type,
        "candidate": {"name": "aspose-cells-foss"},
        "verification": {"published": published, "consecutive_checks_agreeing": consecutive},
    }


def test_first_published_check_increments_counter_but_no_proposal():
    data = {"cells": {"python": _entry(consecutive=0)}}
    result = CheckResult(published=True, ambiguous=False, evidence_url="u", method="m")
    adapters = {"pypi": _fake_adapter(result)}
    proposals, uncorroborated = sut.check_unpublished_entries(data, adapters=adapters)
    assert proposals == []
    assert uncorroborated == []
    assert data["cells"]["python"]["verification"]["consecutive_checks_agreeing"] == 1
    assert data["cells"]["python"]["verification"]["published"] is False  # never auto-flipped


def test_second_consecutive_published_check_produces_proposal():
    data = {"cells": {"python": _entry(consecutive=1)}}
    result = CheckResult(published=True, ambiguous=False, evidence_url="https://pypi.org/x", method="pypi-json-api", verified_owner="Aspose")
    adapters = {"pypi": _fake_adapter(result)}
    proposals, uncorroborated = sut.check_unpublished_entries(data, adapters=adapters)
    assert len(proposals) == 1
    assert uncorroborated == []
    p = proposals[0]
    assert p["family"] == "cells" and p["platform"] == "python"
    assert p["evidence_url"] == "https://pypi.org/x"
    assert p["verified_owner"] == "Aspose"
    # counter is NOT required to persist a specific value post-flip; published flip itself must NOT be applied
    assert data["cells"]["python"]["verification"]["published"] is False


def test_ambiguous_result_does_not_advance_counter():
    data = {"cells": {"python": _entry(consecutive=1)}}
    result = CheckResult(published=False, ambiguous=True, evidence_url="u", method="m")
    adapters = {"pypi": _fake_adapter(result)}
    proposals, uncorroborated = sut.check_unpublished_entries(data, adapters=adapters)
    assert proposals == []
    assert uncorroborated == []
    assert data["cells"]["python"]["verification"]["consecutive_checks_agreeing"] == 1  # unchanged


def test_not_published_result_resets_counter():
    data = {"cells": {"python": _entry(consecutive=1)}}
    result = CheckResult(published=False, ambiguous=False, evidence_url="u", method="m")
    adapters = {"pypi": _fake_adapter(result)}
    sut.check_unpublished_entries(data, adapters=adapters)
    assert data["cells"]["python"]["verification"]["consecutive_checks_agreeing"] == 0


def test_already_published_entries_are_never_rechecked():
    data = {"cells": {"python": _entry(published=True)}}
    calls = []

    class _Adapter:
        @staticmethod
        def check_published(candidate):
            calls.append(candidate)
            return CheckResult(published=True, ambiguous=False, evidence_url="u", method="m")

    sut.check_unpublished_entries(data, adapters={"pypi": _Adapter()})
    assert calls == []


def _published_entry(registry_type="pypi", consecutive_absent=0):
    return {
        "registry_type": registry_type,
        "candidate": {"name": "aspose-cells-foss"},
        "verification": {"published": True, "evidence_url": "https://pypi.org/prior",
                          "consecutive_checks_absent": consecutive_absent},
    }


class TestApplyDriftDebounce:
    """TC-MT018-09: symmetric counterpart to package_registries.apply_debounce."""

    def test_ambiguous_result_does_not_advance_counter(self):
        result = CheckResult(published=False, ambiguous=True, evidence_url="u", method="m")
        counter, should_flip = sut.apply_drift_debounce(1, result)
        assert counter == 1 and should_flip is False

    def test_still_published_result_resets_counter(self):
        result = CheckResult(published=True, ambiguous=False, evidence_url="u", method="m")
        counter, should_flip = sut.apply_drift_debounce(1, result)
        assert counter == 0 and should_flip is False

    def test_first_absent_result_increments_but_no_flip(self):
        result = CheckResult(published=False, ambiguous=False, evidence_url="u", method="m")
        counter, should_flip = sut.apply_drift_debounce(0, result)
        assert counter == 1 and should_flip is False

    def test_second_consecutive_absent_result_flips(self):
        result = CheckResult(published=False, ambiguous=False, evidence_url="u", method="m")
        counter, should_flip = sut.apply_drift_debounce(1, result)
        assert counter == 2 and should_flip is True


class TestCheckPublishedEntriesForDrift:
    """TC-MT018-09: the true->false direction check_unpublished_entries never covered."""

    def test_first_absent_check_increments_counter_but_no_proposal(self):
        data = {"cells": {"python": _published_entry(consecutive_absent=0)}}
        result = CheckResult(published=False, ambiguous=False, evidence_url="u", method="m")
        adapters = {"pypi": _fake_adapter(result)}
        drift = sut.check_published_entries_for_drift(data, adapters=adapters)
        assert drift == []
        assert data["cells"]["python"]["verification"]["consecutive_checks_absent"] == 1
        assert data["cells"]["python"]["verification"]["published"] is True  # never auto-flipped

    def test_second_consecutive_absent_check_produces_drift_proposal(self):
        data = {"cells": {"python": _published_entry(consecutive_absent=1)}}
        result = CheckResult(published=False, ambiguous=False, evidence_url="u", method="m")
        adapters = {"pypi": _fake_adapter(result)}
        drift = sut.check_published_entries_for_drift(data, adapters=adapters)
        assert len(drift) == 1
        p = drift[0]
        assert p["family"] == "cells" and p["platform"] == "python"
        assert p["previous_evidence_url"] == "https://pypi.org/prior"
        # published flip itself must NOT be applied automatically
        assert data["cells"]["python"]["verification"]["published"] is True

    def test_ambiguous_result_does_not_advance_absent_counter(self):
        data = {"cells": {"python": _published_entry(consecutive_absent=1)}}
        result = CheckResult(published=False, ambiguous=True, evidence_url="u", method="m")
        adapters = {"pypi": _fake_adapter(result)}
        sut.check_published_entries_for_drift(data, adapters=adapters)
        assert data["cells"]["python"]["verification"]["consecutive_checks_absent"] == 1

    def test_still_resolving_result_resets_absent_counter(self):
        data = {"cells": {"python": _published_entry(consecutive_absent=1)}}
        result = CheckResult(published=True, ambiguous=False, evidence_url="u", method="m")
        adapters = {"pypi": _fake_adapter(result)}
        sut.check_published_entries_for_drift(data, adapters=adapters)
        assert data["cells"]["python"]["verification"]["consecutive_checks_absent"] == 0

    def test_unpublished_entries_are_never_checked_by_this_function(self):
        data = {"cells": {"python": _entry(published=False)}}
        calls = []

        class _Adapter:
            @staticmethod
            def check_published(candidate):
                calls.append(candidate)
                return CheckResult(published=False, ambiguous=False, evidence_url="u", method="m")

        sut.check_published_entries_for_drift(data, adapters={"pypi": _Adapter()})
        assert calls == []  # check_unpublished_entries's job, not this function's

    def test_maven_entries_are_skipped(self):
        data = {"cells": {"java": _published_entry(registry_type="maven", consecutive_absent=1)}}
        drift = sut.check_published_entries_for_drift(data, adapters={"pypi": _fake_adapter(
            CheckResult(published=False, ambiguous=False, evidence_url="u", method="m"))})
        assert drift == []
        assert data["cells"]["java"]["verification"]["consecutive_checks_absent"] == 1  # untouched


class TestIdentityCorroborationGate:
    """Mission MT066-2026-09-09-PACKAGE-INSTALL-RECONCILIATION, Phase 2: the
    unpublished->published transition (the riskier of the two this mission
    automates, since it asserts a brand-new public identity) must not be
    proposed on an uncorroborated identity, even once debounce is satisfied."""

    def _non_foss_entry(self, consecutive=1):
        return {
            "registry_type": "pypi",
            "candidate": {"name": "aspose-note"},  # no "foss" substring -- the real historical case
            "verification": {"published": False, "consecutive_checks_agreeing": consecutive},
        }

    def test_non_foss_name_with_no_corroborating_project_url_is_uncorroborated_not_a_proposal(self, tmp_path):
        data = {"cells": {"python": self._non_foss_entry(consecutive=1)}}
        result = CheckResult(
            published=True, ambiguous=False, evidence_url="https://pypi.org/x",
            method="pypi-json-api", project_url="https://products.aspose.com/unrelated/",
        )
        sut.configure(products_path=tmp_path / "does-not-exist.json")
        proposals, uncorroborated = sut.check_unpublished_entries(data, adapters={"pypi": _fake_adapter(result)})
        assert proposals == []
        assert len(uncorroborated) == 1
        assert uncorroborated[0]["family"] == "cells"
        assert uncorroborated[0]["platform"] == "python"
        assert "identity could not be corroborated" in uncorroborated[0]["reason"]
        sut.configure()

    def test_non_foss_name_corroborated_via_matching_project_url_still_produces_a_proposal(self, tmp_path):
        """Real historical case: PyPI's aspose-note has no 'foss' substring but
        IS the genuine FOSS package -- its project_url corroborates it."""
        products_path = tmp_path / "products.json"
        products_path.write_text(json.dumps([
            {"family": "note", "platform": "python", "repo_url": "https://github.com/aspose-note-foss/Aspose.Note-FOSS-for-Python"},
        ]), encoding="utf-8")
        sut.configure(products_path=products_path)
        try:
            entry = self._non_foss_entry(consecutive=1)
            data = {"note": {"python": entry}}
            result = CheckResult(
                published=True, ambiguous=False, evidence_url="https://pypi.org/x",
                method="pypi-json-api", project_url="https://github.com/aspose-note-foss/Aspose.Note-FOSS-for-Python",
            )
            proposals, uncorroborated = sut.check_unpublished_entries(data, adapters={"pypi": _fake_adapter(result)})
            assert len(proposals) == 1
            assert uncorroborated == []
        finally:
            sut.configure()

    def test_foss_substring_name_needs_no_products_json_at_all(self, tmp_path):
        """The overwhelming common case (candidate name already contains
        'foss') never needs products.json/project_url corroboration."""
        data = {"cells": {"python": _entry(consecutive=1)}}  # "aspose-cells-foss"
        result = CheckResult(published=True, ambiguous=False, evidence_url="u", method="m", project_url=None)
        sut.configure(products_path=tmp_path / "does-not-exist.json")
        proposals, uncorroborated = sut.check_unpublished_entries(data, adapters={"pypi": _fake_adapter(result)})
        assert len(proposals) == 1
        assert uncorroborated == []
        sut.configure()


class TestExpectedRepoFragment:
    def test_returns_empty_string_when_products_json_missing(self, tmp_path):
        sut.configure(products_path=tmp_path / "does-not-exist.json")
        assert sut._expected_repo_fragment("cells") == ""
        sut.configure()

    def test_returns_empty_string_when_family_not_found(self, tmp_path):
        products_path = tmp_path / "products.json"
        products_path.write_text(json.dumps([{"family": "pdf", "repo_url": "https://github.com/aspose-pdf-foss/x"}]), encoding="utf-8")
        sut.configure(products_path=products_path)
        assert sut._expected_repo_fragment("cells") == ""
        sut.configure()

    def test_extracts_org_from_repo_url(self, tmp_path):
        products_path = tmp_path / "products.json"
        products_path.write_text(json.dumps([
            {"family": "cells", "platform": "java", "repo_url": "https://github.com/aspose-cells-foss/Aspose.Cells-FOSS-for-Java"},
        ]), encoding="utf-8")
        sut.configure(products_path=products_path)
        assert sut._expected_repo_fragment("cells") == "aspose-cells-foss"
        sut.configure()

    def test_returns_empty_string_on_malformed_json(self, tmp_path):
        products_path = tmp_path / "products.json"
        products_path.write_text("not json{{{", encoding="utf-8")
        sut.configure(products_path=products_path)
        assert sut._expected_repo_fragment("cells") == ""
        sut.configure()


class TestApplyVersionDebounce:
    """Mission MT066-2026-09-09-PACKAGE-INSTALL-RECONCILIATION, Phase 2: the
    steady-state version-update debounce for the 5 non-Maven registries."""

    def test_ambiguous_result_never_advances(self):
        counter, propose = sut.apply_version_debounce(0, CheckResult(published=False, ambiguous=True, evidence_url="u", method="m"), "1.0.0")
        assert counter == 0
        assert propose is False

    def test_no_version_reported_never_advances(self):
        counter, propose = sut.apply_version_debounce(0, CheckResult(published=True, ambiguous=False, evidence_url="u", method="m", version=None), "1.0.0")
        assert counter == 0
        assert propose is False

    def test_same_version_resets_counter(self):
        counter, propose = sut.apply_version_debounce(1, CheckResult(published=True, ambiguous=False, evidence_url="u", method="m", version="1.0.0"), "1.0.0")
        assert counter == 0
        assert propose is False

    def test_first_differing_version_increments_but_does_not_propose(self):
        counter, propose = sut.apply_version_debounce(0, CheckResult(published=True, ambiguous=False, evidence_url="u", method="m", version="2.0.0"), "1.0.0")
        assert counter == 1
        assert propose is False

    def test_second_consecutive_differing_version_proposes(self):
        counter, propose = sut.apply_version_debounce(1, CheckResult(published=True, ambiguous=False, evidence_url="u", method="m", version="2.0.0"), "1.0.0")
        assert counter == 2
        assert propose is True


class TestCheckPublishedEntriesForVersionUpdate:
    def _published_versioned_entry(self, version="1.0.0", counter=0, registry_type="pypi"):
        return {
            "registry_type": registry_type,
            "candidate": {"name": "aspose-cells-foss", "version": version},
            "verification": {"published": True, "consecutive_version_checks_agreeing": counter},
        }

    def test_no_proposal_below_debounce_threshold(self):
        data = {"cells": {"python": self._published_versioned_entry(version="26.7.0", counter=0)}}
        result = CheckResult(published=True, ambiguous=False, evidence_url="u", method="m", version="26.8.0")
        proposals = sut.check_published_entries_for_version_update(data, adapters={"pypi": _fake_adapter(result)})
        assert proposals == []
        assert data["cells"]["python"]["verification"]["consecutive_version_checks_agreeing"] == 1

    def test_proposal_once_debounce_satisfied(self):
        data = {"cells": {"python": self._published_versioned_entry(version="26.7.0", counter=1)}}
        result = CheckResult(published=True, ambiguous=False, evidence_url="https://pypi.org/x", method="pypi-json-api", version="26.8.0")
        proposals = sut.check_published_entries_for_version_update(data, adapters={"pypi": _fake_adapter(result)})
        assert len(proposals) == 1
        p = proposals[0]
        assert p["recorded_version"] == "26.7.0"
        assert p["live_version"] == "26.8.0"

    def test_unpublished_entries_are_never_checked(self):
        data = {"cells": {"python": _entry(published=False)}}
        calls = []

        class _Adapter:
            @staticmethod
            def check_published(candidate):
                calls.append(candidate)
                return CheckResult(published=True, ambiguous=False, evidence_url="u", method="m", version="1.0.0")

        sut.check_published_entries_for_version_update(data, adapters={"pypi": _Adapter()})
        assert calls == []

    def test_yanked_live_version_is_never_proposed(self):
        """A yanked version is discouraged, not gone -- recommending it in
        install instructions would be actively harmful."""
        data = {"cells": {"rust": self._published_versioned_entry(version="26.7.0", counter=1, registry_type="cargo")}}
        result = CheckResult(published=True, ambiguous=False, evidence_url="u", method="m", version="26.8.0", yanked=True)
        proposals = sut.check_published_entries_for_version_update(data, adapters={"cargo": _fake_adapter(result)})
        assert proposals == []

    def test_maven_entries_are_skipped_own_watcher_handles_them(self):
        data = {"cells": {"java": self._published_versioned_entry(version="1.0.0", registry_type="maven")}}
        proposals = sut.check_published_entries_for_version_update(data, adapters={"pypi": _fake_adapter(
            CheckResult(published=True, ambiguous=False, evidence_url="u", method="m", version="2.0.0"))})
        assert proposals == []


def test_apply_version_update_proposal_updates_candidate_and_verification():
    data = {"cells": {"python": {
        "registry_type": "pypi",
        "candidate": {"name": "aspose-cells-foss", "version": "26.7.0"},
        "verification": {"published": True},
    }}}
    proposal = {
        "family": "cells", "platform": "python", "registry_type": "pypi",
        "candidate": {"name": "aspose-cells-foss", "version": "26.7.0"},
        "recorded_version": "26.7.0", "live_version": "26.8.0",
        "evidence_url": "https://pypi.org/x", "method": "pypi-json-api",
    }
    sut.apply_version_update_proposal(data, proposal, checked_at="2026-09-09")
    entry = data["cells"]["python"]
    assert entry["candidate"]["version"] == "26.8.0"
    assert entry["verification"]["published"] is True
    assert entry["verification"]["verified_at"] == "2026-09-09"
    assert "26.7.0 -> 26.8.0" in entry["verification"]["evidence_note"]


def test_format_version_update_issue_body_lists_findings():
    body = sut.format_version_update_issue_body([{
        "family": "pdf", "platform": "python", "registry_type": "pypi",
        "recorded_version": "26.7.0", "live_version": "26.8.0", "evidence_url": "https://pypi.org/x",
    }])
    assert "pdf/python" in body
    assert "26.7.0" in body and "26.8.0" in body


def test_format_uncorroborated_body_lists_findings_and_reason():
    body = sut.format_uncorroborated_body([{
        "family": "note", "platform": "python", "registry_type": "pypi",
        "candidate": {"name": "aspose-note"}, "evidence_url": "https://pypi.org/x",
        "project_url": "https://unrelated.example/", "reason": "identity could not be corroborated",
    }])
    assert "note/python" in body
    assert "identity could not be corroborated" in body


def test_format_uncorroborated_body_empty_when_no_findings():
    assert sut.format_uncorroborated_body([]) == ""


class TestCheckExclusionReconciliation:
    """TC-MT018-09: reconciliation between registry_exclusions.json and live content."""

    def test_returns_excluded_but_still_live_from_scan(self):
        stub = lambda: {"excluded_but_still_live": ["cells/typescript"]}  # noqa: E731
        result = sut.check_exclusion_reconciliation(scan_fn=stub)
        assert result == ["cells/typescript"]

    def test_empty_when_scan_reports_nothing(self):
        stub = lambda: {"excluded_but_still_live": []}  # noqa: E731
        result = sut.check_exclusion_reconciliation(scan_fn=stub)
        assert result == []


class TestFormatDriftAndReconciliationBody:
    def test_includes_drift_section_when_present(self):
        drift = [{"family": "cells", "platform": "python", "registry_type": "pypi",
                  "candidate": {"name": "aspose-cells-foss"}, "previous_evidence_url": "https://pypi.org/x"}]
        body = sut.format_drift_and_reconciliation_body(drift, [])
        assert "no longer resolve" in body
        assert "cells/python" in body

    def test_includes_reconciliation_section_when_present(self):
        body = sut.format_drift_and_reconciliation_body([], ["cells/typescript"])
        assert "Excluded products with live content" in body
        assert "cells/typescript" in body

    def test_empty_sections_omitted(self):
        body = sut.format_drift_and_reconciliation_body([], [])
        assert "no longer resolve" not in body
        assert "Excluded products with live content" not in body


class TestMainIntegratesDriftAndReconciliation:
    def test_exit_code_1_when_only_drift_found_no_publish_proposals(self, tmp_path):
        data_path = tmp_path / "package_registry.json"
        data_path.write_text(json.dumps({"cells": {"python": _published_entry(consecutive_absent=1)}}), encoding="utf-8")
        sut.configure(data_path=data_path)
        result = CheckResult(published=False, ambiguous=False, evidence_url="u", method="m")
        exit_code = sut.main(["--no-persist-counters"], adapters={"pypi": _fake_adapter(result)},
                              scan_fn=lambda: {"excluded_but_still_live": []})
        assert exit_code == 1

    def test_exit_code_1_when_only_reconciliation_found(self, tmp_path):
        data_path = tmp_path / "package_registry.json"
        data_path.write_text(json.dumps({}), encoding="utf-8")
        sut.configure(data_path=data_path)
        exit_code = sut.main(["--no-persist-counters"], adapters={},
                              scan_fn=lambda: {"excluded_but_still_live": ["cells/typescript"]})
        assert exit_code == 1

    def test_exit_code_0_when_nothing_found(self, tmp_path):
        data_path = tmp_path / "package_registry.json"
        data_path.write_text(json.dumps({}), encoding="utf-8")
        sut.configure(data_path=data_path)
        exit_code = sut.main(["--no-persist-counters"], adapters={},
                              scan_fn=lambda: {"excluded_but_still_live": []})
        assert exit_code == 0


def test_maven_entries_are_skipped_own_watcher_handles_them():
    data = {"cells": {"java": _entry(registry_type="maven", consecutive=1)}}
    proposals, uncorroborated = sut.check_unpublished_entries(data, adapters={"pypi": _fake_adapter(
        CheckResult(published=True, ambiguous=False, evidence_url="u", method="m"))})
    assert proposals == []
    assert uncorroborated == []
    # counter untouched -- no adapter registered for "maven" in this watcher
    assert data["cells"]["java"]["verification"]["consecutive_checks_agreeing"] == 1


def test_apply_proposal_flips_state_correctly():
    data = {"cells": {"python": _entry(consecutive=2)}}
    proposal = {
        "family": "cells", "platform": "python",
        "candidate": {"name": "aspose-cells-foss"},
        "evidence_url": "https://pypi.org/x", "method": "pypi-json-api", "verified_owner": "Aspose",
    }
    sut.apply_proposal(data, proposal, checked_at="2026-08-01")
    entry = data["cells"]["python"]
    assert entry["verification"]["published"] is True
    assert entry["verification"]["verified_at"] == "2026-08-01"
    assert entry["verification"]["verified_owner"] == "Aspose"


def test_apply_proposal_sets_content_healing_status_atomically():
    """Regression test (2026-09-07): content_healing_status must be set in
    the SAME call as the publish-state flip, never left for a separate,
    memorable-or-forgettable step -- this is the fix for 3d/python's content
    healing sitting untracked after its own registry flip."""
    data = {
        "cells": {"python": _entry(consecutive=2)},
        "3d": {"python": _entry(consecutive=2)},
    }
    needs_healing = {
        "family": "cells", "platform": "python",
        "candidate": {"name": "aspose-cells-foss"},
        "evidence_url": "https://pypi.org/x", "method": "pypi-json-api",
        "verified_owner": "Aspose", "content_healing_needed": True,
    }
    no_healing_needed = {
        "family": "3d", "platform": "python",
        "candidate": {"name": "aspose-3d-foss"},
        "evidence_url": "https://pypi.org/y", "method": "pypi-json-api",
        "verified_owner": "Aspose", "content_healing_needed": False,
    }
    sut.apply_proposal(data, needs_healing, checked_at="2026-09-07")
    sut.apply_proposal(data, no_healing_needed, checked_at="2026-09-07")

    assert data["cells"]["python"]["content_healing_status"] == "pending"
    assert data["cells"]["python"]["content_healing_status_set_at"] == "2026-09-07"
    assert data["3d"]["python"]["content_healing_status"] == "not_needed"
    assert data["3d"]["python"]["content_healing_status_set_at"] == "2026-09-07"


def test_apply_proposal_is_not_called_by_run_watch(tmp_path):
    """Design invariant (matches test_publish_watcher.py's own test of the
    same name): the automatic path never writes verification.published --
    proven observationally (state stays False) rather than by monkeypatching
    apply_proposal itself."""
    data_path = tmp_path / "package_registry.json"
    original = {"cells": {"python": _entry(consecutive=1)}}
    data_path.write_text(json.dumps(original), encoding="utf-8")
    sut.configure(data_path=data_path)

    result = CheckResult(published=True, ambiguous=False, evidence_url="u", method="m")
    sut.run_watch(adapters={"pypi": _fake_adapter(result)})

    assert json.loads(data_path.read_text(encoding="utf-8"))["cells"]["python"]["verification"]["published"] is False


def test_format_issue_body_includes_actionable_steps_and_healing_hint():
    proposals = [{
        "family": "cells", "platform": "python", "registry_type": "pypi",
        "evidence_url": "https://pypi.org/x", "content_healing_needed": True,
        "literal_content_files_flagged": 5,
    }]
    body = sut.format_issue_body(proposals)
    assert "Action Required" in body
    assert "cells/python" in body
    assert "content healing needed, 5 file(s)" in body


def test_format_issue_body_no_healing_needed_case():
    proposals = [{
        "family": "cells", "platform": "python", "registry_type": "pypi",
        "evidence_url": "https://pypi.org/x", "content_healing_needed": False,
    }]
    body = sut.format_issue_body(proposals)
    assert "no literal content healing needed" in body


def test_cli_no_persist_flag_leaves_disk_untouched(tmp_path):
    """CLI-wiring test -- uses main()'s `adapters` test-injection point (zero
    live network calls) rather than monkeypatching run_watch itself."""
    data_path = tmp_path / "package_registry.json"
    original = {"cells": {"python": _entry(consecutive=0)}}
    data_path.write_text(json.dumps(original), encoding="utf-8")
    sut.configure(data_path=data_path)

    result = CheckResult(published=True, ambiguous=False, evidence_url="u", method="m")
    exit_code = sut.main(["--no-persist-counters"], adapters={"pypi": _fake_adapter(result)})
    assert exit_code == 0  # 1 agreeing check only advances the counter, doesn't reach threshold=2
    on_disk = json.loads(data_path.read_text(encoding="utf-8"))
    assert on_disk["cells"]["python"]["verification"]["consecutive_checks_agreeing"] == 0  # disk untouched


def test_cli_persists_updated_counters_by_default(tmp_path):
    data_path = tmp_path / "package_registry.json"
    data_path.write_text(json.dumps({"cells": {"python": _entry(consecutive=0)}}), encoding="utf-8")
    sut.configure(data_path=data_path)

    result = CheckResult(published=True, ambiguous=False, evidence_url="u", method="m")
    sut.main([], adapters={"pypi": _fake_adapter(result)})
    on_disk = json.loads(data_path.read_text(encoding="utf-8"))
    assert on_disk["cells"]["python"]["verification"]["consecutive_checks_agreeing"] == 1


def test_literal_content_scope_counts_flagged_files(tmp_path):
    """_literal_content_scope must use the configurable _CONTENT_ROOT (not the
    real repo content/), so this test runs in milliseconds against fixture
    files instead of scanning the full ~14k-file real corpus."""
    docs_dir = tmp_path / "content" / "docs.aspose.org" / "en" / "slides" / "net" / "getting-started"
    docs_dir.mkdir(parents=True)
    (docs_dir / "installation.md").write_text(
        "```bash\ndotnet add package Aspose.Slides.Foss\n```\n", encoding="utf-8"
    )
    clean_dir = tmp_path / "content" / "docs.aspose.org" / "en" / "slides" / "net" / "developer-guide"
    clean_dir.mkdir(parents=True)
    (clean_dir / "shapes.md").write_text("No install text here.\n", encoding="utf-8")

    sut.configure(data_path=tmp_path / "package_registry.json", content_root=tmp_path / "content")
    entry = {"registry_type": "nuget", "verification": {"published": False}}
    count = sut._literal_content_scope("slides", "net", entry)
    assert count == 1


def test_cli_exit_code_reflects_proposals(tmp_path):
    """Real proposal path, no monkeypatch: seed the counter at 1 (one prior
    agreeing check already recorded) so this run's 2nd agreeing result
    crosses the debounce threshold via main()'s real adapters-injection seam."""
    data_path = tmp_path / "package_registry.json"
    data_path.write_text(json.dumps({"cells": {"python": _entry(consecutive=1)}}), encoding="utf-8")
    sut.configure(data_path=data_path)

    result = CheckResult(published=True, ambiguous=False, evidence_url="u", method="m")
    exit_code = sut.main(["--no-persist-counters"], adapters={"pypi": _fake_adapter(result)})
    assert exit_code == 1
