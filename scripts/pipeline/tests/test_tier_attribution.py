"""Integration tests for run_gap_eval()'s tier attribution counters (TC-VEC-08).

Marked implicitly via the same real-clone-cache dependency as
test_tier3_cache_integration.py — requires:
  {repo_root}/runs/.clone_cache/aspose_3d_java/
  {repo_root}/knowledge/3d/java/merged/api_surface.json

What this proves: run_gap_eval()'s output includes a tier_attribution dict
whose counters genuinely reflect what tier2_verify()/tier3_verify() were
configured to return — not just that the keys exist with plausible-looking
values. Complements test_gap_eval_tier2_vectors.py/test_tier2_determinism.py,
which test tier2_verify() in isolation; this proves the counters wired around
it in run_gap_eval()'s main loop are wired to the right branches.

Uses run.configure(tier2_verify_fn=..., tier3_verify_fn=...,
update_profile_actuals_fn=...) — a DI seam (AGENTS.md §16) — rather than
monkeypatch.setattr/patch.object on run.py's module internals.
test_tier3_cache_integration.py's patch.object usage predates this seam and
is grandfathered baseline debt, not a pattern to replicate here.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_GAP_EVAL_DIR = Path(__file__).resolve().parents[2] / "gap-eval" / "src"
if str(_GAP_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_GAP_EVAL_DIR))

import run as gap_eval_run  # type: ignore  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CLONE_CACHE_3D_JAVA = _REPO_ROOT / "runs" / ".clone_cache" / "aspose_3d_java"
_API_SURFACE_3D_JAVA = _REPO_ROOT / "knowledge" / "3d" / "java" / "merged" / "api_surface.json"


@pytest.fixture(autouse=True)
def _require_clone_cache_and_reset_config():
    if not _CLONE_CACHE_3D_JAVA.exists():
        pytest.skip(f"Clone cache not found: {_CLONE_CACHE_3D_JAVA}.")
    if not _API_SURFACE_3D_JAVA.exists():
        pytest.skip(f"Knowledge not bootstrapped: {_API_SURFACE_3D_JAVA} absent.")
    yield
    gap_eval_run.configure()


def _mock_tier3_confirmed():
    """Tier 3 stand-in that confirms every claim accurate (zero findings, zero
    needs-review) — same shape as test_tier3_cache_integration.py's pattern.
    NOTE: no_llm=True is deliberately NOT used to isolate Tier 2, because
    run_gap_eval()'s own _no_embed = no_embed or no_llm derivation means
    no_llm=True also disables Tier 2 — found live while writing this test
    (the first version used no_llm=True and every assertion below silently
    passed on all-zero counters, a vacuous test that never exercised Tier 2
    at all). Configuring tier3_verify_fn instead keeps Tier 2 genuinely active."""
    from llm_router import EndpointStatus
    from run import Tier3Result  # type: ignore
    return MagicMock(return_value=Tier3Result(
        verdict=None, status=EndpointStatus.OK, reason="claim confirmed accurate",
    ))


class TestTierAttribution:
    def test_forced_tier2_match_reflected_exactly_in_counters(self, tmp_path):
        """Every Tier-2-eligible claim forced to MATCH must show up as
        tier2_match, with every other Tier 2 outcome bucket at zero."""
        tmp_state = tmp_path / "state"
        tmp_state.mkdir()
        t2_mock = MagicMock(return_value=("MATCH", 0.99))
        gap_eval_run.configure(
            tier2_verify_fn=t2_mock,
            tier3_verify_fn=_mock_tier3_confirmed(),
            update_profile_actuals_fn=lambda *a, **kw: None,
        )

        result = gap_eval_run.run_gap_eval(
            "3d", "java", scope="docs",
            out_override=str(tmp_path / "run1"), state_dir=tmp_state,
        )

        assert t2_mock.call_count > 0, (
            "expected at least one tier2_verify call for docs/3d/java scope — "
            "if this fails, the fixture scope has no claims that reach Tier 2"
        )
        ta = result["tier_attribution"]
        assert ta["tier2_calls"] == t2_mock.call_count
        assert ta["tier2_match"] == t2_mock.call_count
        assert ta["tier2_mismatch_finding"] == 0
        assert ta["tier2_escalated"] == 0
        assert ta["tier2_unavailable"] == 0

    def test_tier2_unavailable_when_verify_returns_none(self, tmp_path):
        """tier2_verify() returning None (no vectors) must count as
        tier2_unavailable, not silently vanish from the attribution."""
        tmp_state = tmp_path / "state"
        tmp_state.mkdir()
        t2_mock = MagicMock(return_value=None)
        gap_eval_run.configure(
            tier2_verify_fn=t2_mock,
            tier3_verify_fn=_mock_tier3_confirmed(),
            update_profile_actuals_fn=lambda *a, **kw: None,
        )

        result = gap_eval_run.run_gap_eval(
            "3d", "java", scope="docs",
            out_override=str(tmp_path / "run2"), state_dir=tmp_state,
        )

        assert t2_mock.call_count > 0, (
            "expected at least one tier2_verify call — otherwise every "
            "assertion below passes vacuously on all-zero counters"
        )
        ta = result["tier_attribution"]
        assert ta["tier2_calls"] == t2_mock.call_count
        assert ta["tier2_unavailable"] == t2_mock.call_count
        assert ta["tier2_match"] == 0

    def test_tier_attribution_present_in_written_json_report(self, tmp_path):
        """The real JSON report file on disk must include tier_attribution —
        not just the in-memory return value — so a human/tool inspecting
        reports/gap-analysis/*.json after the fact can see it."""
        import json

        tmp_state = tmp_path / "state"
        tmp_state.mkdir()
        out_stem = tmp_path / "run3"
        gap_eval_run.configure(
            tier2_verify_fn=MagicMock(return_value=("MATCH", 0.9)),
            tier3_verify_fn=_mock_tier3_confirmed(),
            update_profile_actuals_fn=lambda *a, **kw: None,
        )

        gap_eval_run.run_gap_eval(
            "3d", "java", scope="docs",
            out_override=str(out_stem), state_dir=tmp_state,
        )

        json_path = out_stem.with_suffix(".json")
        assert json_path.exists()
        written = json.loads(json_path.read_text(encoding="utf-8"))
        assert "tier_attribution" in written
        assert written["tier_attribution"]["tier2_calls"] > 0
