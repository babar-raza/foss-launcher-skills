"""Tests for scripts/pipeline/commands/ops/check_registry_merge_safety.py
(MT075-T5, plan Revision 2 SR2.5/SR2.8).

Each negative control here corresponds to one line of the governing plan's
own §R2.8 list; every one must resolve to HOLD or REJECT, never a silent
AUTO_APPLY -- that is the entire point of this gate.
"""

import sys
from pathlib import Path

import pytest

_PIPELINE_ROOT = Path(__file__).resolve().parent.parent
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

import commands.ops.check_registry_merge_safety as sut  # noqa: E402


def _entry(*, registry_type="pypi", name="aspose-words-foss", version="26.5.0",
           published=True, group_id=None, artifact_id=None) -> dict:
    candidate = {"version": version}
    if group_id or artifact_id:
        candidate["group_id"] = group_id
        candidate["artifact_id"] = artifact_id
    else:
        candidate["name"] = name
    return {
        "registry_type": registry_type,
        "candidate": candidate,
        "candidate_owner": "asposefoss",
        "verification": {
            "published": published, "verified_at": "2026-09-01", "verified_owner": None,
            "evidence_url": "https://pypi.org/project/aspose-words-foss/", "method": "pypi-poll",
            "evidence_note": "aspose corroboration",
        },
        "owner_match": None,
    }


class TestClassifyEvent:
    def test_no_base_entry_is_first_publish(self):
        assert sut.classify_event(None, _entry(published=True)) == sut.TIER_2_FIRST_PUBLISH

    def test_unpublished_to_published_is_first_publish(self):
        base = _entry(published=False)
        cand = _entry(published=True)
        assert sut.classify_event(base, cand) == sut.TIER_2_FIRST_PUBLISH

    def test_published_to_unpublished_is_unpublish(self):
        base = _entry(published=True)
        cand = _entry(published=False)
        assert sut.classify_event(base, cand) == sut.TIER_2_UNPUBLISH

    def test_both_published_same_identity_is_version_bump(self):
        base = _entry(published=True, version="26.5.0")
        cand = _entry(published=True, version="26.6.0")
        assert sut.classify_event(base, cand) == sut.TIER_1_VERSION_BUMP

    def test_registry_type_change_is_identity_change(self):
        base = _entry(registry_type="pypi", published=True)
        cand = _entry(registry_type="nuget", published=True)
        assert sut.classify_event(base, cand) == sut.TIER_2_IDENTITY_CHANGE

    def test_candidate_name_change_is_identity_change(self):
        base = _entry(name="aspose-words-foss", published=True)
        cand = _entry(name="aspose-words-foss-v2", published=True)
        assert sut.classify_event(base, cand) == sut.TIER_2_IDENTITY_CHANGE

    def test_maven_identity_uses_group_and_artifact(self):
        base = _entry(registry_type="maven", group_id="org.aspose", artifact_id="aspose-cells-foss", published=True)
        cand = _entry(registry_type="maven", group_id="org.aspose", artifact_id="aspose-cells-foss",
                       version="26.7.0", published=True)
        assert sut.classify_event(base, cand) == sut.TIER_1_VERSION_BUMP


class TestEvaluateEntryChangeVersionBump:
    def test_clean_version_bump_auto_applies(self):
        base = _entry(published=True, version="26.5.0")
        cand = _entry(published=True, version="26.6.0")
        verdict = sut.evaluate_entry_change("words", "python", base, cand)
        assert verdict.decision == sut.DECISION_AUTO_APPLY
        assert verdict.tier == sut.TIER_1_VERSION_BUMP

    def test_downgrade_is_rejected(self):
        """Negative control: non-monotonic version -- never applied, in
        either tier, no matter what else is true."""
        base = _entry(published=True, version="26.6.0")
        cand = _entry(published=True, version="26.5.0")
        verdict = sut.evaluate_entry_change("words", "python", base, cand)
        assert verdict.decision == sut.DECISION_REJECT
        assert "downgrade" in verdict.reason

    def test_same_version_is_no_change(self):
        base = _entry(published=True, version="26.5.0")
        cand = _entry(published=True, version="26.5.0")
        verdict = sut.evaluate_entry_change("words", "python", base, cand)
        assert verdict.decision == sut.DECISION_NO_CHANGE

    def test_prerelease_bump_is_held(self):
        base = _entry(published=True, version="26.5.0")
        cand = _entry(published=True, version="26.6.0rc1")
        verdict = sut.evaluate_entry_change("words", "python", base, cand)
        assert verdict.decision == sut.DECISION_HOLD
        assert "prerelease" in verdict.reason

    def test_prerelease_to_prerelease_bump_is_allowed(self):
        """Already on a prerelease line -- a further prerelease bump is fine."""
        base = _entry(published=True, version="26.6.0rc1")
        cand = _entry(published=True, version="26.6.0rc2")
        verdict = sut.evaluate_entry_change("words", "python", base, cand)
        assert verdict.decision == sut.DECISION_AUTO_APPLY

    def test_version_bump_touching_a_non_allowlisted_field_is_held(self):
        """Negative control: a version-bump-shaped diff that ALSO changes
        something outside the allowlist (e.g. candidate_owner) must not be
        trusted as a plain bump."""
        base = _entry(published=True, version="26.5.0")
        cand = _entry(published=True, version="26.6.0")
        cand["candidate_owner"] = "someone-else"
        verdict = sut.evaluate_entry_change("words", "python", base, cand)
        assert verdict.decision == sut.DECISION_HOLD
        assert "non-allowlisted" in verdict.reason


class TestEvaluateEntryChangeIdenticalCandidateGuard:
    def test_identical_candidate_is_no_change_even_if_shaped_like_first_publish(self):
        """Defense-in-depth regression test for the live-proof-run bug
        (2026-09-28, cells/rust): a candidate that is byte-for-byte identical
        to the base entry must be NO_CHANGE regardless of what tier
        classification or corroboration would otherwise decide -- a
        corroboration_check stub that would (wrongly) say True here must
        never get a chance to run."""
        base = _entry(published=False, version=None)
        candidate = dict(base)  # identical
        verdict = sut.evaluate_entry_change(
            "words", "python", base, candidate,
            corroboration_check=lambda f, p, v: True,  # would wrongly approve if reached
        )
        assert verdict.decision == sut.DECISION_NO_CHANGE

    def test_reobserving_the_same_unchanged_state_at_a_different_time_is_no_change(self):
        """Independent review (2026-09-28): build_candidate_entry always
        rewrites verified_at/evidence_note to the current observation
        timestamp, so an exact-dict-equality guard could never actually
        fire against a real candidate -- every unchanged re-observation
        differs cosmetically. The guard must compare semantic fields only
        (registry_type/identity/version/published), not the whole dict."""
        base = _entry(published=False, version=None)
        candidate = _entry(published=False, version=None)
        candidate["verification"]["verified_at"] = "2026-09-28T12:00:00Z"  # cosmetic-only diff
        candidate["verification"]["evidence_note"] = "a different observation timestamp"
        verdict = sut.evaluate_entry_change(
            "words", "python", base, candidate,
            corroboration_check=lambda f, p, v: True,  # would wrongly approve if reached
        )
        assert verdict.decision == sut.DECISION_NO_CHANGE


class TestEvaluateEntryChangeUnpublish:
    def test_unpublish_is_always_rejected_never_corroboration_gated(self):
        base = _entry(published=True)
        cand = _entry(published=False)
        verdict = sut.evaluate_entry_change(
            "words", "python", base, cand,
            corroboration_check=lambda f, p, v: True,  # even if "corroborated", must still reject
        )
        assert verdict.decision == sut.DECISION_REJECT
        assert verdict.tier == sut.TIER_2_UNPUBLISH

    def test_unpublish_combined_with_identity_change_is_still_rejected(self):
        """Independent review (2026-09-28): identity was checked before
        published in the original classify_event, so a candidate that
        changes BOTH identity AND published:true->false in the same
        observation was classified TIER_2_IDENTITY_CHANGE (corroboration-
        eligible) instead of TIER_2_UNPUBLISH (always-reject) -- a real
        bypass of the never-auto-unpublish invariant."""
        base = _entry(name="aspose-words-foss", published=True, version="26.5.0")
        cand = _entry(name="aspose-words-foss-renamed", published=False, version="26.5.0")
        verdict = sut.evaluate_entry_change(
            "words", "python", base, cand, corroboration_check=lambda f, p, v: True,
        )
        assert verdict.decision == sut.DECISION_REJECT
        assert verdict.tier == sut.TIER_2_UNPUBLISH


class TestEvaluateEntryChangeSchemaInvalid:
    def test_missing_required_field_is_rejected(self):
        base = None
        cand = {"registry_type": "pypi", "candidate": {"name": "x", "version": "1.0"}}
        # missing candidate_owner/verification/owner_match -> schema-invalid
        verdict = sut.evaluate_entry_change("words", "python", base, cand)
        assert verdict.decision == sut.DECISION_REJECT
        assert "schema-invalid" in verdict.reason


class TestEvaluateEntryChangeTier2Corroboration:
    def test_first_publish_corroborated_auto_applies(self):
        base = _entry(published=False, version=None)
        cand = _entry(published=True, version="26.5.0")
        verdict = sut.evaluate_entry_change(
            "words", "python", base, cand,
            corroboration_check=lambda f, p, v: True,
        )
        assert verdict.decision == sut.DECISION_AUTO_APPLY
        assert verdict.tier == sut.TIER_2_FIRST_PUBLISH

    def test_first_publish_uncorroborated_is_held_not_rejected(self):
        """The pre-squat fixture: no matching upstream release exists.
        Must HOLD (retry later), never silently apply, and never a hard
        REJECT either -- the candidate may still corroborate on a later run."""
        base = _entry(published=False, version=None)
        cand = _entry(published=True, version="26.5.0")
        verdict = sut.evaluate_entry_change(
            "words", "python", base, cand,
            corroboration_check=lambda f, p, v: False,
        )
        assert verdict.decision == sut.DECISION_HOLD
        assert verdict.tier == sut.TIER_2_FIRST_PUBLISH

    def test_tier2_downgrade_is_rejected_even_if_corroborated(self):
        """Independent review (2026-09-28): the original version-comparison
        block lived only inside the Tier-1 branch, so a Tier-2 candidate
        (identity change) with a corroborated but OLDER version than the
        base auto-applied a downgrade. Reproduced live with pdf/go's base
        v0.9.0 against a renamed candidate v0.1.0."""
        base = _entry(name="aspose-words-foss", published=True, version="26.7.0")
        cand = _entry(name="aspose-words-foss-renamed", published=True, version="26.1.0")
        verdict = sut.evaluate_entry_change(
            "words", "python", base, cand, corroboration_check=lambda f, p, v: True,
        )
        assert verdict.decision == sut.DECISION_REJECT
        assert "downgrade" in verdict.reason

    def test_prerelease_without_a_base_version_is_held(self):
        """Independent review (2026-09-28): the original prerelease check
        was inside the `if base_version and cand_version` block, so an
        already-published entry with NO recorded base version at all skipped
        the prerelease check entirely and could auto-apply a prerelease
        candidate (same identity, both published -> Tier 1)."""
        base = _entry(name="aspose-words-foss", published=True)
        base["candidate"] = {"name": "aspose-words-foss"}  # no version recorded yet
        cand = _entry(name="aspose-words-foss", published=True, version="26.7.0rc1")
        verdict = sut.evaluate_entry_change("words", "python", base, cand)
        assert verdict.decision == sut.DECISION_HOLD
        assert "prerelease" in verdict.reason

    def test_identity_change_uses_corroboration_too(self):
        base = _entry(name="aspose-words-foss", published=True, version="26.5.0")
        cand = _entry(name="aspose-words-foss-renamed", published=True, version="26.5.0")
        held = sut.evaluate_entry_change(
            "words", "python", base, cand, corroboration_check=lambda f, p, v: False,
        )
        assert held.decision == sut.DECISION_HOLD
        applied = sut.evaluate_entry_change(
            "words", "python", base, cand, corroboration_check=lambda f, p, v: True,
        )
        assert applied.decision == sut.DECISION_AUTO_APPLY


class TestVersionCorroboratedByRepo:
    def test_v_prefixed_tag_matches_bare_version(self):
        assert sut.version_corroborated_by_repo("26.7.0", ["v26.7.0", "v26.5.0"])

    def test_prefixed_tag_name_matches(self):
        assert sut.version_corroborated_by_repo("26.7.0", ["Aspose.Cells.FOSS-26.7.0"])

    def test_unrelated_tags_do_not_match(self):
        assert not sut.version_corroborated_by_repo("26.7.0", ["v1.0.0", "v2.0.0"])

    def test_empty_tag_list_does_not_match(self):
        assert not sut.version_corroborated_by_repo("26.7.0", [])

    # Independent review (2026-09-28): the original naive substring check
    # (`bare in tag or tag_bare in version`) had a backwards second clause
    # that made almost any version match almost any short tag. Each of these
    # is a real false positive that check produced.
    def test_short_fragment_does_not_match_a_longer_version(self):
        assert not sut.version_corroborated_by_repo("7.0", ["v26.7.0"])

    def test_bare_short_tag_does_not_match_an_unrelated_version(self):
        assert not sut.version_corroborated_by_repo("1.0.0", ["v1"])

    def test_prefix_digit_collision_does_not_match(self):
        assert not sut.version_corroborated_by_repo("26.7.0", ["v2"])

    def test_embedded_digit_run_does_not_match(self):
        assert not sut.version_corroborated_by_repo("0.1.0", ["v10.1.0"])

    def test_trailing_component_continuation_does_not_match(self):
        assert not sut.version_corroborated_by_repo("26.7.0", ["v26.7.0.1"])


class TestFetchRepoTagsAndReleases:
    def test_combines_tags_and_releases_via_injected_fetch(self):
        calls = []

        def fake_fetch(url):
            calls.append(url)
            if url.endswith("/tags"):
                return [{"name": "v26.7.0"}, {"name": "v26.6.0"}]
            if url.endswith("/releases"):
                return [{"tag_name": "v26.7.0", "name": "Release 26.7.0"}]
            return []

        names = sut.fetch_repo_tags_and_releases(
            "https://github.com/aspose-cells-foss/Aspose.Cells-FOSS-for-Java", fetch=fake_fetch,
        )
        assert "v26.7.0" in names
        assert "v26.6.0" in names
        assert len(calls) == 2

    def test_network_failure_returns_empty_not_raises(self):
        def broken_fetch(url):
            raise ConnectionError("no network in this test")

        assert sut.fetch_repo_tags_and_releases("https://github.com/a/b", fetch=broken_fetch) == []

    def test_malformed_repo_url_returns_empty(self):
        assert sut.fetch_repo_tags_and_releases("", fetch=lambda url: []) == []


class TestCheckRepoReleaseCorroboration:
    def test_no_products_json_entry_is_false(self):
        assert not sut.check_repo_release_corroboration(
            "unknownfamily", "python", "1.0.0",
            fetch=lambda url: [], product_lookup=lambda f, p: None,
        )

    def test_corroborated_end_to_end_with_fake_repo_and_fetch(self):
        def fake_lookup(family, platform):
            return {"repo_url": "https://github.com/aspose-words-foss/Aspose.Words-FOSS-for-Python"}

        def fake_fetch(url):
            if url.endswith("/tags"):
                return [{"name": "v26.5.0"}]
            return []

        assert sut.check_repo_release_corroboration(
            "words", "python", "26.5.0", fetch=fake_fetch, product_lookup=fake_lookup,
        )

    def test_not_corroborated_when_no_matching_tag(self):
        def fake_lookup(family, platform):
            return {"repo_url": "https://github.com/aspose-words-foss/Aspose.Words-FOSS-for-Python"}

        def fake_fetch(url):
            if url.endswith("/tags"):
                return [{"name": "v1.0.0"}]
            return []

        assert not sut.check_repo_release_corroboration(
            "words", "python", "26.5.0", fetch=fake_fetch, product_lookup=fake_lookup,
        )


class TestCheckRegistryVelocity:
    """MT075-T9 (plan Revision 2 R2.13): the cross-run velocity/anomaly check
    that replaces the bootstrap-PR human-merge step's nominal safety net."""

    def test_real_change_budget_module_loads_and_warms_up(self):
        """Sanity: the real scripts/seo/pipeline/change_budget.py import
        must actually work from this module's context (not just in a
        fixture) -- an unseen family is warm-up, never blocked."""
        blocked, reason = sut.check_registry_velocity("a-family-with-no-history-xyz")
        assert blocked is False
        assert "warm-up" in reason or "INACTIVE" in reason

    def test_injected_fake_budgets_and_history_can_force_a_block(self):
        fake_budgets = {
            "registry_watch_max_pages_per_run": 5,
            "registry_watch_max_pages_per_site_per_run": 5,
            "max_title_changes_per_run": 999, "max_description_changes_per_run": 999,
            "max_total_metadata_changes_per_run": 999,
            "anomaly_multiplier": 3.0, "warmup_runs": 1,
        }
        # 1 prior run of history (>= warmup_runs=1) with a low baseline mean.
        fake_history = {"burstfam/registry_watch": [1]}
        blocked, reason = sut.check_registry_velocity(
            "burstfam", budgets=fake_budgets, history=fake_history,
        )
        # ceiling = 1 * 3.0 = 3.0; proposed total_items=1 <= 3.0 -> not blocked.
        assert blocked is False

        # A much larger prior baseline is irrelevant here since this check
        # always proposes total_items=1 per call -- the real burst-detection
        # value comes from the static per-run cap plus repeated calls
        # across runs recording history; verify the static cap path instead.
        tiny_cap_budgets = dict(fake_budgets, registry_watch_max_pages_per_run=0)
        blocked2, reason2 = sut.check_registry_velocity(
            "burstfam", budgets=tiny_cap_budgets, history=fake_history,
        )
        assert blocked2 is True
        assert "static cap" in reason2

    def test_missing_change_budget_module_fails_closed(self):
        """Defense in depth: if the seo subpackage is ever unavailable, this
        must BLOCK (HOLD), never silently pass -- it's a safety control.
        Uses the _change_budget_module injection seam, not monkeypatch.setattr
        on the private _load_change_budget (AGENTS.md 16, T2)."""
        blocked, reason = sut.check_registry_velocity("any-family", _change_budget_module=None)
        assert blocked is True
        assert "unavailable" in reason

    def test_change_budget_exception_fails_closed(self):
        class _Boom:
            def load_budgets(self):
                raise RuntimeError("boom")

        blocked, reason = sut.check_registry_velocity("any-family", _change_budget_module=_Boom())
        assert blocked is True
        assert "boom" in reason


class TestEvaluateEntryChangeVelocityWiring:
    def test_tier1_auto_apply_blocked_by_velocity_downgrades_to_hold(self):
        base = _entry(published=True, version="26.5.0")
        cand = _entry(published=True, version="26.6.0")
        verdict = sut.evaluate_entry_change(
            "words", "python", base, cand,
            velocity_check=lambda family: (True, "synthetic block for this test"),
        )
        assert verdict.decision == sut.DECISION_HOLD
        assert "velocity" in verdict.reason

    def test_tier1_auto_apply_passes_when_velocity_clears(self):
        base = _entry(published=True, version="26.5.0")
        cand = _entry(published=True, version="26.6.0")
        verdict = sut.evaluate_entry_change(
            "words", "python", base, cand,
            velocity_check=lambda family: (False, "ok"),
        )
        assert verdict.decision == sut.DECISION_AUTO_APPLY

    def test_tier2_corroborated_but_velocity_blocked_downgrades_to_hold(self):
        base = _entry(published=False, version=None)
        cand = _entry(published=True, version="26.5.0")
        verdict = sut.evaluate_entry_change(
            "words", "python", base, cand,
            corroboration_check=lambda f, p, v: True,
            velocity_check=lambda family: (True, "synthetic block for this test"),
        )
        assert verdict.decision == sut.DECISION_HOLD
        assert "velocity" in verdict.reason

    def test_velocity_check_receives_the_correct_family(self):
        seen = {}

        def _fake_velocity(family):
            seen["family"] = family
            return False, "ok"

        base = _entry(published=True, version="26.5.0")
        cand = _entry(published=True, version="26.6.0")
        sut.evaluate_entry_change("cells", "python", base, cand, velocity_check=_fake_velocity)
        assert seen["family"] == "cells"

    def test_unpublish_never_reaches_velocity_check(self):
        """A hard-invariant REJECT must short-circuit before any velocity
        call -- confirmed by a velocity_check that would raise if invoked."""
        def _boom(family):
            raise AssertionError("velocity_check must not be called for an unpublish")

        base = _entry(published=True)
        cand = _entry(published=False)
        verdict = sut.evaluate_entry_change("words", "python", base, cand, velocity_check=_boom)
        assert verdict.decision == sut.DECISION_REJECT


class TestEvaluateBatch:
    def test_no_diff_is_no_change(self):
        registry = {"words": {"python": _entry(published=True, version="26.5.0")}}
        verdict = sut.evaluate_batch(registry, registry)
        assert verdict.decision == sut.DECISION_NO_CHANGE

    def test_all_clean_version_bumps_auto_apply(self):
        base = {
            "words": {"python": _entry(published=True, version="26.5.0")},
            "cells": {"python": _entry(published=True, version="26.5.0")},
        }
        candidate = {
            "words": {"python": _entry(published=True, version="26.6.0")},
            "cells": {"python": _entry(published=True, version="26.6.0")},
        }
        verdict = sut.evaluate_batch(base, candidate)
        assert verdict.decision == sut.DECISION_AUTO_APPLY
        assert len(verdict.per_entry) == 2

    def test_over_batch_cap_is_held(self):
        """Negative control: >5 entries changed at once -- always HOLD,
        regardless of how clean each individual change looks."""
        base = {f"fam{i}": {"python": _entry(published=True, version="26.5.0")} for i in range(6)}
        candidate = {f"fam{i}": {"python": _entry(published=True, version="26.6.0")} for i in range(6)}
        verdict = sut.evaluate_batch(base, candidate)
        assert verdict.decision == sut.DECISION_HOLD
        assert "batch cap" in verdict.reason

    def test_deleted_entry_holds_the_batch_not_silently_no_change(self):
        """Independent review (2026-09-28): the original loop only ever
        iterated candidate_registry, so a family/platform present in base
        but removed entirely from candidate was invisible -- evaluate_batch
        reported NO_CHANGE for a real deletion, bypassing the
        never-auto-unpublish spirit by a different route than TIER_2_UNPUBLISH."""
        base = {"words": {"python": _entry(published=True, version="26.5.0")}}
        candidate = {"words": {}}  # words/python entirely removed
        verdict = sut.evaluate_batch(base, candidate)
        assert verdict.decision == sut.DECISION_HOLD
        assert "deletion" in verdict.reason

    def test_one_bad_entry_holds_the_whole_batch(self):
        """A partial apply (skip the risky one, apply the rest silently)
        would itself be an unreviewed, undocumented state -- must not happen."""
        base = {
            "words": {"python": _entry(published=True, version="26.5.0")},
            "cells": {"python": _entry(published=True, version="26.6.0")},
        }
        candidate = {
            "words": {"python": _entry(published=True, version="26.6.0")},  # clean bump
            "cells": {"python": _entry(published=True, version="26.5.0")},  # downgrade!
        }
        verdict = sut.evaluate_batch(base, candidate)
        assert verdict.decision == sut.DECISION_HOLD
        assert verdict.per_entry[("cells", "python")].decision == sut.DECISION_REJECT
