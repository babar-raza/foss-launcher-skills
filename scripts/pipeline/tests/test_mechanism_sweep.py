"""Tests for the mechanism-sweep backing script (Task 7, S-117, §9.4, closes G2).

Covers: candidate enumeration honoring --exclude and launched/active gating;
the compute-only diff never touches the real merged/ tree (promote_atomic()'s
atomic swap is never invoked); the three-way NONE/METADATA_ONLY/CONTENT_AFFECTING
classification; and the mechanism-vs-upstream-drift separation (step 4) the
skill doc's own PDFGO-STALE-001 precedent calls out.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

PIPELINE_DIR = Path(__file__).resolve().parents[1]
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))
DIAG_DIR = PIPELINE_DIR / "commands" / "diagnostics"
if str(DIAG_DIR) not in sys.path:
    sys.path.insert(0, str(DIAG_DIR))

import mechanism_sweep as ms


@pytest.fixture(autouse=True)
def _reset_seams():
    yield
    ms.configure()


# ---------------------------------------------------------------------------
# enumerate_candidates
# ---------------------------------------------------------------------------

def _write_registry(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries), encoding="utf-8")


def _write_phase_state(path: Path, launched: dict[str, bool]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    state = {}
    for key, is_launched in launched.items():
        values = {k: True for k in ms._LAUNCHED_PHASE_KEYS} if is_launched else {}
        state[key] = {"values": values}
    path.write_text(json.dumps(state), encoding="utf-8")


class TestEnumerateCandidates:
    def test_filters_by_language_matching_platform(self, tmp_path):
        registry = tmp_path / "products.json"
        phase = tmp_path / "phase_state.json"
        _write_registry(registry, [
            {"family": "pdf", "platform": "java", "active": True},
            {"family": "pdf", "platform": "net", "active": True},
        ])
        _write_phase_state(phase, {"pdf/java": True, "pdf/net": True})

        candidates = ms.enumerate_candidates("java", registry_path=registry, phase_state_path=phase)
        assert candidates == [{"family": "pdf", "platform": "java"}]

    def test_excludes_named_pairs(self, tmp_path):
        registry = tmp_path / "products.json"
        phase = tmp_path / "phase_state.json"
        _write_registry(registry, [
            {"family": "pdf", "platform": "go", "active": True},
            {"family": "cells", "platform": "go", "active": True},
        ])
        _write_phase_state(phase, {"pdf/go": True, "cells/go": True})

        candidates = ms.enumerate_candidates(
            "go", exclude={("pdf", "go")}, registry_path=registry, phase_state_path=phase,
        )
        assert candidates == [{"family": "cells", "platform": "go"}]

    def test_excludes_inactive_products(self, tmp_path):
        registry = tmp_path / "products.json"
        phase = tmp_path / "phase_state.json"
        _write_registry(registry, [{"family": "pdf", "platform": "rust", "active": False}])
        _write_phase_state(phase, {"pdf/rust": True})

        candidates = ms.enumerate_candidates("rust", registry_path=registry, phase_state_path=phase)
        assert candidates == []

    def test_excludes_products_with_no_phase_state_entry(self, tmp_path):
        registry = tmp_path / "products.json"
        phase = tmp_path / "phase_state.json"
        _write_registry(registry, [{"family": "pdf", "platform": "rust", "active": True}])
        _write_phase_state(phase, {})  # never onboarded/scored

        candidates = ms.enumerate_candidates("rust", registry_path=registry, phase_state_path=phase)
        assert candidates == []

    def test_excludes_products_not_fully_launched(self, tmp_path):
        registry = tmp_path / "products.json"
        phase = tmp_path / "phase_state.json"
        _write_registry(registry, [{"family": "pdf", "platform": "rust", "active": True}])
        _write_phase_state(phase, {"pdf/rust": False})  # onboarding in progress

        candidates = ms.enumerate_candidates("rust", registry_path=registry, phase_state_path=phase)
        assert candidates == []


# ---------------------------------------------------------------------------
# check_upstream_drift (step 4: separate mechanism drift from upstream drift)
# ---------------------------------------------------------------------------

class TestCheckUpstreamDrift:
    def test_matching_sha_returns_none(self, tmp_path, monkeypatch):
        knowledge_root = tmp_path / "knowledge"
        model_path = knowledge_root / "pdf" / "go" / "merged" / "model.yaml"
        model_path.parent.mkdir(parents=True)
        model_path.write_text(yaml.safe_dump({"repo_sha": "sha_abc"}), encoding="utf-8")

        ms.configure(clone_exists_fn=lambda f, p: True, clone_head_sha_fn=lambda f, p: "sha_abc")

        assert ms.check_upstream_drift("pdf", "go", knowledge_root=knowledge_root) is None

    def test_differing_sha_flags_drift(self, tmp_path, monkeypatch):
        knowledge_root = tmp_path / "knowledge"
        model_path = knowledge_root / "pdf" / "go" / "merged" / "model.yaml"
        model_path.parent.mkdir(parents=True)
        model_path.write_text(yaml.safe_dump({"repo_sha": "sha_old"}), encoding="utf-8")

        ms.configure(clone_exists_fn=lambda f, p: True, clone_head_sha_fn=lambda f, p: "sha_new")

        result = ms.check_upstream_drift("pdf", "go", knowledge_root=knowledge_root)
        assert result is not None
        assert result["stored_sha"] == "sha_old"
        assert result["current_sha"] == "sha_new"

    def test_no_clone_returns_reason(self, tmp_path, monkeypatch):
        ms.configure(clone_exists_fn=lambda f, p: False)
        result = ms.check_upstream_drift("pdf", "go", knowledge_root=tmp_path / "knowledge")
        assert result == {"reason": "no local clone exists"}


# ---------------------------------------------------------------------------
# compute_delta (pure diff)
# ---------------------------------------------------------------------------

class TestComputeDelta:
    def test_detects_new_removed_modified_apis(self):
        old_apis = [
            {"name": "Foo", "methods": [{"name": "bar"}]},
            {"name": "Gone", "methods": []},
        ]
        new_apis = [
            {"name": "Foo", "methods": [{"name": "bar"}, {"name": "baz"}]},  # modified
            {"name": "New", "methods": []},  # new
        ]
        delta = ms.compute_delta([], [], old_apis, new_apis)
        assert delta["new_apis"] == ["New"]
        assert delta["removed_apis"] == ["Gone"]
        assert delta["modified_apis"] == ["Foo"]

    def test_detects_new_removed_modified_claims(self):
        old_claims = [{"claim_id": "CLM-1", "text": "old text"}, {"claim_id": "CLM-2", "text": "stable"}]
        new_claims = [{"claim_id": "CLM-1", "text": "new text"}, {"claim_id": "CLM-3", "text": "fresh"}]
        delta = ms.compute_delta(old_claims, new_claims, [], [])
        assert delta["new_claims"] == ["CLM-3"]
        assert delta["removed_claims"] == ["CLM-2"]
        assert delta["modified_claims"] == ["CLM-1"]

    def test_identical_input_yields_empty_delta(self):
        apis = [{"name": "Foo", "methods": [{"name": "bar"}]}]
        claims = [{"claim_id": "CLM-1", "text": "same"}]
        delta = ms.compute_delta(claims, claims, apis, apis)
        assert ms._delta_is_empty(delta)


# ---------------------------------------------------------------------------
# diff_only_rerun (never touches the real merged/ tree)
# ---------------------------------------------------------------------------

class TestDiffOnlyRerun:
    def test_never_mutates_real_merged_and_computes_diff(self, tmp_path, monkeypatch):
        knowledge_root = tmp_path / "knowledge"
        merged = knowledge_root / "pdf" / "go" / "merged"
        merged.mkdir(parents=True)
        old_apis = [{"name": "Foo", "methods": [{"name": "bar"}]}]
        (merged / "api_surface.json").write_text(json.dumps(old_apis), encoding="utf-8")
        (merged / "claims.json").write_text("[]", encoding="utf-8")
        real_api_surface_before = (merged / "api_surface.json").read_text(encoding="utf-8")

        def _fake_promote(family, platform, knowledge_root_arg, *, merged_dir_override=None):
            # Simulates the fixed extraction/enrichment producing a corrected
            # api_surface.json/claims.json -- written ONLY into the isolated
            # staging dir, matching promote()'s own merged_dir_override contract.
            new_apis = [{"name": "Foo", "methods": [{"name": "bar"}, {"name": "corrected"}]}]
            Path(merged_dir_override, "api_surface.json").write_text(json.dumps(new_apis), encoding="utf-8")
            Path(merged_dir_override, "claims.json").write_text("[]", encoding="utf-8")
            return True

        ms.configure(promote_fn=_fake_promote)

        delta = ms.diff_only_rerun("pdf", "go", knowledge_root=knowledge_root)

        assert delta["modified_apis"] == ["Foo"]
        # Real merged/ untouched:
        assert (merged / "api_surface.json").read_text(encoding="utf-8") == real_api_surface_before
        # No staging directories leaked on disk:
        leftovers = [p for p in (knowledge_root / "pdf" / "go").iterdir() if p.name != "merged"]
        assert leftovers == []

    def test_promote_failure_raises_runtime_error(self, tmp_path, monkeypatch):
        knowledge_root = tmp_path / "knowledge"
        merged = knowledge_root / "pdf" / "go" / "merged"
        merged.mkdir(parents=True)
        (merged / "api_surface.json").write_text("[]", encoding="utf-8")
        (merged / "claims.json").write_text("[]", encoding="utf-8")

        ms.configure(promote_fn=lambda *a, **kw: False)

        with pytest.raises(RuntimeError):
            ms.diff_only_rerun("pdf", "go", knowledge_root=knowledge_root)


# ---------------------------------------------------------------------------
# classify_candidate (NONE / METADATA_ONLY / CONTENT_AFFECTING)
# ---------------------------------------------------------------------------

def _write_page(path: Path, apis: list[str], claims: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\ntitle: Test\nevidence:\n"
        f"  apis: {json.dumps(apis)}\n  claims: {json.dumps(claims)}\n"
        "---\n\nBody.\n",
        encoding="utf-8",
    )


class TestClassifyCandidate:
    def test_empty_delta_is_none(self, tmp_path):
        delta = {k: [] for k in ("new_claims", "removed_claims", "modified_claims", "new_apis", "removed_apis", "modified_apis")}
        classification, summary = ms.classify_candidate("pdf", "go", delta, content_root=tmp_path / "content")
        assert classification == "NONE"

    def test_delta_with_no_cited_page_is_metadata_only(self, tmp_path):
        content_root = tmp_path / "content"
        _write_page(
            content_root / "docs.aspose.org" / "en" / "pdf" / "go" / "unrelated.md",
            apis=["Unrelated"], claims=[],
        )
        delta = {
            "new_claims": [], "removed_claims": [], "modified_claims": [],
            "new_apis": [], "removed_apis": [], "modified_apis": ["Foo"],
        }
        classification, summary = ms.classify_candidate("pdf", "go", delta, content_root=content_root)
        assert classification == "METADATA_ONLY"
        assert summary["HIGH_IMPACT"] == 0

    def test_delta_citing_a_real_page_is_content_affecting(self, tmp_path):
        content_root = tmp_path / "content"
        _write_page(
            content_root / "docs.aspose.org" / "en" / "pdf" / "go" / "foo.md",
            apis=["Foo"], claims=[],
        )
        delta = {
            "new_claims": [], "removed_claims": [], "modified_claims": [],
            "new_apis": [], "removed_apis": [], "modified_apis": ["Foo"],
        }
        classification, summary = ms.classify_candidate("pdf", "go", delta, content_root=content_root)
        assert classification == "CONTENT_AFFECTING"
        assert summary["HIGH_IMPACT"] == 1


# ---------------------------------------------------------------------------
# run_sweep / report writing (end-to-end wiring)
# ---------------------------------------------------------------------------

class TestRunSweepIntegration:
    def test_full_sweep_report_shape(self, tmp_path, monkeypatch):
        registry = tmp_path / "products.json"
        phase = tmp_path / "phase_state.json"
        knowledge_root = tmp_path / "knowledge"
        content_root = tmp_path / "content"

        _write_registry(registry, [
            {"family": "pdf", "platform": "go", "active": True},
            {"family": "cells", "platform": "go", "active": True},
        ])
        _write_phase_state(phase, {"pdf/go": True, "cells/go": True})

        for fam in ("pdf", "cells"):
            merged = knowledge_root / fam / "go" / "merged"
            merged.mkdir(parents=True)
            (merged / "api_surface.json").write_text("[]", encoding="utf-8")
            (merged / "claims.json").write_text("[]", encoding="utf-8")
            (merged / "model.yaml").write_text(yaml.safe_dump({"repo_sha": "sha1"}), encoding="utf-8")

        def _fake_promote(family, platform, knowledge_root_arg, *, merged_dir_override=None):
            Path(merged_dir_override, "api_surface.json").write_text("[]", encoding="utf-8")
            Path(merged_dir_override, "claims.json").write_text("[]", encoding="utf-8")
            return True

        ms.configure(
            clone_exists_fn=lambda f, p: True,
            clone_head_sha_fn=lambda f, p: "sha1",  # no upstream drift for either
            promote_fn=_fake_promote,
        )

        report = ms.run_sweep(
            "abc123def456", "go",
            registry_path=registry, phase_state_path=phase,
            knowledge_root=knowledge_root, content_root=content_root,
        )
        assert report["candidates_checked"] == 2
        assert report["summary"]["none"] == 2  # both candidates: empty delta (fake promote returns no change)
        assert report["summary"]["errors"] == 0

        json_path, md_path = ms.write_sweep_report(report, report_root=tmp_path / "reports" / "mechanism_sweep")
        assert json_path.is_file()
        assert md_path.is_file()
        rendered = md_path.read_text(encoding="utf-8")
        assert "pdf/go" in rendered or "confirmed no drift" in rendered

    def test_candidate_with_upstream_drift_is_separated_not_classified(self, tmp_path, monkeypatch):
        registry = tmp_path / "products.json"
        phase = tmp_path / "phase_state.json"
        knowledge_root = tmp_path / "knowledge"

        _write_registry(registry, [{"family": "pdf", "platform": "go", "active": True}])
        _write_phase_state(phase, {"pdf/go": True})
        merged = knowledge_root / "pdf" / "go" / "merged"
        merged.mkdir(parents=True)
        (merged / "model.yaml").write_text(yaml.safe_dump({"repo_sha": "old_sha"}), encoding="utf-8")

        def _should_not_be_called(*a, **kw):
            raise AssertionError("diff_only_rerun must not run for a drifted candidate")

        ms.configure(
            clone_exists_fn=lambda f, p: True,
            clone_head_sha_fn=lambda f, p: "new_sha",  # source has moved
            promote_fn=_should_not_be_called,
        )

        report = ms.run_sweep(
            "abc123", "go",
            registry_path=registry, phase_state_path=phase, knowledge_root=knowledge_root,
        )
        assert report["summary"]["separated_upstream_drift"] == 1
        assert report["summary"]["none"] == 0
        assert report["summary"]["metadata_only"] == 0
        assert report["summary"]["content_affecting"] == 0
