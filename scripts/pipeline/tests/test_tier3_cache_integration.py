"""Integration test: Tier 3 cache reduces LLM calls on second run of run_gap_eval().

Marked @pytest.mark.integration — requires clone cache at:
  {repo_root}/../foss-launcher/runs/.clone_cache/aspose_3d_java/

Run with:
  pytest -m integration scripts/pipeline/tests/test_tier3_cache_integration.py -v

What this proves:
  - run_gap_eval() calls tier3_verify on the first run (cache miss)
  - run_gap_eval() calls tier3_verify ZERO times on the second run with the same
    content (cache hit from state file written by run 1)
  - Findings from the cache-hit path are annotated with tier3_cache_hit: True

Design:
  - tier2_verify is mocked to return None → all api-token/package-declaration
    claims escalate to Tier 3 (bypassing T2's vector-match gate)
  - tier3_verify is mocked to return None → all claims "confirmed accurate"
    (zero Tier 3 findings, but the LLM path is exercised and counted)
  - _update_profile_actuals is mocked to prevent writes to the profile YAML
  - out_override directs output to tmp_path (no writes to main reports/)
  - state_dir is a tmp dir shared between runs (cache persists across the
    two calls within one test)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Path setup — identical pattern to test_gap_eval_profile_safety.py
# ---------------------------------------------------------------------------

_GAP_EVAL_DIR = Path(__file__).resolve().parents[2] / "gap-eval"
if str(_GAP_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_GAP_EVAL_DIR))

import run as gap_eval_run  # type: ignore  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Clone cache lives inside the repo at runs/.clone_cache/ (not in foss-launcher).
# Path confirmed via _clone_cache_base() in run.py.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_CLONE_CACHE_3D_JAVA = _REPO_ROOT / "runs" / ".clone_cache" / "aspose_3d_java"


def _run_gap_eval(tmp_state_dir: Path, tmp_out: str) -> tuple[dict, MagicMock, MagicMock]:
    """Execute run_gap_eval with mocked T2/T3 and _update_profile_actuals.

    Returns (result, t2_mock, t3_mock) so callers can inspect call counts.
    """
    from llm_router import EndpointStatus
    from run import Tier3Result  # type: ignore
    t2_mock = MagicMock(return_value=None)   # no T2 verdict → escalate to T3
    # T3 confirms all claims accurate — return Tier3Result with OK status
    t3_mock = MagicMock(return_value=Tier3Result(
        verdict=None, status=EndpointStatus.OK, reason="claim confirmed accurate",
    ))

    with (
        patch.object(gap_eval_run, "tier2_verify", t2_mock),
        patch.object(gap_eval_run, "tier3_verify", t3_mock),
        patch.object(gap_eval_run, "_update_profile_actuals"),
    ):
        result = gap_eval_run.run_gap_eval(
            "3d",
            "java",
            scope="docs",
            out_override=tmp_out,
            state_dir=tmp_state_dir,
        )

    return result, t2_mock, t3_mock


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestTier3CacheIntegration:
    """Two-run integration tests for the Tier 3 cache."""

    @pytest.fixture(autouse=True)
    def _require_clone_cache(self):
        """Skip every test in this class if the 3d/java clone cache is absent."""
        if not _CLONE_CACHE_3D_JAVA.exists():
            pytest.skip(
                f"Clone cache not found: {_CLONE_CACHE_3D_JAVA}. "
                "Run S-34 (repo-scout) first to populate the clone cache."
            )

    def test_run1_makes_tier3_calls(self, tmp_path):
        """Baseline: run_gap_eval calls tier3_verify at least once on the first run.

        If this fails, the docs/3d/java scope has no api-token/package-declaration
        claims that escape Tier 1 — investigate the profile or docs files.
        """
        tmp_state = tmp_path / "state"
        tmp_state.mkdir()
        _, _, t3_mock = _run_gap_eval(tmp_state, str(tmp_path / "run1"))

        assert t3_mock.call_count > 0, (
            "Expected at least one tier3_verify call on first run. "
            "Check that content/docs.aspose.org/en/3d/java/ has api-token claims "
            "that pass Tier 1 and are not resolved by the mocked Tier 2."
        )

    def test_run2_zero_tier3_calls_when_content_unchanged(self, tmp_path):
        """Core cache proof: Run 2 with unchanged content makes zero Tier 3 LLM calls.

        After Run 1 populates the tier3_cache in the state file, Run 2 with the same
        content (same file hashes, same profile SHA, same clone SHA) must return all
        Tier 3 results from cache without calling tier3_verify.
        """
        tmp_state = tmp_path / "state"
        tmp_state.mkdir()

        # --- Run 1: warm the cache ---
        _, _, t3_mock_1 = _run_gap_eval(tmp_state, str(tmp_path / "run1"))

        run1_t3_calls = t3_mock_1.call_count
        assert run1_t3_calls > 0, (
            f"Run 1 made {run1_t3_calls} Tier 3 calls — cannot prove cache benefit. "
            "Check that docs files have claims reaching Tier 3."
        )

        # State file must exist with a populated tier3_cache
        state_path = tmp_state / "3d-java.json"
        assert state_path.exists(), "State file not written after Run 1"
        state1 = json.loads(state_path.read_text(encoding="utf-8"))
        assert state1.get("tier3_cache"), (
            "tier3_cache key missing or empty in state file after Run 1"
        )

        # --- Run 2: same content, same state_dir → should hit cache ---
        _, _, t3_mock_2 = _run_gap_eval(tmp_state, str(tmp_path / "run2"))

        run2_t3_calls = t3_mock_2.call_count
        assert run2_t3_calls == 0, (
            f"Run 2 made {run2_t3_calls} Tier 3 call(s) but expected 0 (cache hit). "
            "The Tier 3 cache is not being used for unchanged content. "
            "Run 1 made {run1_t3_calls} Tier 3 call(s) — their results should be cached."
        )

    def test_run2_findings_annotated_with_tier3_cache_hit(self, tmp_path):
        """Cache-sourced Tier 3 findings carry tier3_cache_hit: True on Run 2.

        On Run 1, tier3_verify is configured to return a fake finding for the first
        call (simulating an LLM finding a real problem). That finding is stored in the
        cache. On Run 2, the cache returns it annotated with tier3_cache_hit: True.
        """
        tmp_state = tmp_path / "state"
        tmp_state.mkdir()

        # --- Run 1: first T3 call returns a finding, rest return None (accurate) ---
        from llm_router import EndpointStatus as _ES
        from run import Tier3Result as _T3R  # type: ignore
        call_count = [0]

        def _t3_side_effect(claim, family, platform, clone_cache):
            idx = call_count[0]
            call_count[0] += 1
            if idx == 0:
                # Return a finding on the very first Tier 3 call
                return _T3R(
                    verdict={
                        "type": "wrong-claim",
                        "severity": "S",
                        "tier_resolved_by": 3,
                        "file": claim.get("file", "unknown"),
                        "line": claim.get("line", 0),
                        "old_value": claim.get("value", ""),
                        "correct_value": None,
                        "description": "Integration test injected finding",
                    },
                    status=_ES.OK,
                    reason="claim inaccurate",
                )
            return _T3R(verdict=None, status=_ES.OK, reason="claim confirmed accurate")

        t2_1 = MagicMock(return_value=None)
        t3_1 = MagicMock(side_effect=_t3_side_effect)

        with (
            patch.object(gap_eval_run, "tier2_verify", t2_1),
            patch.object(gap_eval_run, "tier3_verify", t3_1),
            patch.object(gap_eval_run, "_update_profile_actuals"),
        ):
            gap_eval_run.run_gap_eval(
                "3d", "java",
                scope="docs",
                out_override=str(tmp_path / "run1"),
                state_dir=tmp_state,
            )

        run1_calls = call_count[0]
        if run1_calls == 0:
            pytest.skip(
                "No Tier 3 calls on Run 1 — cannot test annotation behavior. "
                "Docs may have no claims escaping Tier 1."
            )

        # --- Run 2: verify annotation ---
        _, _, t3_2 = _run_gap_eval(tmp_state, str(tmp_path / "run2"))

        assert t3_2.call_count == 0, (
            f"Expected 0 T3 calls on Run 2 but got {t3_2.call_count}. Cache not working."
        )

        # Read run2 output JSON to inspect findings
        out_json = Path(str(tmp_path / "run2")).with_suffix(".json")
        assert out_json.exists(), "Run 2 output JSON not written"
        run2_output = json.loads(out_json.read_text(encoding="utf-8"))

        all_findings = run2_output.get("findings", [])
        cache_hit_findings = [
            f for f in all_findings if f.get("tier3_cache_hit") is True
        ]

        # The injected finding from Run 1 should reappear annotated on Run 2
        assert cache_hit_findings, (
            "No findings with tier3_cache_hit: True on Run 2, even though Run 1 "
            "injected a Tier 3 finding that should have been cached.\n"
            f"All Run 2 findings: {json.dumps(all_findings, indent=2)}"
        )
