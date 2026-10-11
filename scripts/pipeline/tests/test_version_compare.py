"""Exhaustive fixture tests for scripts/pipeline/lib/version_compare.py (MT075-T1).

Each fixture cites where its expected ordering comes from (PEP 440, the
semver.org 2.0.0 spec's own example chain, NuGet's documented SemVer2+4-part
scheme, or Maven's ComparableVersion qualifier table) rather than asserting
an ordering invented for this test.
"""

import pytest

from lib import version_compare as vc


# ---------------------------------------------------------------------------
# pypi (PEP 440)
# ---------------------------------------------------------------------------

class TestPypi:
    def test_trailing_zero_equal(self):
        # PEP 440: "26.3" normalizes the same as "26.3.0".
        assert vc.compare_pypi("26.3", "26.3.0") == 0

    def test_patch_bump_is_newer(self):
        assert vc.compare_pypi("26.3.1", "26.3.0") == 1
        assert vc.compare_pypi("26.3.0", "26.3.1") == -1

    def test_prerelease_chain(self):
        # PEP 440 example ordering: dev < a < b < rc < final
        chain = ["1.0.dev1", "1.0a1", "1.0b1", "1.0rc1", "1.0"]
        for lo, hi in zip(chain, chain[1:]):
            assert vc.compare_pypi(lo, hi) == -1, f"{lo} should be < {hi}"
            assert vc.compare_pypi(hi, lo) == 1

    def test_is_prerelease(self):
        assert vc.is_prerelease_pypi("1.0rc1") is True
        assert vc.is_prerelease_pypi("1.0") is False

    def test_invalid_raises(self):
        with pytest.raises(vc.VersionParseError):
            vc.compare_pypi("not-a-version", "1.0")


# ---------------------------------------------------------------------------
# nuget (SemVer2 + legacy 4-part)
# ---------------------------------------------------------------------------

class TestNuGet:
    def test_missing_fourth_part_defaults_zero(self):
        assert vc.compare_nuget("1.0.0.0", "1.0.0") == 0

    def test_major_minor_ordering_not_lexical(self):
        # A pure-lexical bug would say "2.0.0" < "1.9.9.9" (wrong); numeric
        # per-component comparison must get this right.
        assert vc.compare_nuget("2.0.0", "1.9.9.9") == 1

    def test_release_outranks_prerelease(self):
        assert vc.compare_nuget("1.0.0-alpha", "1.0.0") == -1

    def test_prerelease_numeric_label_ordering(self):
        assert vc.compare_nuget("1.0.0-alpha.1", "1.0.0-alpha.2") == -1
        assert vc.compare_nuget("1.0.0-alpha.2", "1.0.0-beta") == -1

    def test_is_prerelease(self):
        assert vc.is_prerelease_nuget("1.0.0-alpha") is True
        assert vc.is_prerelease_nuget("1.0.0") is False

    def test_invalid_raises(self):
        with pytest.raises(vc.VersionParseError):
            vc.compare_nuget("not.a.version", "1.0.0")

    def test_prerelease_labels_compare_case_insensitively(self):
        """Independent review (2026-09-28): NuGet compares prerelease labels
        case-insensitively; the original code sorted '1.0.0-Beta' below
        '1.0.0-alpha' purely from ASCII case ('B' < 'a')."""
        assert vc.compare_nuget("1.0.0-Beta", "1.0.0-alpha") == 1
        assert vc.compare_nuget("1.0.0-ALPHA", "1.0.0-alpha") == 0


# ---------------------------------------------------------------------------
# npm / cargo (strict semver core) -- semver.org 2.0.0 spec's own precedence
# example, verbatim: 1.0.0-alpha < 1.0.0-alpha.1 < 1.0.0-alpha.beta <
# 1.0.0-beta < 1.0.0-beta.2 < 1.0.0-beta.11 < 1.0.0-rc.1 < 1.0.0
# ---------------------------------------------------------------------------

_SEMVER_SPEC_CHAIN = [
    "1.0.0-alpha",
    "1.0.0-alpha.1",
    "1.0.0-alpha.beta",
    "1.0.0-beta",
    "1.0.0-beta.2",
    "1.0.0-beta.11",
    "1.0.0-rc.1",
    "1.0.0",
]


class TestNpmCargoSemverSpecChain:
    @pytest.mark.parametrize("compare_fn", [vc.compare_npm, vc.compare_cargo])
    def test_spec_chain_strictly_increasing(self, compare_fn):
        for lo, hi in zip(_SEMVER_SPEC_CHAIN, _SEMVER_SPEC_CHAIN[1:]):
            assert compare_fn(lo, hi) == -1, f"{lo} should be < {hi}"
            assert compare_fn(hi, lo) == 1

    def test_npm_v_prefix_rejected(self):
        # npm/cargo registries do not use a leading 'v' -- go_modules does.
        with pytest.raises(vc.VersionParseError):
            vc.compare_npm("v1.0.0", "1.0.0")

    def test_build_metadata_ignored(self):
        assert vc.compare_npm("1.0.0+build1", "1.0.0+build2") == 0

    def test_is_prerelease(self):
        assert vc.is_prerelease_npm("1.0.0-alpha") is True
        assert vc.is_prerelease_cargo("1.0.0") is False


# ---------------------------------------------------------------------------
# go_modules (semver core, mandatory 'v' prefix)
# ---------------------------------------------------------------------------

class TestGoModules:
    def test_v_prefix_required(self):
        assert vc.compare_go("v0.10.0", "v0.9.0") == 1
        with pytest.raises(vc.VersionParseError):
            vc.compare_go("0.9.0", "v0.9.0")

    def test_double_digit_minor_not_lexical(self):
        # A naive string comparison would rank "v0.9.0" > "v0.10.0"; numeric
        # component comparison must not make that mistake.
        assert vc.compare_go("v0.9.0", "v0.10.0") == -1

    def test_prerelease(self):
        assert vc.compare_go("v1.0.0-beta", "v1.0.0") == -1
        assert vc.is_prerelease_go("v1.0.0-beta") is True


# ---------------------------------------------------------------------------
# maven (common-case ComparableVersion subset)
# ---------------------------------------------------------------------------

class TestMaven:
    def test_trailing_zero_component_equal(self):
        assert vc.compare_maven("1.0", "1.0.0") == 0

    def test_real_registry_bump(self):
        # The real cells/java incident this mission's plan cites: 26.5.0 -> 26.7.0.
        assert vc.compare_maven("26.7.0", "26.5.0") == 1

    def test_qualifier_precedence_chain(self):
        # Maven's own documented QUALIFIERS order.
        chain = ["1.0-alpha", "1.0-beta", "1.0-milestone", "1.0-rc", "1.0-snapshot", "1.0", "1.0-sp"]
        for lo, hi in zip(chain, chain[1:]):
            assert vc.compare_maven(lo, hi) == -1, f"{lo} should be < {hi}"
            assert vc.compare_maven(hi, lo) == 1

    def test_ga_and_final_alias_release(self):
        assert vc.compare_maven("1.0-ga", "1.0") == 0
        assert vc.compare_maven("1.0-final", "1.0") == 0

    def test_same_qualifier_numbered_ordering(self):
        assert vc.compare_maven("1.0-rc1", "1.0-rc2") == -1

    def test_is_prerelease(self):
        assert vc.is_prerelease_maven("1.0-alpha") is True
        assert vc.is_prerelease_maven("1.0-sp") is False
        assert vc.is_prerelease_maven("1.0") is False

    def test_unsupported_shape_raises_not_guesses(self):
        with pytest.raises(vc.VersionParseError):
            vc.compare_maven("1.0-weirdqualifier", "1.0")

    def test_cr_and_rc_are_equivalent_ranks(self):
        """Independent review (2026-09-28): Maven's real ComparableVersion
        treats 'cr' and 'rc' as ALIASES (same rank), not a strict rc<cr
        ordering -- the original tuple-index version ranked cr above rc,
        reproduced live as '1.0-cr1' outranking '1.0-rc2'."""
        assert vc.compare_maven("1.0-cr1", "1.0-rc1") == 0
        assert vc.compare_maven("1.0-rc2", "1.0-cr1") == 1  # same rank, numbered comparison applies


# ---------------------------------------------------------------------------
# Unified dispatch (compare / is_newer / is_prerelease)
# ---------------------------------------------------------------------------

class TestUnifiedDispatch:
    @pytest.mark.parametrize(
        "registry_type,lo,hi",
        [
            ("pypi", "1.0", "1.0.1"),
            ("nuget", "1.0.0", "1.0.1"),
            ("npm", "1.0.0", "1.0.1"),
            ("go_modules", "v1.0.0", "v1.0.1"),
            ("cargo", "1.0.0", "1.0.1"),
            ("maven", "1.0.0", "1.0.1"),
        ],
    )
    def test_compare_dispatches_per_registry(self, registry_type, lo, hi):
        assert vc.compare(registry_type, lo, hi) == -1
        assert vc.compare(registry_type, hi, lo) == 1

    def test_is_newer_true_for_actual_bump(self):
        assert vc.is_newer("maven", "26.5.0", "26.7.0") is True

    def test_is_newer_false_for_same_or_older(self):
        assert vc.is_newer("maven", "26.7.0", "26.7.0") is False
        assert vc.is_newer("maven", "26.7.0", "26.5.0") is False

    def test_is_newer_none_current_always_newer(self):
        # No confirmed version yet -- nothing to be "newer than".
        assert vc.is_newer("pypi", None, "1.0.0") is True

    def test_unknown_registry_type_raises_keyerror(self):
        with pytest.raises(KeyError):
            vc.compare("not_a_real_registry", "1.0.0", "1.0.1")

    def test_is_prerelease_dispatches(self):
        assert vc.is_prerelease("pypi", "1.0rc1") is True
        assert vc.is_prerelease("maven", "1.0") is False
