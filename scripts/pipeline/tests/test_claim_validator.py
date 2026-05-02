"""Tests for evidence/claim_validator.py — stale claim detection (TC-CLAIM-05).

All tests use tmp_path only; no real content/ files are read.
"""
from __future__ import annotations

import json
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_md(tmp_path: Path, name: str, claims: list[str]) -> Path:
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
        "Some content here.",
    ]
    p = tmp_path / name
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def _knowledge(claim_ids: set[str]) -> MagicMock:
    """Return a mock Knowledge object with the given claim_ids."""
    k = MagicMock()
    k.claim_ids = claim_ids
    k.available = True
    return k


# ---------------------------------------------------------------------------
# detect_stale_claims tests
# ---------------------------------------------------------------------------

def test_detect_stale_finds_orphaned_id(tmp_path):
    from evidence.claim_validator import detect_stale_claims
    f = _write_md(tmp_path, "test.md", ["CLM-cells-abc123", "ERC-STALE-0000"])
    k = _knowledge({"CLM-cells-abc123"})
    stale = detect_stale_claims(f, k)
    assert stale == ["ERC-STALE-0000"]


def test_detect_stale_passes_on_all_valid_claims(tmp_path):
    from evidence.claim_validator import detect_stale_claims
    f = _write_md(tmp_path, "test.md", ["CLM-cells-abc123", "ERC-cells-java-aabbccdd"])
    k = _knowledge({"CLM-cells-abc123", "ERC-cells-java-aabbccdd"})
    stale = detect_stale_claims(f, k)
    assert stale == []


def test_detect_stale_empty_claims_returns_empty(tmp_path):
    from evidence.claim_validator import detect_stale_claims
    f = _write_md(tmp_path, "test.md", [])
    k = _knowledge({"CLM-cells-abc123"})
    stale = detect_stale_claims(f, k)
    assert stale == []


def test_detect_stale_no_evidence_block(tmp_path):
    from evidence.claim_validator import detect_stale_claims
    content = "---\ntitle: Test\n---\n# Test\n"
    f = tmp_path / "no_evidence.md"
    f.write_text(content, encoding="utf-8")
    k = _knowledge({"CLM-cells-abc123"})
    stale = detect_stale_claims(f, k)
    assert stale == []


def test_detect_stale_multiple_orphans(tmp_path):
    from evidence.claim_validator import detect_stale_claims
    f = _write_md(tmp_path, "test.md",
                  ["CLM-cells-abc123", "ERC-OLD-1111", "ERC-OLD-2222"])
    k = _knowledge({"CLM-cells-abc123"})
    stale = detect_stale_claims(f, k)
    assert sorted(stale) == ["ERC-OLD-1111", "ERC-OLD-2222"]


# ---------------------------------------------------------------------------
# report_stale_claims tests
# ---------------------------------------------------------------------------

def test_report_stale_produces_valid_json(tmp_path):
    from evidence.claim_validator import report_stale_claims

    f = _write_md(tmp_path, "test.md", ["CLM-cells-abc123", "ERC-STALE-0000"])

    with patch("evidence.claim_validator.discover_content") as mock_disc, \
         patch("knowledge_core.Knowledge") as mock_klass:
        mock_klass.return_value = _knowledge({"CLM-cells-abc123"})
        mock_disc.return_value = [f]

        report = report_stale_claims("cells", "java")
        # Must be JSON-serialisable
        serialised = json.dumps(report)
        parsed = json.loads(serialised)
        assert "stale" in parsed
        assert "total_files_scanned" in parsed
        assert "total_stale_claims" in parsed


def test_report_stale_no_content_files_modified(tmp_path):
    """report_stale_claims must not modify any file."""
    from evidence.claim_validator import report_stale_claims

    f = _write_md(tmp_path, "test.md", ["CLM-cells-abc123", "ERC-STALE-0000"])
    content_before = f.read_bytes()

    with patch("evidence.claim_validator.discover_content") as mock_disc, \
         patch("knowledge_core.Knowledge") as mock_klass:
        mock_klass.return_value = _knowledge({"CLM-cells-abc123"})
        mock_disc.return_value = [f]

        report_stale_claims("cells", "java")

    assert f.read_bytes() == content_before, "report_stale_claims modified a content file"


def test_report_stale_respects_subdomain_filter(tmp_path):
    from evidence.claim_validator import report_stale_claims

    f_ref = _write_md(tmp_path, "ref.md", ["ERC-STALE-0001"])
    f_blog = _write_md(tmp_path, "blog.md", ["ERC-STALE-0002"])

    with patch("evidence.claim_validator.discover_content") as mock_disc, \
         patch("evidence.claim_validator._infer_subdomain") as mock_infer, \
         patch("knowledge_core.Knowledge") as mock_klass:
        mock_klass.return_value = _knowledge(set())
        mock_disc.return_value = [f_ref, f_blog]
        mock_infer.side_effect = lambda p: (
            "reference.aspose.org" if p == f_ref else "blog.aspose.org"
        )

        report = report_stale_claims("cells", "java",
                                     subdomain="reference.aspose.org")

    assert report["total_files_scanned"] == 1
    assert str(f_ref) in report["stale"]
    assert str(f_blog) not in report["stale"]


def test_report_stale_unavailable_knowledge(tmp_path):
    from evidence.claim_validator import report_stale_claims

    k = MagicMock()
    k.available = False

    with patch("knowledge_core.Knowledge") as mock_klass:
        mock_klass.return_value = k
        report = report_stale_claims("cells", "java")

    assert "error" in report
    assert report["total_files_scanned"] == 0
