"""Tests for the dead_internal_link evaluator (G-18).

Root cause under test: Hugo renders a leaf page (e.g. developer-guide/diff.md) one
URL segment deeper than its filesystem location (.../developer-guide/diff/), while
a section index (_index.md) or leaf bundle (index.md) deploys at the same depth as
its directory. Relative sibling links (../sibling/) are authored against the
rendered URL, so the evaluator must resolve them against that same base — not the
raw filesystem directory.

These tests build real directory trees under tmp_path because the evaluator
performs actual Path.exists() checks.
"""
from __future__ import annotations

from pathlib import Path

from content_eval.evaluators.dead_internal_link import DeadInternalLinkEvaluator
from content_eval.models import Link, Page


def _make_page(filepath: Path, links: list[Link]) -> Page:
    return Page(filepath=filepath, raw_text="dummy", links=links)


def _link(url: str, line_no: int = 1) -> Link:
    return Link(text="link", url=url, line_no=line_no, is_internal=True)


class TestDeadInternalLinkLeafPage:
    """A plain leaf page (e.g. developer-guide/diff.md) renders one segment deeper
    than its filesystem location."""

    def test_leaf_page_sibling_resolves(self, tmp_path):
        dev_guide = tmp_path / "developer-guide"
        dev_guide.mkdir()
        (dev_guide / "diff.md").write_text("# Diff\n", encoding="utf-8")
        (dev_guide / "exceptions.md").write_text("# Exceptions\n", encoding="utf-8")

        page = _make_page(dev_guide / "diff.md", [_link("../exceptions/")])
        findings = DeadInternalLinkEvaluator().evaluate(page, None)

        assert findings == [], f"sibling link should resolve, got: {findings}"

    def test_leaf_page_broken_link_still_flagged(self, tmp_path):
        """Proves the fix doesn't over-correct — a genuinely broken link is still caught."""
        dev_guide = tmp_path / "developer-guide"
        dev_guide.mkdir()
        (dev_guide / "diff.md").write_text("# Diff\n", encoding="utf-8")

        page = _make_page(dev_guide / "diff.md", [_link("../nonexistent-sibling/")])
        findings = DeadInternalLinkEvaluator().evaluate(page, None)

        assert len(findings) == 1
        assert findings[0].category == "DL"
        assert findings[0].level == "WARN"


class TestDeadInternalLinkSectionAndBundle:
    """_index.md (section) and index.md (leaf bundle) deploy at the same depth as
    their directory — no extra URL segment."""

    def test_index_page_resolves(self, tmp_path):
        dev_guide = tmp_path / "developer-guide"
        dev_guide.mkdir()
        (dev_guide / "_index.md").write_text("# Developer Guide\n", encoding="utf-8")
        gs = tmp_path / "getting-started"
        gs.mkdir()
        (gs / "_index.md").write_text("# Getting Started\n", encoding="utf-8")

        page = _make_page(dev_guide / "_index.md", [_link("../getting-started/")])
        findings = DeadInternalLinkEvaluator().evaluate(page, None)

        assert findings == [], f"section sibling link should resolve, got: {findings}"

    def test_index_md_page_bundle_resolves(self, tmp_path):
        """Regression guard: a naive fix keying only on stem == '_index' would treat
        this Hugo leaf-bundle file as a regular leaf page, adding a spurious URL
        segment and breaking this exact resolution."""
        post_a = tmp_path / "blog-post-a"
        post_a.mkdir()
        (post_a / "index.md").write_text("# Post A\n", encoding="utf-8")
        post_b = tmp_path / "blog-post-b"
        post_b.mkdir()
        (post_b / "index.md").write_text("# Post B\n", encoding="utf-8")

        page = _make_page(post_a / "index.md", [_link("../blog-post-b/")])
        findings = DeadInternalLinkEvaluator().evaluate(page, None)

        assert findings == [], f"leaf-bundle sibling link should resolve, got: {findings}"


class TestDeadInternalLinkTwoLevelsUp:
    def test_two_levels_up_resolves(self, tmp_path):
        dev_guide = tmp_path / "pdf" / "net" / "developer-guide"
        dev_guide.mkdir(parents=True)
        (dev_guide / "diff.md").write_text("# Diff\n", encoding="utf-8")
        quickstart_dir = tmp_path / "pdf" / "net" / "getting-started"
        quickstart_dir.mkdir(parents=True)
        (quickstart_dir / "quickstart.md").write_text("# Quickstart\n", encoding="utf-8")

        page = _make_page(dev_guide / "diff.md", [_link("../../getting-started/quickstart/")])
        findings = DeadInternalLinkEvaluator().evaluate(page, None)

        assert findings == [], f"two-level-up link should resolve, got: {findings}"


class TestDeadInternalLinkScopeBoundary:
    def test_absolute_and_bare_relative_links_out_of_scope(self, tmp_path):
        """Documents current scope boundary, not new behavior: absolute paths are
        skipped entirely, even when the target does not exist locally."""
        dev_guide = tmp_path / "developer-guide"
        dev_guide.mkdir()
        (dev_guide / "diff.md").write_text("# Diff\n", encoding="utf-8")

        page = _make_page(
            dev_guide / "diff.md",
            [_link("/pdf/net/developer-guide/does-not-exist/")],
        )
        findings = DeadInternalLinkEvaluator().evaluate(page, None)

        assert findings == [], "absolute paths must remain out of scope for this evaluator"
