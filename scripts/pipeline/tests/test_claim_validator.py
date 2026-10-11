"""Tests for evidence/claim_validator.py — stale claim detection (TC-CLAIM-05).

All tests use tmp_path only; no real content/ files are read. Module
collaborators are injected via the configure() seam (AGENTS.md §16) instead
of unittest.mock.patch on internals (TC-W3H-007).
"""
from __future__ import annotations

import json
import textwrap
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from evidence import claim_validator


@pytest.fixture(autouse=True)
def _reset_claim_validator_configure():
    """Reset the claim_validator configure() seam after every test."""
    yield
    claim_validator.configure()


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

    claim_validator.configure(
        discover_content=lambda family, platform: [f],
        knowledge_factory=lambda family, platform: _knowledge({"CLM-cells-abc123"}),
    )
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

    claim_validator.configure(
        discover_content=lambda family, platform: [f],
        knowledge_factory=lambda family, platform: _knowledge({"CLM-cells-abc123"}),
    )
    report_stale_claims("cells", "java")

    assert f.read_bytes() == content_before, "report_stale_claims modified a content file"


def test_report_stale_respects_subdomain_filter(tmp_path):
    from evidence.claim_validator import report_stale_claims

    f_ref = _write_md(tmp_path, "ref.md", ["ERC-STALE-0001"])
    f_blog = _write_md(tmp_path, "blog.md", ["ERC-STALE-0002"])

    claim_validator.configure(
        discover_content=lambda family, platform: [f_ref, f_blog],
        infer_subdomain=lambda p: (
            "reference.aspose.org" if p == f_ref else "blog.aspose.org"
        ),
        knowledge_factory=lambda family, platform: _knowledge(set()),
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

    claim_validator.configure(knowledge_factory=lambda family, platform: k)
    report = report_stale_claims("cells", "java")

    assert "error" in report
    assert report["total_files_scanned"] == 0


# ---------------------------------------------------------------------------
# detect_stale_apis tests  (TC-CLAIM-06)
# ---------------------------------------------------------------------------

def _write_md_with_apis(tmp_path: Path, name: str, apis: list[str]) -> Path:
    """Write a minimal content .md file with given evidence.apis."""
    apis_yaml = "[" + ", ".join(repr(a) for a in apis) + "]"
    lines = [
        "---",
        "title: Test Page",
        "evidence:",
        "  model_sha: abc123",
        "  claims: []",
        f"  apis: {apis_yaml}",
        "---",
        "# Test",
        "",
        "Some content here.",
    ]
    p = tmp_path / name
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def _knowledge_with_classes(classes: set[str]) -> MagicMock:
    """Return a mock Knowledge object with the given class names."""
    k = MagicMock()
    k.classes = classes
    k.available = True
    return k


def test_detect_stale_apis_finds_unknown_class(tmp_path):
    from evidence.claim_validator import detect_stale_apis
    f = _write_md_with_apis(tmp_path, "test.md", ["BarCodeReader.read_bar_codes", "GhostClass.method"])
    k = _knowledge_with_classes({"BarCodeReader"})
    stale = detect_stale_apis(f, k)
    assert stale == ["GhostClass.method"]


def test_detect_stale_apis_passes_on_valid_class(tmp_path):
    from evidence.claim_validator import detect_stale_apis
    f = _write_md_with_apis(tmp_path, "test.md", ["BarCodeReader.read_bar_codes", "BarCodeGenerator"])
    k = _knowledge_with_classes({"BarCodeReader", "BarCodeGenerator"})
    stale = detect_stale_apis(f, k)
    assert stale == []


def test_detect_stale_apis_empty_apis_returns_empty(tmp_path):
    from evidence.claim_validator import detect_stale_apis
    f = _write_md_with_apis(tmp_path, "test.md", [])
    k = _knowledge_with_classes({"BarCodeReader"})
    stale = detect_stale_apis(f, k)
    assert stale == []


def test_detect_stale_apis_no_evidence_block(tmp_path):
    from evidence.claim_validator import detect_stale_apis
    content = "---\ntitle: Test\n---\n# Test\n"
    f = tmp_path / "no_evidence.md"
    f.write_text(content, encoding="utf-8")
    k = _knowledge_with_classes({"BarCodeReader"})
    stale = detect_stale_apis(f, k)
    assert stale == []


def test_detect_stale_apis_class_only_entry(tmp_path):
    """Entries without a dot (bare class names) are also validated."""
    from evidence.claim_validator import detect_stale_apis
    f = _write_md_with_apis(tmp_path, "test.md", ["KnownClass", "UnknownClass"])
    k = _knowledge_with_classes({"KnownClass"})
    stale = detect_stale_apis(f, k)
    assert stale == ["UnknownClass"]


def test_detect_stale_apis_multiple_unknown(tmp_path):
    from evidence.claim_validator import detect_stale_apis
    f = _write_md_with_apis(tmp_path, "test.md",
                             ["Good.method", "Bad1.foo", "Bad2.bar"])
    k = _knowledge_with_classes({"Good"})
    stale = detect_stale_apis(f, k)
    assert sorted(stale) == ["Bad1.foo", "Bad2.bar"]


def test_report_stale_apis_produces_valid_json(tmp_path):
    from evidence.claim_validator import report_stale_apis

    f = _write_md_with_apis(tmp_path, "test.md", ["GhostClass.method"])

    claim_validator.configure(
        discover_content=lambda family, platform: [f],
        knowledge_factory=lambda family, platform: _knowledge_with_classes(set()),
    )
    report = report_stale_apis("barcode", "python")
    serialised = json.dumps(report)
    parsed = json.loads(serialised)
    assert "stale" in parsed
    assert "total_files_scanned" in parsed
    assert "total_stale_apis" in parsed


def test_report_stale_apis_no_content_files_modified(tmp_path):
    """report_stale_apis must not modify any file."""
    from evidence.claim_validator import report_stale_apis

    f = _write_md_with_apis(tmp_path, "test.md", ["GhostClass.method"])
    content_before = f.read_bytes()

    claim_validator.configure(
        discover_content=lambda family, platform: [f],
        knowledge_factory=lambda family, platform: _knowledge_with_classes(set()),
    )
    report_stale_apis("barcode", "python")

    assert f.read_bytes() == content_before, "report_stale_apis modified a content file"


def test_report_stale_apis_unavailable_knowledge(tmp_path):
    from evidence.claim_validator import report_stale_apis

    k = MagicMock()
    k.available = False

    claim_validator.configure(knowledge_factory=lambda family, platform: k)
    report = report_stale_apis("barcode", "python")

    assert "error" in report
    assert report["total_files_scanned"] == 0
