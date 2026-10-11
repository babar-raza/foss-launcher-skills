"""Tests for the bulk --force model_version-jump gate (TC-SFH-007 guardrail).

Root incident: commit 643c02f7b8 ran `attach_evidence.py pdf net --force`
after the knowledge model jumped 0.1.0-alpha -> 26.6.0, re-stamping 845
pages' evidence.model_sha/model_version with zero body reconciliation.
attach_product() now refuses a bulk force re-stamp when the product's
currently-stamped evidence.model_version differs from the knowledge model's
current version by more than a trivial rebuild, unless
--confirm-model-version-jump (confirm_version_jump=True) is passed.

All tests use tmp_path; no real content/ files are read or written.
Dependencies (discover_content, attach_evidence, Knowledge) are injected via
evidence.runner.configure() -- the module's own T1/T2-compliant DI seam
(AGENTS.md 16.2) -- rather than unittest.mock.patch() on internal names.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PIPELINE_DIR = Path(__file__).resolve().parent.parent
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

import evidence.runner as runner
from evidence.runner import (
    attach_product,
    _is_model_version_jump,
    _parse_version_tuple,
    _sample_stamped_model_version,
)


@pytest.fixture(autouse=True)
def _reset_configure():
    """Reset the configure() seam after every test (module docstring: 'Call
    configure() with no args to reset')."""
    yield
    runner.configure()


def _make_md(path: Path, model_version="0.1.0-alpha") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = (
        "---\ntitle: Test\nweight: 1\n"
        "evidence:\n"
        "  model_sha: old-sha\n"
        f"  model_version: {model_version}\n"
        "  claims: []\n  apis: []\n---\n\n# Test\n\nContent.\n"
    )
    path.write_text(text, encoding="utf-8")
    return path


class _FakeKnowledge:
    def __init__(self, family, platform, version="26.6.0", repo_sha="new-sha"):
        self.family = family
        self.platform = platform
        self.available = True
        self.repo_sha = repo_sha
        self.version = version
        self.claim_ids = set()
        self.classes = {}
        self.api_to_claim = {}


def _knowledge_factory(version="26.6.0", repo_sha="new-sha"):
    """Return a knowledge_fn compatible with configure(knowledge_fn=...):
    called as knowledge_fn(family, platform), matching the real Knowledge class."""
    return lambda family, platform: _FakeKnowledge(family, platform, version=version, repo_sha=repo_sha)


# ---------------------------------------------------------------------------
# _parse_version_tuple / _is_model_version_jump unit tests
# ---------------------------------------------------------------------------


def test_parse_version_tuple_clean_semver():
    assert _parse_version_tuple("26.6.0") == (26, 6)
    assert _parse_version_tuple("26.6") == (26, 6)


def test_parse_version_tuple_prerelease_is_unparseable():
    assert _parse_version_tuple("0.1.0-alpha") is None


def test_parse_version_tuple_empty_is_unparseable():
    assert _parse_version_tuple("") is None
    assert _parse_version_tuple(None) is None


def test_version_jump_same_version_is_not_a_jump():
    assert not _is_model_version_jump("26.6.0", "26.6.0")


def test_version_jump_patch_only_is_not_a_jump():
    """Same major.minor, different patch -- trivial rebuild, not a jump."""
    assert not _is_model_version_jump("26.6.0", "26.6.1")


def test_version_jump_minor_bump_is_a_jump():
    assert _is_model_version_jump("26.6.0", "26.7.0")


def test_version_jump_from_prerelease_is_always_a_jump():
    """The exact TC-SFH-007 shape: 0.1.0-alpha -> 26.6.0."""
    assert _is_model_version_jump("0.1.0-alpha", "26.6.0")


# ---------------------------------------------------------------------------
# _sample_stamped_model_version
# ---------------------------------------------------------------------------


def test_sample_stamped_model_version_reads_first_page(tmp_path):
    f = tmp_path / "content/docs.aspose.org/en/pdf/net/page.md"
    _make_md(f, model_version="0.1.0-alpha")

    runner.configure(discover_content_fn=lambda family, platform: [f])
    assert _sample_stamped_model_version("pdf", "net") == "0.1.0-alpha"


def test_sample_stamped_model_version_none_when_no_evidence(tmp_path):
    f = tmp_path / "content/docs.aspose.org/en/pdf/net/page.md"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("---\ntitle: Test\n---\n\n# Test\n", encoding="utf-8")

    runner.configure(discover_content_fn=lambda family, platform: [f])
    assert _sample_stamped_model_version("pdf", "net") is None


# ---------------------------------------------------------------------------
# attach_product() gate integration
# ---------------------------------------------------------------------------


def test_bulk_force_refuses_on_real_version_jump(tmp_path):
    """The TC-SFH-007 shape: force=True, real jump, no confirm -> refused,
    attach_evidence is never called for any file."""
    f1 = tmp_path / "content/docs.aspose.org/en/pdf/net/page1.md"
    f2 = tmp_path / "content/docs.aspose.org/en/pdf/net/page2.md"
    _make_md(f1, model_version="0.1.0-alpha")
    _make_md(f2, model_version="0.1.0-alpha")

    called = []

    def fake_attach(fp, knowledge, dry_run=False, force=False, dry_run_records=None):
        called.append(str(fp))
        return "UPDATED"

    runner.configure(
        discover_content_fn=lambda family, platform: [f1, f2],
        attach_evidence_fn=fake_attach,
        knowledge_fn=_knowledge_factory(version="26.6.0"),
    )
    counts = attach_product("pdf", "net", force=True)

    assert called == []
    assert counts == {"REFUSED (model_version jump)": 2}


def test_bulk_force_proceeds_with_confirm_flag(tmp_path):
    """Same jump, but --confirm-model-version-jump passed -> proceeds."""
    f1 = tmp_path / "content/docs.aspose.org/en/pdf/net/page1.md"
    _make_md(f1, model_version="0.1.0-alpha")

    called = []

    def fake_attach(fp, knowledge, dry_run=False, force=False, dry_run_records=None):
        called.append(str(fp))
        return "UPDATED"

    runner.configure(
        discover_content_fn=lambda family, platform: [f1],
        attach_evidence_fn=fake_attach,
        knowledge_fn=_knowledge_factory(version="26.6.0"),
    )
    counts = attach_product("pdf", "net", force=True, confirm_version_jump=True)

    assert called == [str(f1)]
    assert counts.get("UPDATED") == 1


def test_bulk_force_proceeds_on_trivial_rebuild(tmp_path):
    """Same major.minor (just a SHA/patch rebuild) -> proceeds without the flag."""
    f1 = tmp_path / "content/docs.aspose.org/en/pdf/net/page1.md"
    _make_md(f1, model_version="26.6.0")

    called = []

    def fake_attach(fp, knowledge, dry_run=False, force=False, dry_run_records=None):
        called.append(str(fp))
        return "UPDATED"

    runner.configure(
        discover_content_fn=lambda family, platform: [f1],
        attach_evidence_fn=fake_attach,
        knowledge_fn=_knowledge_factory(version="26.6.1"),
    )
    counts = attach_product("pdf", "net", force=True)

    assert called == [str(f1)]
    assert counts.get("UPDATED") == 1


def test_bulk_force_proceeds_on_first_run_no_existing_evidence(tmp_path):
    """No page has an evidence block yet -- nothing to reconcile, gate doesn't apply."""
    f1 = tmp_path / "content/docs.aspose.org/en/pdf/net/page1.md"
    f1.parent.mkdir(parents=True, exist_ok=True)
    f1.write_text("---\ntitle: Test\n---\n\n# Test\n", encoding="utf-8")

    called = []

    def fake_attach(fp, knowledge, dry_run=False, force=False, dry_run_records=None):
        called.append(str(fp))
        return "UPDATED"

    runner.configure(
        discover_content_fn=lambda family, platform: [f1],
        attach_evidence_fn=fake_attach,
        knowledge_fn=_knowledge_factory(version="26.6.0"),
    )
    counts = attach_product("pdf", "net", force=True)

    assert called == [str(f1)]


def test_non_force_run_is_not_gated_even_on_real_jump(tmp_path):
    """force=False (default) never triggers the gate -- idempotent-skip logic
    inside attach_evidence() handles that path instead."""
    f1 = tmp_path / "content/docs.aspose.org/en/pdf/net/page1.md"
    _make_md(f1, model_version="0.1.0-alpha")

    called = []

    def fake_attach(fp, knowledge, dry_run=False, force=False, dry_run_records=None):
        called.append(str(fp))
        return "SKIP (current)"

    runner.configure(
        discover_content_fn=lambda family, platform: [f1],
        attach_evidence_fn=fake_attach,
        knowledge_fn=_knowledge_factory(version="26.6.0"),
    )
    counts = attach_product("pdf", "net", force=False)

    assert called == [str(f1)]
