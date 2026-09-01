"""Tests for scripts/pipeline/lib/publication_reconciler.py (TC-15,
readme-refresh-trackb-and-followon-2026-09-01).

Real regression inputs: the exact two live cases this module was built to catch
(cells/typescript PR #2, 3d/net PR #3 -- both real, merged, human-approved
/readme-refresh publications this repo's own registry never recorded until this
mission's manual `gh pr view` investigation found them by hand).
"""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from lib import publication_reconciler as pr


@pytest.fixture(autouse=True)
def _reset_config():
    yield
    pr.configure()


def _write_products(repo_root: Path, entries: list[dict]) -> None:
    (repo_root / "data").mkdir(parents=True, exist_ok=True)
    (repo_root / "data" / "products.json").write_text(
        json.dumps(entries, indent=2), encoding="utf-8",
    )


def _write_published_state(repo_root: Path, rows: list[dict]) -> None:
    (repo_root / "data").mkdir(parents=True, exist_ok=True)
    (repo_root / "data" / "readme_published_state.json").write_text(
        json.dumps({"schema_version": 1, "products": rows}, indent=2), encoding="utf-8",
    )


def _fake_gh_runner(
    pr_list_stdout: str, pr_list_returncode: int = 0, *, reachable: "bool | None" = True,
    merged_by_login: "str | None" = "babar-raza", readme_content: "str | None" = "# Real README\n",
):
    """Routes gh's 5 distinct call shapes: `pr list` (caller-supplied), `api repos/{repo}`
    (default branch lookup), `api repos/{repo}/compare/...` (reachability check),
    `api repos/{repo}/pulls/{number}` (TC-41: single-PR fetch for merged_by), and
    `api -H ... repos/{repo}/contents/README.md -f ref=...` (TC-41: live blob fetch).
    `reachable=True` -> compare returns status "ahead" (happy path for most existing
    tests); `reachable=False` -> compare fails like a real 404 "No common ancestor";
    `reachable=None` -> the default-branch lookup itself fails. `merged_by_login=None` /
    `readme_content=None` simulate a gh failure on those specific TC-41 calls."""
    def _runner(argv, *args, **kwargs):
        if "pr" in argv and "list" in argv:
            return subprocess.CompletedProcess(argv, pr_list_returncode, stdout=pr_list_stdout, stderr="")
        if "api" in argv:
            joined = " ".join(argv)
            if "contents/README.md" in joined:
                if readme_content is None:
                    return subprocess.CompletedProcess(argv, 1, stdout="", stderr="not found")
                return subprocess.CompletedProcess(argv, 0, stdout=readme_content, stderr="")
            api_arg = argv[argv.index("api") + 1]
            if "/compare/" in api_arg:
                if reachable is False:
                    return subprocess.CompletedProcess(argv, 1, stdout="", stderr="404 No common ancestor")
                return subprocess.CompletedProcess(
                    argv, 0, stdout=json.dumps({"status": "ahead"}), stderr="",
                )
            if "/pulls/" in api_arg:
                if merged_by_login is None:
                    return subprocess.CompletedProcess(argv, 1, stdout="", stderr="not found")
                return subprocess.CompletedProcess(
                    argv, 0, stdout=json.dumps({"merged_by": {"login": merged_by_login}}), stderr="",
                )
            # repos/{owner}/{repo} -- default branch lookup
            if reachable is None:
                return subprocess.CompletedProcess(argv, 1, stdout="", stderr="rate limited")
            return subprocess.CompletedProcess(argv, 0, stdout=json.dumps({"default_branch": "main"}), stderr="")
        raise AssertionError(f"unexpected gh invocation: {argv!r}")
    return _runner


_MERGED_PRS_ONE_REFRESH = json.dumps([
    {
        "number": 2, "mergedAt": "2026-08-14T14:57:33Z",
        "headRefName": "readme-refresh/2026-08-14",
        "mergeCommit": {"oid": "fc186507e5b7124f4664aa6035f25cfd3112367d"},
        "url": "https://github.com/aspose-cells-foss/Aspose.Cells-FOSS-for-TypeScript/pull/2",
    },
    {
        "number": 1, "mergedAt": "2026-06-01T00:00:00Z",
        "headRefName": "some-other-branch",
        "mergeCommit": {"oid": "deadbeef"},
        "url": "https://example.com/pull/1",
    },
])


def test_reconcile_finds_unrecorded_publication_real_cells_typescript_case(tmp_path):
    """The exact live regression: cells/typescript PR #2, no registry entry at all."""
    _write_products(tmp_path, [{
        "family": "cells", "platform": "typescript",
        "repo_url": "https://github.com/aspose-cells-foss/Aspose.Cells-FOSS-for-TypeScript",
        "active": True,
    }])
    _write_published_state(tmp_path, [])  # no entry -- the real, live gap
    pr.configure(repo_root=tmp_path, command_runner=_fake_gh_runner(_MERGED_PRS_ONE_REFRESH))

    report = pr.reconcile_product("cells", "typescript")
    assert report["state"] == "UNRECORDED_PUBLICATION"
    assert report["latest_readme_refresh_pr"]["number"] == 2
    assert report["registry_entry"] is None


def test_reconcile_ignores_non_readme_refresh_branches(tmp_path):
    """Only the second PR (readme-refresh/... branch) counts; a real other-purpose PR
    merged on the same repo must never be mistaken for a readme-refresh publication."""
    _write_products(tmp_path, [{
        "family": "cells", "platform": "typescript",
        "repo_url": "https://github.com/aspose-cells-foss/Aspose.Cells-FOSS-for-TypeScript",
        "active": True,
    }])
    only_other_pr = json.dumps([{
        "number": 9, "mergedAt": "2026-06-01T00:00:00Z",
        "headRefName": "fix-something-unrelated",
        "mergeCommit": {"oid": "cafef00d"},
        "url": "https://example.com/pull/9",
    }])
    pr.configure(repo_root=tmp_path, command_runner=_fake_gh_runner(only_other_pr))

    report = pr.reconcile_product("cells", "typescript")
    assert report["state"] == "UNPUBLISHED"


def test_reconcile_in_sync_when_registry_already_cites_the_pr(tmp_path):
    _write_products(tmp_path, [{
        "family": "cells", "platform": "typescript",
        "repo_url": "https://github.com/aspose-cells-foss/Aspose.Cells-FOSS-for-TypeScript",
        "active": True,
    }])
    _write_published_state(tmp_path, [{
        "family": "cells", "platform": "typescript",
        "last_known_publication": "2026-08-14",
        "evidence": "PR #2 squash-merged 2026-08-14",
    }])
    pr.configure(repo_root=tmp_path, command_runner=_fake_gh_runner(_MERGED_PRS_ONE_REFRESH))

    report = pr.reconcile_product("cells", "typescript")
    assert report["state"] == "IN_SYNC"


def test_reconcile_stale_registry_entry_pointing_at_an_older_pr_is_unrecorded(tmp_path):
    """A registry entry that exists but cites a DIFFERENT (older) PR than the real latest
    readme-refresh publication must still surface as needing reconciliation."""
    _write_products(tmp_path, [{
        "family": "cells", "platform": "typescript",
        "repo_url": "https://github.com/aspose-cells-foss/Aspose.Cells-FOSS-for-TypeScript",
        "active": True,
    }])
    _write_published_state(tmp_path, [{
        "family": "cells", "platform": "typescript",
        "last_known_publication": "2026-05-01",
        "evidence": "PR #1 merged pre-history, unrelated",
    }])
    pr.configure(repo_root=tmp_path, command_runner=_fake_gh_runner(_MERGED_PRS_ONE_REFRESH))

    report = pr.reconcile_product("cells", "typescript")
    assert report["state"] == "UNRECORDED_PUBLICATION"


def test_reconcile_reverted_when_merge_commit_unreachable_real_font_python_case(tmp_path):
    """The critical safety regression: font/python's real PR #1 (merge commit
    7971880964143c86ffd4baa7c8ea1dd959fea04e) shows as merged via `gh pr list`, but this
    repo's own prior investigation confirmed via `gh api .../compare/...` that the commit
    has "No common ancestor" with the live default branch -- the publication was wiped.
    Must classify REVERTED, never UNRECORDED_PUBLICATION (which apply_reconciliation
    would then be free to write as a false "IN_SYNC" record for the one product under the
    strictest hard rule in this mission: font/python must never be treated as published)."""
    _write_products(tmp_path, [{
        "family": "font", "platform": "python",
        "repo_url": "https://github.com/aspose-font-foss/Aspose.Font-FOSS-for-Python",
        "active": True,
    }])
    _write_published_state(tmp_path, [])
    merged_prs = json.dumps([{
        "number": 1, "mergedAt": "2026-08-15T15:22:31Z",
        "headRefName": "readme-refresh/2026-08-15",
        "mergeCommit": {"oid": "7971880964143c86ffd4baa7c8ea1dd959fea04e"},
        "url": "https://github.com/aspose-font-foss/Aspose.Font-FOSS-for-Python/pull/1",
    }])
    pr.configure(repo_root=tmp_path, command_runner=_fake_gh_runner(merged_prs, reachable=False))

    report = pr.reconcile_product("font", "python")
    assert report["state"] == "REVERTED"
    # And the safety net holds even if a caller ignores the state and calls apply anyway:
    assert pr.apply_reconciliation(report) is None


def test_reconcile_unconfirmed_reachability_when_ancestry_check_itself_fails(tmp_path):
    _write_products(tmp_path, [{
        "family": "cells", "platform": "typescript",
        "repo_url": "https://github.com/aspose-cells-foss/Aspose.Cells-FOSS-for-TypeScript",
        "active": True,
    }])
    pr.configure(repo_root=tmp_path, command_runner=_fake_gh_runner(_MERGED_PRS_ONE_REFRESH, reachable=None))

    report = pr.reconcile_product("cells", "typescript")
    assert report["state"] == "UNCONFIRMED_REACHABILITY"
    assert pr.apply_reconciliation(report) is None


def test_reconcile_no_repo_access_on_gh_failure_never_raises(tmp_path):
    _write_products(tmp_path, [{
        "family": "cells", "platform": "typescript",
        "repo_url": "https://github.com/aspose-cells-foss/Aspose.Cells-FOSS-for-TypeScript",
        "active": True,
    }])
    pr.configure(repo_root=tmp_path, command_runner=_fake_gh_runner("", pr_list_returncode=1))

    report = pr.reconcile_product("cells", "typescript")
    assert report["state"] == "NO_REPO_ACCESS"


def test_reconcile_no_repo_access_when_product_unknown(tmp_path):
    _write_products(tmp_path, [])
    report = pr.reconcile_product("nope", "nowhere")
    assert report["state"] == "NO_REPO_ACCESS"


def test_apply_reconciliation_writes_additive_fields(tmp_path):
    _write_products(tmp_path, [{
        "family": "cells", "platform": "typescript",
        "repo_url": "https://github.com/aspose-cells-foss/Aspose.Cells-FOSS-for-TypeScript",
        "active": True,
    }])
    _write_published_state(tmp_path, [])
    pr.configure(repo_root=tmp_path, command_runner=_fake_gh_runner(_MERGED_PRS_ONE_REFRESH))

    report = pr.reconcile_product("cells", "typescript")
    written = pr.apply_reconciliation(report)
    assert written["pr_number"] == 2
    assert written["reconciliation_state"] == "IN_SYNC"
    # TC-41: fingerprint fields written alongside the original schema.
    assert written["published_blob_sha256"] == hashlib.sha256("# Real README\n".encode("utf-8")).hexdigest()
    assert written["published_commit"] == "fc186507e5b7124f4664aa6035f25cfd3112367d"
    assert written["merged_by_login"] == "babar-raza"

    state = json.loads((tmp_path / "data" / "readme_published_state.json").read_text(encoding="utf-8"))
    row = state["products"][0]
    assert row["family"] == "cells" and row["platform"] == "typescript"
    assert row["pr_number"] == 2
    # Original 4-field schema stays populated too -- additive, not a replacement shape.
    assert row["last_known_publication"] == "2026-08-14"
    assert "evidence" in row


def test_apply_reconciliation_tolerates_fingerprint_fetch_failure(tmp_path):
    """TC-41: a gh failure on the NEW fingerprint calls must never break the existing,
    already-proven UNRECORDED_PUBLICATION write -- the core registry entry still lands,
    just without the fields gh couldn't confirm."""
    _write_products(tmp_path, [{
        "family": "cells", "platform": "typescript",
        "repo_url": "https://github.com/aspose-cells-foss/Aspose.Cells-FOSS-for-TypeScript",
        "active": True,
    }])
    _write_published_state(tmp_path, [])
    pr.configure(repo_root=tmp_path, command_runner=_fake_gh_runner(
        _MERGED_PRS_ONE_REFRESH, merged_by_login=None, readme_content=None,
    ))

    report = pr.reconcile_product("cells", "typescript")
    written = pr.apply_reconciliation(report)
    assert written["pr_number"] == 2  # core write still succeeds
    assert "published_blob_sha256" not in written
    assert "merged_by_login" not in written


def test_apply_reconciliation_refreshes_fingerprint_on_in_sync(tmp_path):
    """TC-41: the 28 already-IN_SYNC products (from TC-15's own live sweep) need their
    fingerprint populated too, on re-reconciliation -- not just newly-discovered
    UNRECORDED_PUBLICATION rows -- since TC-17's regression check needs a recorded
    baseline for every already-published product, not only future ones."""
    _write_products(tmp_path, [{
        "family": "cells", "platform": "typescript",
        "repo_url": "https://github.com/aspose-cells-foss/Aspose.Cells-FOSS-for-TypeScript",
        "active": True,
    }])
    _write_published_state(tmp_path, [{
        "family": "cells", "platform": "typescript",
        "last_known_publication": "2026-08-14",
        "evidence": "PR #2 squash-merged 2026-08-14",
    }])
    pr.configure(repo_root=tmp_path, command_runner=_fake_gh_runner(_MERGED_PRS_ONE_REFRESH))

    report = pr.reconcile_product("cells", "typescript")
    assert report["state"] == "IN_SYNC"
    written = pr.apply_reconciliation(report)
    assert written is not None
    assert written["published_blob_sha256"] == hashlib.sha256("# Real README\n".encode("utf-8")).hexdigest()
    assert written["merged_by_login"] == "babar-raza"
    # Original fields the IN_SYNC row already had are genuinely untouched, not rewritten.
    assert written["evidence"] == "PR #2 squash-merged 2026-08-14"


def test_apply_reconciliation_in_sync_noop_without_resolvable_pr_or_repo(tmp_path):
    report = {"family": "x", "platform": "y", "state": "IN_SYNC", "latest_readme_refresh_pr": None}
    assert pr.apply_reconciliation(report) is None


def test_merged_by_login_identical_across_every_real_sampled_merge_never_gates(tmp_path):
    """TC-41's own live investigation finding, pinned as a regression test: font/python's
    real, REVERTED PR #1 -- the exact case the strictest hard rule in this mission exists
    to catch -- shows the SAME merged_by ('babar-raza') as every legitimate merge. This
    proves the identity field cannot discriminate REVERTED from a real publication in this
    repo, and confirms apply_reconciliation never even reaches the fingerprint/identity
    code path for REVERTED (the ancestor-reachability check alone is what protects
    font/python, not merged_by)."""
    _write_products(tmp_path, [{
        "family": "font", "platform": "python",
        "repo_url": "https://github.com/aspose-font-foss/Aspose.Font-FOSS-for-Python",
        "active": True,
    }])
    _write_published_state(tmp_path, [])
    merged_prs = json.dumps([{
        "number": 1, "mergedAt": "2026-08-15T15:22:31Z",
        "headRefName": "readme-refresh/2026-08-15",
        "mergeCommit": {"oid": "7971880964143c86ffd4baa7c8ea1dd959fea04e"},
        "url": "https://github.com/aspose-font-foss/Aspose.Font-FOSS-for-Python/pull/1",
    }])
    pr.configure(repo_root=tmp_path, command_runner=_fake_gh_runner(
        merged_prs, reachable=False, merged_by_login="babar-raza",
    ))

    report = pr.reconcile_product("font", "python")
    assert report["state"] == "REVERTED"
    assert pr.apply_reconciliation(report) is None  # never written, regardless of merged_by



def test_apply_reconciliation_updates_existing_row_in_place(tmp_path):
    _write_products(tmp_path, [{
        "family": "cells", "platform": "typescript",
        "repo_url": "https://github.com/aspose-cells-foss/Aspose.Cells-FOSS-for-TypeScript",
        "active": True,
    }])
    _write_published_state(tmp_path, [
        {"family": "cells", "platform": "typescript", "last_known_publication": "2026-05-01",
         "evidence": "stale, unrelated entry"},
        {"family": "other", "platform": "product", "last_known_publication": "2026-01-01",
         "evidence": "untouched sibling row"},
    ])
    pr.configure(repo_root=tmp_path, command_runner=_fake_gh_runner(_MERGED_PRS_ONE_REFRESH))

    report = pr.reconcile_product("cells", "typescript")
    pr.apply_reconciliation(report)

    state = json.loads((tmp_path / "data" / "readme_published_state.json").read_text(encoding="utf-8"))
    assert len(state["products"]) == 2  # updated in place, not appended as a duplicate
    other = next(r for r in state["products"] if r["family"] == "other")
    assert other["evidence"] == "untouched sibling row"  # sibling row genuinely untouched


def test_reconcile_portfolio_sweeps_explicit_pair_list_only(tmp_path):
    _write_products(tmp_path, [
        {"family": "cells", "platform": "typescript",
         "repo_url": "https://github.com/aspose-cells-foss/Aspose.Cells-FOSS-for-TypeScript",
         "active": True},
    ])
    _write_published_state(tmp_path, [])
    pr.configure(repo_root=tmp_path, command_runner=_fake_gh_runner(_MERGED_PRS_ONE_REFRESH))

    reports = pr.reconcile_portfolio([("cells", "typescript")])
    assert len(reports) == 1
    assert reports[0]["state"] == "UNRECORDED_PUBLICATION"


# --- fetch_current_readme_blob_sha256 (TC-17, MT061-2026-09-01-TRACKB-FOLLOWON-2) -----------


def test_fetch_current_readme_blob_sha256_calls_contents_endpoint_with_no_ref(tmp_path):
    """The 'current live' half of check_live_published_regression's comparison: no ref
    pinned at all, so gh resolves it to whatever is live on the default branch right now --
    deliberately different from TC-41's _fetch_readme_blob_sha256(repo, merge_commit_sha)
    callers, which always pin a specific historical commit."""
    _write_products(tmp_path, [{
        "family": "cells", "platform": "typescript",
        "repo_url": "https://github.com/aspose-cells-foss/Aspose.Cells-FOSS-for-TypeScript",
        "active": True,
    }])
    seen_urls = []

    def _runner(argv, *args, **kwargs):
        joined = " ".join(argv)
        seen_urls.append(joined)
        return subprocess.CompletedProcess(argv, 0, stdout="# Live content right now\n", stderr="")

    pr.configure(repo_root=tmp_path, command_runner=_runner)
    result = pr.fetch_current_readme_blob_sha256("cells", "typescript")

    assert result == hashlib.sha256("# Live content right now\n".encode("utf-8")).hexdigest()
    assert len(seen_urls) == 1
    assert "contents/README.md" in seen_urls[0]
    assert "?ref=" not in seen_urls[0]  # no ref pinned -- current default-branch content


def test_fetch_current_readme_blob_sha256_returns_none_on_gh_failure(tmp_path):
    _write_products(tmp_path, [{
        "family": "cells", "platform": "typescript",
        "repo_url": "https://github.com/aspose-cells-foss/Aspose.Cells-FOSS-for-TypeScript",
        "active": True,
    }])
    pr.configure(
        repo_root=tmp_path,
        command_runner=lambda argv, **kw: subprocess.CompletedProcess(argv, 1, stdout="", stderr="rate limited"),
    )
    assert pr.fetch_current_readme_blob_sha256("cells", "typescript") is None


def test_fetch_current_readme_blob_sha256_returns_none_for_unresolvable_product(tmp_path):
    _write_products(tmp_path, [])  # no matching product/repo_url at all
    pr.configure(repo_root=tmp_path, command_runner=lambda argv, **kw: (_ for _ in ()).throw(
        AssertionError("must not call gh when the repo cannot even be resolved")
    ))
    assert pr.fetch_current_readme_blob_sha256("unknown", "unknown") is None


def test_fetch_readme_blob_sha256_still_supports_pinned_ref_backward_compatible(tmp_path):
    """TC-41's existing callers (_fetch_fingerprint_fields, pinned to a merge_commit_sha) must
    keep working unchanged after this function's signature grew an optional ref."""
    _write_products(tmp_path, [{
        "family": "cells", "platform": "typescript",
        "repo_url": "https://github.com/aspose-cells-foss/Aspose.Cells-FOSS-for-TypeScript",
        "active": True,
    }])
    seen_urls = []

    def _runner(argv, *args, **kwargs):
        seen_urls.append(" ".join(argv))
        return subprocess.CompletedProcess(argv, 0, stdout="# Pinned content\n", stderr="")

    pr.configure(repo_root=tmp_path, command_runner=_runner)
    result = pr._fetch_readme_blob_sha256(
        "aspose-cells-foss/Aspose.Cells-FOSS-for-TypeScript", "abc123deadbeef",
    )
    assert result == hashlib.sha256("# Pinned content\n".encode("utf-8")).hexdigest()
    assert "?ref=abc123deadbeef" in seen_urls[0]
