"""Tests for lib/freshness_guard.py — the single source of truth for knowledge
bundle freshness, its 8-state model, and the collapsed baseline resolution order."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

_PIPELINE_DIR = Path(__file__).resolve().parents[1]
_LIB_DIR = _PIPELINE_DIR / "lib"
for p in (str(_PIPELINE_DIR), str(_LIB_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

import freshness_guard as fg


@pytest.fixture(autouse=True)
def _configure(tmp_path, monkeypatch):
    fg.configure(repo_root=tmp_path)
    # RC-freshness-guard-tree-identity (readme-refresh-hardening-and-regen-2026-08-30, TC-11):
    # the new reachability check reads core.clone_cache, which has no configure() seam of its
    # own -- it resolves purely from ASPOSE_CLONE_CACHE (or the real repo's runs/.clone_cache/
    # as an unwanted default). Without this, every EXISTING test in this file would have the
    # new check silently reach into the real repo's clone cache looking for whatever family/
    # platform string the test happens to use -- a real cross-contamination risk, not a
    # hypothetical one (this repo has real clones for common test names like "cells/net").
    # Pointing it at an empty tmp_path subdir makes clone_exists() reliably False for every
    # test that doesn't explicitly set up its own clone cache, which is the correct, safe
    # default (falls through to the pre-existing stale_since-only logic, unchanged).
    monkeypatch.setenv("ASPOSE_CLONE_CACHE", str(tmp_path / "_no_clone_cache"))
    yield
    fg.configure(repo_root=None)


def _write_model(tmp_path, family, platform, *, repo_sha="sha-1", stale_since=None, schema_version=2):
    merged = tmp_path / "knowledge" / family / platform / "merged"
    merged.mkdir(parents=True, exist_ok=True)
    model = {"repo_sha": repo_sha, "stale_since": stale_since, "schema_version": schema_version}
    (merged / "model.yaml").write_text(yaml.dump(model), encoding="utf-8")
    return merged


def _write_bundle_manifest(merged_dir, *, status="COMPLETE"):
    (merged_dir / "bundle_manifest.json").write_text(
        json.dumps({"status": status, "bundle_id": "b1"}), encoding="utf-8")


def _write_products_json(tmp_path, family, platform, *, clone_url="https://example.com/repo.git"):
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "products.json").write_text(
        json.dumps([{"family": family, "platform": platform, "clone_url": clone_url}]), encoding="utf-8")


def _write_upstream_baselines(tmp_path, entries: dict):
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "upstream_baselines.json").write_text(json.dumps(entries), encoding="utf-8")


class TestResolveBaseline:
    def test_prefers_model_yaml_over_projections(self, tmp_path):
        _write_model(tmp_path, "cells", "net", repo_sha="from-model")
        _write_upstream_baselines(tmp_path, {"cells/net": "from-projection"})
        sha, source = fg.resolve_baseline("cells", "net")
        assert sha == "from-model" and source == "model.yaml"

    def test_falls_back_to_upstream_baselines_when_no_model(self, tmp_path):
        _write_upstream_baselines(tmp_path, {"cells/net": "from-projection"})
        sha, source = fg.resolve_baseline("cells", "net")
        assert sha == "from-projection" and source == "upstream_baselines.json"

    def test_falls_back_to_knowledge_state_when_no_model_or_upstream_baselines(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "knowledge_state.json").write_text(
            json.dumps({"cells/net": {"accepted_baseline": {"repo_sha": "from-state"}}}), encoding="utf-8")
        sha, source = fg.resolve_baseline("cells", "net")
        assert sha == "from-state" and source == "knowledge_state.json"

    def test_falls_back_to_ledger_head(self, tmp_path):
        merged = tmp_path / "knowledge" / "cells" / "net" / "merged"
        merged.mkdir(parents=True)
        (merged / "baseline_ledger_head.json").write_text(
            json.dumps({"new_repo_sha": "from-ledger"}), encoding="utf-8")
        sha, source = fg.resolve_baseline("cells", "net")
        assert sha == "from-ledger" and source == "baseline_ledger_head.json"

    def test_returns_none_when_nothing_resolves(self, tmp_path):
        # baseline_resolver._sample_content_model_sha's default discover_content_fn
        # is not repo-root-isolated (scans the REAL repo's content/ tree) — patch it
        # out explicitly so this test proves the "truly nothing resolves" floor,
        # not "the real repo happens to have committed evidence for cells/net".
        with patch("baseline_resolver._sample_content_model_sha", return_value=None):
            sha, source = fg.resolve_baseline("cells", "net")
        assert sha is None and source == "none"


class TestDurableSourcesAgree:
    def test_agree_when_only_one_source_present(self, tmp_path):
        _write_model(tmp_path, "cells", "net", repo_sha="sha-1")
        agree, detail = fg._durable_sources_agree("cells", "net")
        assert agree is True

    def test_disagree_when_model_and_projection_differ(self, tmp_path):
        _write_model(tmp_path, "cells", "net", repo_sha="sha-model")
        _write_upstream_baselines(tmp_path, {"cells/net": "sha-projection-DIFFERENT"})
        agree, detail = fg._durable_sources_agree("cells", "net")
        assert agree is False
        assert detail["model.yaml"] == "sha-model"
        assert detail["upstream_baselines.json"] == "sha-projection-DIFFERENT"

    def test_agree_when_all_sources_match(self, tmp_path):
        _write_model(tmp_path, "cells", "net", repo_sha="sha-1")
        _write_upstream_baselines(tmp_path, {"cells/net": "sha-1"})
        agree, _ = fg._durable_sources_agree("cells", "net")
        assert agree is True


class TestCheckFreshnessStates:
    def test_provenance_missing_when_no_model_yaml(self, tmp_path):
        result = fg.check_freshness("cells", "net", mode="degraded")
        assert result.state == "PROVENANCE_MISSING"

    def test_current_in_degraded_mode_when_no_stale_flag(self, tmp_path):
        _write_model(tmp_path, "cells", "net", stale_since=None)
        result = fg.check_freshness("cells", "net", mode="degraded")
        assert result.state == "CURRENT"

    def test_stale_in_degraded_mode_when_stale_since_set(self, tmp_path):
        _write_model(tmp_path, "cells", "net", stale_since="2026-08-14")
        result = fg.check_freshness("cells", "net", mode="degraded")
        assert result.state == "STALE"

    def test_corrupt_when_durable_sources_disagree(self, tmp_path):
        _write_model(tmp_path, "cells", "net", repo_sha="sha-model")
        _write_upstream_baselines(tmp_path, {"cells/net": "sha-DIFFERENT"})
        result = fg.check_freshness("cells", "net", mode="degraded")
        assert result.state == "CORRUPT"

    def test_corrupt_when_bundle_manifest_status_not_complete(self, tmp_path):
        merged = _write_model(tmp_path, "cells", "net")
        _write_bundle_manifest(merged, status="IN_PROGRESS")
        result = fg.check_freshness("cells", "net", mode="degraded")
        assert result.state == "CORRUPT"

    def test_current_when_bundle_manifest_complete(self, tmp_path):
        merged = _write_model(tmp_path, "cells", "net")
        _write_bundle_manifest(merged, status="COMPLETE")
        result = fg.check_freshness("cells", "net", mode="degraded")
        assert result.state == "CURRENT"

    def test_refreshing_when_regen_lock_held(self, tmp_path):
        _write_model(tmp_path, "cells", "net")
        from knowledge_regen_lock import acquire_regen_lock
        lock = acquire_regen_lock("cells", "net", owner="test", knowledge_root=fg.KNOWLEDGE_ROOT)
        with lock:
            result = fg.check_freshness("cells", "net", mode="degraded")
        assert result.state == "REFRESHING"

    def test_refresh_failed_when_marker_present(self, tmp_path):
        _write_model(tmp_path, "cells", "net")
        fg.mark_regen_failed("cells", "net", reason="enrich.py timed out")
        result = fg.check_freshness("cells", "net", mode="degraded")
        assert result.state == "REFRESH_FAILED"
        assert "enrich.py timed out" in result.reason

    def test_refresh_failed_cleared_by_mark_succeeded(self, tmp_path):
        _write_model(tmp_path, "cells", "net")
        fg.mark_regen_failed("cells", "net", reason="boom")
        fg.mark_regen_succeeded("cells", "net")
        result = fg.check_freshness("cells", "net", mode="degraded")
        assert result.state != "REFRESH_FAILED"

    def test_offline_mode_never_touches_network_and_ignores_stale_flag(self, tmp_path):
        _write_model(tmp_path, "cells", "net", stale_since="2026-08-14")
        with patch.object(fg, "_live_upstream_sha") as mock_live:
            result = fg.check_freshness("cells", "net", mode="offline")
        mock_live.assert_not_called()
        assert result.state == "CURRENT"
        assert "offline" in result.reason

    def test_strict_mode_current_when_live_sha_matches(self, tmp_path):
        _write_model(tmp_path, "cells", "net", repo_sha="sha-1")
        _write_products_json(tmp_path, "cells", "net")
        with patch.object(fg, "_live_upstream_sha", return_value="sha-1"):
            result = fg.check_freshness("cells", "net", mode="strict")
        assert result.state == "CURRENT"

    def test_strict_mode_stale_when_live_sha_differs(self, tmp_path):
        _write_model(tmp_path, "cells", "net", repo_sha="sha-old")
        _write_products_json(tmp_path, "cells", "net")
        with patch.object(fg, "_live_upstream_sha", return_value="sha-new"):
            result = fg.check_freshness("cells", "net", mode="strict")
        assert result.state == "STALE"
        assert result.live_sha == "sha-new"

    def test_strict_mode_upstream_unavailable_never_downgrades_silently(self, tmp_path):
        _write_model(tmp_path, "cells", "net", repo_sha="sha-1")
        _write_products_json(tmp_path, "cells", "net")
        with patch.object(fg, "_live_upstream_sha", return_value=None):
            result = fg.check_freshness("cells", "net", mode="strict")
        assert result.state == "UPSTREAM_UNAVAILABLE"

    def test_strict_mode_upstream_unavailable_when_no_repo_url(self, tmp_path):
        _write_model(tmp_path, "cells", "net", repo_sha="sha-1")
        # no products.json at all
        result = fg.check_freshness("cells", "net", mode="strict")
        assert result.state == "UPSTREAM_UNAVAILABLE"

    def test_invalid_mode_raises(self, tmp_path):
        with pytest.raises(ValueError):
            fg.check_freshness("cells", "net", mode="not-a-real-mode")


def _run_git(args, cwd):
    import subprocess
    r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                        encoding="utf-8", errors="replace", timeout=30)
    assert r.returncode == 0, f"git {args} failed: {r.stderr}"
    return r.stdout.strip()


def _make_clone_cache(tmp_path, family, platform, monkeypatch):
    """A real local git repo standing in for the clone cache, matching this plan's
    established real-git-repo testing convention (never a mocked subprocess for
    this class of test)."""
    clone_cache_root = tmp_path / "clone_cache"
    clone_dir = clone_cache_root / f"aspose_{family}_{platform}"
    clone_dir.mkdir(parents=True)
    (clone_dir / "README.md").write_text("v1\n", encoding="utf-8")
    _run_git(["init", "-q", "-b", "main"], clone_dir)
    _run_git(["config", "user.email", "test@example.com"], clone_dir)
    _run_git(["config", "user.name", "Test"], clone_dir)
    _run_git(["add", "."], clone_dir)
    _run_git(["commit", "-q", "-m", "initial"], clone_dir)
    monkeypatch.setenv("ASPOSE_CLONE_CACHE", str(clone_cache_root))
    return clone_dir


def _rewrite_history_with_fresh_root_commit(clone_dir, *, content: "str | None" = None):
    """Faithfully reproduces the real font/python incident's mechanism -- a mirror sync
    that replaces the entire history with a fresh, zero-parent commit -- NOT
    `git commit --amend`, which leaves the old commit object dangling but still
    physically present (`cat-file -e` visible) in the same repo's object store.
    `update_clone()`'s real `git fetch --depth=2` against a genuinely rewritten
    remote never downloads objects unreachable from the new tip at all, so the old
    object is truly ABSENT afterward, not merely unreferenced -- this rebuilds that
    exact condition by re-initializing the repo from scratch. `content=None` means
    "same file content as before" (the content-identical rewrite case);
    a real string means "genuinely different content" (the content-changed case).
    """
    existing = (clone_dir / "README.md").read_text(encoding="utf-8")
    keep = existing if content is None else content
    import os
    import shutil
    import stat

    def _force_remove_readonly(func, path, exc_info):
        # Windows stores real git object files read-only; shutil.rmtree can't
        # delete them without clearing that bit first (a well-known Windows/git
        # rmtree gotcha, not specific to this test).
        os.chmod(path, stat.S_IWRITE)
        func(path)

    shutil.rmtree(clone_dir / ".git", onexc=_force_remove_readonly)
    (clone_dir / "README.md").write_text(keep, encoding="utf-8")
    _run_git(["init", "-q", "-b", "main"], clone_dir)
    _run_git(["config", "user.email", "test@example.com"], clone_dir)
    _run_git(["config", "user.name", "Test"], clone_dir)
    _run_git(["add", "."], clone_dir)
    _run_git(["commit", "-q", "-m", "mirror resync"], clone_dir)


def _record_ledger_entry(tmp_path, family, platform, *, new_repo_sha, repo_tree_sha):
    sys.path.insert(0, str(_LIB_DIR))
    from baseline_ledger import BaselineLedger
    ledger = BaselineLedger(family, platform, repo_root=tmp_path)
    ledger.append(
        new_repo_sha=new_repo_sha, sha_source="scout", run_id="RUN-TEST",
        status="accepted", accepted_at="2026-08-31T00:00:00Z", repo_tree_sha=repo_tree_sha,
    )


class TestBaselineTreeIdentity:
    """RC-1 / TC-11 (readme-refresh-hardening-and-regen-2026-08-30): the reachability
    + tree-identity check, using real local git repos throughout -- no mocked git
    subprocess calls for this mechanism specifically, since the whole point is
    proving real git plumbing (cat-file -e, rev-parse ^{tree}) behaves as designed."""

    def test_reachable_baseline_falls_through_unchanged(self, tmp_path, monkeypatch):
        clone_dir = _make_clone_cache(tmp_path, "cells", "net", monkeypatch)
        head_sha = _run_git(["rev-parse", "HEAD"], clone_dir)
        _write_model(tmp_path, "cells", "net", repo_sha=head_sha, stale_since=None)
        result = fg.check_freshness("cells", "net", mode="degraded")
        # A reachable baseline must produce the ordinary CURRENT verdict -- the new
        # check is invisible on the (common) non-orphaned path.
        assert result.state == "CURRENT"

    def test_unreachable_with_identical_tree_is_history_rewritten(self, tmp_path, monkeypatch):
        """The font/python reproduction: the recorded baseline commit is gone (a real
        history rewrite), but the real content is byte-identical."""
        clone_dir = _make_clone_cache(tmp_path, "cells", "net", monkeypatch)
        orphaned_sha = _run_git(["rev-parse", "HEAD"], clone_dir)
        tree_sha = _run_git(["rev-parse", "HEAD^{tree}"], clone_dir)
        _record_ledger_entry(tmp_path, "cells", "net", new_repo_sha=orphaned_sha, repo_tree_sha=tree_sha)
        _rewrite_history_with_fresh_root_commit(clone_dir)  # content=None -> identical
        new_head = _run_git(["rev-parse", "HEAD"], clone_dir)
        new_tree = _run_git(["rev-parse", "HEAD^{tree}"], clone_dir)
        assert new_head != orphaned_sha  # the commit genuinely changed
        assert new_tree == tree_sha  # but the tree (real content) did not
        _write_model(tmp_path, "cells", "net", repo_sha=orphaned_sha, stale_since=None)

        result = fg.check_freshness("cells", "net", mode="degraded")
        assert result.state == "HISTORY_REWRITTEN_CONTENT_IDENTICAL"
        allowed, _ = fg.is_generation_allowed("cells", "net", mode="degraded")
        assert allowed is True

    def test_unreachable_with_different_tree_is_stale_orphaned(self, tmp_path, monkeypatch):
        """The slides/python reproduction: same orphaned-baseline SHAPE, but the tree
        genuinely differs -- real content drift, must NOT be treated as safe."""
        clone_dir = _make_clone_cache(tmp_path, "cells", "net", monkeypatch)
        orphaned_sha = _run_git(["rev-parse", "HEAD"], clone_dir)
        tree_sha = _run_git(["rev-parse", "HEAD^{tree}"], clone_dir)
        _record_ledger_entry(tmp_path, "cells", "net", new_repo_sha=orphaned_sha, repo_tree_sha=tree_sha)
        _rewrite_history_with_fresh_root_commit(clone_dir, content="v2 -- a real change\n")
        new_tree = _run_git(["rev-parse", "HEAD^{tree}"], clone_dir)
        assert new_tree != tree_sha
        _write_model(tmp_path, "cells", "net", repo_sha=orphaned_sha, stale_since=None)

        result = fg.check_freshness("cells", "net", mode="degraded")
        assert result.state == "STALE_ORPHANED"
        allowed, _ = fg.is_generation_allowed("cells", "net", mode="degraded")
        assert allowed is False

    def test_the_falsifiable_test_one_mechanism_two_opposite_correct_answers(self, tmp_path, monkeypatch):
        """The plan's own acceptance criterion, verbatim: one freshness mechanism must
        return 'proceed' for a font/python-shaped case and 'block' for a
        slides/python-shaped case -- both are 'baseline commit unreachable', the
        ONLY thing distinguishing them is real tree-content identity. Exercises both
        shapes in a single test to prove it's the same function, same code path,
        producing opposite verdicts from the same structural input."""
        for platform, real_change, expected_state, expected_allowed in [
            ("identical_case", False, "HISTORY_REWRITTEN_CONTENT_IDENTICAL", True),
            ("changed_case", True, "STALE_ORPHANED", False),
        ]:
            clone_dir = _make_clone_cache(tmp_path, "family", platform, monkeypatch)
            orphaned_sha = _run_git(["rev-parse", "HEAD"], clone_dir)
            tree_sha = _run_git(["rev-parse", "HEAD^{tree}"], clone_dir)
            _record_ledger_entry(tmp_path, "family", platform, new_repo_sha=orphaned_sha, repo_tree_sha=tree_sha)
            _rewrite_history_with_fresh_root_commit(
                clone_dir, content=("changed\n" if real_change else None),
            )
            _write_model(tmp_path, "family", platform, repo_sha=orphaned_sha, stale_since=None)

            result = fg.check_freshness("family", platform, mode="degraded")
            allowed, _ = fg.is_generation_allowed("family", platform, mode="degraded")
            assert result.state == expected_state, f"{platform}: {result.state} != {expected_state}"
            assert allowed is expected_allowed, f"{platform}: allowed={allowed} != {expected_allowed}"

    def test_unreachable_with_no_recorded_tree_sha_is_conservatively_stale_orphaned(self, tmp_path, monkeypatch):
        """A pre-TC-10 baseline (or a promote that ran without clone-cache access) has
        no repo_tree_sha recorded at all -- must never be silently treated as safe."""
        clone_dir = _make_clone_cache(tmp_path, "cells", "net", monkeypatch)
        orphaned_sha = _run_git(["rev-parse", "HEAD"], clone_dir)
        # Deliberately no _record_ledger_entry call -- nothing in the ledger for this sha.
        _rewrite_history_with_fresh_root_commit(clone_dir)
        _write_model(tmp_path, "cells", "net", repo_sha=orphaned_sha, stale_since=None)

        result = fg.check_freshness("cells", "net", mode="degraded")
        assert result.state == "STALE_ORPHANED"
        assert "no recorded tree SHA" in result.reason

    def test_dangling_but_present_orphan_with_no_ledger_entry_is_still_history_rewritten(
        self, tmp_path, monkeypatch,
    ):
        """RC-1 follow-up (found live during the font/python TC-27b canary, not a
        synthesized case): reproduces the REAL font/python shape using `git commit
        --amend` (the old commit stays dangling-but-`cat-file -e`-visible), not
        `_rewrite_history_with_fresh_root_commit`'s full re-init (which genuinely
        removes the object) -- the two prior tests above never exercised git's
        actual object-retention behavior on a real mirror-resync-shaped rewrite.
        Deliberately NO ledger entry recorded for the orphaned sha (pre-TC-10-style
        baseline, exactly font/python's real live state): before this fix, the pre-
        existing `git_reachable` bug (`cat-file -e` instead of `merge-base
        --is-ancestor`) made this silently resolve CURRENT; the fix's live-git
        fallback (`_orphaned_commit_tree_sha`) must still correctly classify it
        HISTORY_REWRITTEN_CONTENT_IDENTICAL because the dangling object is directly
        `rev-parse`-able, with no ledger record needed."""
        clone_dir = _make_clone_cache(tmp_path, "font", "python", monkeypatch)
        orphaned_sha = _run_git(["rev-parse", "HEAD"], clone_dir)
        tree_sha = _run_git(["rev-parse", "HEAD^{tree}"], clone_dir)
        _run_git(["commit", "--amend", "-q", "-m", "mirror resync"], clone_dir)
        new_head = _run_git(["rev-parse", "HEAD"], clone_dir)
        new_tree = _run_git(["rev-parse", "HEAD^{tree}"], clone_dir)
        assert new_head != orphaned_sha  # the commit genuinely changed identity
        assert new_tree == tree_sha  # content is byte-identical (amend didn't touch files)
        # No _record_ledger_entry call -- the real font/python ledger entry pre-dates TC-10.
        _write_model(tmp_path, "font", "python", repo_sha=orphaned_sha, stale_since=None)

        result = fg.check_freshness("font", "python", mode="degraded")
        assert result.state == "HISTORY_REWRITTEN_CONTENT_IDENTICAL"
        assert "live" in result.reason  # provenance disclosed: not a ledger-recorded value
        allowed, _ = fg.is_generation_allowed("font", "python", mode="degraded")
        assert allowed is True

    def test_no_clone_cache_falls_through_to_old_behavior(self, tmp_path, monkeypatch):
        """No clone cache reachable at all (cold-start / CI without a clone) must not
        break -- falls through to the pre-existing stale_since-only degraded logic."""
        monkeypatch.setenv("ASPOSE_CLONE_CACHE", str(tmp_path / "_never_created"))
        _write_model(tmp_path, "cells", "net", repo_sha="sha-with-no-clone", stale_since=None)
        result = fg.check_freshness("cells", "net", mode="degraded")
        assert result.state == "CURRENT"

    def test_offline_mode_ignores_orphaned_baseline_by_contract(self, tmp_path, monkeypatch):
        """offline mode must never touch the filesystem beyond resolve_baseline() --
        an orphaned/content-changed baseline must not surface here at all."""
        clone_dir = _make_clone_cache(tmp_path, "cells", "net", monkeypatch)
        orphaned_sha = _run_git(["rev-parse", "HEAD"], clone_dir)
        tree_sha = _run_git(["rev-parse", "HEAD^{tree}"], clone_dir)
        _record_ledger_entry(tmp_path, "cells", "net", new_repo_sha=orphaned_sha, repo_tree_sha=tree_sha)
        _rewrite_history_with_fresh_root_commit(clone_dir, content="changed\n")
        _write_model(tmp_path, "cells", "net", repo_sha=orphaned_sha, stale_since=None)

        result = fg.check_freshness("cells", "net", mode="offline")
        assert result.state == "CURRENT"  # unchanged offline-mode contract, orphan check never runs

    def test_strict_mode_short_circuits_before_the_live_network_call(self, tmp_path, monkeypatch):
        """The orphan check must run BEFORE strict mode's live ls-remote comparison --
        a raw SHA-string mismatch against a live remote is exactly the wrong signal
        once the baseline is already known to be a content-identical orphan."""
        clone_dir = _make_clone_cache(tmp_path, "cells", "net", monkeypatch)
        orphaned_sha = _run_git(["rev-parse", "HEAD"], clone_dir)
        tree_sha = _run_git(["rev-parse", "HEAD^{tree}"], clone_dir)
        _record_ledger_entry(tmp_path, "cells", "net", new_repo_sha=orphaned_sha, repo_tree_sha=tree_sha)
        _rewrite_history_with_fresh_root_commit(clone_dir)
        _write_model(tmp_path, "cells", "net", repo_sha=orphaned_sha, stale_since=None)
        _write_products_json(tmp_path, "cells", "net")

        with patch.object(fg, "_live_upstream_sha") as mock_live:
            result = fg.check_freshness("cells", "net", mode="strict")
        mock_live.assert_not_called()
        assert result.state == "HISTORY_REWRITTEN_CONTENT_IDENTICAL"


class TestIsGenerationAllowed:
    def test_allowed_true_for_current(self, tmp_path):
        _write_model(tmp_path, "cells", "net")
        allowed, result = fg.is_generation_allowed("cells", "net", mode="degraded")
        assert allowed is True
        assert result.state == "CURRENT"

    def test_allowed_false_for_stale(self, tmp_path):
        _write_model(tmp_path, "cells", "net", stale_since="2026-08-14")
        allowed, result = fg.is_generation_allowed("cells", "net", mode="degraded")
        assert allowed is False
        assert result.state == "STALE"

    def test_last_known_good_requires_explicit_opt_in(self, tmp_path):
        _write_model(tmp_path, "cells", "net", repo_sha="sha-1")
        _write_products_json(tmp_path, "cells", "net")
        with patch.object(fg, "_live_upstream_sha", return_value=None):
            allowed, result = fg.is_generation_allowed(
                "cells", "net", mode="strict", allow_last_known_good=False)
        assert allowed is False
        assert result.state == "UPSTREAM_UNAVAILABLE"

    def test_last_known_good_allowed_when_opted_in_and_bundle_exists(self, tmp_path):
        _write_model(tmp_path, "cells", "net", repo_sha="sha-1")
        _write_products_json(tmp_path, "cells", "net")
        with patch.object(fg, "_live_upstream_sha", return_value=None):
            allowed, result = fg.is_generation_allowed(
                "cells", "net", mode="strict", allow_last_known_good=True)
        assert allowed is True
        assert result.state == "LAST_KNOWN_GOOD"

    def test_last_known_good_is_audit_logged(self, tmp_path):
        _write_model(tmp_path, "cells", "net", repo_sha="sha-1")
        _write_products_json(tmp_path, "cells", "net")
        with patch.object(fg, "_live_upstream_sha", return_value=None):
            fg.is_generation_allowed("cells", "net", mode="strict", allow_last_known_good=True)
        assert fg.LAST_KNOWN_GOOD_LOG.is_file()
        entry = json.loads(fg.LAST_KNOWN_GOOD_LOG.read_text(encoding="utf-8").strip().splitlines()[-1])
        assert entry["family"] == "cells" and entry["platform"] == "net"

    def test_last_known_good_not_allowed_without_prior_bundle(self, tmp_path):
        # no model.yaml at all -> PROVENANCE_MISSING, not eligible for LKG fallback
        allowed, result = fg.is_generation_allowed(
            "cells", "net", mode="strict", allow_last_known_good=True)
        assert allowed is False
        assert result.state == "PROVENANCE_MISSING"

    def test_corrupt_never_allowed_even_with_last_known_good(self, tmp_path):
        _write_model(tmp_path, "cells", "net", repo_sha="sha-model")
        _write_upstream_baselines(tmp_path, {"cells/net": "sha-DIFFERENT"})
        allowed, result = fg.is_generation_allowed(
            "cells", "net", mode="degraded", allow_last_known_good=True)
        assert allowed is False
        assert result.state == "CORRUPT"
