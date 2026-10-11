"""Tests for verify_deploy_trigger.py — Mission
MT066-2026-09-09-PACKAGE-INSTALL-RECONCILIATION, taskcard TC-PKG-04-L3.

All fixture data below (manifest commit shas/dates/messages, and the JSON blobs
at each revision) is REAL data captured live from `Aspose/aspose.org-workflows`
via `gh api` on 2026-09-17, not synthesized. The two SHAs under test in the
"real case" classes are REAL commits in THIS repo that touch ONLY
`data/package_registry.json`:

  cd86f7ad67e25cfc7ea23c1957504164109430d4  2026-09-10T14:09:38Z
  7bb086aa90250b967696b001c83bfab136d5acdf  2026-09-12T13:26:18Z

Their real, reconstructed fates (independently confirmed against the live repo
history before this test was written, see module docstring of
verify_deploy_trigger.py):

  cd86f7ad... -> covered by the 2026-09-11 scan cycle (scan_id
                 20260911-091834), which reached "completed" -- a clean
                 CONFIRMED_DEPLOYED case.
  7bb086aa... -> covered by the 2026-09-13 scan cycle (scan_id
                 20260913-090311), which was silently superseded by the next
                 day's fresh scan while still "pending" (a REAL, live-confirmed
                 orphaned cycle -- it never received a "Deploy triggered" or
                 any later status commit). The change only reached a real
                 completed deploy via the NEXT cycle (20260914-093709,
                 completed 2026-09-14T17:30:03Z) -- RECOVERED_VIA_LATER_CYCLE.

These tests run real `git merge-base --is-ancestor` / `git show` against THIS
repo's own history (both SHAs, and every content_sha referenced below, exist
in this repo -- confirmed via `git cat-file -t` before this test was written)
-- no mocking of ancestry for the "real case" tests. Only the network call to
`gh api` (fetching the sibling repo's file history) is replaced with the
captured fixture data, since a live network call has no place in a
deterministic test suite.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "checks"))

import verify_deploy_trigger as vdt  # noqa: E402


# ---------------------------------------------------------------------------
# Real SHAs under test (this repo, data/package_registry.json-only commits)
# ---------------------------------------------------------------------------

SHA_CONFIRMED = "cd86f7ad67e25cfc7ea23c1957504164109430d4"   # 2026-09-10T14:09:38Z
SHA_RECOVERED = "7bb086aa90250b967696b001c83bfab136d5acdf"   # 2026-09-12T13:26:18Z


# ---------------------------------------------------------------------------
# Real manifest commit history (scripts/deploy/deploy_manifest.json in
# Aspose/aspose.org-workflows), captured 2026-09-17 via `gh api
# repos/Aspose/aspose.org-workflows/commits?path=scripts/deploy/deploy_manifest.json`.
# Newest-first, exactly as the GitHub API returns it.
# ---------------------------------------------------------------------------

REAL_MANIFEST_COMMITS = [
    {"sha": "3385f5bb1ac79d5d4094820b6baf99fff7f4c7a7", "date": "2026-09-14T17:30:08Z", "message": "Deploy status: completed 2026-09-14"},
    {"sha": "0d98b8c7b3318b4dccc184b9a03b9cbea5f7c04b", "date": "2026-09-14T11:34:56Z", "message": "Deploy status: production 2026-09-14"},
    {"sha": "0538def1c9cec9c510f5c3542e3ac5dc6d2cbb42", "date": "2026-09-14T09:37:45Z", "message": "Deploy triggered: 2026-09-14"},
    {"sha": "392e7aea20c58be6fec483d249203df9ff0dbdd1", "date": "2026-09-14T09:37:09Z", "message": "Deploy manifest: 2026-09-14"},
    {"sha": "f9564bbfd4f771dd25c8f5743546bad3963bbcdd", "date": "2026-09-13T09:03:11Z", "message": "Deploy manifest: 2026-09-13"},
    {"sha": "56f42782a52d14c9c73ceaa763b7f94007cf24bb", "date": "2026-09-12T11:55:30Z", "message": "Deploy status: completed 2026-09-12"},
    {"sha": "c815125e4a67b363d324abce57b0513e60b14ada", "date": "2026-09-12T09:48:53Z", "message": "Deploy status: production 2026-09-12"},
    {"sha": "2e364a4af48a61c427a4e1dd0b13d3a0eec1fba1", "date": "2026-09-12T08:32:35Z", "message": "Deploy status: staging 2026-09-12"},
    {"sha": "44cfbd0dac7d2518bd6b309c723b023a35330ad6", "date": "2026-09-12T08:28:49Z", "message": "Deploy status: staging 2026-09-12"},
    {"sha": "1d82d40dfad61f4833a6a45205eb720ecbf8ba73", "date": "2026-09-12T08:24:56Z", "message": "Deploy triggered: 2026-09-12"},
    {"sha": "1005df758689bad8a190de863733b418beee7370", "date": "2026-09-12T08:24:10Z", "message": "Deploy manifest: 2026-09-12"},
    {"sha": "395b418d13e17df4bbc1e04939796c2eb24535a0", "date": "2026-09-11T14:48:34Z", "message": "Deploy status: completed 2026-09-11"},
    {"sha": "db8611393f7c1ca5e8ad86868f5f5f290ab66a87", "date": "2026-09-11T10:30:06Z", "message": "Deploy status: production 2026-09-11"},
    {"sha": "9659188943add6a24e0a0f6c3ee8f4418bbfbce4", "date": "2026-09-11T09:19:37Z", "message": "Deploy triggered: 2026-09-11"},
    {"sha": "fddb11e8b38a8ab3b35c689040e66d0749f519e5", "date": "2026-09-11T09:18:34Z", "message": "Deploy manifest: 2026-09-11"},
    {"sha": "a37934322f75f31c12388274f4a98a18df68f20d", "date": "2026-09-10T14:44:13Z", "message": "Deploy status: completed 2026-09-10"},
    {"sha": "b064957de6d5ffa22807530c6fb16b32d9dd423f", "date": "2026-09-10T10:27:52Z", "message": "Deploy status: production 2026-09-10"},
    {"sha": "4900e206c8e72627c470b62fb31530fded88aefb", "date": "2026-09-10T08:42:30Z", "message": "Deploy triggered: 2026-09-10"},
    {"sha": "14d7d2d1b54af02c96e0b7040f45fd8ca74d0dfd", "date": "2026-09-10T08:41:39Z", "message": "Deploy manifest: 2026-09-10"},
]

# Real JSON blobs fetched via `gh api
# repos/Aspose/aspose.org-workflows/contents/scripts/deploy/deploy_manifest.json?ref=<sha>`.
# Only the boundary revisions (cycle-start "pending" + cycle-terminal state) were
# captured for each cycle -- reconstruct_cycles() only needs those to group
# correctly (see its own docstring); intermediate staging/production commits are
# listed above (for an accurate commit history) but their blob content was not
# separately fetched, and reconstruct_cycles() correctly skips shas with no
# fixture entry.
REAL_MANIFEST_BLOBS = {
    "14d7d2d1b54af02c96e0b7040f45fd8ca74d0dfd": {
        "scan_id": "20260910-084139", "content_sha": "f9cbe210fbf126254e01fea8873d49f722c50047",
        "previous_sha": "500ed05cf7d29469830c5f77dd1a66829c0d80fc",
        "detected_at": "2026-09-10T08:41:39.733262+00:00", "global_change": True, "state": "pending",
        "completed_at": None,
    },
    "a37934322f75f31c12388274f4a98a18df68f20d": {
        "scan_id": "20260910-084139", "content_sha": "f9cbe210fbf126254e01fea8873d49f722c50047",
        "previous_sha": "500ed05cf7d29469830c5f77dd1a66829c0d80fc",
        "detected_at": "2026-09-10T08:41:39.733262+00:00", "global_change": True, "state": "completed",
        "completed_at": "2026-09-10T14:44:07.195150+00:00",
    },
    "fddb11e8b38a8ab3b35c689040e66d0749f519e5": {
        "scan_id": "20260911-091834", "content_sha": "8089d9f63d234201f3c175fd9b71ea9185c0ac96",
        "previous_sha": "f9cbe210fbf126254e01fea8873d49f722c50047",
        "detected_at": "2026-09-11T09:18:34.507250+00:00", "global_change": True, "state": "pending",
        "completed_at": None,
    },
    "395b418d13e17df4bbc1e04939796c2eb24535a0": {
        "scan_id": "20260911-091834", "content_sha": "8089d9f63d234201f3c175fd9b71ea9185c0ac96",
        "previous_sha": "f9cbe210fbf126254e01fea8873d49f722c50047",
        "detected_at": "2026-09-11T09:18:34.507250+00:00", "global_change": True, "state": "completed",
        "completed_at": "2026-09-11T14:48:25.230894+00:00",
    },
    "1005df758689bad8a190de863733b418beee7370": {
        "scan_id": "20260912-082410", "content_sha": "bf33a2a192d194d5d9697677d49a4d3b39ad72d3",
        "previous_sha": "8089d9f63d234201f3c175fd9b71ea9185c0ac96",
        "detected_at": "2026-09-12T08:24:10.068964+00:00", "global_change": False, "state": "pending",
        "completed_at": None,
    },
    "56f42782a52d14c9c73ceaa763b7f94007cf24bb": {
        "scan_id": "20260912-082410", "content_sha": "bf33a2a192d194d5d9697677d49a4d3b39ad72d3",
        "previous_sha": "8089d9f63d234201f3c175fd9b71ea9185c0ac96",
        "detected_at": "2026-09-12T08:24:10.068964+00:00", "global_change": False, "state": "completed",
        "completed_at": "2026-09-12T11:55:25.515782+00:00",
    },
    # 09-13's ONLY revision -- confirmed the whole real history, no further
    # commit ever touched deploy_manifest.json at this content_sha before
    # 09-14's fresh scan overwrote it (see REAL_MANIFEST_COMMITS above: the
    # very next entry after this one, going backwards in time, is
    # 2026-09-14's own "Deploy manifest" commit) -- this IS the real orphan.
    "f9564bbfd4f771dd25c8f5743546bad3963bbcdd": {
        "scan_id": "20260913-090311", "content_sha": "92b8818286e40e1afef82c891b58c3d48bc2c717",
        "previous_sha": "bf33a2a192d194d5d9697677d49a4d3b39ad72d3",
        "detected_at": "2026-09-13T09:03:11.918780+00:00", "global_change": False, "state": "pending",
        "completed_at": None,
    },
    "392e7aea20c58be6fec483d249203df9ff0dbdd1": {
        "scan_id": "20260914-093709", "content_sha": "ec5a71f804e5b6ec8ebefeaa04ccdcba523b5d3a",
        # previous_sha reverted to 09-12's content_sha (NOT 09-13's) -- direct
        # evidence that 09-13's cycle was bypassed entirely, real and confirmed.
        "previous_sha": "bf33a2a192d194d5d9697677d49a4d3b39ad72d3",
        "detected_at": "2026-09-14T09:37:09.773925+00:00", "global_change": False, "state": "pending",
        "completed_at": None,
    },
    "3385f5bb1ac79d5d4094820b6baf99fff7f4c7a7": {
        "scan_id": "20260914-093709", "content_sha": "ec5a71f804e5b6ec8ebefeaa04ccdcba523b5d3a",
        "previous_sha": "bf33a2a192d194d5d9697677d49a4d3b39ad72d3",
        "detected_at": "2026-09-14T09:37:09.773925+00:00", "global_change": False, "state": "completed",
        "completed_at": "2026-09-14T17:30:03.287435+00:00",
    },
}


def _fixture_fetch(sha: str):
    return REAL_MANIFEST_BLOBS.get(sha)


def _commits_up_to(cutoff_sha: str) -> list:
    """Return the suffix of REAL_MANIFEST_COMMITS starting at cutoff_sha
    (inclusive) -- i.e. "everything from cutoff_sha backwards in time",
    simulating what list_path_commits() would have returned had it been
    queried right after cutoff_sha's own scan (before anything newer existed).
    """
    idx = next(i for i, c in enumerate(REAL_MANIFEST_COMMITS) if c["sha"] == cutoff_sha)
    return REAL_MANIFEST_COMMITS[idx:]


# ---------------------------------------------------------------------------
# reconstruct_cycles() -- pure grouping/orphan-detection logic
# ---------------------------------------------------------------------------

class TestReconstructCycles:
    def test_groups_real_history_into_five_cycles(self):
        cycles = vdt.reconstruct_cycles(REAL_MANIFEST_COMMITS, _fixture_fetch)
        scan_ids = [c.scan_id for c in cycles]
        assert scan_ids == [
            "20260910-084139", "20260911-091834", "20260912-082410",
            "20260913-090311", "20260914-093709",
        ]

    def test_0913_cycle_is_marked_orphaned(self):
        cycles = vdt.reconstruct_cycles(REAL_MANIFEST_COMMITS, _fixture_fetch)
        by_id = {c.scan_id: c for c in cycles}
        assert by_id["20260913-090311"].orphaned is True
        assert by_id["20260913-090311"].final_state == "pending"
        assert by_id["20260913-090311"].completed_at is None

    def test_completed_cycles_are_not_orphaned(self):
        cycles = vdt.reconstruct_cycles(REAL_MANIFEST_COMMITS, _fixture_fetch)
        by_id = {c.scan_id: c for c in cycles}
        for sid in ("20260910-084139", "20260911-091834", "20260912-082410", "20260914-093709"):
            assert by_id[sid].orphaned is False, sid
            assert by_id[sid].final_state == "completed", sid

    def test_0914_previous_sha_reverted_to_0912_content_sha(self):
        """Direct evidence the 09-13 cycle was bypassed: 09-14's own
        previous_sha is 09-12's content_sha, not 09-13's."""
        cycles = vdt.reconstruct_cycles(REAL_MANIFEST_COMMITS, _fixture_fetch)
        by_id = {c.scan_id: c for c in cycles}
        assert by_id["20260914-093709"].previous_sha == by_id["20260912-082410"].content_sha


# ---------------------------------------------------------------------------
# classify_sha() against REAL local git ancestry (no ancestor_check/date_lookup
# injection in this class -- these shell out to the real `git` in this repo)
# ---------------------------------------------------------------------------

class TestClassifySha_RealCases:
    def test_confirmed_deployed_real_case(self):
        """cd86f7ad (2026-09-10T14:09:38Z, package_registry.json-only) is a
        clean CONFIRMED_DEPLOYED: its native cycle (09-11) completed."""
        cycles = vdt.reconstruct_cycles(REAL_MANIFEST_COMMITS, _fixture_fetch)
        result = vdt.classify_sha(SHA_CONFIRMED, cycles)
        assert result.verdict == vdt.VERDICT_CONFIRMED
        assert result.native_cycle.scan_id == "20260911-091834"
        assert result.covering_cycle.scan_id == "20260911-091834"

    def test_recovered_via_later_cycle_real_case_full_history(self):
        """7bb086aa (2026-09-12T13:26:18Z, package_registry.json-only) fell
        into the REAL orphaned 09-13 cycle; only the 09-14 cycle's completed
        window recovers it."""
        cycles = vdt.reconstruct_cycles(REAL_MANIFEST_COMMITS, _fixture_fetch)
        result = vdt.classify_sha(SHA_RECOVERED, cycles)
        assert result.verdict == vdt.VERDICT_RECOVERED
        assert result.native_cycle.scan_id == "20260913-090311"
        assert result.native_cycle.orphaned is True
        assert result.covering_cycle.scan_id == "20260914-093709"

    def test_recovered_case_not_falsely_confirmed_before_recovery_lands(self):
        """The critical discrimination: AS OF right after the 09-13 scan (before
        09-14's scan ever ran), the tool must NOT claim 7bb086aa is confirmed
        deployed -- its only covering cycle (09-13) is still 'pending' with no
        rescue yet visible. It also must not prematurely cry SILENTLY_DROPPED
        after under a day. Uses the REAL commit history truncated to exactly
        what existed at that historical moment (see _commits_up_to)."""
        commits_as_of_0913 = _commits_up_to("f9564bbfd4f771dd25c8f5743546bad3963bbcdd")
        cycles = vdt.reconstruct_cycles(commits_as_of_0913, _fixture_fetch)
        # Confirm the simulation: 4 real cycles known as of this point (09-10
        # through 09-13; 09-14 has not happened yet), the latest (09-13) still
        # pending and not yet known to be orphaned (no newer cycle exists yet
        # in this truncated view to trigger that detection).
        assert len(cycles) == 4
        assert cycles[-1].scan_id == "20260913-090311"
        assert cycles[-1].orphaned is False

        from datetime import datetime, timezone
        as_of = datetime(2026, 9, 13, 10, 0, 0, tzinfo=timezone.utc)  # ~50 min after the 09-13 scan
        result = vdt.classify_sha(SHA_RECOVERED, cycles, now=as_of, drop_threshold_days=3)
        assert result.verdict == vdt.VERDICT_PENDING
        assert result.native_cycle.scan_id == "20260913-090311"

    def test_confirmed_case_already_settled_as_of_0911_completion(self):
        """cd86f7ad is ALREADY confirmed as of right after the 09-11 cycle
        completes -- it never needed a rescue, unlike 7bb086aa."""
        commits_as_of_0911_completion = _commits_up_to("395b418d13e17df4bbc1e04939796c2eb24535a0")
        cycles = vdt.reconstruct_cycles(commits_as_of_0911_completion, _fixture_fetch)
        result = vdt.classify_sha(SHA_CONFIRMED, cycles)
        assert result.verdict == vdt.VERDICT_CONFIRMED


# ---------------------------------------------------------------------------
# classify_sha() boundary condition: SILENTLY_DROPPED
#
# NOTE: no real data/package_registry.json commit has ever gone unrecovered
# long enough to genuinely earn this verdict (the taskcard instructions are
# explicit: do not fabricate a "real" dropped case that doesn't exist). This
# test instead re-uses the REAL 09-13 orphan cycle's exact shape/fields
# (proven real above) and only pushes `now` artificially far forward, to prove
# the drop-threshold arithmetic itself is correct. It is clearly NOT presented
# as a second real historical case -- SHA_RECOVERED's real fate is
# RECOVERED_VIA_LATER_CYCLE, demonstrated above with the real full history.
# ---------------------------------------------------------------------------

class TestClassifySha_DropThresholdBoundary:
    def test_silently_dropped_once_threshold_exceeded_with_no_rescue(self):
        from datetime import datetime, timezone
        commits_as_of_0913 = _commits_up_to("f9564bbfd4f771dd25c8f5743546bad3963bbcdd")
        cycles = vdt.reconstruct_cycles(commits_as_of_0913, _fixture_fetch)
        far_future = datetime(2026, 9, 20, 0, 0, 0, tzinfo=timezone.utc)  # >3 days after 7bb086aa, no rescue cycle known
        result = vdt.classify_sha(SHA_RECOVERED, cycles, now=far_future, drop_threshold_days=3)
        assert result.verdict == vdt.VERDICT_DROPPED
        assert result.native_cycle.scan_id == "20260913-090311"

    def test_pending_within_grace_period(self):
        from datetime import datetime, timezone
        commits_as_of_0913 = _commits_up_to("f9564bbfd4f771dd25c8f5743546bad3963bbcdd")
        cycles = vdt.reconstruct_cycles(commits_as_of_0913, _fixture_fetch)
        just_inside = datetime(2026, 9, 15, 0, 0, 0, tzinfo=timezone.utc)  # ~2.4 days after 7bb086aa
        result = vdt.classify_sha(SHA_RECOVERED, cycles, now=just_inside, drop_threshold_days=3)
        assert result.verdict == vdt.VERDICT_PENDING


# ---------------------------------------------------------------------------
# is_ancestor() / commit_date() / sha_exists_locally() -- real git integration
# ---------------------------------------------------------------------------

class TestGitAncestryHelpers:
    def test_confirmed_sha_is_ancestor_of_its_native_content_sha(self):
        assert vdt.is_ancestor(SHA_CONFIRMED, "8089d9f63d234201f3c175fd9b71ea9185c0ac96") is True

    def test_confirmed_sha_not_ancestor_of_earlier_content_sha(self):
        assert vdt.is_ancestor(SHA_CONFIRMED, "f9cbe210fbf126254e01fea8873d49f722c50047") is False

    def test_recovered_sha_ancestor_of_orphaned_and_recovering_content_shas(self):
        assert vdt.is_ancestor(SHA_RECOVERED, "92b8818286e40e1afef82c891b58c3d48bc2c717") is True
        assert vdt.is_ancestor(SHA_RECOVERED, "ec5a71f804e5b6ec8ebefeaa04ccdcba523b5d3a") is True

    def test_recovered_sha_not_ancestor_of_its_own_scan_baseline(self):
        assert vdt.is_ancestor(SHA_RECOVERED, "bf33a2a192d194d5d9697677d49a4d3b39ad72d3") is False

    def test_sha_exists_locally_true_for_real_shas(self):
        assert vdt.sha_exists_locally(SHA_CONFIRMED) is True
        assert vdt.sha_exists_locally(SHA_RECOVERED) is True

    def test_sha_exists_locally_false_for_bogus_sha(self):
        assert vdt.sha_exists_locally("0" * 40) is False

    def test_commit_date_resolves_real_shas(self):
        d = vdt.commit_date(SHA_CONFIRMED)
        assert d is not None
        assert d.year == 2026 and d.month == 9 and d.day == 10


# ---------------------------------------------------------------------------
# Issue filing -- injected runner only, never a real `gh issue create` call
# ---------------------------------------------------------------------------

class TestFileIssue:
    def test_file_issue_refuses_non_dropped_verdict(self):
        result = vdt.VerificationResult(SHA_CONFIRMED, vdt.VERDICT_CONFIRMED, None, None, "detail")
        with pytest.raises(ValueError):
            vdt.file_issue(result, repo="Aspose/aspose.org")

    def test_file_issue_creates_for_dropped_verdict(self):
        from unittest.mock import MagicMock
        result = vdt.VerificationResult(SHA_RECOVERED, vdt.VERDICT_DROPPED, None, None, "detail")
        runner = MagicMock(return_value=MagicMock(
            returncode=0, stdout="https://github.com/Aspose/aspose.org/issues/42\n",
        ))
        outcome = vdt.file_issue(result, repo="Aspose/aspose.org", runner=runner)
        assert outcome == {"action": "created", "issue_number": 42}
        args = runner.call_args[0][0]
        assert args[:3] == ["gh", "issue", "create"]
        assert "--repo" in args and "Aspose/aspose.org" in args

    def test_file_issue_reports_failure_on_nonzero_exit(self):
        from unittest.mock import MagicMock
        result = vdt.VerificationResult(SHA_RECOVERED, vdt.VERDICT_DROPPED, None, None, "detail")
        runner = MagicMock(return_value=MagicMock(returncode=1, stdout=""))
        outcome = vdt.file_issue(result, repo="Aspose/aspose.org", runner=runner)
        assert outcome == {"action": "failed", "issue_number": None}


# ---------------------------------------------------------------------------
# verify_sha() orchestration -- injected runner (no live `gh api` call)
# ---------------------------------------------------------------------------

class TestVerifySha:
    def test_verify_sha_uses_injected_runner_end_to_end(self):
        """Full orchestration (list_path_commits + fetch_file_at_ref +
        reconstruct_cycles + classify_sha) driven entirely by an injected
        runner returning the REAL captured fixture payloads -- proves the
        wiring, not just the pure functions in isolation."""
        import base64
        import json as _json
        from unittest.mock import MagicMock

        def fake_runner(args, **kwargs):
            joined = " ".join(args)
            if "commits?path=" in joined:
                return MagicMock(returncode=0, stdout=_json.dumps([
                    {"sha": c["sha"], "commit": {"author": {"date": c["date"]}, "message": c["message"]}}
                    for c in REAL_MANIFEST_COMMITS
                ]))
            for sha, blob in REAL_MANIFEST_BLOBS.items():
                if f"ref={sha}" in joined:
                    encoded = base64.b64encode(_json.dumps(blob).encode("utf-8")).decode("ascii")
                    return MagicMock(returncode=0, stdout=encoded)
            # Realistic gh CLI 404 stderr shape (confirmed live 2026-09-17:
            # `gh: Not Found (HTTP 404)`) -- these intermediate commits (no
            # fixture blob captured) must classify as genuine "no data", not
            # a poll failure, so reconstruct_cycles() can skip them as
            # documented above.
            return MagicMock(returncode=1, stdout="", stderr="gh: Not Found (HTTP 404)")

        result = vdt.verify_sha(SHA_CONFIRMED, runner=fake_runner)
        assert result.verdict == vdt.VERDICT_CONFIRMED


# ---------------------------------------------------------------------------
# TC-PKG-04-L3-FIX (this taskcard): a non-404 `gh api` failure must NEVER be
# folded into the same "no data" signal as a genuine 404. Fixture stderr text
# below matches real `gh` CLI output confirmed live on 2026-09-17 (`gh: Not
# Found (HTTP 404)`, `gh: API rate limit exceeded ... (HTTP 403)`, etc. --
# `gh`'s own error format is always `gh: <message> (HTTP <status>)`).
# ---------------------------------------------------------------------------

class TestFetchFileAtRefErrorHandling:
    def test_genuine_404_still_returns_none(self):
        """Regression guard: a real 404 must keep returning None (this is the
        ONE case that legitimately means 'no data for this revision')."""
        from unittest.mock import MagicMock
        runner = MagicMock(return_value=MagicMock(
            returncode=1, stdout="", stderr="gh: Not Found (HTTP 404)",
        ))
        result = vdt.fetch_file_at_ref("Aspose/aspose.org-workflows", vdt.MANIFEST_PATH,
                                        "deadbeef", runner=runner)
        assert result is None

    def test_rate_limit_403_raises_api_error_not_none(self):
        """The core defect: a rate-limited poll must be LOUD, never silently
        'no data'. Distinguishing this is the entire point of the fix."""
        from unittest.mock import MagicMock
        runner = MagicMock(return_value=MagicMock(
            returncode=1, stdout="",
            stderr="gh: API rate limit exceeded for installation ID 123. (HTTP 403)",
        ))
        with pytest.raises(vdt.DeployTriggerAPIError, match="403"):
            vdt.fetch_file_at_ref("Aspose/aspose.org-workflows", vdt.MANIFEST_PATH,
                                   "deadbeef", runner=runner)

    def test_auth_failure_401_raises_api_error(self):
        from unittest.mock import MagicMock
        runner = MagicMock(return_value=MagicMock(
            returncode=1, stdout="", stderr="gh: Bad credentials (HTTP 401)",
        ))
        with pytest.raises(vdt.DeployTriggerAPIError):
            vdt.fetch_file_at_ref("Aspose/aspose.org-workflows", vdt.MANIFEST_PATH,
                                   "deadbeef", runner=runner)

    def test_server_5xx_raises_api_error(self):
        from unittest.mock import MagicMock
        runner = MagicMock(return_value=MagicMock(
            returncode=1, stdout="", stderr="gh: Internal Server Error (HTTP 500)",
        ))
        with pytest.raises(vdt.DeployTriggerAPIError):
            vdt.fetch_file_at_ref("Aspose/aspose.org-workflows", vdt.MANIFEST_PATH,
                                   "deadbeef", runner=runner)

    def test_network_failure_with_no_http_status_raises_api_error(self):
        """No HTTP status at all (couldn't reach the network) must NOT be
        misread as a 404 just because it's also a failure."""
        from unittest.mock import MagicMock
        runner = MagicMock(return_value=MagicMock(
            returncode=1, stdout="",
            stderr="gh: could not resolve host: api.github.com",
        ))
        with pytest.raises(vdt.DeployTriggerAPIError):
            vdt.fetch_file_at_ref("Aspose/aspose.org-workflows", vdt.MANIFEST_PATH,
                                   "deadbeef", runner=runner)

    def test_gh_binary_missing_raises_api_error_not_silently_none(self):
        """FileNotFoundError (gh not installed) was previously caught and
        silently turned into None -- must now raise, loudly."""
        def runner(*args, **kwargs):
            raise FileNotFoundError("gh")
        with pytest.raises(vdt.DeployTriggerAPIError):
            vdt.fetch_file_at_ref("Aspose/aspose.org-workflows", vdt.MANIFEST_PATH,
                                   "deadbeef", runner=runner)

    def test_timeout_raises_api_error_not_silently_none(self):
        import subprocess as _subprocess

        def runner(*args, **kwargs):
            raise _subprocess.TimeoutExpired(cmd="gh", timeout=60)
        with pytest.raises(vdt.DeployTriggerAPIError):
            vdt.fetch_file_at_ref("Aspose/aspose.org-workflows", vdt.MANIFEST_PATH,
                                   "deadbeef", runner=runner)


class TestListPathCommitsErrorHandling:
    def test_rate_limit_raises_instead_of_silently_ending_pagination(self):
        """Before the fix, ANY non-zero exit here (including a rate limit
        mid-pagination) was treated identically to 'no more pages' -- silently
        returning whatever had been collected so far. This endpoint has no
        legitimate 404 case for a real path, so any failure must be loud."""
        from unittest.mock import MagicMock
        runner = MagicMock(return_value=MagicMock(
            returncode=1, stdout="",
            stderr="gh: API rate limit exceeded for installation ID 123. (HTTP 403)",
        ))
        with pytest.raises(vdt.DeployTriggerAPIError, match="403"):
            vdt.list_path_commits("Aspose/aspose.org-workflows", vdt.MANIFEST_PATH, runner=runner)

    def test_gh_binary_missing_raises_api_error(self):
        def runner(*args, **kwargs):
            raise FileNotFoundError("gh")
        with pytest.raises(vdt.DeployTriggerAPIError):
            vdt.list_path_commits("Aspose/aspose.org-workflows", vdt.MANIFEST_PATH, runner=runner)

    def test_unparseable_json_on_success_raises_api_error(self):
        """A 200 response with garbage JSON is not 'no more pages' either --
        it's a corrupted/unexpected response, distinct from exhausted
        pagination (which is a clean 200 with an empty array)."""
        from unittest.mock import MagicMock
        runner = MagicMock(return_value=MagicMock(returncode=0, stdout="not json{"))
        with pytest.raises(vdt.DeployTriggerAPIError):
            vdt.list_path_commits("Aspose/aspose.org-workflows", vdt.MANIFEST_PATH, runner=runner)

    def test_exhausted_pagination_still_returns_cleanly(self):
        """Regression guard: a genuinely empty page (200, empty array) is NOT
        an error -- pagination ending cleanly must keep working."""
        from unittest.mock import MagicMock
        runner = MagicMock(return_value=MagicMock(returncode=0, stdout="[]"))
        result = vdt.list_path_commits("Aspose/aspose.org-workflows", vdt.MANIFEST_PATH, runner=runner)
        assert result == []


class TestVerifyShaPropagatesAPIErrors:
    def test_verify_sha_propagates_error_from_commit_listing(self):
        """A failure fetching the commit list itself (the very first `gh api`
        call verify_sha() makes) must propagate all the way out -- never get
        swallowed into a PENDING VerificationResult."""
        from unittest.mock import MagicMock

        def fake_runner(args, **kwargs):
            if args[0] == "git":
                import subprocess as _subprocess
                return _subprocess.run(args, **kwargs)
            return MagicMock(
                returncode=1, stdout="",
                stderr="gh: API rate limit exceeded for installation ID 123. (HTTP 403)",
            )

        with pytest.raises(vdt.DeployTriggerAPIError):
            vdt.verify_sha(SHA_CONFIRMED, runner=fake_runner)

    def test_verify_sha_propagates_error_from_mid_poll_blob_fetch(self):
        """The commit list succeeds, but a blob fetch mid-poll fails non-404 --
        must still propagate, not silently degrade to PENDING."""
        import base64
        import json as _json
        from unittest.mock import MagicMock

        def fake_runner(args, **kwargs):
            joined = " ".join(args)
            if "commits?path=" in joined:
                return MagicMock(returncode=0, stdout=_json.dumps([
                    {"sha": c["sha"], "commit": {"author": {"date": c["date"]}, "message": c["message"]}}
                    for c in REAL_MANIFEST_COMMITS
                ]))
            # Every blob fetch fails with a simulated 5xx, including the ones
            # that have real fixture data -- proves the error isn't masked.
            return MagicMock(returncode=1, stdout="", stderr="gh: Internal Server Error (HTTP 500)")

        with pytest.raises(vdt.DeployTriggerAPIError, match="500"):
            vdt.verify_sha(SHA_CONFIRMED, runner=fake_runner)


# ---------------------------------------------------------------------------
# main() CLI wiring -- injected `runner` (a keyword-only testing seam added by
# TC-PKG-04-L3-FIX, mirroring every other function in this module) instead of
# monkeypatching module internals (AGENTS.md 16 bans Tier-1/2 patches).
# ---------------------------------------------------------------------------

class TestMainExitCodes:
    @staticmethod
    def _git_passthrough_runner(gh_response):
        """A runner that answers real `git` invocations for real (needed by
        sha_exists_locally/commit_date/is_ancestor against THIS repo's actual
        history) and returns `gh_response` for every `gh` invocation."""
        import subprocess as _subprocess

        def runner(args, **kwargs):
            if args[0] == "git":
                return _subprocess.run(args, **kwargs)
            return gh_response
        return runner

    def test_main_exits_distinct_code_on_gh_api_poll_failure(self, capsys):
        """The exact regression this taskcard exists to prevent: a rate-limited
        (or otherwise broken) gh api poll must exit loudly and distinctly --
        never exit 0 (indistinguishable from a clean verdict) and never reuse
        exit 2 (the pre-existing bad-SHA lookup error)."""
        from unittest.mock import MagicMock
        gh_response = MagicMock(
            returncode=1, stdout="",
            stderr="gh: API rate limit exceeded for installation ID 123. (HTTP 403)",
        )
        runner = self._git_passthrough_runner(gh_response)

        exit_code = vdt.main(["--sha", SHA_CONFIRMED], runner=runner)

        assert exit_code == vdt.EXIT_API_POLL_FAILURE
        assert exit_code == 3
        assert exit_code not in (vdt.EXIT_OK, vdt.EXIT_LOOKUP_ERROR, vdt.EXIT_DROPPED)
        captured = capsys.readouterr()
        assert "poll failed" in captured.err.lower()
        assert "PENDING" in captured.err  # explicitly disclaims being a PENDING verdict
        # No JSON verdict must be printed to stdout for a failed poll -- a
        # caller scripting against stdout must not see anything verdict-shaped.
        assert captured.out.strip() == ""

    def test_main_bad_sha_still_exits_2_unchanged(self, capsys):
        """Regression guard: the pre-existing lookup-error path (bad SHA) must
        keep its own exit code, distinct from the new API-failure code."""
        exit_code = vdt.main(["--sha", "0" * 40])
        assert exit_code == vdt.EXIT_LOOKUP_ERROR
        assert exit_code == 2
        assert exit_code != vdt.EXIT_API_POLL_FAILURE

    def test_main_confirmed_case_still_exits_0_with_injected_runner(self):
        """Regression guard: routing `runner` through main() must not disturb
        the real, previously-verified CONFIRMED_DEPLOYED case."""
        import base64
        import json as _json
        from unittest.mock import MagicMock
        import subprocess as _subprocess

        def fake_runner(args, **kwargs):
            if args[0] == "git":
                return _subprocess.run(args, **kwargs)
            joined = " ".join(args)
            if "commits?path=" in joined:
                return MagicMock(returncode=0, stdout=_json.dumps([
                    {"sha": c["sha"], "commit": {"author": {"date": c["date"]}, "message": c["message"]}}
                    for c in REAL_MANIFEST_COMMITS
                ]))
            for sha, blob in REAL_MANIFEST_BLOBS.items():
                if f"ref={sha}" in joined:
                    encoded = base64.b64encode(_json.dumps(blob).encode("utf-8")).decode("ascii")
                    return MagicMock(returncode=0, stdout=encoded)
            return MagicMock(returncode=1, stdout="", stderr="gh: Not Found (HTTP 404)")

        exit_code = vdt.main(["--sha", SHA_CONFIRMED], runner=fake_runner)
        assert exit_code == vdt.EXIT_OK == 0


# ---------------------------------------------------------------------------
# Secondary finding (TC-PKG-04-L3-REVIEW): a SHA predating ALL tracked scan
# history was mislabeled with a backwards "too recent" message. Verdict/exit
# code are unchanged (still PENDING/0, the safe side) -- only the message.
# ---------------------------------------------------------------------------

class TestClassifyShaPredatesAllHistory:
    def test_sha_older_than_earliest_cycle_gets_accurate_message(self):
        earliest = vdt.DeployCycle(
            scan_id="20260901-000000", content_sha="C1", previous_sha="P0",
            detected_at="2026-09-01T00:00:00+00:00", final_state="completed",
            completed_at="2026-09-01T01:00:00+00:00",
        )

        def fake_ancestor_check(a, b):
            # OLDSHA predates the earliest cycle's own baseline (P0) --
            # it's outside all tracked history, not "too recent".
            return {("OLDSHA", "P0"): True, ("OLDSHA", "C1"): True}.get((a, b), False)

        result = vdt.classify_sha(
            "OLDSHA", [earliest],
            ancestor_check=fake_ancestor_check,
            date_lookup=lambda s: (_ for _ in ()).throw(
                AssertionError("date_lookup should not be called on this path")
            ),
        )
        assert result.verdict == vdt.VERDICT_PENDING  # unchanged, safe side
        assert "predates" in result.detail.lower()
        assert "too recent" not in result.detail.lower()
        assert "20260901-000000" in result.detail

    def test_genuinely_new_sha_keeps_original_too_recent_message(self):
        """Regression guard: a SHA that's simply newer than anything scanned
        yet must keep the original (correct, for THAT case) wording."""
        earliest = vdt.DeployCycle(
            scan_id="20260901-000000", content_sha="C1", previous_sha="P0",
            detected_at="2026-09-01T00:00:00+00:00", final_state="completed",
            completed_at="2026-09-01T01:00:00+00:00",
        )

        def fake_ancestor_check(a, b):
            return False  # NEWSHA is not covered by, nor predates, anything

        result = vdt.classify_sha(
            "NEWSHA", [earliest],
            ancestor_check=fake_ancestor_check,
            date_lookup=lambda s: (_ for _ in ()).throw(
                AssertionError("date_lookup should not be called on this path")
            ),
        )
        assert result.verdict == vdt.VERDICT_PENDING
        assert "too recent" in result.detail.lower()

    def test_no_cycles_at_all_keeps_original_message(self):
        """No tracked history exists yet at all (cycles == []) -- must not
        crash on cycles[0], and must fall back to the generic message."""
        result = vdt.classify_sha("ANYSHA", [], ancestor_check=lambda a, b: False)
        assert result.verdict == vdt.VERDICT_PENDING
        assert "too recent" in result.detail.lower()
