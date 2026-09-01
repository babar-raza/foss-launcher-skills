"""Tests for scripts/pipeline/lib/publication_reconciler.py (TC-15,
readme-refresh-trackb-and-followon-2026-09-01).

Real regression inputs: the exact two live cases this module was built to catch
(cells/typescript PR #2, 3d/net PR #3 -- both real, merged, human-approved
/readme-refresh publications this repo's own registry never recorded until this
mission's manual `gh pr view` investigation found them by hand).
"""

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


def _fake_gh_runner(pr_list_stdout: str, pr_list_returncode: int = 0, *, reachable: "bool | None" = True):
    """Routes gh's 3 distinct call shapes: `pr list` (caller-supplied), `api repos/{repo}`
    (default branch lookup), and `api repos/{repo}/compare/...` (reachability check).
    `reachable=True` -> compare returns status "ahead" (happy path for most existing
    tests); `reachable=False` -> compare fails like a real 404 "No common ancestor";
    `reachable=None` -> the default-branch lookup itself fails."""
    def _runner(argv, *args, **kwargs):
        if "pr" in argv and "list" in argv:
            return subprocess.CompletedProcess(argv, pr_list_returncode, stdout=pr_list_stdout, stderr="")
        if "api" in argv:
            api_arg = argv[argv.index("api") + 1]
            if "/compare/" in api_arg:
                if reachable is False:
                    return subprocess.CompletedProcess(argv, 1, stdout="", stderr="404 No common ancestor")
                return subprocess.CompletedProcess(
                    argv, 0, stdout=json.dumps({"status": "ahead"}), stderr="",
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

    state = json.loads((tmp_path / "data" / "readme_published_state.json").read_text(encoding="utf-8"))
    row = state["products"][0]
    assert row["family"] == "cells" and row["platform"] == "typescript"
    assert row["pr_number"] == 2
    # Original 4-field schema stays populated too -- additive, not a replacement shape.
    assert row["last_known_publication"] == "2026-08-14"
    assert "evidence" in row


def test_apply_reconciliation_is_noop_for_in_sync(tmp_path):
    report = {"family": "x", "platform": "y", "state": "IN_SYNC", "latest_readme_refresh_pr": None}
    assert pr.apply_reconciliation(report) is None


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
