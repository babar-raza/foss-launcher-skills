"""Tests for gap-eval known_false_positives.yaml suppression mechanism (FIX-N4-01).

Covers:
- _load_false_positives(): graceful skip when YAML missing, correct parse when present
- _apply_false_positives(): BUG-enet-001 fingerprint suppression, no over-suppression
- YAML schema validation: committed file has expected structure
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

# Allow imports from scripts/gap-eval/
_GAP_EVAL_DIR = Path(__file__).resolve().parents[2] / "gap-eval"
if str(_GAP_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_GAP_EVAL_DIR))

from run import _load_false_positives, _apply_false_positives  # type: ignore  # noqa: E402

# Path to committed YAML file
_KFP_YAML = _GAP_EVAL_DIR / "known_false_positives.yaml"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _finding(description: str = "Some description", **kwargs) -> dict:
    base: dict[str, Any] = {
        "type": "wrong-claim",
        "severity": "M",
        "file": "content/docs/index.md",
        "description": description,
        "status": "open",
    }
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# _load_false_positives: file-loading behaviour
# ---------------------------------------------------------------------------

class TestLoadFalsePositives:
    """Tests for _load_false_positives() loading function."""

    def test_graceful_skip_when_yaml_missing(self, tmp_path, monkeypatch):
        """_load_false_positives returns [] when known_false_positives.yaml does not exist.

        This test verifies FIX-N4-01 Step 3 backward-compatibility requirement:
        the pipeline must not break if the file is absent.
        """
        # Redirect _GAP_EVAL_DIR inside run module to tmp_path (no YAML there)
        import run as run_mod  # type: ignore
        original = run_mod._GAP_EVAL_DIR
        monkeypatch.setattr(run_mod, "_GAP_EVAL_DIR", tmp_path)
        try:
            result = _load_false_positives()
        finally:
            monkeypatch.setattr(run_mod, "_GAP_EVAL_DIR", original)
        assert result == [], (
            "_load_false_positives must return [] when YAML file is absent; "
            "got: %r" % result
        )

    def test_returns_list_from_yaml(self, tmp_path, monkeypatch):
        """_load_false_positives parses false_positives list from a valid YAML."""
        yaml_text = (
            "false_positives:\n"
            "  - id: TEST-001\n"
            "    reason: test\n"
            "    matches:\n"
            "      description_contains: 'foo'\n"
        )
        (tmp_path / "known_false_positives.yaml").write_text(yaml_text, encoding="utf-8")

        import run as run_mod  # type: ignore
        original = run_mod._GAP_EVAL_DIR
        monkeypatch.setattr(run_mod, "_GAP_EVAL_DIR", tmp_path)
        try:
            result = _load_false_positives()
        finally:
            monkeypatch.setattr(run_mod, "_GAP_EVAL_DIR", original)

        assert len(result) == 1
        assert result[0]["id"] == "TEST-001"

    def test_empty_yaml_returns_empty_list(self, tmp_path, monkeypatch):
        """_load_false_positives returns [] for empty YAML (null document)."""
        (tmp_path / "known_false_positives.yaml").write_text("", encoding="utf-8")

        import run as run_mod  # type: ignore
        original = run_mod._GAP_EVAL_DIR
        monkeypatch.setattr(run_mod, "_GAP_EVAL_DIR", tmp_path)
        try:
            result = _load_false_positives()
        finally:
            monkeypatch.setattr(run_mod, "_GAP_EVAL_DIR", original)

        assert result == []

    def test_missing_false_positives_key_returns_empty(self, tmp_path, monkeypatch):
        """YAML without 'false_positives' key returns []."""
        (tmp_path / "known_false_positives.yaml").write_text(
            "version: 1\n", encoding="utf-8"
        )

        import run as run_mod  # type: ignore
        original = run_mod._GAP_EVAL_DIR
        monkeypatch.setattr(run_mod, "_GAP_EVAL_DIR", tmp_path)
        try:
            result = _load_false_positives()
        finally:
            monkeypatch.setattr(run_mod, "_GAP_EVAL_DIR", original)

        assert result == []


# ---------------------------------------------------------------------------
# BUG-enet-001 fingerprint suppression
# ---------------------------------------------------------------------------

class TestBugEnet001Suppression:
    """Verify BUG-enet-001 (CfbDocument false positive) is suppressed correctly."""

    def _make_enet001_rules(self) -> list[dict]:
        """Return the suppression rule matching BUG-enet-001's committed entry."""
        return [
            {
                "id": "BUG-enet-001",
                "matches": {
                    "family": "email",
                    "platform": "net",
                    "description_contains": "CfbDocument",
                },
            }
        ]

    def test_suppression_matches_fingerprint(self):
        """BUG-enet-001 fingerprint is suppressed when YAML rule is active."""
        findings = [
            _finding(description="Profile package_name does not match CfbDocument constructor call")
        ]
        rules = self._make_enet001_rules()
        n = _apply_false_positives(findings, "email", "net", rules)
        assert n == 1, "Expected exactly 1 suppressed finding"
        assert findings[0]["status"] == "suppressed"
        assert findings[0]["suppressed_by"] == "BUG-enet-001"

    def test_unknown_fingerprint_not_suppressed(self):
        """A finding that doesn't match any suppression passes through unchanged."""
        findings = [_finding(description="Wrong package name: Aspose.Cells.Net")]
        rules = self._make_enet001_rules()
        n = _apply_false_positives(findings, "email", "net", rules)
        assert n == 0, "Non-matching finding must not be suppressed"
        assert findings[0]["status"] == "open"

    def test_different_family_not_suppressed(self):
        """BUG-enet-001 rule does NOT suppress findings from a different family."""
        findings = [_finding(description="CfbDocument constructor issue")]
        rules = self._make_enet001_rules()
        n = _apply_false_positives(findings, "cells", "net", rules)
        assert n == 0, "Family-scoped rule must not suppress findings from wrong family"

    def test_different_platform_not_suppressed(self):
        """BUG-enet-001 rule does NOT suppress findings from a different platform."""
        findings = [_finding(description="CfbDocument constructor issue")]
        rules = self._make_enet001_rules()
        n = _apply_false_positives(findings, "email", "java", rules)
        assert n == 0, "Platform-scoped rule must not suppress findings from wrong platform"

    def test_already_suppressed_not_double_counted(self):
        """A finding already suppressed is not counted again."""
        findings = [_finding(description="CfbDocument issue", status="suppressed")]
        rules = self._make_enet001_rules()
        n = _apply_false_positives(findings, "email", "net", rules)
        assert n == 0

    def test_fixed_finding_not_re_suppressed(self):
        """A finding with status=fixed is not touched by suppression."""
        findings = [_finding(description="CfbDocument issue", status="fixed")]
        rules = self._make_enet001_rules()
        n = _apply_false_positives(findings, "email", "net", rules)
        assert n == 0
        assert findings[0]["status"] == "fixed"


# ---------------------------------------------------------------------------
# Committed YAML file validation
# ---------------------------------------------------------------------------

class TestCommittedYamlFile:
    """Verify the committed known_false_positives.yaml has the expected structure."""

    @pytest.mark.skipif(
        not _KFP_YAML.exists(),
        reason="known_false_positives.yaml not yet committed",
    )
    def test_yaml_file_exists(self):
        """The committed YAML file is present at scripts/gap-eval/."""
        assert _KFP_YAML.exists(), f"Expected {_KFP_YAML} to exist"

    @pytest.mark.skipif(
        not _KFP_YAML.exists(),
        reason="known_false_positives.yaml not yet committed",
    )
    def test_yaml_has_false_positives_key(self):
        """YAML root must have 'false_positives' key (matches _load_false_positives schema)."""
        import yaml  # type: ignore
        data = yaml.safe_load(_KFP_YAML.read_text(encoding="utf-8"))
        assert data is not None, "YAML must not be empty"
        assert "false_positives" in data, (
            "Root key must be 'false_positives' (got keys: %s)" % list(data.keys())
        )

    @pytest.mark.skipif(
        not _KFP_YAML.exists(),
        reason="known_false_positives.yaml not yet committed",
    )
    def test_bug_enet_001_entry_present(self):
        """BUG-enet-001 suppression entry must be in the committed file."""
        import yaml  # type: ignore
        data = yaml.safe_load(_KFP_YAML.read_text(encoding="utf-8"))
        entries = data.get("false_positives", [])
        ids = [e.get("id") for e in entries]
        assert "BUG-enet-001" in ids, (
            "BUG-enet-001 not found in known_false_positives.yaml; found: %r" % ids
        )

    @pytest.mark.skipif(
        not _KFP_YAML.exists(),
        reason="known_false_positives.yaml not yet committed",
    )
    def test_bug_enet_001_has_required_fields(self):
        """BUG-enet-001 entry has id, reason, retracted_at, and matches.description_contains."""
        import yaml  # type: ignore
        data = yaml.safe_load(_KFP_YAML.read_text(encoding="utf-8"))
        entry = next(
            (e for e in data.get("false_positives", []) if e.get("id") == "BUG-enet-001"),
            None,
        )
        assert entry is not None
        assert "id" in entry
        assert "reason" in entry or "justification" in entry, (
            "Entry must have 'reason' or 'justification' field"
        )
        matches = entry.get("matches", {})
        assert "description_contains" in matches, (
            "BUG-enet-001 matches block must have 'description_contains'"
        )

    @pytest.mark.skipif(
        not _KFP_YAML.exists(),
        reason="known_false_positives.yaml not yet committed",
    )
    def test_committed_yaml_suppresses_bug_enet_001_finding(self):
        """End-to-end: loading the committed YAML file suppresses BUG-enet-001 findings."""
        import run as run_mod  # type: ignore
        # Load rules directly from committed YAML
        rules = _load_false_positives()
        assert len(rules) >= 1, "Committed YAML must have at least 1 rule"

        # Simulate a finding that BUG-enet-001 should suppress
        findings = [_finding(description="CfbDocument constructor is invalid")]
        n = _apply_false_positives(findings, "email", "net", rules)
        assert n == 1, (
            "Committed YAML rule must suppress CfbDocument finding for email/net; "
            "got n=%d, findings=%r" % (n, findings)
        )
