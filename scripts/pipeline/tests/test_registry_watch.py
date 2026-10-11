"""Tests for scripts/pipeline/commands/ops/registry_watch.py (MT075-T6,
plan Revision 2 SR2.5) -- the unified watcher consolidating
package_publish_watch.py + publish_watcher.py into one 6-registry loop
gated by check_registry_merge_safety (MT075-T5).
"""

import json
import sys
from pathlib import Path

import pytest

_PIPELINE_ROOT = Path(__file__).resolve().parent.parent
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

import commands.ops.registry_watch as sut  # noqa: E402
from package_registries import CheckResult  # noqa: E402
from seo.pipeline import change_budget  # noqa: E402


@pytest.fixture(autouse=True)
def isolate(tmp_path):
    sut.configure(data_path=tmp_path / "package_registry.json")
    # MT075-T9: run_auto_apply()'s default record_apply writes into
    # change_budget's rolling history (reports/seo/change_budget_history.json)
    # -- without this, every test run of TestRunAutoApply (which doesn't
    # override record_apply) silently pollutes the REAL, local, gitignored
    # history file with family="words" entries. Caught live this session:
    # 4 real test runs had already written into it before this fix landed.
    change_budget.configure(repo_root=tmp_path)
    yield
    sut.configure(data_path=None)
    change_budget.configure(repo_root=None)


def _entry(*, registry_type="pypi", name="aspose-words-foss", version="26.5.0", published=True) -> dict:
    return {
        "registry_type": registry_type,
        "candidate": {"name": name, "version": version},
        "candidate_owner": "asposefoss",
        "verification": {
            "published": published, "verified_at": "2026-09-01", "verified_owner": None,
            "evidence_url": "https://pypi.org/project/aspose-words-foss/", "method": "pypi-poll",
        },
        "owner_match": None,
    }


def _fake_adapter(result: "CheckResult | None"):
    class _Adapter:
        @staticmethod
        def check_published(candidate, *, fetch=None):
            return result
    return _Adapter


class TestObserveEntry:
    def test_dispatches_to_the_right_adapter(self):
        called = {}

        class _Adapter:
            @staticmethod
            def check_published(candidate, *, fetch=None):
                called["candidate"] = candidate
                return CheckResult(published=True, ambiguous=False, evidence_url="u", method="m")

        result = sut.observe_entry("pypi", {"name": "aspose-words-foss"}, adapters={"pypi": _Adapter}, fetch=None)
        assert result.published is True
        assert called["candidate"] == {"name": "aspose-words-foss"}

    def test_unknown_registry_type_returns_none(self):
        assert sut.observe_entry("not_a_registry", {}, adapters={}) is None


class TestBuildCandidateEntry:
    def test_preserves_untouched_fields(self):
        base = _entry(published=True, version="26.5.0")
        base["content_healing_status"] = "not_needed"
        result = CheckResult(published=True, ambiguous=False, evidence_url="u2", method="m2", version="26.6.0")
        candidate = sut.build_candidate_entry(base, result, recorded_at="2026-09-28T00:00:00Z")
        assert candidate["content_healing_status"] == "not_needed"
        assert candidate["candidate_owner"] == "asposefoss"

    def test_updates_version_and_verification(self):
        base = _entry(published=False, version=None)
        result = CheckResult(
            published=True, ambiguous=False, evidence_url="https://pypi.org/x", method="pypi-poll",
            version="26.5.0", verified_owner="Aspose",
        )
        candidate = sut.build_candidate_entry(base, result, recorded_at="2026-09-28T00:00:00Z")
        assert candidate["candidate"]["version"] == "26.5.0"
        assert candidate["verification"]["published"] is True
        assert candidate["verification"]["verified_owner"] == "Aspose"
        assert candidate["verification"]["verified_at"] == "2026-09-28T00:00:00Z"

    def test_stale_version_is_not_leaked_through_even_when_published_true(self):
        """Independent review (2026-09-28): the original fix only nulled the
        version when `result.published` was False. An adapter can report
        published=True with version=None (NuGet's flatcontainer versions
        list empty/unparseable, Go's @latest failing after @v/list
        succeeds, PyPI missing info.version) -- that case still leaked the
        stale base version through unfixed."""
        base = _entry(published=True, version="26.7.0")
        result = CheckResult(published=True, ambiguous=False, evidence_url="u", method="m", version=None)
        candidate = sut.build_candidate_entry(base, result, recorded_at="x")
        assert candidate["candidate"]["version"] is None

    def test_go_modules_candidate_name_is_never_injected(self):
        """Independent review (2026-09-28): go_modules entries identify by
        module_path, not name -- injecting a `name` key (as the pypi/nuget/
        npm/cargo branch does) corrupted _candidate_identity_key's
        classification, turning an unchanged version-bump observation into a
        spurious TIER_2_IDENTITY_CHANGE on every single run. Reproduced live
        against both real go_modules entries in data/package_registry.json."""
        base = {
            "registry_type": "go_modules",
            "candidate": {"module_path": "github.com/aspose-pdf-foss/aspose-pdf-foss-for-go", "version": "v0.9.0"},
            "candidate_owner": "asposefoss",
            "verification": {"published": True, "verified_at": "d", "verified_owner": None,
                              "evidence_url": "u", "method": "m"},
            "owner_match": None,
        }
        result = CheckResult(published=True, ambiguous=False, evidence_url="u2", method="m2",
                              version="v0.9.1", candidate_name="github.com/aspose-pdf-foss/aspose-pdf-foss-for-go")
        candidate = sut.build_candidate_entry(base, result, recorded_at="x")
        assert "name" not in candidate["candidate"]

    def test_stale_owner_and_project_url_not_carried_into_a_first_publish(self):
        """Independent review (2026-09-28): verified_owner/project_url fell
        back to the base's stale value whenever this run's result didn't
        report one -- for a previously-unpublished entry that's a false
        provenance claim ("verified" by an owner this run never saw)."""
        base = _entry(published=False, version=None)
        base["verification"]["verified_owner"] = "some-stale-owner-from-a-manual-edit"
        result = CheckResult(published=True, ambiguous=False, evidence_url="u", method="m", version="26.5.0")
        candidate = sut.build_candidate_entry(base, result, recorded_at="x")
        assert candidate["verification"]["verified_owner"] is None

    def test_stale_version_is_not_leaked_through_when_still_unpublished(self):
        """Live-data proof run (2026-09-28) caught this for real: cells/rust
        carried an old placeholder version from before it was ever checked
        live; crates.io returned a definitive 'still not published' (no
        version). The candidate's version field must be cleared, not left
        equal to the stale base value -- otherwise a downstream corroboration
        check can mistake the old placeholder for genuine new-publish
        evidence (it can real-world corroborate, since that version really
        is tagged in the product's repo -- it just was never actually
        published to the registry)."""
        base = _entry(published=False, version="26.7.0")
        result = CheckResult(published=False, ambiguous=False, evidence_url="u", method="m", version=None)
        candidate = sut.build_candidate_entry(base, result, recorded_at="x")
        assert candidate["candidate"]["version"] is None

    def test_does_not_mutate_the_base_entry(self):
        """Deep-copy discipline -- a caller iterating the original registry
        dict must never see it silently mutated underneath it."""
        base = _entry(published=True, version="26.5.0")
        result = CheckResult(published=True, ambiguous=False, evidence_url="u", method="m", version="26.6.0")
        sut.build_candidate_entry(base, result, recorded_at="x")
        assert base["candidate"]["version"] == "26.5.0"


class TestRunWatch:
    def test_clean_version_bump_is_applied_and_merged_into_updated_registry(self):
        data = {"words": {"python": _entry(published=True, version="26.5.0")}}
        result_obj = CheckResult(published=True, ambiguous=False, evidence_url="u", method="pypi-poll", version="26.6.0")
        result = sut.run_watch(data, adapters={"pypi": _fake_adapter(result_obj)})
        assert len(result["applied"]) == 1
        assert result["updated_registry"]["words"]["python"]["candidate"]["version"] == "26.6.0"
        # Original input dict must be untouched (pure function).
        assert data["words"]["python"]["candidate"]["version"] == "26.5.0"

    def test_ambiguous_observation_is_skipped_not_applied(self):
        data = {"words": {"python": _entry(published=True, version="26.5.0")}}
        result_obj = CheckResult(published=False, ambiguous=True, evidence_url="u", method="pypi-poll")
        result = sut.run_watch(data, adapters={"pypi": _fake_adapter(result_obj)})
        assert result["applied"] == []
        assert len(result["ambiguous"]) == 1
        assert result["updated_registry"]["words"]["python"]["candidate"]["version"] == "26.5.0"

    def test_uncorroborated_first_publish_is_held_not_written(self):
        data = {"words": {"python": _entry(published=False, version=None)}}
        result_obj = CheckResult(published=True, ambiguous=False, evidence_url="u", method="pypi-poll", version="26.5.0")
        result = sut.run_watch(
            data, adapters={"pypi": _fake_adapter(result_obj)},
            corroboration_check=lambda f, p, v: False,
        )
        assert result["applied"] == []
        assert len(result["held"]) == 1
        assert result["updated_registry"]["words"]["python"]["verification"]["published"] is False

    def test_corroborated_first_publish_is_applied(self):
        data = {"words": {"python": _entry(published=False, version=None)}}
        result_obj = CheckResult(published=True, ambiguous=False, evidence_url="u", method="pypi-poll", version="26.5.0")
        result = sut.run_watch(
            data, adapters={"pypi": _fake_adapter(result_obj)},
            corroboration_check=lambda f, p, v: True,
        )
        assert len(result["applied"]) == 1
        assert result["updated_registry"]["words"]["python"]["verification"]["published"] is True

    def test_downgrade_is_rejected_not_applied(self):
        data = {"words": {"python": _entry(published=True, version="26.6.0")}}
        result_obj = CheckResult(published=True, ambiguous=False, evidence_url="u", method="pypi-poll", version="26.5.0")
        result = sut.run_watch(data, adapters={"pypi": _fake_adapter(result_obj)})
        assert result["applied"] == []
        assert len(result["rejected"]) == 1

    def test_batch_cap_demotes_extra_auto_applies_to_held(self):
        data = {
            f"fam{i}": {"python": _entry(published=True, version="26.5.0")}
            for i in range(7)
        }
        result_obj = CheckResult(published=True, ambiguous=False, evidence_url="u", method="pypi-poll", version="26.6.0")
        result = sut.run_watch(data, adapters={"pypi": _fake_adapter(result_obj)})
        assert len(result["applied"]) == 5  # gate.MAX_ENTRIES_PER_BATCH
        assert len(result["held"]) == 2

    def test_all_six_registry_types_are_dispatched_uniformly(self):
        """The consolidation's core claim -- one loop, all 6 registries,
        no special-casing at the call site."""
        data = {}
        # go_modules is the one registry whose version strings require a
        # leading 'v' (proxy.golang.org convention, enforced by
        # lib.version_compare._parse_go_core) -- everything else uses a bare
        # numeric version.
        base_versions = {"go_modules": "v1.0.0"}
        bump_versions = {"go_modules": "v1.0.1"}
        for i, registry_type in enumerate(["pypi", "nuget", "npm", "go_modules", "cargo", "maven"]):
            base_version = base_versions.get(registry_type, "1.0.0")
            candidate = {"version": base_version}
            if registry_type == "maven":
                candidate = {"group_id": "org.aspose", "artifact_id": "aspose-x-foss", "version": base_version}
            elif registry_type == "go_modules":
                candidate["module_path"] = "github.com/aspose-x-foss/aspose-x-foss-for-go"
            else:
                candidate["name"] = "aspose-x-foss"
            data[f"fam{i}"] = {"plat": {
                "registry_type": registry_type, "candidate": candidate, "candidate_owner": "asposefoss",
                "verification": {"published": True, "verified_at": "d", "verified_owner": None,
                                  "evidence_url": "u", "method": "m"},
                "owner_match": None,
            }}

        def _fake_adapter_for(registry_type):
            bump = bump_versions.get(registry_type, "1.0.1")
            return _fake_adapter(CheckResult(published=True, ambiguous=False, evidence_url="u2", method="m2", version=bump))

        adapters = {rt: _fake_adapter_for(rt) for rt in
                    ["pypi", "nuget", "npm", "go_modules", "cargo", "maven"]}
        result = sut.run_watch(data, adapters=adapters)
        # 6 entries hits the 5-entry batch cap (proven separately below) --
        # what this test asserts is that all 6 were dispatched and reached a
        # real AUTO_APPLY-eligible verdict (applied or capped-to-held), never
        # an ambiguous/rejected fallthrough from a registry-type special case.
        assert len(result["applied"]) + len(result["held"]) == 6
        assert result["rejected"] == []
        assert result["ambiguous"] == []


class _NugetByName:
    """check_published() answers per package id: only ids in `live` resolve."""

    def __init__(self, live: "dict[str, str]", ambiguous: "set[str] | None" = None):
        self._live = live
        self._ambiguous = ambiguous or set()
        self.probed: list[str] = []

    def check_published(self, candidate, *, fetch=None):
        name = candidate["name"]
        self.probed.append(name)
        if name in self._ambiguous:
            return CheckResult(published=False, ambiguous=True, evidence_url="u", method="nuget-flatcontainer-api")
        if name in self._live:
            return CheckResult(
                published=True, ambiguous=False, evidence_url=f"https://api.nuget.org/{name.lower()}",
                method="nuget-flatcontainer-api", candidate_name=name, version=self._live[name],
                verified_owner="Aspose",
            )
        return CheckResult(published=False, ambiguous=False, evidence_url="u", method="nuget-flatcontainer-api")


def _cpp_entry_with_guessed_name() -> dict:
    """pdf/cpp as backfilled 2026-08-01: a CMake-style guess, not the NuGet id."""
    entry = _entry(registry_type="nuget", name="Aspose_PDF_FOSS", version=None, published=False)
    entry["verification"].update({"evidence_url": None, "method": "nuget-backfill-scan", "verified_at": "2026-08-01"})
    return entry


class TestIdentityDiscovery:
    """Regression: Aspose.PDF.Cpp.FOSS went live on NuGet 2026-09-30 while the registry
    held the backfill guess `Aspose_PDF_FOSS`. The unified watcher probed only the stored
    name, so every run reported no_change -- the same blind spot slides/cpp hit earlier."""

    def test_wrong_stored_name_is_rediscovered_and_applied(self):
        data = {"pdf": {"cpp": _cpp_entry_with_guessed_name()}}
        adapter = _NugetByName({"Aspose.PDF.Cpp.FOSS": "1.0.1"})
        result = sut.run_watch(data, adapters={"nuget": adapter}, corroboration_check=lambda f, p, v: True)
        assert [r["platform"] for r in result["applied"]] == ["cpp"]
        entry = result["updated_registry"]["pdf"]["cpp"]
        assert entry["candidate"]["name"] == "Aspose.PDF.Cpp.FOSS"
        assert entry["candidate"]["version"] == "1.0.1"
        assert entry["verification"]["published"] is True
        assert entry["verification"]["identity_basis"] == "foss-convention-match"
        assert adapter.probed[0] == "Aspose_PDF_FOSS"  # the stored name is always tried first

    def test_discovered_identity_is_still_gated_not_trusted(self):
        data = {"pdf": {"cpp": _cpp_entry_with_guessed_name()}}
        adapter = _NugetByName({"Aspose.PDF.Cpp.FOSS": "1.0.1"})
        result = sut.run_watch(data, adapters={"nuget": adapter}, corroboration_check=lambda f, p, v: False)
        assert result["applied"] == []
        assert len(result["held"]) == 1
        assert result["updated_registry"]["pdf"]["cpp"]["verification"]["published"] is False
        assert result["updated_registry"]["pdf"]["cpp"]["candidate"]["name"] == "Aspose_PDF_FOSS"

    def test_package_absent_under_every_name_is_not_a_change(self):
        data = {"pdf": {"cpp": _cpp_entry_with_guessed_name()}}
        result = sut.run_watch(data, adapters={"nuget": _NugetByName({})}, corroboration_check=lambda f, p, v: True)
        assert result["applied"] == [] and result["held"] == [] and result["rejected"] == []
        assert len(result["no_change"]) == 1

    def test_ambiguous_discovery_probe_is_not_reported_as_absent(self):
        data = {"pdf": {"cpp": _cpp_entry_with_guessed_name()}}
        adapter = _NugetByName({}, ambiguous={"Aspose.PDF.Cpp.FOSS"})
        result = sut.run_watch(data, adapters={"nuget": adapter}, corroboration_check=lambda f, p, v: True)
        assert result["no_change"] == []
        assert len(result["ambiguous"]) == 1

    def test_published_entries_are_never_re_resolved(self):
        def _boom(*args, **kwargs):
            raise AssertionError("identity resolution must only run for unpublished entries")

        data = {"pdf": {"net": _entry(registry_type="nuget", name="Aspose.PDF.FOSS", version="26.9.0", published=True)}}
        adapter = _NugetByName({"Aspose.PDF.FOSS": "26.9.0"})
        result = sut.run_watch(data, adapters={"nuget": adapter}, identity_resolver=_boom)
        assert len(result["no_change"]) == 1


class TestVelocityAndRecordApplyWiring:
    """MT075-T9 (plan Revision 2 R2.13): the cross-run velocity/anomaly
    check that replaces the bootstrap-PR human-merge step."""

    def test_run_watch_propagates_velocity_check_to_the_gate(self):
        data = {"words": {"python": _entry(published=True, version="26.5.0")}}
        result_obj = CheckResult(published=True, ambiguous=False, evidence_url="u", method="pypi-poll", version="26.6.0")
        result = sut.run_watch(
            data, adapters={"pypi": _fake_adapter(result_obj)},
            velocity_check=lambda family: (True, "synthetic block"),
        )
        assert result["applied"] == []
        assert len(result["held"]) == 1
        assert "velocity" in result["held"][0]["reason"]

    def test_run_auto_apply_records_actual_applied_count_per_family(self, tmp_path):
        data = {
            "words": {"python": _entry(published=True, version="26.5.0")},
            "cells": {"python": _entry(published=True, version="26.5.0")},
        }
        (tmp_path / "package_registry.json").write_text(json.dumps(data), encoding="utf-8")
        result_obj = CheckResult(published=True, ambiguous=False, evidence_url="u", method="pypi-poll", version="26.6.0")
        recorded = []
        result = sut.run_auto_apply(
            adapters={"pypi": _fake_adapter(result_obj)},
            record_apply=lambda family, count: recorded.append((family, count)),
        )
        assert result["wrote_changes"] is True
        assert sorted(recorded) == [("cells", 1), ("words", 1)]

    def test_no_write_means_nothing_recorded(self, tmp_path):
        data = {"words": {"python": _entry(published=True, version="26.5.0")}}
        (tmp_path / "package_registry.json").write_text(json.dumps(data), encoding="utf-8")
        result_obj = CheckResult(published=True, ambiguous=False, evidence_url="u", method="pypi-poll", version="26.5.0")  # same version
        recorded = []
        result = sut.run_auto_apply(
            adapters={"pypi": _fake_adapter(result_obj)},
            record_apply=lambda family, count: recorded.append((family, count)),
        )
        assert result["wrote_changes"] is False
        assert recorded == []

    def test_velocity_blocked_entry_is_never_recorded(self, tmp_path):
        data = {"words": {"python": _entry(published=True, version="26.5.0")}}
        (tmp_path / "package_registry.json").write_text(json.dumps(data), encoding="utf-8")
        result_obj = CheckResult(published=True, ambiguous=False, evidence_url="u", method="pypi-poll", version="26.6.0")
        recorded = []
        result = sut.run_auto_apply(
            adapters={"pypi": _fake_adapter(result_obj)},
            velocity_check=lambda family: (True, "synthetic block"),
            record_apply=lambda family, count: recorded.append((family, count)),
        )
        assert result["wrote_changes"] is False
        assert recorded == []


class TestRunAutoApply:
    def test_writes_file_atomically_when_something_applies(self, tmp_path):
        data = {"words": {"python": _entry(published=True, version="26.5.0")}}
        (tmp_path / "package_registry.json").write_text(json.dumps(data), encoding="utf-8")
        result_obj = CheckResult(published=True, ambiguous=False, evidence_url="u", method="pypi-poll", version="26.6.0")
        result = sut.run_auto_apply(adapters={"pypi": _fake_adapter(result_obj)})
        assert result["wrote_changes"] is True
        on_disk = json.loads((tmp_path / "package_registry.json").read_text(encoding="utf-8"))
        assert on_disk["words"]["python"]["candidate"]["version"] == "26.6.0"

    def test_no_write_when_nothing_applies(self, tmp_path):
        data = {"words": {"python": _entry(published=True, version="26.5.0")}}
        (tmp_path / "package_registry.json").write_text(json.dumps(data), encoding="utf-8")
        result_obj = CheckResult(published=True, ambiguous=False, evidence_url="u", method="pypi-poll", version="26.5.0")
        result = sut.run_auto_apply(adapters={"pypi": _fake_adapter(result_obj)})
        assert result["wrote_changes"] is False

    def test_idempotent_rerun_writes_nothing_the_second_time(self, tmp_path):
        """3-run idempotency proof, scoped: an unchanged live observation
        applied once must not keep re-triggering a write on subsequent runs."""
        data = {"words": {"python": _entry(published=True, version="26.5.0")}}
        (tmp_path / "package_registry.json").write_text(json.dumps(data), encoding="utf-8")
        result_obj = CheckResult(published=True, ambiguous=False, evidence_url="u", method="pypi-poll", version="26.6.0")
        adapters = {"pypi": _fake_adapter(result_obj)}
        first = sut.run_auto_apply(adapters=adapters)
        assert first["wrote_changes"] is True
        second = sut.run_auto_apply(adapters=adapters)
        assert second["wrote_changes"] is False
        third = sut.run_auto_apply(adapters=adapters)
        assert third["wrote_changes"] is False

    def test_invalid_candidate_never_gets_written(self, tmp_path):
        data = {"words": {"python": _entry(published=True, version="26.5.0")}}
        (tmp_path / "package_registry.json").write_text(json.dumps(data), encoding="utf-8")

        class _BadAdapter:
            @staticmethod
            def check_published(candidate, *, fetch=None):
                return CheckResult(published=True, ambiguous=False, evidence_url="u", method="m", version="not-a-version!!")

        result = sut.run_auto_apply(adapters={"pypi": _BadAdapter})
        assert result["wrote_changes"] is False
        on_disk = json.loads((tmp_path / "package_registry.json").read_text(encoding="utf-8"))
        assert on_disk["words"]["python"]["candidate"]["version"] == "26.5.0"
