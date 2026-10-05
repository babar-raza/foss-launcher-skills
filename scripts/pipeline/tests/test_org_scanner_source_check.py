"""Tests for org_scanner.has_product_source / default_branch (MT075 TC-RPG-04).

A repo is a *product* iff its DEFAULT branch carries product source. The HTTP call
is injected through the ``fetch`` seam (and ``sleep`` for the rate-limit retry), so
nothing here patches module internals.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_PIPELINE = Path(__file__).resolve().parents[1]
for _p in (str(_PIPELINE), str(_PIPELINE / "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import org_scanner  # noqa: E402


def _blob(path):
    return {"path": path, "type": "blob"}


def _tree(path):
    return {"path": path, "type": "tree"}


class _Fetch:
    """Injectable HTTP seam: returns canned responses in order, records URLs/headers."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.urls = []
        self.headers = []

    def __call__(self, url, headers, timeout=30):
        self.urls.append(url)
        self.headers.append(headers)
        r = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(r, Exception):
            raise r
        return r


def _resp(status=200, body=None, headers=None):
    r = MagicMock()
    r.status_code = status
    r.headers = headers or {}
    r.json.return_value = body if body is not None else {}
    return r


def _tree_resp(*nodes, truncated=False):
    return _resp(200, {"tree": list(nodes), "truncated": truncated})


def _probe(*responses, branch="main", **kw):
    fetch = _Fetch(*responses)
    out = org_scanner.has_product_source("some-org", "some-repo", branch,
                                         token="tok", fetch=fetch, **kw)
    return out, fetch


class TestSourceClassification:
    def test_source_at_root_is_source(self):
        out, _ = _probe(_tree_resp(_blob("README.md"), _blob("main.py")))
        assert out is True

    def test_nested_source_is_source(self):
        out, _ = _probe(_tree_resp(_blob("README.md"), _tree("src"), _blob("src/x.py")))
        assert out is True

    def test_readme_only_is_not_source(self):
        out, _ = _probe(_tree_resp(_blob("README.md")))
        assert out is False

    def test_boilerplate_only_is_not_source(self):
        out, _ = _probe(_tree_resp(
            _blob("README.rst"), _blob("LICENSE"), _blob("license.txt"),
            _blob("CHANGELOG.md"), _blob("SECURITY.md"), _blob("CONTRIBUTING.md"),
            _blob("CODE_OF_CONDUCT.md"), _blob("Readme")))
        assert out is False

    def test_docs_only_is_not_source(self):
        out, _ = _probe(_tree_resp(_blob("README.md"), _tree("docs"),
                                   _blob("docs/index.md"), _blob("docs/guide/a.rst")))
        assert out is False

    def test_github_only_is_not_source(self):
        out, _ = _probe(_tree_resp(_blob("README.md"), _tree(".github"),
                                   _blob(".github/workflows/ci.yml"),
                                   _blob(".github/FUNDING.yml")))
        assert out is False

    def test_dotfiles_only_is_not_source(self):
        out, _ = _probe(_tree_resp(_blob(".gitignore"), _blob(".gitattributes"),
                                   _blob(".editorconfig"), _blob(".config/tool.json")))
        assert out is False

    def test_trees_alone_are_not_source(self):
        out, _ = _probe(_tree_resp(_tree("src"), _tree("lib")))
        assert out is False

    def test_empty_tree_is_not_source(self):
        out, _ = _probe(_tree_resp())
        assert out is False

    def test_non_boilerplate_root_file_is_source(self):
        out, _ = _probe(_tree_resp(_blob("README.md"), _blob("pyproject.toml")))
        assert out is True

    def test_docs_dir_match_is_root_only_and_case_insensitive(self):
        assert _probe(_tree_resp(_blob("Docs/a.md")))[0] is False
        assert _probe(_tree_resp(_blob("src/docs/a.py")))[0] is True

    def test_truncated_tree_counts_as_source(self):
        out, _ = _probe(_tree_resp(_blob("README.md"), truncated=True))
        assert out is True

    def test_is_source_path_unit(self):
        assert org_scanner._is_source_path("src/x.py") is True
        assert org_scanner._is_source_path("README.md") is False
        assert org_scanner._is_source_path(".github/x.yml") is False
        assert org_scanner._is_source_path("") is False


class TestRequestShape:
    @pytest.mark.parametrize("branch", ["main", "master"])
    def test_url_uses_the_default_branch(self, branch):
        _, fetch = _probe(_tree_resp(_blob("a.py")), branch=branch)
        assert fetch.urls == [
            f"https://api.github.com/repos/some-org/some-repo/git/trees/{branch}?recursive=1"
        ]

    def test_full_name_is_accepted_and_repo_name_ignored(self):
        fetch = _Fetch(_tree_resp(_blob("a.py")))
        out = org_scanner.has_product_source("org-x/repo-y", "ignored", "main",
                                             token="tok", fetch=fetch)
        assert out is True
        assert fetch.urls == [
            "https://api.github.com/repos/org-x/repo-y/git/trees/main?recursive=1"
        ]

    def test_authorization_header_sent_and_token_optional(self):
        _, fetch = _probe(_tree_resp(_blob("a.py")))
        assert fetch.headers[0]["Authorization"] == "Bearer tok"
        fetch2 = _Fetch(_tree_resp(_blob("a.py")))
        org_scanner.has_product_source("o", "r", "main", token=None, fetch=fetch2)
        assert "Authorization" not in fetch2.headers[0]


class TestUnknownAndEmpty:
    def test_empty_default_branch_is_unknown_without_a_request(self):
        fetch = _Fetch(_tree_resp(_blob("a.py")))
        assert org_scanner.has_product_source("o", "r", "", token="t", fetch=fetch) is None
        assert fetch.urls == []

    def test_409_empty_repository_is_false(self):
        out, _ = _probe(_resp(409, {"message": "Git Repository is empty."}))
        assert out is False

    @pytest.mark.parametrize("status", [401, 403, 404, 422, 500, 502, 503])
    def test_http_errors_are_unknown_not_false(self, status):
        out, _ = _probe(_resp(status, {"message": "boom"}))
        assert out is None

    def test_network_exception_is_unknown_never_raises(self):
        out, _ = _probe(ConnectionError("reset"))
        assert out is None

    def test_malformed_json_is_unknown(self):
        bad = _resp(200)
        bad.json.side_effect = ValueError("not json")
        assert _probe(bad)[0] is None
        assert _probe(_resp(200, {"unexpected": 1}))[0] is None
        assert _probe(_resp(200, ["not", "a", "dict"]))[0] is None

    def test_auth_403_with_quota_left_is_unknown_without_sleep(self):
        slept = []
        out, fetch = _probe(
            _resp(403, {"message": "forbidden"}, {"X-RateLimit-Remaining": "4990"}),
            sleep=slept.append)
        assert out is None and slept == [] and len(fetch.urls) == 1


class TestRateLimit:
    def test_rate_limit_waits_capped_then_retries_once(self):
        slept = []
        limited = _resp(403, {"message": "rate limit"}, {"X-RateLimit-Remaining": "0"})
        out, fetch = _probe(limited, _tree_resp(_blob("a.py")),
                            sleep=slept.append, max_rate_wait=7)
        assert out is True
        assert len(fetch.urls) == 2
        assert len(slept) == 1 and slept[0] <= 7

    def test_still_rate_limited_after_retry_is_unknown(self):
        slept = []
        limited = _resp(429, {"message": "slow down"}, {"Retry-After": "3"})
        out, fetch = _probe(limited, sleep=slept.append)
        assert out is None
        assert len(fetch.urls) == 2 and slept == [3]


class TestScanOrgReturnsDefaultBranch:
    def test_scan_org_includes_default_branch(self):
        page = _resp(200, [
            {"name": "a", "full_name": "o/a", "html_url": "h", "clone_url": "c",
             "default_branch": "master"},
            {"name": "b", "full_name": "o/b", "html_url": "h", "clone_url": "c"},
        ])
        # T3-MOCK: target=requests reason="HTTP boundary call to GitHub API" removal=PERMANENT
        with patch.object(org_scanner, "requests") as mock_req:
            mock_req.get.return_value = page
            repos = org_scanner.scan_org("o", token="t")
        assert [r["default_branch"] for r in repos] == ["master", ""]
