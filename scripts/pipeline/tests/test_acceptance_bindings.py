"""Tests for lib/acceptance_bindings.py (R-1, MT040-2026-08-28-PDF-TYPESCRIPT-LAUNCH
TC-MT040-49).

Coverage:
- compute_bindings reads model_sha/extractor_hash from a real model.yaml
- compute_bindings degrades gracefully (None fields) when model.yaml is
  missing/unreadable -- never raises
- bindings_status: unverifiable when stored has no model_sha (legacy
  artifact, or None)
- bindings_status: current when all known fields match
- bindings_status: stale when any known field differs
- bindings_status: unknown (None-vs-None) fields never cause a false "stale"
- format_bindings_yaml / parse_bindings_yaml round-trip
- parse_bindings_yaml returns None for text with no bindings block (legacy
  artifact predating this module)
"""
from __future__ import annotations

import pytest

import acceptance_bindings as ab


@pytest.fixture(autouse=True)
def _reset_ab():
    yield
    ab.configure()


def _write_model_yaml(tmp_path, family, platform, *, repo_sha=None, extractor_hash=None):
    d = tmp_path / "knowledge" / family / platform / "merged"
    d.mkdir(parents=True)
    lines = []
    if repo_sha is not None:
        lines.append(f"repo_sha: {repo_sha}")
    if extractor_hash is not None:
        lines.append(f"extractor_hash: {extractor_hash}")
    (d / "model.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


class TestComputeBindings:
    def test_reads_real_model_sha_and_extractor_hash(self, tmp_path):
        _write_model_yaml(tmp_path, "pdf", "typescript", repo_sha="abc123", extractor_hash="deadbeef01234567")
        ab.configure(repo_root=tmp_path)
        b = ab.compute_bindings("pdf", "typescript")
        assert b["model_sha"] == "abc123"
        assert b["extractor_hash"] == "deadbeef01234567"

    def test_missing_model_yaml_degrades_to_none_never_raises(self, tmp_path):
        ab.configure(repo_root=tmp_path)
        b = ab.compute_bindings("pdf", "typescript")
        assert b["model_sha"] is None
        assert b["extractor_hash"] is None

    def test_forward_declared_fields_present_as_none(self, tmp_path):
        """D-4/D-1 fields don't exist yet as of this card -- must be present
        as explicit None keys, not silently absent, so callers can iterate
        a stable key set."""
        ab.configure(repo_root=tmp_path)
        b = ab.compute_bindings("pdf", "typescript")
        assert "module_assignment_version" in b
        assert "grouped_index_generator_version" in b
        assert "platform_capabilities_digest" in b

    def test_evaluator_logic_version_populated(self, tmp_path):
        ab.configure(repo_root=tmp_path)
        b = ab.compute_bindings("pdf", "typescript")
        # Real, non-None as of this session (content_eval.EVALUATOR_FREEZE_VERSION == "18")
        assert b["evaluator_logic_version"] is not None


class TestBindingsStatus:
    def test_unverifiable_when_stored_is_none(self):
        assert ab.bindings_status(None, {"model_sha": "x"}) == "unverifiable"

    def test_unverifiable_when_stored_has_no_model_sha(self):
        assert ab.bindings_status({"model_sha": None}, {"model_sha": "x"}) == "unverifiable"

    def test_current_when_known_fields_match(self):
        stored = {"model_sha": "x", "extractor_hash": "h1", "evaluator_logic_version": "18"}
        current = {"model_sha": "x", "extractor_hash": "h1", "evaluator_logic_version": "18"}
        assert ab.bindings_status(stored, current) == "current"

    def test_stale_when_model_sha_differs(self):
        stored = {"model_sha": "old", "extractor_hash": "h1", "evaluator_logic_version": "18"}
        current = {"model_sha": "new", "extractor_hash": "h1", "evaluator_logic_version": "18"}
        assert ab.bindings_status(stored, current) == "stale"

    def test_stale_when_extractor_hash_differs(self):
        stored = {"model_sha": "x", "extractor_hash": "old_hash", "evaluator_logic_version": "18"}
        current = {"model_sha": "x", "extractor_hash": "new_hash", "evaluator_logic_version": "18"}
        assert ab.bindings_status(stored, current) == "stale"

    def test_stale_when_evaluator_logic_version_differs(self):
        stored = {"model_sha": "x", "extractor_hash": "h1", "evaluator_logic_version": "17"}
        current = {"model_sha": "x", "extractor_hash": "h1", "evaluator_logic_version": "18"}
        assert ab.bindings_status(stored, current) == "stale"

    def test_none_vs_none_field_never_causes_false_stale(self):
        """A forward-declared field that's None on BOTH sides (neither side
        knows it yet) must never be treated as a mismatch."""
        stored = {"model_sha": "x", "extractor_hash": "h1",
                  "evaluator_logic_version": "18", "module_assignment_version": None}
        current = {"model_sha": "x", "extractor_hash": "h1",
                   "evaluator_logic_version": "18", "module_assignment_version": None}
        assert ab.bindings_status(stored, current) == "current"


class TestFormatAndParseRoundTrip:
    def test_round_trip_preserves_string_and_none_values(self):
        original = {"model_sha": "abc123", "extractor_hash": None, "evaluator_logic_version": "18"}
        text = ab.format_bindings_yaml(original)
        parsed = ab.parse_bindings_yaml(text)
        assert parsed == original

    def test_round_trip_inside_larger_document(self):
        """Real usage: the bindings block is embedded inside a much larger
        markdown/YAML sign-off document, not the whole file."""
        original = {"model_sha": "abc123", "extractor_hash": "deadbeef"}
        doc = f"""# Some Report

## Sign-Off

```yaml
reviewer: ""
result: "PASS"
{ab.format_bindings_yaml(original)}
```

Trailing prose after the block.
"""
        parsed = ab.parse_bindings_yaml(doc)
        assert parsed == original

    def test_no_bindings_block_returns_none(self):
        """A legacy artifact predating this module has no bindings block at
        all -- must return None, not raise or return {}."""
        text = "# H-01 Human Prose Review\n\nresult: \"PASS\"\n"
        assert ab.parse_bindings_yaml(text) is None

    def test_indented_bindings_block_inside_fenced_code(self):
        """format_bindings_yaml's default (no indent) matches how it's
        actually embedded by readiness_scorecard.py/human_review_sampler.py
        -- both write it flush inside a ```yaml fence, not indented further."""
        original = {"model_sha": "x"}
        text = "```yaml\n" + ab.format_bindings_yaml(original) + "\n```\n"
        assert ab.parse_bindings_yaml(text) == original
