"""Tests for lib/stale_file_regression.py — the OID window engine
(2026-08-30, stale-guard plan T1 / TC-SG-04).

Every fixture here encodes a defect class established with evidence in the
plan: the MT018 replay, the 2026-08-07 pre-session revert (RC0 → lookback
class), side-branch merges the old ancestry predicate missed (A3), quotepath
path-dropping (A1), autocrlf worktrees (RC1's CRLF face), deletion semantics
(A6), the explicit-base-not-ancestor gate (A4), and the lookback commit cap.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_PIPELINE_DIR = _TESTS_DIR.parent
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

from lib import stale_file_regression as slib  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_lib():
    yield
    slib.configure()


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True,
        text=True, encoding="utf-8", errors="replace", check=False,
    )


def _init(tmp_path: Path, **config: str) -> Path:
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    for key, value in config.items():
        _git(repo, "config", key.replace("_", "."), value)
    return repo


def _commit(repo: Path, name: str, content: bytes, msg: str = "c") -> str:
    p = repo / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)
    _git(repo, "add", name)
    _git(repo, "commit", "-q", "-m", msg)
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _stage(repo: Path, name: str, content: bytes) -> None:
    (repo / name).write_bytes(content)
    _git(repo, "add", name)


def _head(repo: Path) -> str:
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _explicit_baseline(base: str) -> slib.Baseline:
    return slib.Baseline(window_sha=base, source="explicit",
                         session_sha=base, session_id=None)


def _detect(repo: Path, paths, baseline, mode="index"):
    return slib.detect_regressions(paths, baseline=baseline, head=_head(repo),
                                   mode=mode, repo_root=repo,
                                   content_prefix_session_only=True)


def test_mt018_incident_replay_session_class_blocks(tmp_path):
    repo = _init(tmp_path)
    base = _commit(repo, "data/targets.json", b'{"url": "404"}\n', "seed wrong")
    _commit(repo, "data/targets.json", b'{"url": "ok"}\n', "fix by another session")
    _stage(repo, "data/targets.json", b'{"url": "404"}\n')

    report = _detect(repo, ["data/targets.json"], _explicit_baseline(base))

    assert report.status == "regression"
    finding = report.findings[0]
    assert finding.finding_class == "session"
    assert [f.path for f in report.blocking(wide_findings="warn")] == ["data/targets.json"]


def test_pre_session_revert_is_lookback_class(tmp_path):
    """RC0 (`55586b637c`): the intervening commit predates the session's own
    base -- invisible to the old window, warn-class under the soak policy,
    blocking under wide_findings=block."""
    repo = _init(tmp_path)
    _commit(repo, "k.json", b"old\n", "seed")
    _commit(repo, "k.json", b"refreshed\n", "refresh 5 days ago")
    session_base = _commit(repo, "other.txt", b"x\n", "session starts after the refresh")
    _stage(repo, "k.json", b"old\n")  # 'pre-existing content found staged'

    baseline = slib.resolve_baseline(
        explicit_sha=None,
        session_ctx=type("Ctx", (), {"status": "resolved", "session_id": "s1",
                                     "base_sha": session_base})(),
        head=_head(repo), repo_root=repo,
    )
    assert baseline.source == "lookback"          # the wider window won
    assert baseline.session_sha == session_base   # classing anchor kept

    report = _detect(repo, ["k.json"], baseline)
    finding = report.findings[0]
    assert finding.finding_class == "lookback"
    assert report.blocking(wide_findings="warn") == []
    assert [f.path for f in report.blocking(wide_findings="block")] == ["k.json"]


def test_side_branch_merge_counts_as_intervening(tmp_path):
    """A3: a fix committed on a branch BEFORE the session base but merged
    AFTER it. The old `merge-base --is-ancestor(base, L)` predicate returned
    None for it; membership in base..head via first-parent log catches the
    merge as the toucher."""
    repo = _init(tmp_path)
    _commit(repo, "f.txt", b"wrong\n", "c0")
    _git(repo, "checkout", "-q", "-b", "side")
    _commit(repo, "f.txt", b"right\n", "fix on side branch")
    _git(repo, "checkout", "-q", "main")
    base = _commit(repo, "other.txt", b"x\n", "session base on main")
    _git(repo, "merge", "-q", "--no-ff", "-m", "merge side", "side")
    _stage(repo, "f.txt", b"wrong\n")

    report = _detect(repo, ["f.txt"], _explicit_baseline(base))

    assert [f.path for f in report.findings] == ["f.txt"]
    assert report.findings[0].finding_class == "session"


def test_quotepath_true_nonascii_path_still_checked(tmp_path):
    """A1: with core.quotepath=true (the default everywhere but this repo's
    own machine), text listings octal-escape non-ASCII paths; the NUL/bytes
    pipeline must keep them in the intersection."""
    repo = _init(tmp_path, core_quotepath="true")
    name = "docs/nötes-ü.md"
    base = _commit(repo, name, b"wrong\n", "seed")
    _commit(repo, name, b"right\n", "fix")
    _stage(repo, name, b"wrong\n")

    report = _detect(repo, [name], _explicit_baseline(base))

    assert [f.path for f in report.findings] == [name]


def test_autocrlf_worktree_mode_detects_revert(tmp_path):
    """RC1's CRLF face: on-disk CRLF bytes differ from the LF blob; the clean
    filter path must still equate a pristine revert with the old blob."""
    repo = _init(tmp_path, core_autocrlf="true")
    base = _commit(repo, "f.txt", b"wrong line\r\nsecond\r\n", "seed")
    _commit(repo, "f.txt", b"right line\r\nsecond\r\n", "fix")
    (repo / "f.txt").write_bytes(b"wrong line\r\nsecond\r\n")  # worktree revert

    report = _detect(repo, ["f.txt"], _explicit_baseline(base), mode="worktree")

    assert [f.path for f in report.findings] == ["f.txt"]


def test_recreating_a_deleted_file_is_a_finding(tmp_path):
    repo = _init(tmp_path)
    base = _commit(repo, "f.txt", b"v1\n", "create")
    _git(repo, "rm", "-q", "f.txt")
    _git(repo, "commit", "-q", "-m", "delete f.txt")
    _stage(repo, "f.txt", b"v1\n")  # re-create with the pre-deletion blob

    report = _detect(repo, ["f.txt"], _explicit_baseline(base))

    assert [f.path for f in report.findings] == ["f.txt"]
    assert report.findings[0].intervening_oid is None


def test_file_created_by_intervening_commit_is_not_a_finding(tmp_path):
    repo = _init(tmp_path)
    base = _commit(repo, "seed.txt", b"s\n", "base")
    _commit(repo, "new.txt", b"v1\n", "created by the intervening commit")
    _stage(repo, "new.txt", b"anything\n")

    report = _detect(repo, ["new.txt"], _explicit_baseline(base))
    assert report.findings == []


def test_proposed_deletion_is_never_a_finding(tmp_path):
    repo = _init(tmp_path)
    base = _commit(repo, "f.txt", b"v1\n", "base")
    _commit(repo, "f.txt", b"v2\n", "fix")
    _git(repo, "rm", "-q", "--cached", "f.txt")  # staged deletion

    report = _detect(repo, ["f.txt"], _explicit_baseline(base))
    assert report.findings == []


def test_content_lookback_findings_suppressed_session_class_kept(tmp_path):
    """D-A(ii): content/ stays on the session window until the content-scale
    replay is measured -- lookback-class content findings are suppressed with
    a diagnostic; session-class content findings still fire."""
    repo = _init(tmp_path)
    _commit(repo, "content/site/page.md", b"old\n", "seed")
    _commit(repo, "content/site/page.md", b"new\n", "regen")
    session_base = _commit(repo, "other.txt", b"x\n", "session after regen")
    _stage(repo, "content/site/page.md", b"old\n")

    lookback_baseline = slib.resolve_baseline(
        explicit_sha=None,
        session_ctx=type("Ctx", (), {"status": "resolved", "session_id": "s",
                                     "base_sha": session_base})(),
        head=_head(repo), repo_root=repo,
    )
    report = _detect(repo, ["content/site/page.md"], lookback_baseline)
    assert report.findings == []
    assert any("suppressed" in d for d in report.diagnostics)

    # Session-class content finding (intervening commit after the base) fires.
    base2 = session_base
    _commit(repo, "content/site/page.md", b"newer\n", "regen inside session")
    _stage(repo, "content/site/page.md", b"new\n")
    report2 = _detect(repo, ["content/site/page.md"], _explicit_baseline(base2))
    assert [f.path for f in report2.findings] == ["content/site/page.md"]


def test_explicit_base_not_ancestor_is_ignored_with_diagnostic(tmp_path):
    repo = _init(tmp_path)
    _commit(repo, "f.txt", b"v1\n", "only commit")
    baseline = slib.resolve_baseline(explicit_sha="0" * 40, session_ctx=None,
                                     head=_head(repo), repo_root=repo)
    assert baseline.source == "lookback"
    assert "ignored" in baseline.detail


def test_lookback_commit_cap_bounds_the_window(tmp_path):
    repo = _init(tmp_path)
    _commit(repo, "f.txt", b"wrong\n", "seed")
    _commit(repo, "f.txt", b"right\n", "old fix")     # will fall outside the cap
    for i in range(3):
        _commit(repo, f"filler{i}.txt", b"x\n", f"filler {i}")
    _stage(repo, "f.txt", b"wrong\n")

    slib.configure(lookback_max_commits=2)
    capped = slib.resolve_baseline(explicit_sha=None, session_ctx=None,
                                   head=_head(repo), repo_root=repo)
    report_capped = slib.detect_regressions(
        ["f.txt"], baseline=capped, head=_head(repo), mode="index", repo_root=repo)
    assert report_capped.findings == []  # the fix predates the capped window

    slib.configure()
    full = slib.resolve_baseline(explicit_sha=None, session_ctx=None,
                                 head=_head(repo), repo_root=repo)
    report_full = slib.detect_regressions(
        ["f.txt"], baseline=full, head=_head(repo), mode="index", repo_root=repo)
    assert [f.path for f in report_full.findings] == ["f.txt"]


def test_override_lookup_marks_findings_covered(tmp_path):
    repo = _init(tmp_path)
    base = _commit(repo, "f.txt", b"wrong\n", "seed")
    _commit(repo, "f.txt", b"right\n", "fix")
    _stage(repo, "f.txt", b"wrong\n")

    report = slib.detect_regressions(
        ["f.txt"], baseline=_explicit_baseline(base), head=_head(repo),
        mode="index", repo_root=repo,
        override_lookup=lambda p: {"override_id": "tok-1"} if p == "f.txt" else None,
    )
    assert report.findings[0].override_token_id == "tok-1"
    assert report.blocking(wide_findings="warn") == []
    assert report.blocking(wide_findings="block") == []
