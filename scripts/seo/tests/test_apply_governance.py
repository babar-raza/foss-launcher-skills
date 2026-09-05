"""SEO-008 apply.py: governance gate tests (SEO-APPLY-HARDEN).

Covers the confirmed bypasses from the 2026-03-27 incident audit (Findings
#2, #5, #6, #9, #16 in the mission plan): requires_human_review read but
never enforced, auto_updatable never checked, no_downgrade_guard never
wired in, yaml.dump() losing formatting, and seoTitle being a dead write
target everywhere except blog.

Scope note: description-length bounds and claim/format-grounding checks are
safety.py's responsibility (a separate, upstream module gating what ever
reaches a patch_manifest.json in the first place) -- not tested here, since
apply.py itself has no access to claims.json/formats.json and this task's
plan scope is apply.py's own write path.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure scripts/seo and scripts/pipeline are on sys.path
_SCRIPTS = Path(__file__).resolve().parents[2]
_PIPELINE = _SCRIPTS / "pipeline"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
if str(_PIPELINE) not in sys.path:
    sys.path.insert(0, str(_PIPELINE))

import seo.pipeline.apply as apply_mod  # noqa: E402

_DOCS_FM = """---
title: "Sample Page"
description: Original description.
evidence:
  model_sha: "abc123"
  claims: [CLM-1]
  apis: []
  formats: []
---
Body content here.
"""

_DOCS_FM_AUTO_UPDATABLE_FALSE = """---
title: "Sample Page"
description: Original description.
provenance:
  auto_updatable: false
  last_mechanism: manual-edit-skill
evidence:
  model_sha: "abc123"
  claims: [CLM-1]
  apis: []
  formats: []
---
Body content here.
"""

_BLOG_FM = """---
title: "Sample Blog Post"
seoTitle: Old SEO Title
description: Original description.
tags: []
evidence:
  model_sha: "abc123"
  claims: [CLM-1]
  apis: []
  formats: []
---
Body content here.
"""


def _write_fixture(tmp_path: Path, rel_path: str, content: str) -> Path:
    full = tmp_path / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")
    return full


def _basic_patch(page_path: str, **fields) -> dict:
    return {
        "page_path": page_path,
        "requires_human_review": False,
        "fields_to_update": fields,
    }


@pytest.fixture(autouse=True)
def _patch_repo_root(tmp_path, monkeypatch):
    """Point apply.py's REPO_ROOT-relative file access at tmp_path."""
    monkeypatch.setattr(apply_mod, "_REPO_ROOT", tmp_path)


@pytest.fixture(autouse=True)
def _allow_no_downgrade_guard(monkeypatch):
    """Default: no_downgrade_guard always ALLOWs, so tests focus on the gate
    under test rather than requiring a real content_eval stack."""
    monkeypatch.setattr(
        apply_mod, "compare_content",
        lambda target_path, proposed_text, **kw: {"decision": "ALLOW", "reason": "test-default"},
    )


@pytest.fixture(autouse=True)
def _allow_autonomy_gate(monkeypatch):
    """Default: every (family, mechanism) is AUTONOMOUSLY_ELIGIBLE, so these
    tests exercise the gate each one names rather than Contract I's own gate
    (covered on its own merits by scripts/seo/tests/test_autonomy_state.py
    and its family_from_page_path/is_autonomously_eligible coverage)."""
    monkeypatch.setattr(apply_mod.autonomy_state, "is_autonomously_eligible", lambda *a, **k: True)


class TestRequiresHumanReviewGate:
    def test_rejects_true(self, tmp_path):
        page = "content/docs.aspose.org/en/x/index.md"
        _write_fixture(tmp_path, page, _DOCS_FM)
        patch_dict = _basic_patch(page, description="New description.")
        patch_dict["requires_human_review"] = True

        apply_mod.run_apply([patch_dict], dry_run=False)

        assert (tmp_path / page).read_text(encoding="utf-8") == _DOCS_FM, \
            "requires_human_review:true must not be written"

    def test_rejects_absent(self, tmp_path):
        page = "content/docs.aspose.org/en/x/index.md"
        _write_fixture(tmp_path, page, _DOCS_FM)
        patch_dict = _basic_patch(page, description="New description.")
        del patch_dict["requires_human_review"]

        apply_mod.run_apply([patch_dict], dry_run=False)

        assert (tmp_path / page).read_text(encoding="utf-8") == _DOCS_FM

    def test_allows_explicit_false(self, tmp_path):
        page = "content/docs.aspose.org/en/x/index.md"
        _write_fixture(tmp_path, page, _DOCS_FM)
        patch_dict = _basic_patch(page, description="New description.")

        apply_mod.run_apply([patch_dict], dry_run=False)

        result = (tmp_path / page).read_text(encoding="utf-8")
        assert "New description." in result


class TestAutonomyStateGate:
    """SEO-AUTONOMY-STATE-MACHINE (Contract I) read-gate: a non-dry-run write
    is only permitted when the target's family is AUTONOMOUSLY_ELIGIBLE for
    title_description_writes. The state machine's own transition/idempotency
    correctness lives in test_autonomy_state.py; this class only proves
    apply.py's write path actually calls the gate."""

    def test_rejects_when_not_eligible(self, tmp_path, monkeypatch):
        monkeypatch.setattr(apply_mod.autonomy_state, "is_autonomously_eligible", lambda *a, **k: False)
        page = "content/docs.aspose.org/en/x/index.md"
        _write_fixture(tmp_path, page, _DOCS_FM)
        patch_dict = _basic_patch(page, description="New description.")

        apply_mod.run_apply([patch_dict], dry_run=False)

        assert (tmp_path / page).read_text(encoding="utf-8") == _DOCS_FM, \
            "a family not AUTONOMOUSLY_ELIGIBLE for title_description_writes must not be written"

    def test_rejects_when_family_unresolvable(self, tmp_path):
        # websites.aspose.org has no family/platform concept (autonomy_state.
        # family_from_page_path returns None); an unresolvable family fails
        # closed regardless of the autouse eligibility override.
        page = "content/websites.aspose.org/some-page/index.md"
        _write_fixture(tmp_path, page, _DOCS_FM)
        patch_dict = _basic_patch(page, description="New description.")

        apply_mod.run_apply([patch_dict], dry_run=False)

        assert (tmp_path / page).read_text(encoding="utf-8") == _DOCS_FM

    def test_allows_when_eligible(self, tmp_path):
        # The autouse _allow_autonomy_gate fixture grants eligibility by default.
        page = "content/docs.aspose.org/en/x/index.md"
        _write_fixture(tmp_path, page, _DOCS_FM)
        patch_dict = _basic_patch(page, description="New description.")

        apply_mod.run_apply([patch_dict], dry_run=False)

        assert "New description." in (tmp_path / page).read_text(encoding="utf-8")


class TestAutoUpdatableGate:
    def test_rejects_auto_updatable_false(self, tmp_path):
        page = "content/docs.aspose.org/en/x/index.md"
        _write_fixture(tmp_path, page, _DOCS_FM_AUTO_UPDATABLE_FALSE)
        patch_dict = _basic_patch(page, description="New description.")

        apply_mod.run_apply([patch_dict], dry_run=False)

        assert (tmp_path / page).read_text(encoding="utf-8") == _DOCS_FM_AUTO_UPDATABLE_FALSE, \
            "auto_updatable:false target must never be written"

    def test_allows_when_auto_updatable_true_or_absent(self, tmp_path):
        page = "content/docs.aspose.org/en/x/index.md"
        _write_fixture(tmp_path, page, _DOCS_FM)  # no provenance block at all
        patch_dict = _basic_patch(page, description="New description.")

        apply_mod.run_apply([patch_dict], dry_run=False)

        assert "New description." in (tmp_path / page).read_text(encoding="utf-8")


class TestNoDowngradeGuardGate:
    def test_block_rejects_write(self, tmp_path, monkeypatch):
        page = "content/docs.aspose.org/en/x/index.md"
        _write_fixture(tmp_path, page, _DOCS_FM)
        monkeypatch.setattr(
            apply_mod, "compare_content",
            lambda target_path, proposed_text, **kw: {"decision": "BLOCK", "reason": "test-block"},
        )
        patch_dict = _basic_patch(page, description="New description.")

        apply_mod.run_apply([patch_dict], dry_run=False)

        assert (tmp_path / page).read_text(encoding="utf-8") == _DOCS_FM, \
            "a BLOCK decision must prevent the write"

    def test_warn_proceeds(self, tmp_path, monkeypatch):
        page = "content/docs.aspose.org/en/x/index.md"
        _write_fixture(tmp_path, page, _DOCS_FM)
        monkeypatch.setattr(
            apply_mod, "compare_content",
            lambda target_path, proposed_text, **kw: {"decision": "WARN", "reason": "test-warn"},
        )
        patch_dict = _basic_patch(page, description="New description.")

        apply_mod.run_apply([patch_dict], dry_run=False)

        assert "New description." in (tmp_path / page).read_text(encoding="utf-8"), \
            "a WARN decision must still allow the write"


class TestEvidenceBlockImmutability:
    def test_patch_touching_evidence_is_rejected(self, tmp_path):
        page = "content/docs.aspose.org/en/x/index.md"
        _write_fixture(tmp_path, page, _DOCS_FM)
        # A patch can only propose description/keywords/seoTitle -- there is no
        # legitimate way for a well-formed patch to touch evidence: directly.
        # This test proves the immutability check would catch it if one did,
        # by simulating a hand-crafted malicious/malformed patch attempting it
        # via a monkeypatched _apply_patch_to_fm.
        import copy as copy_mod
        original_impl = apply_mod._apply_patch_to_fm

        def _malicious(fm, patch, page_path):
            new_fm, changed, rejected = original_impl(fm, patch, page_path)
            tampered = copy_mod.deepcopy(new_fm)
            tampered["evidence"]["model_sha"] = "TAMPERED"
            return tampered, changed + ["evidence"], rejected

        with patch.object(apply_mod, "_apply_patch_to_fm", _malicious):
            patch_dict = _basic_patch(page, description="New description.")
            apply_mod.run_apply([patch_dict], dry_run=False)

        assert (tmp_path / page).read_text(encoding="utf-8") == _DOCS_FM, \
            "any patch that would change the evidence block must be rejected"


class TestWritableFieldsScopedBySite:
    def test_seotitle_writable_on_blog(self, tmp_path):
        page = "content/blog.aspose.org/x/index.md"
        _write_fixture(tmp_path, page, _BLOG_FM)
        patch_dict = _basic_patch(page, seoTitle="New SEO Title")

        apply_mod.run_apply([patch_dict], dry_run=False)

        assert "New SEO Title" in (tmp_path / page).read_text(encoding="utf-8")

    def test_seotitle_rejected_on_docs(self, tmp_path):
        page = "content/docs.aspose.org/en/x/index.md"
        _write_fixture(tmp_path, page, _DOCS_FM)
        patch_dict = _basic_patch(page, seoTitle="Should Not Be Written")

        apply_mod.run_apply([patch_dict], dry_run=False)

        result = (tmp_path / page).read_text(encoding="utf-8")
        assert "Should Not Be Written" not in result
        assert result == _DOCS_FM, "a patch with only a rejected field must change nothing"

    def test_tags_to_add_retired_everywhere(self, tmp_path):
        page = "content/blog.aspose.org/x/index.md"
        _write_fixture(tmp_path, page, _BLOG_FM)
        patch_dict = _basic_patch(page, **{"tags_to_add": ["new-tag"]})

        apply_mod.run_apply([patch_dict], dry_run=False)

        assert (tmp_path / page).read_text(encoding="utf-8") == _BLOG_FM, \
            "tags_to_add is retired and must never be written, on any site"

    def test_keywords_writable_everywhere(self, tmp_path):
        page = "content/docs.aspose.org/en/x/index.md"
        _write_fixture(tmp_path, page, _DOCS_FM)
        patch_dict = _basic_patch(page, keywords=["term one", "term two"])

        apply_mod.run_apply([patch_dict], dry_run=False)

        result = (tmp_path / page).read_text(encoding="utf-8")
        assert "term one" in result and "term two" in result


class TestFormatPreservation:
    def test_untouched_keys_byte_identical(self, tmp_path):
        page = "content/docs.aspose.org/en/x/index.md"
        _write_fixture(tmp_path, page, _DOCS_FM)
        patch_dict = _basic_patch(page, description="Changed description only.")

        apply_mod.run_apply([patch_dict], dry_run=False)

        result = (tmp_path / page).read_text(encoding="utf-8")
        assert 'title: "Sample Page"' in result, "untouched quoted scalar must keep its quote style"
        assert 'model_sha: "abc123"' in result, "evidence block must be byte-identical"
        assert "claims: [CLM-1]" in result, "untouched flow-style list must keep flow style"
        assert "Body content here." in result, "body must be untouched"
        assert "Changed description only." in result

    def test_non_ascii_values_round_trip_exactly(self, tmp_path):
        page = "content/blog.aspose.org/x/index.md"
        fm_with_unicode = _BLOG_FM.replace(
            "Old SEO Title", "Aspose.3D FOSS for TypeScript — Open-Source 3D File Processing"
        )
        _write_fixture(tmp_path, page, fm_with_unicode)
        patch_dict = _basic_patch(page, description="New description.")

        apply_mod.run_apply([patch_dict], dry_run=False)

        result = (tmp_path / page).read_text(encoding="utf-8")
        assert "Aspose.3D FOSS for TypeScript — Open-Source 3D File Processing" in result, \
            "em-dash and other non-ASCII characters in untouched fields must round-trip exactly"


class TestBatchSizeCap:
    def test_max_batch_size_constant_is_50(self):
        assert apply_mod.MAX_BATCH_SIZE == 50


class TestChangeBudgetGuard:
    """Contract G (SEO-CHANGE-BUDGET-GUARD): apply.py's batch-level
    pre-flight gate 0, and post-run actual-count recording."""

    def _small_budgets(self, **overrides):
        budgets = {
            "max_pages_per_run": 15, "max_pages_per_site_per_run": 10,
            "max_title_changes_per_run": 10, "max_description_changes_per_run": 15,
            "max_total_metadata_changes_per_run": 20, "anomaly_multiplier": 3.0,
            "warmup_runs": 3, "max_cross_mechanism_changes_per_family_per_week": 20,
        }
        budgets.update(overrides)
        return budgets

    def test_refuses_whole_batch_when_static_cap_exceeded(self, tmp_path, monkeypatch):
        monkeypatch.setattr(apply_mod.change_budget, "load_budgets", lambda path=None: self._small_budgets(max_pages_per_run=2))
        pages = [f"content/docs.aspose.org/en/x/page{i}/index.md" for i in range(3)]
        for page in pages:
            _write_fixture(tmp_path, page, _DOCS_FM)
        patches = [_basic_patch(page, description="New description.") for page in pages]

        apply_mod.run_apply(patches, dry_run=False)

        for page in pages:
            assert (tmp_path / page).read_text(encoding="utf-8") == _DOCS_FM, \
                "no page in a refused batch may be written, not even ones within a per-page sub-limit"

    def test_proceeds_when_batch_within_static_caps(self, tmp_path, monkeypatch):
        monkeypatch.setattr(apply_mod.change_budget, "load_budgets", lambda path=None: self._small_budgets())
        page = "content/docs.aspose.org/en/x/index.md"
        _write_fixture(tmp_path, page, _DOCS_FM)
        patch_dict = _basic_patch(page, description="New description.")

        apply_mod.run_apply([patch_dict], dry_run=False)

        assert "New description." in (tmp_path / page).read_text(encoding="utf-8")

    def test_refuses_when_anomaly_check_blocks_family(self, tmp_path, monkeypatch):
        monkeypatch.setattr(apply_mod.change_budget, "load_budgets", lambda path=None: self._small_budgets())
        page = "content/docs.aspose.org/en/x/index.md"
        _write_fixture(tmp_path, page, _DOCS_FM)
        patch_dict = _basic_patch(page, description="New description.")

        # 3 completed warm-up runs with a real mean of 0 for family "x" --
        # any nonzero proposal is an anomaly.
        apply_mod.change_budget.configure(repo_root=tmp_path)
        for _ in range(3):
            apply_mod.change_budget.record_run("x", "title_description_writes", 0)

        apply_mod.run_apply([patch_dict], dry_run=False)

        assert (tmp_path / page).read_text(encoding="utf-8") == _DOCS_FM, \
            "an anomaly-blocked family must not be written"

    def test_dry_run_never_invokes_or_is_blocked_by_the_budget_gate(self, tmp_path, monkeypatch):
        monkeypatch.setattr(apply_mod.change_budget, "load_budgets", lambda path=None: self._small_budgets(max_pages_per_run=0))
        page = "content/docs.aspose.org/en/x/index.md"
        _write_fixture(tmp_path, page, _DOCS_FM)
        patch_dict = _basic_patch(page, description="New description.")

        # dry_run=True must never be refused by the budget gate (Contract J:
        # --dry-run is always permitted regardless of state) -- and since
        # run_apply's own dry-run branch writes nothing, this just proves no
        # exception/refusal short-circuits it before reaching that branch.
        apply_mod.run_apply([patch_dict], dry_run=True)

        assert (tmp_path / page).read_text(encoding="utf-8") == _DOCS_FM

    def test_records_real_applied_counts_after_successful_write(self, tmp_path, monkeypatch):
        import json as _json
        monkeypatch.setattr(apply_mod.change_budget, "load_budgets", lambda path=None: self._small_budgets())
        page = "content/docs.aspose.org/en/x/index.md"
        _write_fixture(tmp_path, page, _DOCS_FM)
        patch_dict = _basic_patch(page, description="New description.")

        apply_mod.run_apply([patch_dict], dry_run=False)

        history_path = tmp_path / "reports" / "seo" / "change_budget_history.json"
        assert history_path.exists(), "a real, successful apply run must record its actual volume"
        history = _json.loads(history_path.read_text(encoding="utf-8"))
        assert history == {"x/title_description_writes": [1]}

    def test_does_not_record_when_batch_is_refused(self, tmp_path, monkeypatch):
        monkeypatch.setattr(apply_mod.change_budget, "load_budgets", lambda path=None: self._small_budgets(max_pages_per_run=0))
        page = "content/docs.aspose.org/en/x/index.md"
        _write_fixture(tmp_path, page, _DOCS_FM)
        patch_dict = _basic_patch(page, description="New description.")

        apply_mod.run_apply([patch_dict], dry_run=False)

        history_path = tmp_path / "reports" / "seo" / "change_budget_history.json"
        assert not history_path.exists(), "a refused batch must never contribute to the rolling baseline"

    def test_does_not_record_when_apply_run_touches_zero_families(self, tmp_path, monkeypatch):
        """An empty patch list is within every static cap and has no family
        to record against -- must not create a spurious history file."""
        monkeypatch.setattr(apply_mod.change_budget, "load_budgets", lambda path=None: self._small_budgets())

        apply_mod.run_apply([], dry_run=False)

        history_path = tmp_path / "reports" / "seo" / "change_budget_history.json"
        assert not history_path.exists()
