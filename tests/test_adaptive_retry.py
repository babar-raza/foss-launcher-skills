"""Tests for adaptive_retry.py — retry wrapper with backoff and fallback."""

from __future__ import annotations

import pytest
from scripts.pipeline.commands.ops.adaptive_retry import retry_skill, _FALLBACK_MAP


class TestRetrySkill:
    """Tests for retry_skill function."""

    def test_retry_succeeds_first_attempt(self):
        """Happy path: skill succeeds on first try."""
        result = retry_skill(
            skill_id="S-21",
            execute_fn=lambda: "done",
            max_retries=3,
            sleep_fn=lambda _: None,
        )
        assert result["status"] == "success"
        assert result["attempts"] == 1
        assert result["fallback_suggested"] is None
        assert result["error_chain"] == []
        assert result["last_result"] == "done"

    def test_retry_succeeds_after_failures(self):
        """Skill fails twice then succeeds on third attempt."""
        call_count = 0

        def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError(f"fail #{call_count}")
            return "recovered"

        result = retry_skill(
            skill_id="S-21",
            execute_fn=flaky,
            max_retries=3,
            sleep_fn=lambda _: None,
        )
        assert result["status"] == "success"
        assert result["attempts"] == 3
        assert result["fallback_suggested"] is None
        assert len(result["error_chain"]) == 2
        assert result["last_result"] == "recovered"

    def test_retry_exhausted_returns_failure(self):
        """All retries exhausted — returns exhausted with fallback."""
        result = retry_skill(
            skill_id="S-21",
            execute_fn=lambda: (_ for _ in ()).throw(RuntimeError("always fails")),
            max_retries=2,
            sleep_fn=lambda _: None,
        )
        assert result["status"] == "exhausted"
        assert result["attempts"] == 3  # 1 initial + 2 retries
        assert result["fallback_suggested"] == "S-26"  # S-21 -> S-26
        assert len(result["error_chain"]) == 3

    def test_backoff_timing_is_exponential(self):
        """Sleep durations follow exponential pattern."""
        sleep_calls: list[float] = []

        result = retry_skill(
            skill_id="S-21",
            execute_fn=lambda: (_ for _ in ()).throw(RuntimeError("fail")),
            max_retries=3,
            backoff_base=2.0,
            sleep_fn=lambda d: sleep_calls.append(d),
        )
        assert result["status"] == "exhausted"
        # backoff: 2^0=1, 2^1=2, 2^2=4 (3 sleeps for 3 retries)
        assert sleep_calls == [1.0, 2.0, 4.0]

    def test_fallback_skill_suggested_on_exhaustion(self):
        """Known skills get a fallback suggestion; unknown skills get None."""
        # Known skill with fallback
        result = retry_skill(
            skill_id="S-25",
            execute_fn=lambda: (_ for _ in ()).throw(RuntimeError("fail")),
            max_retries=0,
            sleep_fn=lambda _: None,
        )
        assert result["fallback_suggested"] == "S-32"

        # Unknown skill — no fallback
        result = retry_skill(
            skill_id="S-999",
            execute_fn=lambda: (_ for _ in ()).throw(RuntimeError("fail")),
            max_retries=0,
            sleep_fn=lambda _: None,
        )
        assert result["fallback_suggested"] is None

    def test_fallback_map_contains_expected_entries(self):
        """Verify the fallback map has the documented entries."""
        assert "S-21" in _FALLBACK_MAP
        assert "S-26" in _FALLBACK_MAP
        assert "S-20" in _FALLBACK_MAP
        assert "S-25" in _FALLBACK_MAP
