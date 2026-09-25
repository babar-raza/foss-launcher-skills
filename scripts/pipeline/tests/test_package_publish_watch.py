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


def _schema_valid_entry(**kwargs):
    """run_auto_apply() validates the WHOLE registry via validate_package_registry()
    before writing -- _entry()/_published_entry() above are deliberately minimal
    (fine for the debounce/proposal-shape tests they were built for, which never
    validate the full entry), so auto-apply tests need the required fields those
    helpers omit (candidate_owner, owner_match, and every _VERIFICATION_REQUIRED_FIELDS key)."""
    entry = _entry(**kwargs)
    entry["candidate_owner"] = "asposefoss"
    entry["owner_match"] = None
    entry["verification"].setdefault("verified_at", None)
    entry["verification"].setdefault("verified_owner", None)
    entry["verification"].setdefault("evidence_url", None)
    entry["verification"].setdefault("method", None)
    return entry


def _schema_valid_published_entry(**kwargs):
    entry = _published_entry(**kwargs)
    entry["candidate_owner"] = "asposefoss"
    entry["owner_match"] = None
    entry["verification"].setdefault("verified_at", "2026-01-01")
    entry["verification"].setdefault("verified_owner", None)
    entry["verification"].setdefault("method", "pypi-json-api")
    return entry


class TestRunAutoApply:
    """Mission MT066-2026-09-09-PACKAGE-INSTALL-RECONCILIATION, Phase 3."""

    def _write(self, tmp_path, data):
        data_path = tmp_path / "package_registry.json"
        data_path.write_text(json.dumps(data), encoding="utf-8")
        sut.configure(data_path=data_path)
        return data_path

    def test_applies_corroborated_publish_proposal_and_writes(self, tmp_path):
        data = {"cells": {"python": _schema_valid_entry(consecutive=1)}}  # "aspose-cells-foss" -- foss substring
        data_path = self._write(tmp_path, data)
        result = CheckResult(published=True, ambiguous=False, evidence_url="https://pypi.org/x", method="pypi-json-api")
        outcome = sut.run_auto_apply(adapters={"pypi": _fake_adapter(result)}, scan_fn=lambda: {"excluded_but_still_live": []})
        assert outcome["wrote_changes"] is True
        assert len(outcome["applied"]) == 1
        on_disk = json.loads(data_path.read_text(encoding="utf-8"))
        assert on_disk["cells"]["python"]["verification"]["published"] is True

    def test_never_applies_uncorroborated_even_under_auto_apply(self, tmp_path):
        entry = {
            "registry_type": "pypi",
            "candidate": {"name": "aspose-note"},  # no "foss" substring
            "candidate_owner": "asposefoss",
            "verification": {
                "published": False, "consecutive_checks_agreeing": 1,
                "verified_at": None, "verified_owner": None, "evidence_url": None, "method": None,
            },
            "owner_match": None,
        }
        data = {"note": {"python": entry}}
        data_path = self._write(tmp_path, data)
        result = CheckResult(
            published=True, ambiguous=False, evidence_url="https://pypi.org/x",
            method="pypi-json-api", project_url="https://unrelated.example/",
        )
        outcome = sut.run_auto_apply(adapters={"pypi": _fake_adapter(result)}, scan_fn=lambda: {"excluded_but_still_live": []})
        assert outcome["applied"] == []
        assert len(outcome["uncorroborated"]) == 1
        on_disk = json.loads(data_path.read_text(encoding="utf-8"))
        # counter mutation alone may still be written, but published must stay False
        assert on_disk["note"]["python"]["verification"]["published"] is False

    def test_applies_version_update_proposal_and_writes(self, tmp_path):
        entry = {
            "registry_type": "pypi",
            "candidate": {"name": "aspose-cells-foss", "version": "26.7.0"},
            "candidate_owner": "asposefoss",
            "verification": {
                "published": True, "consecutive_version_checks_agreeing": 1,
                "verified_at": "2026-01-01", "verified_owner": None,
                "evidence_url": "https://pypi.org/x", "method": "pypi-json-api",
            },
            "owner_match": None,
        }
        data = {"cells": {"python": entry}}
        data_path = self._write(tmp_path, data)
        result = CheckResult(published=True, ambiguous=False, evidence_url="u", method="m", version="26.8.0")
        outcome = sut.run_auto_apply(adapters={"pypi": _fake_adapter(result)}, scan_fn=lambda: {"excluded_but_still_live": []})
        assert outcome["wrote_changes"] is True
        on_disk = json.loads(data_path.read_text(encoding="utf-8"))
        assert on_disk["cells"]["python"]["candidate"]["version"] == "26.8.0"

    def test_drift_and_exclusion_findings_never_auto_applied(self, tmp_path):
        """Explicit design invariant: no --auto-apply mode ever touches these."""
        data = {"cells": {"python": _schema_valid_published_entry(consecutive_absent=1)}}
        data_path = self._write(tmp_path, data)
        result = CheckResult(published=False, ambiguous=False, evidence_url="u", method="m")
        outcome = sut.run_auto_apply(
            adapters={"pypi": _fake_adapter(result)},
            scan_fn=lambda: {"excluded_but_still_live": ["cells/typescript"]},
        )
        assert len(outcome["drift_proposals"]) == 1
        assert outcome["excluded_but_still_live"] == ["cells/typescript"]
        on_disk = json.loads(data_path.read_text(encoding="utf-8"))
        assert on_disk["cells"]["python"]["verification"]["published"] is True  # never auto-reverted

    def test_no_op_when_nothing_changes(self, tmp_path):
        # Every counter this run's 4 check_* calls could touch (version-update AND
        # drift, since this entry is published:true) is pre-set to 0 -- a prior run
        # already established this tracking state -- otherwise the FIRST-ever check
        # legitimately adds that key (real, meaningful new tracking state, not
        # spurious), which is not the "nothing changes" scenario this test means to
        # exercise.
        entry = _schema_valid_entry(published=True)
        entry["verification"]["consecutive_version_checks_agreeing"] = 0
        entry["verification"]["consecutive_checks_absent"] = 0
        data = {"cells": {"python": entry}}
        data_path = self._write(tmp_path, data)
        original_bytes = data_path.read_text(encoding="utf-8")
        result = CheckResult(published=True, ambiguous=False, evidence_url="u", method="m")
        outcome = sut.run_auto_apply(adapters={"pypi": _fake_adapter(result)}, scan_fn=lambda: {"excluded_but_still_live": []})
        assert outcome["wrote_changes"] is False
        assert data_path.read_text(encoding="utf-8") == original_bytes

    def test_circuit_breaker_caps_combined_publish_and_version_proposals(self, tmp_path):
        data = {
            "cells": {"python": _schema_valid_entry(consecutive=1)},
            "3d": {"python": _schema_valid_entry(consecutive=1)},
        }
        # Give both a distinct family name pattern all containing "foss" already.
        data["3d"]["python"]["candidate"]["name"] = "aspose-3d-foss"
        data_path = self._write(tmp_path, data)
        result = CheckResult(published=True, ambiguous=False, evidence_url="u", method="m")
        outcome = sut.run_auto_apply(
            adapters={"pypi": _fake_adapter(result)}, max_apply=1,
            scan_fn=lambda: {"excluded_but_still_live": []},
        )
        assert len(outcome["applied"]) == 1
        assert len(outcome["skipped_capped"]) == 1
        assert outcome["wrote_changes"] is True

    def test_validation_failure_aborts_entire_write(self, tmp_path):
        data = {
            "cells": {"python": _schema_valid_entry(consecutive=1)},
            "broken": {"java": {"registry_type": "not-a-real-type"}},
        }
        data_path = self._write(tmp_path, data)
        original_bytes = data_path.read_text(encoding="utf-8")
        result = CheckResult(published=True, ambiguous=False, evidence_url="u", method="m")
        outcome = sut.run_auto_apply(adapters={"pypi": _fake_adapter(result)}, scan_fn=lambda: {"excluded_but_still_live": []})
        assert outcome["wrote_changes"] is False
        assert outcome["applied"] == []
        assert outcome["validation_errors"] != []
        assert data_path.read_text(encoding="utf-8") == original_bytes

    def test_cli_auto_apply_writes_github_output(self, tmp_path, monkeypatch):
        output_path = tmp_path / "github_output.txt"
        monkeypatch.setenv("GITHUB_OUTPUT", str(output_path))
        data = {"cells": {"python": _schema_valid_entry(consecutive=1)}}
        self._write(tmp_path, data)
        result = CheckResult(published=True, ambiguous=False, evidence_url="u", method="m")
        exit_code = sut.main(["--auto-apply"], adapters={"pypi": _fake_adapter(result)},
                              scan_fn=lambda: {"excluded_but_still_live": []})
        assert exit_code == 1
        assert "wrote_changes=true" in output_path.read_text(encoding="utf-8")

    def test_idempotency_check_survives_on_disk_formatting_drift(self, tmp_path):
        """Real bug found while writing this test suite: comparing raw bytes
        (json.dumps(data, indent=2) == original_bytes) reports "changed" for a
        purely cosmetic reformatting -- e.g. the on-disk file compact (no
        indent, as written here) vs. this module's own indent=2 output -- with
        zero semantic difference, which would cause a spurious commit every
        single run forever. The fix compares parsed structural equality
        instead. This test's own _write() helper already uses compact
        json.dumps(data) with no indent, deliberately mismatched from
        run_auto_apply()'s indent=2 -- if the comparison ever regresses back
        to a raw byte compare, this test starts failing again."""
        entry = _schema_valid_entry(published=True)
        entry["verification"]["consecutive_version_checks_agreeing"] = 0
        entry["verification"]["consecutive_checks_absent"] = 0
        data = {"cells": {"python": entry}}
        data_path = tmp_path / "package_registry.json"
        data_path.write_text(json.dumps(data), encoding="utf-8")  # compact, no indent -- deliberate
        sut.configure(data_path=data_path)
        original_bytes = data_path.read_text(encoding="utf-8")
        result = CheckResult(published=True, ambiguous=False, evidence_url="u", method="m")
        outcome = sut.run_auto_apply(adapters={"pypi": _fake_adapter(result)}, scan_fn=lambda: {"excluded_but_still_live": []})
        assert outcome["wrote_changes"] is False
        assert data_path.read_text(encoding="utf-8") == original_bytes

    def test_cli_auto_apply_still_reports_uncorroborated_via_issue_body(self, tmp_path, capsys):
        entry = {
            "registry_type": "pypi",
            "candidate": {"name": "aspose-note"},
            "candidate_owner": "asposefoss",
            "verification": {
                "published": False, "consecutive_checks_agreeing": 1,
                "verified_at": None, "verified_owner": None, "evidence_url": None, "method": None,
            },
            "owner_match": None,
        }
        data = {"note": {"python": entry}}
        self._write(tmp_path, data)
        result = CheckResult(published=True, ambiguous=False, evidence_url="https://pypi.org/x",
                              method="pypi-json-api", project_url="https://unrelated.example/")
        exit_code = sut.main(["--auto-apply"], adapters={"pypi": _fake_adapter(result)},
                              scan_fn=lambda: {"excluded_but_still_live": []})
        assert exit_code == 1
        out = capsys.readouterr().out
        assert "Package Identity Needs Manual Review" in out


class _CountingAdapter:
    """Adapter fake that records every check_published call and replays a
    scripted sequence of results (last result repeats). Lets a test prove how
    many times a run sampled the network and WHICH sample each check saw."""

    def __init__(self, *results: CheckResult):
        self._results = list(results)
        self.calls = 0

    def check_published(self, candidate):
        result = self._results[min(self.calls, len(self._results) - 1)]
        self.calls += 1
        return result


class TestSingleObservationPerRun:
    """A run must take ONE observation of each package and evaluate every
    check direction (publish, version-update, drift) against that same
    observation. Before this, check_published_entries_for_version_update and
    check_published_entries_for_drift each called adapter.check_published for
    the same published entry, so one run took two independent samples: a
    flapping registry could advance the version counter from one sample and the
    absence counter from the other within the SAME run, and every published
    entry cost two network round trips per run instead of one."""

    def _write(self, tmp_path, data):
        data_path = tmp_path / "package_registry.json"
        data_path.write_text(json.dumps(data), encoding="utf-8")
        sut.configure(data_path=data_path)
        return data_path

    def test_run_watch_samples_each_published_entry_once(self, tmp_path):
        self._write(tmp_path, {"cells": {"python": _schema_valid_published_entry()}})
        live = CheckResult(published=True, ambiguous=False, evidence_url="u", method="m", version="26.9.0")
        adapter = _CountingAdapter(live)
        sut.run_watch(adapters={"pypi": adapter})
        assert adapter.calls == 1

    def test_version_and_drift_checks_share_one_observation(self, tmp_path):
        """First sample says absent (404), any later sample would say published
        with a new version. Under the old double-sampling the version check saw
        the 404 while the drift check saw the later sample, so the two counters
        described two different realities. One observation => both derive from
        the 404: the absence counter advances, the version counter does not."""
        self._write(tmp_path, {"cells": {"python": _schema_valid_published_entry()}})
        absent = CheckResult(published=False, ambiguous=False, evidence_url="u", method="m")
        later = CheckResult(published=True, ambiguous=False, evidence_url="u", method="m", version="99.0.0")
        adapter = _CountingAdapter(absent, later)
        _, _, version_proposals, _, data = sut.run_watch(adapters={"pypi": adapter})
        verification = data["cells"]["python"]["verification"]
        assert adapter.calls == 1
        assert verification["consecutive_checks_absent"] == 1
        assert verification.get("consecutive_version_checks_agreeing", 0) == 0
        assert version_proposals == []

    def test_run_auto_apply_samples_each_published_entry_once(self, tmp_path):
        self._write(tmp_path, {"cells": {"python": _schema_valid_published_entry()}})
        live = CheckResult(published=True, ambiguous=False, evidence_url="u", method="m", version="26.9.0")
        adapter = _CountingAdapter(live)
        sut.run_auto_apply(adapters={"pypi": adapter}, scan_fn=lambda: {"excluded_but_still_live": []})
        assert adapter.calls == 1

    def test_observation_is_not_shared_across_runs(self, tmp_path):
        """The snapshot is per RUN, never per process: a second run must sample
        again, otherwise the debounce (which is defined over separate runs)
        could never observe a change."""
        self._write(tmp_path, {"cells": {"python": _schema_valid_published_entry()}})
        live = CheckResult(published=True, ambiguous=False, evidence_url="u", method="m", version="26.9.0")
        adapter = _CountingAdapter(live)
        sut.run_watch(adapters={"pypi": adapter})
        sut.run_watch(adapters={"pypi": adapter})
        assert adapter.calls == 2


class _NameKeyedAdapter:
    """Adapter fake keyed by candidate name. Unknown names resolve to a definitive
    'not published' (a real 404), matching a real registry."""

    def __init__(self, live: "dict[str, CheckResult]"):
        self._live = live
        self.probed: list[str] = []

    def check_published(self, candidate, **_kw):
        name = candidate.get("name") or candidate.get("module_path")
        self.probed.append(name)
        return self._live.get(
            name, CheckResult(published=False, ambiguous=False, evidence_url=f"u/{name}", method="fake"))


class _SearchableAdapter(_NameKeyedAdapter):
    def __init__(self, live, search_results):
        super().__init__(live)
        self._search_results = search_results
        self.search_calls: list[str] = []

    def search(self, family, **_kw):
        self.search_calls.append(family)
        return list(self._search_results)


def _live(name, **kw):
    return CheckResult(published=True, ambiguous=False, evidence_url=f"https://reg/{name}", method="fake",
                       candidate_name=name, **kw)


def _cpp_entry(stored="aspose_slides_foss", counter=0):
    return {
        "registry_type": "nuget",
        "candidate": {"name": stored} if stored else {},
        "verification": {"published": False, "consecutive_checks_agreeing": counter},
    }


class TestIdentityReResolution:
    """slides/cpp regression (proven 2026-09-18): NuGet `Aspose.Slides.Cpp.FOSS`
    26.9.0 went live 2026-09-14 while the registry watched only the frozen
    backfill-time guess `aspose_slides_foss`. Backfill had tried the right name
    on 2026-08-01 (nothing existed yet), then froze the wrong one; the watcher
    only ever re-probed that frozen name, so the package could never be
    detected however long anyone waited."""

    def test_finds_live_package_under_naming_convention_when_frozen_name_is_absent(self):
        adapter = _NameKeyedAdapter({"Aspose.Slides.Cpp.FOSS": _live("Aspose.Slides.Cpp.FOSS", version="26.9.0")})
        data = {"slides": {"cpp": _cpp_entry(counter=1)}}
        proposals, uncorroborated = sut.check_unpublished_entries(data, adapters={"nuget": adapter})
        assert uncorroborated == []
        assert len(proposals) == 1
        proposal = proposals[0]
        assert proposal["candidate"] == {"name": "Aspose.Slides.Cpp.FOSS"}
        assert proposal["identity_basis"] == "foss-convention-match"
        assert adapter.probed[0] == "aspose_slides_foss"  # stored identity is always checked first

    def test_first_sighting_under_new_identity_only_advances_counter(self):
        adapter = _NameKeyedAdapter({"Aspose.Slides.Cpp.FOSS": _live("Aspose.Slides.Cpp.FOSS")})
        data = {"slides": {"cpp": _cpp_entry(counter=0)}}
        proposals, _ = sut.check_unpublished_entries(data, adapters={"nuget": adapter})
        assert proposals == []
        assert data["slides"]["cpp"]["verification"]["consecutive_checks_agreeing"] == 1
        # detection never mutates identity or publish state; only apply_proposal does
        assert data["slides"]["cpp"]["candidate"] == {"name": "aspose_slides_foss"}
        assert data["slides"]["cpp"]["verification"]["published"] is False

    def test_nothing_found_anywhere_resets_counter_exactly_as_before(self):
        adapter = _NameKeyedAdapter({})
        data = {"slides": {"cpp": _cpp_entry(counter=1)}}
        proposals, uncorroborated = sut.check_unpublished_entries(data, adapters={"nuget": adapter})
        assert proposals == [] and uncorroborated == []
        assert data["slides"]["cpp"]["verification"]["consecutive_checks_agreeing"] == 0

    def test_ambiguous_alternate_probe_holds_counter_instead_of_resetting(self):
        """The stored name is a definitive 404 but the convention probe timed out.
        We cannot tell whether the package exists, so restarting the debounce
        would punish a real publish for a network stall -- hold, like every other
        ambiguous result in this module."""
        ambiguous = CheckResult(published=False, ambiguous=True, evidence_url="u", method="fake")
        adapter = _NameKeyedAdapter({"Aspose.Slides.Cpp.FOSS": ambiguous})
        data = {"slides": {"cpp": _cpp_entry(counter=1)}}
        sut.check_unpublished_entries(data, adapters={"nuget": adapter})
        assert data["slides"]["cpp"]["verification"]["consecutive_checks_agreeing"] == 1

    def test_stored_name_hit_is_unchanged_and_does_not_search(self):
        adapter = _SearchableAdapter({"aspose_slides_foss": _live("aspose_slides_foss")}, [])
        data = {"slides": {"cpp": _cpp_entry(counter=1)}}
        proposals, _ = sut.check_unpublished_entries(data, adapters={"nuget": adapter})
        assert proposals[0]["candidate"] == {"name": "aspose_slides_foss"}
        assert adapter.search_calls == []
        assert adapter.probed == ["aspose_slides_foss"]

    def test_empty_candidate_is_resolved_instead_of_skipped_forever(self):
        """Backfill can record an empty {} candidate (no manifest name, no
        convention). The watcher used to `continue` past those permanently."""
        adapter = _NameKeyedAdapter({"Aspose.Slides.Cpp.FOSS": _live("Aspose.Slides.Cpp.FOSS")})
        data = {"slides": {"cpp": _cpp_entry(stored=None, counter=1)}}
        proposals, _ = sut.check_unpublished_entries(data, adapters={"nuget": adapter})
        assert [p["candidate"] for p in proposals] == [{"name": "Aspose.Slides.Cpp.FOSS"}]

    def test_search_hit_without_foss_in_name_needs_project_url_corroboration(self):
        good = _live("aspose-note", project_url="https://github.com/aspose-note-foss/Aspose.Note-FOSS-for-Python")
        adapter = _SearchableAdapter({}, [good])
        data = {"note": {"python": {
            "registry_type": "pypi", "candidate": {"name": "aspose-note-foss"},
            "verification": {"published": False, "consecutive_checks_agreeing": 1}}}}
        # the family's FOSS org (corroboration target) comes from products.json
        sut.PRODUCTS_PATH.write_text(json.dumps([{
            "family": "note", "platform": "python",
            "repo_url": "https://github.com/aspose-note-foss/Aspose.Note-FOSS-for-Python"}]), encoding="utf-8")
        proposals, _ = sut.check_unpublished_entries(data, adapters={"pypi": adapter})
        assert [p["candidate"] for p in proposals] == [{"name": "aspose-note"}]
        assert proposals[0]["identity_basis"] == "corroborated-non-convention-match"

    def test_unrelated_commercial_package_from_search_is_ignored(self):
        """PyPI `aspose-page` is a genuinely unrelated commercial package. It has no
        'foss' in its name and its project_url is not the FOSS org -- it must never
        be adopted, no matter how many times it is seen."""
        commercial = _live("aspose-page", project_url="https://products.aspose.com/page/python-net/")
        adapter = _SearchableAdapter({}, [commercial])
        data = {"page": {"python": {
            "registry_type": "pypi", "candidate": {"name": "aspose-page-foss"},
            "verification": {"published": False, "consecutive_checks_agreeing": 1}}}}
        sut.PRODUCTS_PATH.write_text(json.dumps([{
            "family": "page", "platform": "python",
            "repo_url": "https://github.com/aspose-page-foss/Aspose.Page-FOSS-for-Python"}]), encoding="utf-8")
        proposals, uncorroborated = sut.check_unpublished_entries(data, adapters={"pypi": adapter})
        assert proposals == [] and uncorroborated == []
        assert data["page"]["python"]["verification"]["consecutive_checks_agreeing"] == 0

    def test_net_entry_never_adopts_a_cpp_package(self):
        adapter = _SearchableAdapter({}, [_live("Aspose.Slides.Cpp.FOSS")])
        data = {"slides": {"net": {
            "registry_type": "nuget", "candidate": {"name": "Aspose.Slides.Nope"},
            "verification": {"published": False, "consecutive_checks_agreeing": 1}}}}
        proposals, _ = sut.check_unpublished_entries(data, adapters={"nuget": adapter})
        assert proposals == []

    def test_search_is_sampled_once_per_family_per_run(self):
        """net and cpp share a NuGet family search; unpublished entries must not
        multiply the request count."""
        adapter = _SearchableAdapter({}, [])
        data = {"slides": {"net": _cpp_entry("Aspose.Slides.Nope"), "cpp": _cpp_entry("aspose_slides_x")}}
        sut.check_unpublished_entries(data, adapters=sut._once_per_run({"nuget": adapter}))
        assert adapter.search_calls == ["slides"]

    def test_apply_proposal_records_new_identity_and_basis(self):
        entry = _cpp_entry(counter=1)
        entry.update({"candidate_owner": "asposefoss", "owner_match": None})
        data = {"slides": {"cpp": entry}}
        proposal = {
            "family": "slides", "platform": "cpp", "registry_type": "nuget",
            "candidate": {"name": "Aspose.Slides.Cpp.FOSS"}, "evidence_url": "https://reg/x",
            "method": "nuget-flatcontainer-api", "verified_owner": None, "identity_basis": "foss-convention-match",
            "content_healing_needed": False,
        }
        sut.apply_proposal(data, proposal, checked_at="2026-09-18")
        assert data["slides"]["cpp"]["candidate"] == {"name": "Aspose.Slides.Cpp.FOSS"}
        assert data["slides"]["cpp"]["verification"]["identity_basis"] == "foss-convention-match"
        assert data["slides"]["cpp"]["verification"]["published"] is True


class TestAdapterExceptionIsolation:
    """One entry whose adapter raises (e.g. UnicodeDecodeError on a malformed
    body, which the adapters do not catch) must not abort the run: previously it
    killed every other package's check and exited 1 exactly like a findings run."""

    class _Boom:
        @staticmethod
        def check_published(candidate, **_kw):
            raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")

    def test_failing_entry_is_ambiguous_and_others_still_checked(self):
        good = _live("aspose-good-foss")
        data = {
            "cells": {"python": {"registry_type": "npm", "candidate": {"name": "excel-cells"},
                                   "verification": {"published": False, "consecutive_checks_agreeing": 1}}},
            "pdf": {"python": {"registry_type": "pypi", "candidate": {"name": "aspose-good-foss"},
                                 "verification": {"published": False, "consecutive_checks_agreeing": 1}}},
        }
        adapters = sut._once_per_run({"npm": self._Boom(), "pypi": _NameKeyedAdapter({"aspose-good-foss": good})})
        proposals, _ = sut.check_unpublished_entries(data, adapters=adapters)
        assert [p["family"] for p in proposals] == ["pdf"]  # the healthy entry still produced its proposal
        # ambiguous => counter held, never reset and never advanced
        assert data["cells"]["python"]["verification"]["consecutive_checks_agreeing"] == 1
