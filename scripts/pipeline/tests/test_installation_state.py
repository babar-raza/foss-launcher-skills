"""Tests for scripts/pipeline/lib/installation_state.py (Mission
MT066-2026-09-09-PACKAGE-INSTALL-RECONCILIATION, Phase 2, plan section F).

Both functions under test are pure -- no fixtures, no I/O, no DI seam needed.
"""

import sys
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parents[1] / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import pytest  # noqa: E402

from installation_state import (  # noqa: E402
    CANDIDATE_UNCORROBORATED,
    DRIFT_SUSPECTED,
    GITHUB_ONLY,
    IDENTITY_CONFLICT,
    PACKAGE_MANAGER_VERIFIED,
    RETIRED_EXCLUDED,
    SOURCE_GITHUB,
    SOURCE_PACKAGE_MANAGER,
    SOURCE_UNCHANGED,
    UNKNOWN,
    classify_entry,
    desired_source,
)


class TestClassifyEntry:
    def test_none_entry_is_unknown(self):
        assert classify_entry(None) == UNKNOWN

    def test_empty_entry_is_unknown(self):
        assert classify_entry({}) == UNKNOWN

    def test_no_candidate_is_unknown(self):
        entry = {"verification": {"published": False}}
        assert classify_entry(entry) == UNKNOWN

    def test_candidate_but_unpublished_is_github_only(self):
        entry = {"candidate": {"name": "aspose-x-foss"}, "verification": {"published": False}}
        assert classify_entry(entry) == GITHUB_ONLY

    def test_published_is_package_manager_verified(self):
        entry = {"candidate": {"name": "aspose-x-foss"}, "verification": {"published": True}}
        assert classify_entry(entry) == PACKAGE_MANAGER_VERIFIED

    def test_published_with_drift_suspected_flag_is_drift_suspected(self):
        entry = {"candidate": {"name": "aspose-x-foss"}, "verification": {"published": True}}
        assert classify_entry(entry, drift_suspected=True) == DRIFT_SUSPECTED

    def test_conflict_present_is_identity_conflict_even_when_published(self):
        """A conflict overrides every other signal -- no shortcode should ever
        render either candidate while an unresolved conflict exists, published
        or not."""
        entry = {
            "candidate": {"name": "aspose-x"},
            "verification": {"published": True},
            "conflict": {"candidates": ["aspose-x", "aspose-x-mirror"], "note": "ambiguous"},
        }
        assert classify_entry(entry) == IDENTITY_CONFLICT

    def test_null_conflict_is_not_identity_conflict(self):
        entry = {"candidate": {"name": "aspose-x-foss"}, "verification": {"published": False}, "conflict": None}
        assert classify_entry(entry) == GITHUB_ONLY

    def test_drift_suspected_flag_ignored_when_not_published(self):
        """drift_suspected only means anything for an already-published entry."""
        entry = {"candidate": {"name": "aspose-x-foss"}, "verification": {"published": False}}
        assert classify_entry(entry, drift_suspected=True) == GITHUB_ONLY


class TestDesiredSource:
    def test_package_manager_verified_maps_to_package_manager(self):
        assert desired_source(PACKAGE_MANAGER_VERIFIED) == SOURCE_PACKAGE_MANAGER

    def test_github_only_maps_to_github(self):
        assert desired_source(GITHUB_ONLY) == SOURCE_GITHUB

    def test_candidate_uncorroborated_maps_to_github_same_as_github_only(self):
        """Plan section F: CANDIDATE_UNCORROBORATED is 'treated identically to
        GITHUB_ONLY for content purposes' -- same desired source."""
        assert desired_source(CANDIDATE_UNCORROBORATED) == SOURCE_GITHUB

    def test_drift_suspected_maps_to_unchanged(self):
        """Never auto-change content on a single/debounced drift signal alone --
        content stays as-is pending human resolution."""
        assert desired_source(DRIFT_SUSPECTED) == SOURCE_UNCHANGED

    def test_identity_conflict_maps_to_unchanged(self):
        assert desired_source(IDENTITY_CONFLICT) == SOURCE_UNCHANGED

    def test_retired_excluded_maps_to_unchanged(self):
        assert desired_source(RETIRED_EXCLUDED) == SOURCE_UNCHANGED

    def test_unknown_maps_to_unchanged(self):
        assert desired_source(UNKNOWN) == SOURCE_UNCHANGED

    def test_unrecognized_state_raises(self):
        with pytest.raises(ValueError):
            desired_source("NOT_A_REAL_STATE")


def test_classify_then_desired_source_round_trip_for_a_freshly_published_entry():
    """Integration-style sanity check: a freshly-flipped entry (no drift
    signal yet) should resolve all the way to package_manager."""
    entry = {"candidate": {"name": "aspose-pdf-foss"}, "verification": {"published": True}}
    assert desired_source(classify_entry(entry)) == SOURCE_PACKAGE_MANAGER
