"""Tests for baseline_resolver.py (RPR-C-03).

The resolution logic is exercised with an injected reachability fake (pure, fast,
deterministic); one test uses a real temporary git repo to prove `git_reachable`
correctly distinguishes a reachable commit from a rewritten-away one.
"""
import subprocess

import pytest

from lib.baseline_ledger import BaselineLedger
from lib.baseline_resolver import (
    BaselineResolution,
    OrphanedBaselineError,
    _sample_content_model_sha,
    git_reachable,
    resolve_baseline_sha,
)


def _ledger(tmp_path, family="pdf", platform="net"):
    return BaselineLedger(family, platform, merged_dir=tmp_path)


def _append(ledger, run_id, new_sha, status="accepted", prior=None):
    ledger.append(
        run_id=run_id,
        new_repo_sha=new_sha,
        prior_repo_sha=prior,
        sha_source="scout",
        status=status,
        accepted_at="2026-07-16T00:00:00Z" if status == "accepted" else None,
    )


# ── happy path ────────────────────────────────────────────────────────────

def test_resolves_ledger_last_accepted_when_reachable(tmp_path):
    ledger = _ledger(tmp_path)
    _append(ledger, "R1", "aaa111")
    _append(ledger, "R2", "bbb222", prior="aaa111")
    res = resolve_baseline_sha(
        "pdf", "net", reachable=lambda s: s == "bbb222", merged_dir=tmp_path
    )
    assert res == BaselineResolution(sha="bbb222", source="ledger")
    assert res.is_orphaned_recovery is False


def test_falls_back_to_model_yaml_when_ledger_empty(tmp_path):
    # No ledger entries; the legacy scalar is the only baseline available.
    res = resolve_baseline_sha(
        "pdf", "net", reachable=lambda s: True, merged_dir=tmp_path, model_repo_sha="scalar123"
    )
    assert res.sha == "scalar123"
    assert res.source == "model-yaml"


# ── orphaned recovery (the force-push / rebase case) ──────────────────────

def test_forcepush_resolves_via_ledger_walkback(tmp_path):
    """Newest baseline is unreachable (force-pushed away); walk back to the newest
    reachable ancestor and tag it orphaned-recovered."""
    ledger = _ledger(tmp_path)
    _append(ledger, "R1", "old_reachable")
    _append(ledger, "R2", "mid_reachable", prior="old_reachable")
    _append(ledger, "R3", "head_gone", prior="mid_reachable")
    # head_gone was rewritten away; mid/old survive.
    reachable = {"old_reachable", "mid_reachable"}
    res = resolve_baseline_sha(
        "pdf", "net", reachable=lambda s: s in reachable, merged_dir=tmp_path
    )
    assert res.sha == "mid_reachable"
    assert res.source == "orphaned-recovered"
    assert res.orphaned_from == "head_gone"


def test_unresolvable_raises_orphaned_baseline(tmp_path):
    ledger = _ledger(tmp_path)
    _append(ledger, "R1", "gone1")
    _append(ledger, "R2", "gone2", prior="gone1")
    with pytest.raises(OrphanedBaselineError) as exc:
        resolve_baseline_sha("pdf", "net", reachable=lambda s: False, merged_dir=tmp_path)
    # Never silently returns an empty diff — the tried set is reported for triage.
    assert "gone1" in exc.value.tried and "gone2" in exc.value.tried
    assert exc.value.family == "pdf" and exc.value.platform == "net"


def test_3d_net_refresh_002_scenario_resolves(tmp_path):
    """Reproduces the real 3D-NET-REFRESH-002 conflated-baseline chain using the
    actual SHA values from that backlog entry: the recorded head went stale mid-cycle
    when an intervening refresh landed. If the recorded head is unreachable, the
    walkback recovers the prior accepted ancestor rather than fabricating a baseline."""
    ledger = _ledger(tmp_path, "3d", "net")
    _append(ledger, "3D-NET-A", "61580eaa2b")
    _append(ledger, "3D-NET-B", "76ee798cfb", prior="61580eaa2b")
    _append(ledger, "3D-NET-C", "53cb6be63d", prior="76ee798cfb")
    # The recorded head (53cb6be63d) was orphaned by an intervening uncoordinated
    # refresh; the prior accepted SHA is still reachable.
    reachable = {"61580eaa2b", "76ee798cfb"}
    res = resolve_baseline_sha(
        "3d", "net", reachable=lambda s: s in reachable, merged_dir=tmp_path
    )
    assert res.sha == "76ee798cfb"
    assert res.source == "orphaned-recovered"
    assert res.orphaned_from == "53cb6be63d"


def test_only_accepted_entries_are_primary_but_history_walkback_uses_all(tmp_path):
    """last_accepted() ignores 'attempted' rows for the primary pick, but an
    attempted row that is nonetheless git-reachable can still anchor a walkback."""
    ledger = _ledger(tmp_path)
    _append(ledger, "R1", "accepted_gone", status="accepted")
    _append(ledger, "R2", "attempted_here", status="attempted", prior="accepted_gone")
    res = resolve_baseline_sha(
        "pdf", "net", reachable=lambda s: s == "attempted_here", merged_dir=tmp_path
    )
    assert res.sha == "attempted_here"
    assert res.source == "orphaned-recovered"


# ── RPR-J-04: content-frontmatter fallback (fresh clone / never-migrated) ──

def test_fresh_clone_resolves_via_content_frontmatter(tmp_path):
    """No ledger, no model.yaml scalar -- the fresh-clone case. Falls back to the
    evidence.model_sha already committed on a content page instead of failing."""
    res = resolve_baseline_sha(
        "pdf", "net",
        reachable=lambda s: s == "content_sha_abc",
        merged_dir=tmp_path,
        sample_content_model_sha=lambda family, platform: "content_sha_abc",
    )
    assert res.sha == "content_sha_abc"
    assert res.source == "content-frontmatter"
    assert res.is_orphaned_recovery is False


def test_content_frontmatter_fallback_unreachable_still_raises_orphaned(tmp_path):
    """The sampled content sha is itself unreachable (e.g. a shallow clone with no
    matching history) -- must still fail loudly, never silently, and must report the
    sha it tried."""
    with pytest.raises(OrphanedBaselineError) as exc:
        resolve_baseline_sha(
            "pdf", "net",
            reachable=lambda s: False,
            merged_dir=tmp_path,
            sample_content_model_sha=lambda family, platform: "content_sha_unreachable",
        )
    assert "content_sha_unreachable" in exc.value.tried


def test_no_ledger_no_scalar_no_content_sha_raises_orphaned(tmp_path):
    """Nothing resolves anywhere (e.g. product has no content pages yet) -- unchanged
    behavior: explicit OrphanedBaselineError, empty tried set."""
    with pytest.raises(OrphanedBaselineError) as exc:
        resolve_baseline_sha(
            "pdf", "net",
            reachable=lambda s: True,
            merged_dir=tmp_path,
            sample_content_model_sha=lambda family, platform: None,
        )
    assert exc.value.tried == []


def test_ledger_present_and_reachable_never_calls_content_sampler(tmp_path):
    """When the ledger already resolves, the (potentially I/O-heavy) content sampler
    must not run at all -- no behavior change for products with a warm ledger cache."""
    ledger = _ledger(tmp_path)
    _append(ledger, "R1", "warm_cache_sha")

    def _boom(family, platform):
        raise AssertionError("content sampler must not be called when the ledger resolves")

    res = resolve_baseline_sha(
        "pdf", "net",
        reachable=lambda s: s == "warm_cache_sha",
        merged_dir=tmp_path,
        sample_content_model_sha=_boom,
    )
    assert res.sha == "warm_cache_sha"
    assert res.source == "ledger"


def test_sample_content_model_sha_reads_evidence_model_sha_field(tmp_path):
    """Real integration: parse_frontmatter + discover_content wired to an actual
    committed-shaped content file, not just an injected fake."""
    page = tmp_path / "Foo.md"
    page.write_text(
        "---\n"
        "title: Foo\n"
        "evidence:\n"
        "  model_sha: real_committed_sha_123\n"
        "  model_version: 26.6.0\n"
        "---\n"
        "Body text.\n",
        encoding="utf-8",
    )
    sha = _sample_content_model_sha(
        "pdf", "net", discover_content_fn=lambda family, platform: [page]
    )
    assert sha == "real_committed_sha_123"


def test_sample_content_model_sha_skips_pages_without_evidence_block(tmp_path):
    """First page has no evidence block yet; second page does -- must not stop at
    the first miss."""
    no_evidence = tmp_path / "NoEvidence.md"
    no_evidence.write_text("---\ntitle: Bare\n---\nBody.\n", encoding="utf-8")
    with_evidence = tmp_path / "WithEvidence.md"
    with_evidence.write_text(
        "---\ntitle: Stamped\nevidence:\n  model_sha: second_page_sha\n---\nBody.\n",
        encoding="utf-8",
    )
    sha = _sample_content_model_sha(
        "pdf", "net",
        discover_content_fn=lambda family, platform: [no_evidence, with_evidence],
    )
    assert sha == "second_page_sha"


# ── real git reachability probe ───────────────────────────────────────────

def test_git_reachable_against_real_repo(tmp_path):
    """Prove the production reachability probe works: a committed SHA is reachable,
    a fabricated one is not, in a real temporary git repository."""
    repo = tmp_path / "clone"
    repo.mkdir()

    def git(*args):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)

    try:
        git("init", "-q")
        git("config", "user.email", "t@t")
        git("config", "user.name", "t")
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git not available")
    (repo / "f.txt").write_text("hello", encoding="utf-8")
    git("add", "f.txt")
    git("commit", "-q", "-m", "c1")
    head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True
    ).stdout.strip()

    probe = git_reachable(repo)
    assert probe(head) is True
    assert probe("deadbeef" * 5) is False
    assert probe("") is False


def test_git_reachable_rejects_dangling_but_object_present_commit(tmp_path):
    """RC-1 follow-up (readme-refresh-hardening-and-regen-2026-08-30, found live
    during the font/python TC-27b canary): a history-rewritten orphan commit
    remains a dangling-but-present loose object in the local clone cache until
    garbage-collected -- `git cat-file -e <sha>^{commit}` (the old implementation)
    wrongly reports such a commit "reachable" because it only tests OBJECT
    EXISTENCE, not ancestry from HEAD. `git commit --amend` reproduces this exact
    real-world shape (the old commit is dangling but still `cat-file -e` visible,
    unlike a full history re-init which actually removes the object) -- confirmed
    live against font/python's real clone cache before this fix: `cat-file -e`
    exited 0, `merge-base --is-ancestor` exited 1, for the same orphaned SHA
    against the same repo. `git_reachable` must return False for it."""
    repo = tmp_path / "clone"
    repo.mkdir()

    def git(*args):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)

    try:
        git("init", "-q")
        git("config", "user.email", "t@t")
        git("config", "user.name", "t")
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git not available")
    (repo / "f.txt").write_text("hello", encoding="utf-8")
    git("add", "f.txt")
    git("commit", "-q", "-m", "original")
    original_head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True, encoding="utf-8", errors="replace",
    ).stdout.strip()

    git("commit", "--amend", "-q", "-m", "rewritten")
    new_head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True, encoding="utf-8", errors="replace",
    ).stdout.strip()
    assert new_head != original_head  # the commit genuinely changed identity

    # Sanity: the old commit object is still physically present (dangling), the
    # exact real-world condition that defeated the pre-fix `cat-file -e` check.
    still_present = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-e", f"{original_head}^{{commit}}"],
        capture_output=True,
    )
    assert still_present.returncode == 0

    probe = git_reachable(repo)
    assert probe(new_head) is True
    assert probe(original_head) is False  # dangling, not an ancestor of HEAD -- must be False


def test_git_reachable_end_to_end_resolution_with_real_repo(tmp_path):
    """resolve_baseline_sha wired to the real git probe: an unreachable recorded head
    falls back to a reachable earlier commit."""
    repo = tmp_path / "clone"
    repo.mkdir()

    def git(*args, check=True):
        return subprocess.run(
            ["git", "-C", str(repo), *args], check=check, capture_output=True, text=True
        )

    try:
        git("init", "-q")
        git("config", "user.email", "t@t")
        git("config", "user.name", "t")
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git not available")
    (repo / "f.txt").write_text("v1", encoding="utf-8")
    git("add", "f.txt")
    git("commit", "-q", "-m", "c1")
    real_sha = git("rev-parse", "HEAD").stdout.strip()

    merged = tmp_path / "merged"
    ledger = BaselineLedger("pdf", "net", merged_dir=merged)
    ledger.append(
        run_id="R1", new_repo_sha=real_sha, sha_source="scout", status="accepted",
        accepted_at="2026-07-16T00:00:00Z",
    )
    ledger.append(
        run_id="R2", new_repo_sha="f" * 40, prior_repo_sha=real_sha,
        sha_source="scout", status="accepted", accepted_at="2026-07-16T01:00:00Z",
    )  # a fabricated, unreachable "head"

    res = resolve_baseline_sha(
        "pdf", "net", reachable=git_reachable(repo), merged_dir=merged
    )
    assert res.sha == real_sha
    assert res.source == "orphaned-recovered"


# -- MT074 B1: shallow-clone deepen seam ----------------------------------------

def _init_repo_with_commits(tmp_path, n=3):
    repo = tmp_path / "full"
    repo.mkdir()

    def git(*args):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)

    try:
        git("init", "-q")
        git("config", "user.email", "t@t")
        git("config", "user.name", "t")
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git not available")
    shas = []
    for i in range(n):
        (repo / "m.py").write_text(f"v{i}\n", encoding="utf-8")
        git("add", "m.py")
        git("commit", "-q", "-m", f"c{i}")
        shas.append(subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                                   capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip())
    return repo, shas


def test_git_reachable_does_not_deepen_a_full_repo(tmp_path):
    repo, shas = _init_repo_with_commits(tmp_path)
    calls = []

    def deepen(sha):
        calls.append(sha)
        return True

    probe = git_reachable(repo, deepen=deepen)
    assert probe(shas[0]) is True
    assert probe("0" * 40) is False
    assert calls == []  # full history: no network deepening ever


def test_git_reachable_consults_deepen_seam_for_shallow_repo_then_rechecks(tmp_path):
    repo, _ = _init_repo_with_commits(tmp_path)
    calls = []

    def deepen(sha):
        calls.append(sha)
        return True  # claims success, but ancestry is re-verified -> still an orphan

    probe = git_reachable(repo, is_shallow=lambda: True, deepen=deepen)
    assert probe("0" * 40) is False
    assert calls == ["0" * 40]


def test_git_reachable_unreachable_after_deepen_stays_orphaned(tmp_path):
    repo, _ = _init_repo_with_commits(tmp_path)
    probe = git_reachable(repo, is_shallow=lambda: True, deepen=lambda s: False)
    assert probe("f" * 40) is False


def test_git_reachable_deepen_failure_degrades_to_false(tmp_path):
    repo, _ = _init_repo_with_commits(tmp_path)

    def boom(sha):
        raise OSError("network down")

    assert git_reachable(repo, is_shallow=lambda: True, deepen=boom)("e" * 40) is False
