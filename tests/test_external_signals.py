"""Tests for external_signals.py — schema validation, advisory flag enforcement."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_PIPELINE_ROOT = Path(__file__).resolve().parents[1] / "scripts" / "pipeline"
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

from lib.external_signals import (
    EXTERNAL_SIGNALS_SCHEMA_VERSION,
    ExternalSignal,
    SignalBatch,
)


class TestExternalSignal:
    def test_advisory_always_true(self):
        """Advisory flag must always be True, even if constructed with False."""
        sig = ExternalSignal(
            signal_type="coverage_gap",
            text="Missing API docs",
            source="skill_seekers",
            advisory=False,  # Should be forced to True
        )
        assert sig.advisory is True

    def test_default_advisory(self):
        sig = ExternalSignal(
            signal_type="readme_feature",
            text="Supports PDF export",
            source="skill_seekers",
        )
        assert sig.advisory is True

    def test_frozen(self):
        sig = ExternalSignal(
            signal_type="readme_feature",
            text="test",
            source="test",
        )
        with pytest.raises(AttributeError):
            sig.text = "modified"


class TestSignalBatch:
    def _make_batch(self) -> SignalBatch:
        batch = SignalBatch(family="pdf", platform="go", source="skill_seekers")
        batch.add_signal(ExternalSignal(
            signal_type="coverage_gap",
            text="Missing PDF/A docs",
            source="skill_seekers",
            source_file="README.md",
            confidence=0.7,
        ))
        batch.add_signal(ExternalSignal(
            signal_type="readme_feature",
            text="Supports watermarking",
            source="skill_seekers",
            confidence=0.6,
        ))
        return batch

    def test_signal_count(self):
        batch = self._make_batch()
        assert batch.signal_count == 2

    def test_schema_version(self):
        batch = self._make_batch()
        d = batch.to_dict()
        assert d["schema_version"] == EXTERNAL_SIGNALS_SCHEMA_VERSION

    def test_serialization_roundtrip(self):
        batch = self._make_batch()
        json_str = batch.to_json()
        d = json.loads(json_str)
        assert d["signal_count"] == 2
        assert all(s["advisory"] is True for s in d["signals"])

    def test_write_and_read(self, tmp_path):
        batch = self._make_batch()
        path = tmp_path / "signals.json"
        batch.write(path)
        restored = SignalBatch.read(path)
        assert restored.signal_count == batch.signal_count
        assert restored.family == "pdf"

    def test_empty_batch(self):
        batch = SignalBatch(family="pdf", platform="go", source="none")
        assert batch.signal_count == 0
        d = batch.to_dict()
        assert d["signals"] == []


class TestSkillSeekersAdapter:
    def test_parse_findings(self):
        from commands.knowledge.skill_seekers_adapter import parse_skill_seekers_output

        data = {
            "findings": [
                {
                    "type": "readme_feature",
                    "description": "Supports PDF merging",
                    "file": "README.md",
                    "confidence": 0.9,
                },
                {
                    "type": "coverage_gap",
                    "description": "No docs for watermark API",
                    "file": "docs/api.md",
                    "confidence": 0.6,
                },
            ]
        }
        batch = parse_skill_seekers_output(data, "pdf", "go")
        assert batch.signal_count == 2
        assert batch.source == "skill_seekers"
        # Confidence capped at 0.8
        assert all(s.confidence <= 0.8 for s in batch.signals)
        assert all(s.advisory is True for s in batch.signals)

    def test_parse_empty(self):
        from commands.knowledge.skill_seekers_adapter import parse_skill_seekers_output

        batch = parse_skill_seekers_output({}, "pdf", "go")
        assert batch.signal_count == 0
