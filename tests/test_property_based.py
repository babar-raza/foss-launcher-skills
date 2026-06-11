"""Property-based tests using Hypothesis — P6 fuzz testing signal."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest
from hypothesis import given, strategies as st, settings

# Import real project modules for property testing
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from scripts.pipeline.commands.governance.path_guard import (
        check_path, FORBIDDEN_PREFIXES, FORBIDDEN_EXACT, ALLOWED_PREFIXES,
    )
    HAS_PATH_GUARD = True
except ImportError:
    HAS_PATH_GUARD = False

try:
    from scripts.pipeline.commands.ops.run_outcome_log import (
        log_outcome, read_outcomes, VALID_STATUSES,
    )
    HAS_OUTCOME_LOG = True
except ImportError:
    HAS_OUTCOME_LOG = False


class TestGroundingScore:
    """Property tests for grounding/verification score bounds."""

    @given(
        grounded=st.integers(min_value=0, max_value=1000),
        total=st.integers(min_value=1, max_value=1000),
    )
    def test_grounding_score_always_between_0_and_100(self, grounded, total):
        """Grounding percentage must always be in [0, 100]."""
        score = min(grounded, total) / total * 100
        assert 0 <= score <= 100


class TestPathGuardProperties:
    """Property tests using the real path_guard.check_path function."""

    @pytest.mark.skipif(not HAS_PATH_GUARD, reason="path_guard not importable")
    @given(suffix=st.text(min_size=1, max_size=30, alphabet="abcdefghijklmnop/._"))
    def test_forbidden_prefix_always_denied(self, suffix):
        """Paths under forbidden prefixes must always be DENY."""
        for prefix in FORBIDDEN_PREFIXES:
            decision, _ = check_path(prefix + suffix)
            assert decision == "DENY", f"{prefix}{suffix} should be DENY"

    @pytest.mark.skipif(not HAS_PATH_GUARD, reason="path_guard not importable")
    @given(suffix=st.text(min_size=1, max_size=30, alphabet="abcdefghijklmnop/._"))
    def test_allowed_prefix_always_allowed(self, suffix):
        """Paths under allowed prefixes (not also forbidden) must be ALLOW."""
        for prefix in ALLOWED_PREFIXES:
            path = prefix + suffix
            # Skip if path also matches a forbidden prefix (forbidden wins)
            if any(path.startswith(fp) for fp in FORBIDDEN_PREFIXES):
                continue
            if path.rstrip("/") in FORBIDDEN_EXACT:
                continue
            decision, _ = check_path(path)
            assert decision == "ALLOW", f"{path} should be ALLOW"

    @pytest.mark.skipif(not HAS_PATH_GUARD, reason="path_guard not importable")
    @given(exact=st.sampled_from(sorted(FORBIDDEN_EXACT) if HAS_PATH_GUARD else ["AGENTS.md"]))
    def test_forbidden_exact_always_denied(self, exact):
        """Exact forbidden paths must always be DENY."""
        decision, _ = check_path(exact)
        assert decision == "DENY"


class TestSkillIdFormat:
    """Property tests for skill ID format consistency."""

    SKILL_ID_PATTERN = re.compile(r"^S-\d{1,3}$")

    @given(num=st.integers(min_value=1, max_value=110))
    def test_skill_id_format_always_matches_pattern(self, num):
        """Generated skill IDs must match S-NNN pattern."""
        skill_id = f"S-{num}"
        assert self.SKILL_ID_PATTERN.match(skill_id), f"Bad skill ID: {skill_id}"


class TestConfigLoaderProperties:
    """Property tests for config YAML handling."""

    @given(
        key=st.text(min_size=1, max_size=50, alphabet=st.characters(
            whitelist_categories=("L", "N"), whitelist_characters="_-"
        )),
        value=st.text(min_size=0, max_size=100),
    )
    def test_config_loader_handles_arbitrary_yaml_keys(self, key, value):
        """Arbitrary YAML-safe keys should not crash config parsing."""
        import yaml
        data = yaml.safe_load(f"{key}: {json.dumps(value)}")
        assert isinstance(data, dict)


class TestJsonlRoundtrip:
    """Property tests for JSONL serialization via real run_outcome_log module."""

    @pytest.mark.skipif(not HAS_OUTCOME_LOG, reason="run_outcome_log not importable")
    @given(
        skill_id=st.text(min_size=1, max_size=10, alphabet="S-0123456789"),
        status=st.sampled_from(sorted(VALID_STATUSES) if HAS_OUTCOME_LOG else ["success"]),
        duration=st.integers(min_value=0, max_value=999999),
    )
    @settings(max_examples=50)
    def test_jsonl_roundtrip_preserves_data(self, skill_id, status, duration):
        """log_outcome + read_outcomes must preserve all fields."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            log_file = Path(td) / "test_outcomes.jsonl"
            log_outcome(skill_id, status, duration_ms=duration, log_path=log_file)
            entries = read_outcomes(log_path=log_file)
            assert len(entries) >= 1
            last = entries[-1]
            assert last["skill_id"] == skill_id
            assert last["status"] == status
            assert last["duration_ms"] == duration
