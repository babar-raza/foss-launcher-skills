"""Tests for scripts/pipeline/commands/ops/sync_tracked_issues.py
(PKGINSTALL-DEFECT-SWEEP-REDESIGN, MT066 plan section R.3.4).

All GitHub I/O goes through a fake GitHubIssuesClient double -- a real DI
seam (sync_one/sync_all/find_tracked_issue accept the client as an explicit
parameter), never a monkeypatch of `requests` internals.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import commands.ops.sync_tracked_issues as sut  # noqa: E402


class _FakeGitHubIssuesClient:
    """In-memory fake -- real create/update/close semantics, no network."""

    def __init__(self):
        self._next_number = 1
        self.issues: dict[int, dict] = {}
        self.calls: list[tuple] = []

    def list_issues(self, *, label: str, state: str = "open"):
        self.calls.append(("list_issues", label, state))
        return [
            i for i in self.issues.values()
            if label in i.get("labels", []) and i.get("state", "open") == state
        ]

    def create_issue(self, *, title: str, body: str, labels: list[str]):
        number = self._next_number
        self._next_number += 1
        issue = {"number": number, "title": title, "body": body, "labels": labels, "state": "open"}
        self.issues[number] = issue
        self.calls.append(("create_issue", title))
        return issue

    def update_issue(self, number: int, *, body=None):
        issue = self.issues[number]
        if body is not None:
            issue["body"] = body
        self.calls.append(("update_issue", number))
        return issue

    def close_issue(self, number: int):
        issue = self.issues[number]
        issue["state"] = "closed"
        self.calls.append(("close_issue", number))
        return issue


class TestSyncOne:
    def test_first_run_with_findings_creates_an_issue(self):
        client = _FakeGitHubIssuesClient()
        result = sut.sync_one(client, family="words", platform="python", defect_class="literal_install_command", count=5)
        assert result["action"] == "created"
        assert len(client.issues) == 1
        create_calls = [c for c in client.calls if c[0] == "create_issue"]
        assert len(create_calls) == 1

    def test_second_run_with_unchanged_findings_updates_not_creates(self):
        """Dedup proof: a second sync for the same key must update the
        existing issue's body, never create a second one."""
        client = _FakeGitHubIssuesClient()
        sut.sync_one(client, family="words", platform="python", defect_class="literal_install_command", count=5)
        result = sut.sync_one(client, family="words", platform="python", defect_class="literal_install_command", count=5)

        assert result["action"] == "updated"
        assert len(client.issues) == 1, "must not create a second issue for the same key"
        create_calls = [c for c in client.calls if c[0] == "create_issue"]
        assert len(create_calls) == 1

    def test_count_change_updates_the_same_issue(self):
        client = _FakeGitHubIssuesClient()
        sut.sync_one(client, family="words", platform="python", defect_class="literal_install_command", count=5)
        result = sut.sync_one(client, family="words", platform="python", defect_class="literal_install_command", count=3)

        assert result["action"] == "updated"
        assert len(client.issues) == 1
        assert "3" in client.issues[1]["body"]

    def test_zero_findings_with_existing_open_issue_closes_it(self):
        client = _FakeGitHubIssuesClient()
        sut.sync_one(client, family="words", platform="python", defect_class="literal_install_command", count=5)
        result = sut.sync_one(client, family="words", platform="python", defect_class="literal_install_command", count=0)

        assert result["action"] == "closed"
        assert client.issues[1]["state"] == "closed"

    def test_zero_findings_with_no_existing_issue_is_a_noop(self):
        client = _FakeGitHubIssuesClient()
        result = sut.sync_one(client, family="words", platform="python", defect_class="literal_install_command", count=0)

        assert result["action"] == "noop"
        assert client.issues == {}

    def test_different_defect_classes_for_the_same_product_get_separate_issues(self):
        client = _FakeGitHubIssuesClient()
        sut.sync_one(client, family="words", platform="python", defect_class="literal_install_command", count=5)
        sut.sync_one(client, family="words", platform="python", defect_class="publish_claim_contradiction", count=2)

        assert len(client.issues) == 2

    def test_a_closed_issue_for_the_key_is_not_matched_by_find_tracked_issue(self):
        """Once closed, a NEW finding for the same key must open a fresh
        issue (list_issues only ever looks at state='open'), not silently
        reuse the closed one forever."""
        client = _FakeGitHubIssuesClient()
        sut.sync_one(client, family="words", platform="python", defect_class="literal_install_command", count=5)
        sut.sync_one(client, family="words", platform="python", defect_class="literal_install_command", count=0)
        result = sut.sync_one(client, family="words", platform="python", defect_class="literal_install_command", count=7)

        assert result["action"] == "created"
        assert len(client.issues) == 2


class TestSyncAll:
    def test_syncs_every_finding_independently(self):
        client = _FakeGitHubIssuesClient()
        findings = [
            {"family": "words", "platform": "python", "defect_class": "literal_install_command", "count": 5},
            {"family": "barcode", "platform": "python", "defect_class": "publish_claim_contradiction", "count": 9},
        ]
        results = sut.sync_all(client, findings)
        assert len(results) == 2
        assert all(r["action"] == "created" for r in results)
        assert len(client.issues) == 2

    def test_second_run_with_one_key_resolved_closes_only_that_one(self):
        client = _FakeGitHubIssuesClient()
        sut.sync_all(client, [
            {"family": "words", "platform": "python", "defect_class": "literal_install_command", "count": 5},
            {"family": "barcode", "platform": "python", "defect_class": "publish_claim_contradiction", "count": 9},
        ])
        results = sut.sync_all(client, [
            {"family": "words", "platform": "python", "defect_class": "literal_install_command", "count": 0},
            {"family": "barcode", "platform": "python", "defect_class": "publish_claim_contradiction", "count": 9},
        ])
        actions = {(r["key"], r["action"]) for r in results}
        assert ("words/python/literal_install_command", "closed") in actions
        assert ("barcode/python/publish_claim_contradiction", "updated") in actions


class TestFormatIssueBody:
    def test_embeds_the_key_marker(self):
        body = sut.format_issue_body("words", "python", "literal_install_command", 5, [])
        assert sut._key_marker("words/python/literal_install_command") in body

    def test_includes_sample_findings(self):
        body = sut.format_issue_body(
            "words", "python", "literal_install_command", 1,
            [{"path": "content/docs.aspose.org/en/words/python/x.md", "message": "boom"}],
        )
        assert "content/docs.aspose.org/en/words/python/x.md" in body
        assert "boom" in body


class TestFindTrackedIssue:
    def test_returns_none_when_no_issue_matches(self):
        client = _FakeGitHubIssuesClient()
        assert sut.find_tracked_issue(client, "words/python/literal_install_command") is None

    def test_ignores_issues_for_a_different_key(self):
        client = _FakeGitHubIssuesClient()
        sut.sync_one(client, family="words", platform="python", defect_class="literal_install_command", count=5)
        assert sut.find_tracked_issue(client, "barcode/python/publish_claim_contradiction") is None
