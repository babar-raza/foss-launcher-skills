"""Tests for scripts/pipeline/commands/content/claim_report.py (TC-CLAIM-11).

WARN-only CI claim report for non-reference subdomains.
All tests use tmp_path; no real content/ or knowledge/ files are read.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_md(tmp_path: Path, name: str, claims: list[str],
              subdomain_part: str = "blog.aspose.org") -> Path:
    """Write a minimal content .md file with given evidence.claims."""
    claims_yaml = "[" + ", ".join(repr(c) for c in claims) + "]"
    lines = [
        "---",
        "title: Test Page",
        "evidence:",
        "  model_sha: abc123",
        f"  claims: {claims_yaml}",
        "  apis: []",
        "---",
        "# Test",
        "",
        "Body content.",
    ]
    p = tmp_path / subdomain_part / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def _knowledge(claim_ids: set[str]) -> MagicMock:
    k = MagicMock()
    k.claim_ids = claim_ids
    k.available = True
    k.family = "cells"
    k.platform = "java"
    return k


# ---------------------------------------------------------------------------
# scan_files tests
# ---------------------------------------------------------------------------

class TestScanFiles:
    def test_detects_unknown_claim(self, tmp_path):
        from commands.content.claim_report import scan_files
        f = _write_md(tmp_path, "test.md", ["CLM-cells-abc", "ERC-STALE-0000"])
        k = _knowledge({"CLM-cells-abc"})
        report = scan_files([f], k)

        assert report["warn_count"] > 0
        issues = report["records"][0]["issues"]
        issue_types = {i["issue"] for i in issues}
        assert "UNKNOWN_CLAIM" in issue_types

    def test_detects_stale_claim(self, tmp_path):
        """Stale claims (not in knowledge) are reported as UNKNOWN_CLAIM."""
        from commands.content.claim_report import scan_files
        f = _write_md(tmp_path, "test.md", ["ERC-OLD-CLAIM-0001"])
        k = _knowledge(set())  # empty knowledge
        report = scan_files([f], k)

        assert report["total_issues"] > 0
        issues = report["records"][0]["issues"]
        assert any(i["issue"] == "UNKNOWN_CLAIM" for i in issues)

    def test_detects_duplicate_claim(self, tmp_path):
        from commands.content.claim_report import scan_files
        # Write file with duplicate claim IDs manually
        lines = [
            "---",
            "title: Test",
            "evidence:",
            "  model_sha: abc",
            "  claims:",
            "    - CLM-cells-abc",
            "    - CLM-cells-abc",
            "  apis: []",
            "---",
            "# Test",
        ]
        f = tmp_path / "dup.md"
        f.write_text("\n".join(lines) + "\n", encoding="utf-8")
        k = _knowledge({"CLM-cells-abc"})
        report = scan_files([f], k)

        issues = report["records"][0]["issues"]
        assert any(i["issue"] == "DUPLICATE_CLAIM" for i in issues)

    def test_detects_malformed_claim_id(self, tmp_path):
        from commands.content.claim_report import scan_files
        f = _write_md(tmp_path, "test.md", ["not-a-valid-claim-id"])
        k = _knowledge(set())
        report = scan_files([f], k)

        issues = report["records"][0]["issues"]
        assert any(i["issue"] == "MALFORMED_CLAIM_ID" for i in issues)

    def test_no_issues_on_valid_claims(self, tmp_path):
        from commands.content.claim_report import scan_files
        f = _write_md(tmp_path, "test.md", ["CLM-cells-abc123"])
        k = _knowledge({"CLM-cells-abc123"})
        report = scan_files([f], k)

        assert report["warn_count"] == 0
        assert report["files_with_issues"] == 0

    def test_does_not_block_pipeline(self, tmp_path):
        """scan_files always returns a dict; never raises (WARN-only contract)."""
        from commands.content.claim_report import scan_files
        k = _knowledge(set())
        # Malformed file with no evidence block
        f = tmp_path / "bare.md"
        f.write_text("# No frontmatter here", encoding="utf-8")
        report = scan_files([f], k)
        assert isinstance(report, dict)

    def test_produces_json_artifact(self, tmp_path):
        """scan_files report must be JSON-serialisable."""
        from commands.content.claim_report import scan_files
        f = _write_md(tmp_path, "test.md", ["ERC-STALE-0000"])
        k = _knowledge(set())
        report = scan_files([f], k)
        serialised = json.dumps(report)
        parsed = json.loads(serialised)
        assert "records" in parsed
        assert "warn_count" in parsed


class TestClaimReportNoContentWrites:
    def test_scan_files_does_not_modify_content(self, tmp_path):
        """scan_files must not write to any content file."""
        from commands.content.claim_report import scan_files
        f = _write_md(tmp_path, "test.md", ["ERC-STALE-0000"])
        content_before = f.read_bytes()
        k = _knowledge(set())
        scan_files([f], k)
        assert f.read_bytes() == content_before


# ---------------------------------------------------------------------------
# Claim ID format validation tests
# ---------------------------------------------------------------------------

class TestClaimIdFormats:
    def test_valid_clm_format(self):
        from commands.content.claim_report import _is_valid_claim_format
        assert _is_valid_claim_format("CLM-cells-abc1234")
        assert _is_valid_claim_format("CLM-3d-001abc")

    def test_valid_erc_format(self):
        from commands.content.claim_report import _is_valid_claim_format
        assert _is_valid_claim_format("ERC-cells-java-aabbccdd")
        assert _is_valid_claim_format("ERC-3d-python-12345678")

    def test_invalid_formats(self):
        from commands.content.claim_report import _is_valid_claim_format
        assert not _is_valid_claim_format("not-a-claim")
        assert not _is_valid_claim_format("CLM-")
        assert not _is_valid_claim_format("ERC-cells-java")  # missing 8-hex suffix
        assert not _is_valid_claim_format("")
