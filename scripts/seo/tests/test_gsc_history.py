"""Tests for scripts/seo/pipeline/gsc_history.py, built for
SEO-GSC-HISTORY-ASOF-BOUNDARY-RESOLVER-1: `find_snapshot_asof`'s
direction="after" branch used to silently exclude a commit whose timestamp
exactly equalled `target_date` (a strict `>` where the docstring promises an
inclusive "on or after"), unlike the symmetric, correctly-inclusive
direction="before" branch. No test file existed for this module before this
card -- it exercises real weekly-snapshot-shaped commits in a disposable,
isolated `git init` repo (never the real shared repo or its `.git/config`),
mirroring the established convention already used elsewhere in this test
suite (see test_git_identity_guard.py) for git-history-dependent modules.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[2]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from seo.pipeline import gsc_history as gh  # noqa: E402


def _git(repo: Path, *args: str, env: "dict[str, str] | None" = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=True, env=env,
    )


def _commit_snapshot(repo: Path, site: str, records: list, *, author_date_iso: str) -> str:
    """Write keywords/<site>.aspose.org.json and commit it with an explicit
    author date (the collector's real weekly-Sunday commit timestamp), so
    tests can construct exact-boundary scenarios deterministically rather
    than relying on wall-clock timing. `author_date_iso` is also embedded in
    the written payload (a real collector snapshot's own `lastUpdated`-style
    field always changes week to week) so two calls with the same `records`
    still produce a real, committable diff rather than a silent no-op."""
    keywords_dir = repo / "keywords"
    keywords_dir.mkdir(exist_ok=True)
    path = keywords_dir / f"{site}.aspose.org.json"
    # gsc_history.load_snapshot() requires a top-level JSON array (real
    # Schema B shape); prepend a harmless marker record carrying the date so
    # two commits with otherwise-identical `records` still produce a real,
    # committable diff rather than a silent no-op.
    payload = [{"_test_snapshot_date": author_date_iso}, *records]
    path.write_text(json.dumps(payload), encoding="utf-8")
    _git(repo, "add", str(path.relative_to(repo)))
    import os
    full_env = {
        **os.environ,
        "GIT_AUTHOR_DATE": author_date_iso,
        "GIT_COMMITTER_DATE": author_date_iso,
    }
    _git(repo, "commit", "-q", "-m", f"Update queries for {site}.aspose.org", env=full_env)
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


@pytest.fixture
def repo(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    _git(work, "init", "-q", "-b", "main")
    _git(work, "config", "user.email", "test@test.com")
    _git(work, "config", "user.name", "Test")
    # A real repo is never truly commit-less; seed one unrelated commit so
    # `git log --follow` on a site with zero snapshots ever still runs
    # cleanly instead of hitting the "does not have any commits yet" edge
    # case of a literally brand-new repo, which is not the real domain.
    (work / "README.md").write_text("seed", encoding="utf-8")
    _git(work, "add", "README.md")
    _git(work, "commit", "-q", "-m", "seed")
    gh.configure(repo_root=work)
    yield work
    gh.configure()


def _dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


class TestFindSnapshotAsofBoundary:
    def test_before_direction_includes_an_exact_timestamp_match(self, repo):
        sha = _commit_snapshot(repo, "docs", [], author_date_iso="2026-08-16T00:00:00+00:00")
        found = gh.find_snapshot_asof("docs", _dt("2026-08-16T00:00:00+00:00"), direction="before")
        assert found is not None
        assert found["sha"] == sha

    def test_after_direction_includes_an_exact_timestamp_match(self, repo):
        """The regression this card exists to fix: direction='after' must be
        just as inclusive of an exact match as direction='before' is."""
        sha = _commit_snapshot(repo, "docs", [], author_date_iso="2026-08-16T00:00:00+00:00")
        found = gh.find_snapshot_asof("docs", _dt("2026-08-16T00:00:00+00:00"), direction="after")
        assert found is not None
        assert found["sha"] == sha

    def test_before_direction_picks_the_latest_commit_not_after_target(self, repo):
        older = _commit_snapshot(repo, "docs", [], author_date_iso="2026-08-09T00:00:00+00:00")
        _commit_snapshot(repo, "docs", [], author_date_iso="2026-08-23T00:00:00+00:00")
        found = gh.find_snapshot_asof("docs", _dt("2026-08-16T00:00:00+00:00"), direction="before")
        assert found is not None
        assert found["sha"] == older

    def test_after_direction_picks_the_earliest_commit_not_before_target(self, repo):
        _commit_snapshot(repo, "docs", [], author_date_iso="2026-08-09T00:00:00+00:00")
        newer = _commit_snapshot(repo, "docs", [], author_date_iso="2026-08-23T00:00:00+00:00")
        found = gh.find_snapshot_asof("docs", _dt("2026-08-16T00:00:00+00:00"), direction="after")
        assert found is not None
        assert found["sha"] == newer

    def test_no_commit_in_either_direction_returns_none(self, repo):
        assert gh.find_snapshot_asof("docs", _dt("2026-08-16T00:00:00+00:00"), direction="before") is None
        assert gh.find_snapshot_asof("docs", _dt("2026-08-16T00:00:00+00:00"), direction="after") is None

    def test_target_date_before_first_ever_commit_has_no_before_match(self, repo):
        _commit_snapshot(repo, "docs", [], author_date_iso="2026-08-16T00:00:00+00:00")
        assert gh.find_snapshot_asof("docs", _dt("2026-01-01T00:00:00+00:00"), direction="before") is None

    def test_target_date_after_last_ever_commit_has_no_after_match(self, repo):
        _commit_snapshot(repo, "docs", [], author_date_iso="2026-08-16T00:00:00+00:00")
        assert gh.find_snapshot_asof("docs", _dt("2026-12-31T00:00:00+00:00"), direction="after") is None

    def test_naive_target_date_is_treated_as_utc(self, repo):
        sha = _commit_snapshot(repo, "docs", [], author_date_iso="2026-08-16T00:00:00+00:00")
        found = gh.find_snapshot_asof("docs", datetime(2026, 8, 16), direction="after")
        assert found is not None
        assert found["sha"] == sha

    def test_invalid_direction_raises(self, repo):
        with pytest.raises(gh.GscHistoryError):
            gh.find_snapshot_asof("docs", _dt("2026-08-16T00:00:00+00:00"), direction="sideways")


class TestGetUrlRecordAsof:
    def test_returns_none_when_url_not_in_the_matched_snapshot(self, repo):
        _commit_snapshot(
            repo, "docs",
            [{"url": "https://docs.aspose.org/other/", "queries": []}],
            author_date_iso="2026-08-16T00:00:00+00:00",
        )
        result = gh.get_url_record_asof(
            "docs", "https://docs.aspose.org/target/", _dt("2026-08-20T00:00:00+00:00"), direction="before",
        )
        assert result is None

    def test_returns_the_real_record_including_snapshot_provenance(self, repo):
        sha = _commit_snapshot(
            repo, "docs",
            [{"url": "https://docs.aspose.org/target/", "queries": [{"impressions": 10}]}],
            author_date_iso="2026-08-16T00:00:00+00:00",
        )
        result = gh.get_url_record_asof(
            "docs", "https://docs.aspose.org/target/", _dt("2026-08-16T00:00:00+00:00"), direction="after",
        )
        assert result is not None
        assert result["_snapshot_sha"] == sha
        assert result["queries"] == [{"impressions": 10}]


class TestAggregateMetrics:
    def test_none_record_returns_none(self):
        assert gh.aggregate_metrics(None) is None

    def test_zero_impressions_returns_none_not_a_fabricated_zero(self):
        record = {"queries": [{"impressions": 0, "clicks": 0, "position": 0}]}
        assert gh.aggregate_metrics(record) is None

    def test_real_weighted_rollup(self):
        record = {
            "queries": [
                {"impressions": 100, "clicks": 10, "position": 5.0},
                {"impressions": 300, "clicks": 3, "position": 15.0},
            ],
            "_snapshot_sha": "abc123",
            "_snapshot_date": "2026-08-16T00:00:00+00:00",
        }
        result = gh.aggregate_metrics(record)
        assert result is not None
        assert result["impressions"] == 400
        assert result["clicks"] == 13
        assert result["ctr"] == pytest.approx(13 / 400)
        # weighted position: (5*100 + 15*300) / 400 = (500+4500)/400 = 12.5
        assert result["position"] == pytest.approx(12.5)
        assert result["query_count"] == 2
        assert result["snapshot_sha"] == "abc123"
