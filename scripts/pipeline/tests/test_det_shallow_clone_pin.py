"""MT074 B1 -- shallow-clone baseline reachability, pinned checkout, strict fetch.

Every test builds REAL temporary git repositories (no mocked git): an "origin" with
>= 6 commits is cloned with ``git clone --depth 2`` over ``file://`` into a clone-cache
layout selected through ``ASPOSE_CLONE_CACHE``. Fully offline and fast.

Two repo shapes are exercised on purpose (generality gate G-1): a ``main``-branch repo
with 8 commits and a ``trunk``-branch repo with 7 commits under a different
family/platform pair -- the code under test must not depend on either.

Covered: baseline unreachable before / reachable after ``ensure_baseline_reachable``
(progressive deepen, never ``--unshallow``); a baseline removed from origin by a history
rewrite stays ORPHANED (``git_reachable`` and the freshness guard); ``checkout_pinned``
lands on the exact sha without resetting anything; strict fetch failure raises;
pin mismatch fails; ``refresh_knowledge --pin-sha/--strict-fetch`` wiring.
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from core import clone_cache as cc

_PIPELINE = Path(__file__).resolve().parents[1]
for _p in (str(_PIPELINE), str(_PIPELINE / "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from baseline_resolver import git_reachable  # noqa: E402
import freshness_guard as fg  # noqa: E402

# (family, platform, default-branch, commit-count, tracked-file) -- deliberately NOT
# Java/pdf-shaped and with differing branch names / history lengths.
SHAPES = [
    pytest.param(("cells", "net", "main", 8, "Program.cs"), id="net-main-8"),
    pytest.param(("words", "python", "trunk", 7, "module.py"), id="python-trunk-7"),
]


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=t",
         "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false", *args],
        cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {result.stderr}")
    return result.stdout.strip()


def _rmtree(path: Path) -> None:
    def _onexc(func, p, exc_info):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    shutil.rmtree(path, onexc=_onexc)


def _make_origin(root: Path, branch: str, count: int, filename: str) -> "tuple[Path, list[str]]":
    origin = root / "origin"
    origin.mkdir()
    _git(origin, "init", "-q", "-b", branch)
    shas = []
    for i in range(count):
        (origin / filename).write_text(f"revision {i}\n", encoding="utf-8")
        _git(origin, "add", ".")
        _git(origin, "commit", "-q", "-m", f"commit {i}")
        shas.append(_git(origin, "rev-parse", "HEAD"))
    return origin, shas


@pytest.fixture(autouse=True)
def _fast_lock():
    cc.configure(lock_timeout_seconds=10.0)
    yield
    cc.configure()


@pytest.fixture
def world(tmp_path, request, monkeypatch):
    family, platform, branch, count, filename = request.param
    monkeypatch.setenv("ASPOSE_CLONE_CACHE", str(tmp_path / "cache"))
    origin, shas = _make_origin(tmp_path, branch, count, filename)
    dest = cc.clone_path(family, platform)
    dest.parent.mkdir(parents=True)
    subprocess.run(
        ["git", "clone", "-q", "--depth", "2", "-b", branch, origin.resolve().as_uri(), str(dest)],
        check=True, capture_output=True,
    )
    return SimpleNamespace(
        family=family, platform=platform, branch=branch, origin=origin, shas=shas,
        clone=dest, filename=filename,
    )


class _RecordingRunner:
    """Real git, but records every argv so tests can assert what was (not) run."""

    def __init__(self):
        self.calls: "list[list[str]]" = []

    def __call__(self, args, cwd):
        self.calls.append(list(args))
        return subprocess.run(
            list(args), cwd=str(cwd), capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )


# ---------------------------------------------------------------------------
# reachability
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("world", SHAPES, indirect=True)
def test_old_baseline_unreachable_before_reachable_after_ensure(world):
    baseline = world.shas[1]  # far older than the two fetched commits
    never = lambda sha: False  # noqa: E731 - disables deepening so we observe the raw state
    assert cc.is_shallow_repo(world.clone)
    assert git_reachable(world.clone, deepen=never)(baseline) is False  # the false orphan

    assert cc.ensure_baseline_reachable(world.family, world.platform, baseline) is True
    assert git_reachable(world.clone, deepen=never)(baseline) is True


@pytest.mark.parametrize("world", SHAPES, indirect=True)
def test_progressive_deepen_stops_early_and_never_unshallows(world):
    runner = _RecordingRunner()
    # shas[-3] is 2 commits behind the shallow tip's parent: needs the second step.
    baseline = world.shas[-4]
    assert cc.ensure_baseline_reachable(
        world.family, world.platform, baseline, deepen_steps=(1, 2, 50), runner=runner,
    ) is True
    flat = [" ".join(c) for c in runner.calls]
    deepens = [c for c in flat if "--deepen=" in c]
    assert deepens, flat
    assert not any("--deepen=50" in c for c in flat), "must stop at the first sufficient step"
    assert not any("--unshallow" in c for c in flat)


@pytest.mark.parametrize("world", SHAPES, indirect=True)
def test_already_reachable_baseline_makes_no_network_call(world):
    runner = _RecordingRunner()
    assert cc.ensure_baseline_reachable(
        world.family, world.platform, world.shas[-2], runner=runner,
    ) is True
    assert not any("fetch" in c for c in runner.calls)


@pytest.mark.parametrize("world", SHAPES, indirect=True)
def test_git_reachable_default_seam_deepens_shallow_clone(world):
    """The production default seam (no injection) removes the false orphan."""
    assert git_reachable(world.clone)(world.shas[0]) is True


def test_git_reachable_seam_is_injectable_and_skipped_for_full_repo(tmp_path):
    origin, shas = _make_origin(tmp_path, "main", 6, "a.txt")
    calls = []

    def deepen(sha):
        calls.append(sha)
        return True

    probe = git_reachable(origin, deepen=deepen)
    assert probe(shas[0]) is True  # plain ancestor in a full repo
    assert calls == []  # never deepens a non-shallow repo
    assert probe("0" * 40) is False
    assert calls == []


def test_invalid_sha_is_rejected_without_running_git(tmp_path):
    runner = _RecordingRunner()
    assert cc.deepen_until_ancestor(tmp_path, "--upload-pack=evil", runner=runner) is False
    assert cc.deepen_until_ancestor(tmp_path, "", runner=runner) is False
    assert runner.calls == []


# ---------------------------------------------------------------------------
# force-push / history rewrite stays orphaned
# ---------------------------------------------------------------------------

def _rewrite_origin_history(origin: Path, branch: str, filename: str) -> str:
    """Replace the whole history with a fresh root and make the old commits unreachable
    AND physically gone (reflog expired, gc'd) -- a faithful force-push simulation."""
    _git(origin, "checkout", "-q", "--orphan", "rewritten")
    (origin / filename).write_text("rewritten history\n", encoding="utf-8")
    _git(origin, "add", ".")
    _git(origin, "commit", "-q", "-m", "rewritten root")
    _git(origin, "branch", "-q", "-D", branch)
    _git(origin, "branch", "-q", "-m", branch)
    _git(origin, "reflog", "expire", "--expire=now", "--all")
    _git(origin, "gc", "-q", "--prune=now")
    return _git(origin, "rev-parse", "HEAD")


@pytest.mark.parametrize("world", SHAPES, indirect=True)
def test_baseline_removed_by_history_rewrite_stays_orphaned(world):
    baseline = world.shas[1]
    new_head = _rewrite_origin_history(world.origin, world.branch, world.filename)
    assert cc.update_clone(world.family, world.platform) == new_head

    assert cc.ensure_baseline_reachable(
        world.family, world.platform, baseline, deepen_steps=(2, 10),
    ) is False
    assert git_reachable(world.clone)(baseline) is False  # real default path
    # the freshness guard still classifies it as a real orphan (deepening did not weaken it)
    verdict = fg._check_baseline_reachability(world.family, world.platform, baseline)
    assert verdict is not None and verdict[0] == "STALE_ORPHANED"


@pytest.mark.parametrize("world", SHAPES, indirect=True)
def test_freshness_guard_healthy_old_baseline_is_not_orphaned(world):
    """The live bug: a healthy baseline older than the shallow window must NOT be STALE_ORPHANED."""
    assert fg._check_baseline_reachability(world.family, world.platform, world.shas[0]) is None


@pytest.mark.parametrize("world", SHAPES, indirect=True)
def test_freshness_guard_deepen_seam_is_injectable(world):
    seen = []

    def deepen(sha):
        seen.append(sha)
        return False

    verdict = fg._check_baseline_reachability(
        world.family, world.platform, world.shas[0], deepen=deepen,
    )
    assert seen == [world.shas[0]]
    assert verdict is not None and verdict[0] == "STALE_ORPHANED"


# ---------------------------------------------------------------------------
# checkout_pinned
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("world", SHAPES, indirect=True)
def test_checkout_pinned_lands_on_exact_sha_and_never_resets(world):
    target = world.shas[1]
    branch_before = _git(world.clone, "rev-parse", world.branch)
    full = cc.checkout_pinned(world.family, world.platform, target)
    assert full == target
    assert _git(world.clone, "rev-parse", "HEAD") == target
    # detached: not on the local branch any more, and the branch ref was NOT moved
    detached = subprocess.run(
        ["git", "symbolic-ref", "-q", "HEAD"], cwd=str(world.clone), capture_output=True,
    )
    assert detached.returncode != 0
    assert _git(world.clone, "rev-parse", world.branch) == branch_before
    assert (world.clone / world.filename).read_text(encoding="utf-8") == "revision 1\n"


@pytest.mark.parametrize("world", SHAPES, indirect=True)
def test_checkout_pinned_abbreviated_sha_needs_local_object(world):
    # present locally (inside the shallow window): abbreviation resolves to the full sha
    full = cc.checkout_pinned(world.family, world.platform, world.shas[-2][:12])
    assert full == world.shas[-2]
    # absent locally: an abbreviation cannot be fetched by name, so it must fail loudly
    with pytest.raises(RuntimeError):
        cc.checkout_pinned(world.family, world.platform, world.shas[1][:12])


@pytest.mark.parametrize("world", SHAPES, indirect=True)
def test_checkout_pinned_preserves_local_changes_instead_of_resetting(world):
    (world.clone / world.filename).write_text("precious local edit\n", encoding="utf-8")
    with pytest.raises(RuntimeError):
        cc.checkout_pinned(world.family, world.platform, world.shas[1])
    assert (world.clone / world.filename).read_text(encoding="utf-8") == "precious local edit\n"


@pytest.mark.parametrize("world", SHAPES, indirect=True)
def test_checkout_pinned_rejects_unknown_and_malformed_sha(world):
    with pytest.raises(RuntimeError):
        cc.checkout_pinned(world.family, world.platform, "deadbeef" * 5)
    with pytest.raises(RuntimeError):
        cc.checkout_pinned(world.family, world.platform, "not-a-sha")


@pytest.mark.parametrize("world", SHAPES, indirect=True)
def test_checkout_pinned_fails_when_head_is_not_the_pin(world):
    """Pin-mismatch guard: if git claims success but HEAD is elsewhere, it must raise."""
    real = _RecordingRunner()

    def lying_runner(args, cwd):
        if list(args)[:2] == ["git", "checkout"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")  # pretend, don't move HEAD
        return real(args, cwd)

    with pytest.raises(RuntimeError, match="HEAD is not"):
        cc.checkout_pinned(world.family, world.platform, world.shas[1], runner=lying_runner)


def test_checkout_pinned_without_clone_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("ASPOSE_CLONE_CACHE", str(tmp_path / "empty"))
    with pytest.raises(RuntimeError):
        cc.checkout_pinned("cells", "net", "a" * 40)


# ---------------------------------------------------------------------------
# strict fetch
# ---------------------------------------------------------------------------

def _break_origin(clone: Path, tmp_path: Path) -> None:
    _git(clone, "remote", "set-url", "origin", (tmp_path / "does-not-exist").resolve().as_uri())


@pytest.mark.parametrize("world", SHAPES, indirect=True)
def test_update_clone_strict_raises_on_fetch_failure_default_degrades(world, tmp_path):
    head_before = _git(world.clone, "rev-parse", "HEAD")
    _break_origin(world.clone, tmp_path)
    assert cc.update_clone(world.family, world.platform) is None  # legacy contract unchanged
    with pytest.raises(RuntimeError, match="fetch failed"):
        cc.update_clone(world.family, world.platform, strict=True)
    assert _git(world.clone, "rev-parse", "HEAD") == head_before


@pytest.mark.parametrize("world", SHAPES, indirect=True)
def test_update_clone_strict_success_matches_default(world):
    new_head = _git(world.origin, "rev-parse", "HEAD")
    assert cc.update_clone(world.family, world.platform, strict=True) == new_head


def test_update_clone_strict_missing_clone_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("ASPOSE_CLONE_CACHE", str(tmp_path / "empty"))
    assert cc.update_clone("cells", "net") is None
    with pytest.raises(RuntimeError):
        cc.update_clone("cells", "net", strict=True)


# ---------------------------------------------------------------------------
# refresh_knowledge --pin-sha / --strict-fetch wiring
# ---------------------------------------------------------------------------

@pytest.fixture
def rk(tmp_path):
    import refresh_knowledge as _rk
    _rk.configure(repo_root=tmp_path / "repo")
    (tmp_path / "repo" / "knowledge").mkdir(parents=True)
    yield _rk
    _rk.configure()


@pytest.mark.parametrize("world", SHAPES, indirect=True)
def test_refresh_pin_sha_checks_out_pin_then_proceeds(world, rk):
    pin = world.shas[2]
    result = rk.refresh(
        world.family, world.platform, check_only=True, auto_fetch=False, pin_sha=pin,
    )
    assert result == "stale"  # no model.yaml yet -> stale, but only after pinning succeeded
    assert _git(world.clone, "rev-parse", "HEAD") == pin


@pytest.mark.parametrize("world", SHAPES, indirect=True)
def test_refresh_pin_sha_unknown_commit_fails(world, rk):
    result = rk.refresh(
        world.family, world.platform, check_only=True, auto_fetch=False, pin_sha="c0ffee" * 6 + "c0ff",
    )
    assert result == "failed"


@pytest.mark.parametrize("world", SHAPES, indirect=True)
def test_refresh_strict_fetch_failure_is_hard_failure(world, rk, tmp_path):
    _break_origin(world.clone, tmp_path)
    assert rk.refresh(
        world.family, world.platform, check_only=True, auto_fetch=True, strict_fetch=True,
    ) == "failed"
    # default (non-strict) keeps the legacy degraded mode: proceeds on the stale HEAD
    assert rk.refresh(
        world.family, world.platform, check_only=True, auto_fetch=True,
    ) == "stale"


def test_refresh_cli_exposes_new_flags_and_rejects_pin_with_all(rk, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["refresh_knowledge.py", "--all", "--pin-sha", "a" * 40])
    with pytest.raises(SystemExit) as exc:
        rk.main()
    assert exc.value.code == 2
    assert "--pin-sha" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Review R1 fixes: tri-state verdict, memoization, fetch cap, full-clone safety,
# toplevel guard, checkout_pinned error wrapping
# ---------------------------------------------------------------------------

from baseline_resolver import (  # noqa: E402
    BaselineReachabilityUnknown,
    git_reachability_state,
)


class _FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def _fetch_calls(runner: _RecordingRunner) -> "list[list[str]]":
    return [c for c in runner.calls if "fetch" in c]


@pytest.mark.parametrize("world", SHAPES, indirect=True)
def test_network_failure_is_unknown_never_orphaned(world, tmp_path):
    baseline = world.shas[0]
    _break_origin(world.clone, tmp_path)
    assert cc.probe_baseline_reachability_at(world.clone, baseline) == cc.UNKNOWN
    cc.reset_deepen_state()
    assert git_reachability_state(world.clone)(baseline) == "unknown"
    cc.reset_deepen_state()
    verdict = fg._check_baseline_reachability(world.family, world.platform, baseline)
    assert verdict is not None and verdict[0] == "BASELINE_UNVERIFIABLE"
    assert verdict[0] != "STALE_ORPHANED" and "unverifiable" in verdict[1]
    cc.reset_deepen_state()
    with pytest.raises(BaselineReachabilityUnknown):
        git_reachable(world.clone, on_unknown="raise")(baseline)
    assert git_reachable(world.clone)(baseline) is False  # legacy bool view: unverified -> False


@pytest.mark.parametrize("world", SHAPES, indirect=True)
def test_fetch_timeout_or_oserror_is_unknown(world):
    class _R:
        def __call__(self, args, cwd):
            if "fetch" in list(args):
                raise subprocess.TimeoutExpired(args, 60)
            return subprocess.run(list(args), cwd=str(cwd), capture_output=True, text=True,
                                  encoding="utf-8", errors="replace")

    assert cc.probe_baseline_reachability(world.clone, world.shas[0], runner=_R()) == cc.UNKNOWN


@pytest.mark.parametrize("world", SHAPES, indirect=True)
def test_freshness_check_notes_unverifiable_instead_of_stale_orphaned(world, tmp_path, monkeypatch):
    monkeypatch.setenv("ASPOSE_BASELINE_OFFLINE", "1")  # strictly offline: shallow + not ancestor
    merged = tmp_path / "knowledge" / world.family / world.platform / "merged"
    merged.mkdir(parents=True)
    import yaml
    (merged / "model.yaml").write_text(
        yaml.dump({"repo_sha": world.shas[0], "stale_since": None, "schema_version": 2}), encoding="utf-8")
    fg.configure(repo_root=tmp_path)
    try:
        result = fg.check_freshness(world.family, world.platform, mode="degraded")
    finally:
        fg.configure(repo_root=None)
    assert result.state != "STALE_ORPHANED"
    assert "unverifiable" in result.reason


@pytest.mark.parametrize("world", SHAPES, indirect=True)
def test_offline_flag_and_env_never_fetch(world, monkeypatch):
    seen = []

    def deepen(sha):
        seen.append(sha)
        return "reachable"

    probe = git_reachability_state(world.clone, deepen=deepen, offline=True)
    assert probe(world.shas[0]) == "unknown" and seen == []
    monkeypatch.setenv("ASPOSE_BASELINE_OFFLINE", "yes")
    assert git_reachability_state(world.clone, deepen=deepen)(world.shas[0]) == "unknown"
    assert seen == []
    assert git_reachability_state(world.clone, deepen=deepen)(world.shas[-1]) == "reachable"  # local


@pytest.mark.parametrize("world", SHAPES, indirect=True)
def test_memoized_verdicts_make_zero_git_calls_on_repeat(world):
    runner = _RecordingRunner()
    sha = world.shas[1]
    first = cc.probe_baseline_reachability(world.clone, sha, runner=runner)
    assert first == cc.REACHABLE and runner.calls
    n = len(runner.calls)
    assert cc.probe_baseline_reachability(world.clone, sha, runner=runner) == cc.REACHABLE
    assert len(runner.calls) == n  # zero further git calls


@pytest.mark.parametrize("world", SHAPES, indirect=True)
def test_orphan_verdict_is_memoized_and_unknown_is_retried_only_after_the_window(world, tmp_path):
    clock = _FakeClock()
    runner = _RecordingRunner()
    sha = world.shas[0]
    _break_origin(world.clone, tmp_path)
    assert cc.probe_baseline_reachability(world.clone, sha, runner=runner, clock=clock) == cc.UNKNOWN
    n = len(runner.calls)
    clock.t += 10  # still inside the retry window
    assert cc.probe_baseline_reachability(world.clone, sha, runner=runner, clock=clock) == cc.UNKNOWN
    assert len(runner.calls) == n
    clock.t += 10_000  # window elapsed: probed again
    cc.probe_baseline_reachability(world.clone, sha, runner=runner, clock=clock)
    assert len(runner.calls) > n


@pytest.mark.parametrize("world", SHAPES, indirect=True)
def test_genuine_orphan_after_completed_deepen_is_memoized_and_update_clone_invalidates(world):
    baseline = world.shas[1]
    new_head = _rewrite_origin_history(world.origin, world.branch, world.filename)
    assert cc.update_clone(world.family, world.platform) == new_head
    runner = _RecordingRunner()
    assert cc.probe_baseline_reachability(world.clone, baseline, deepen_steps=(2,), runner=runner) == cc.ORPHANED
    n = len(runner.calls)
    assert cc.probe_baseline_reachability(world.clone, baseline, deepen_steps=(2,), runner=runner) == cc.ORPHANED
    assert len(runner.calls) == n  # negative verdict memoized
    assert cc.update_clone(world.family, world.platform) == new_head  # HEAD "moved": memo dropped
    cc.probe_baseline_reachability(world.clone, baseline, deepen_steps=(2,), runner=runner)
    assert len(runner.calls) > n


@pytest.mark.parametrize("world", SHAPES, indirect=True)
def test_per_process_fetch_cap_gives_unknown_and_stops_fetching(world):
    cc.configure(lock_timeout_seconds=10.0, max_deepen_fetches=1)
    runner = _RecordingRunner()
    assert cc.probe_baseline_reachability(world.clone, world.shas[0], deepen_steps=(1, 1, 1), runner=runner) \
        == cc.UNKNOWN
    assert len(_fetch_calls(runner)) == 1  # only the one permitted fetch was spent
    other = _RecordingRunner()
    assert cc.probe_baseline_reachability(world.clone, world.shas[1], runner=other) == cc.UNKNOWN
    assert _fetch_calls(other) == []  # cap is per process: nothing more is fetched


@pytest.mark.parametrize("world", SHAPES, indirect=True)
def test_seam_claiming_reachable_is_reverified_against_real_ancestry(world):
    """Mutant guard: git_reachable must re-check ancestry after a deepen. A seam (or a buggy
    deepen) that claims success without actually fetching must NOT make the sha reachable."""
    baseline = world.shas[0]  # genuinely outside the shallow window
    for claim in ("reachable", True):
        probe = git_reachability_state(world.clone, deepen=lambda s, c=claim: c)
        assert probe(baseline) == "orphaned"
        assert git_reachable(world.clone, deepen=lambda s, c=claim: c)(baseline) is False
    # and a deepen that really fetches does make it reachable (the re-check then passes)
    assert git_reachable(world.clone)(baseline) is True


def test_full_clone_is_never_fetched_into_or_truncated(tmp_path, monkeypatch):
    monkeypatch.setenv("ASPOSE_CLONE_CACHE", str(tmp_path / "cache"))
    origin, shas = _make_origin(tmp_path, "main", 8, "a.txt")
    dest = cc.clone_path("cells", "net")
    dest.parent.mkdir(parents=True)
    subprocess.run(["git", "clone", "-q", origin.resolve().as_uri(), str(dest)],
                   check=True, capture_output=True)  # FULL clone
    assert not cc.is_shallow_repo(dest)
    before = _git(dest, "rev-list", "--count", "HEAD")
    runner = _RecordingRunner()
    assert cc.ensure_baseline_reachable("cells", "net", "a" * 40, runner=runner) is False
    assert cc.deepen_until_ancestor(dest, "b" * 40, runner=runner) is False
    assert cc.probe_baseline_reachability_at(dest, "c" * 40, runner=runner) == cc.ORPHANED
    assert _fetch_calls(runner) == []
    assert cc.ensure_baseline_reachable("cells", "net", "a" * 40) is False  # real git, no runner
    assert _git(dest, "rev-list", "--count", "HEAD") == before == "8"
    assert not cc.is_shallow_repo(dest)


def test_toplevel_guard_stops_path_only_callers_from_touching_a_parent_repo(tmp_path, monkeypatch):
    monkeypatch.setenv("ASPOSE_CLONE_CACHE", str(tmp_path / "cache"))
    origin, shas = _make_origin(tmp_path, "main", 6, "a.txt")
    parent = tmp_path / "cache" / "parent_repo"
    parent.parent.mkdir(parents=True)
    subprocess.run(["git", "clone", "-q", "--depth", "2", origin.resolve().as_uri(), str(parent)],
                   check=True, capture_output=True)
    # a clone-cache-shaped directory that is NOT its own repo (empty .git): git resolves to the parent
    fake = cc.clone_path("words", "python")
    fake = parent / fake.name
    (fake / ".git").mkdir(parents=True)
    runner = _RecordingRunner()
    head_before = _git(parent, "rev-parse", "HEAD")
    assert cc.deepen_until_ancestor_state(fake, shas[0], runner=runner) == cc.UNKNOWN
    assert _fetch_calls(runner) == []
    assert _git(parent, "rev-parse", "HEAD") == head_before


@pytest.mark.parametrize("world", SHAPES, indirect=True)
def test_checkout_pinned_wraps_runner_exceptions_in_runtimeerror(world):
    real = _RecordingRunner()

    def make(exc, trigger):
        def runner(args, cwd):
            if list(args)[:2] == trigger:
                raise exc
            return real(args, cwd)
        return runner

    with pytest.raises(RuntimeError, match="could not run"):
        cc.checkout_pinned(world.family, world.platform, world.shas[-2],
                           runner=make(subprocess.TimeoutExpired("git", 30), ["git", "checkout"]))
    with pytest.raises(RuntimeError, match="could not run"):
        cc.checkout_pinned(world.family, world.platform, world.shas[-2],
                           runner=make(OSError("git vanished"), ["git", "checkout"]))
    # a fetch of a missing commit that times out is also a RuntimeError, not a traceback
    with pytest.raises(RuntimeError):
        cc.checkout_pinned(world.family, world.platform, world.shas[0],
                           runner=make(subprocess.TimeoutExpired("git", 60), ["git", "fetch"]))
