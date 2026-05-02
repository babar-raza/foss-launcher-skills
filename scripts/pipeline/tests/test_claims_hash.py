"""Tests for TC-CLAIM-04 Phase 1 — claims_hash on Knowledge + dry-run-json output.

All tests use tmp_path; no real knowledge/ or content/ files are read.
Phase 1 constraint: zero content files modified.
"""
from __future__ import annotations

import hashlib
import json
import textwrap
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_knowledge_dir(tmp_path: Path, claims: list[dict],
                        family: str = "cells", platform: str = "java") -> Path:
    """Create a minimal knowledge dir with claims.json and model.yaml.

    Returns the knowledge root (tmp_path) so Knowledge(family, platform, knowledge_root=root)
    will resolve to root/family/platform/merged.
    """
    merged = tmp_path / family / platform / "merged"
    merged.mkdir(parents=True)

    # api_surface.json (required for available=True)
    (merged / "api_surface.json").write_text(json.dumps([]), encoding="utf-8")

    # model.yaml
    model = {"version": "1.0", "repo_sha": "abc123def456"}
    import yaml
    (merged / "model.yaml").write_text(yaml.dump(model), encoding="utf-8")

    # claims.json
    (merged / "claims.json").write_text(
        json.dumps(claims, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return tmp_path  # return root, not merged


def _make_content_file(tmp_path: Path, model_sha: str,
                       claims: list[str], claims_hash: str = "") -> Path:
    """Write a minimal .md file with evidence frontmatter (clean YAML, no dedent)."""
    claims_yaml = "[" + ", ".join(repr(c) for c in claims) + "]"
    lines = [
        "---",
        "title: Test",
        "evidence:",
        f"  model_sha: {model_sha}",
    ]
    if claims_hash:
        lines.append(f"  claims_hash: {claims_hash}")
    lines += [
        f"  claims: {claims_yaml}",
        "  apis: []",
        "---",
        "# Test",
        "",
        "Some content.",
    ]
    f = tmp_path / "test_page.md"
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return f


# ---------------------------------------------------------------------------
# Knowledge.claims_hash attribute tests
# ---------------------------------------------------------------------------

def test_claims_hash_attribute_on_knowledge_object(tmp_path):
    """Knowledge.claims_hash must be the sha256 hex of claims.json bytes."""
    claims = [{"claim_id": "CLM-cells-aabb", "text": "Test claim text."}]
    knowledge_root = _make_knowledge_dir(tmp_path, claims)

    claims_path = knowledge_root / "cells" / "java" / "merged" / "claims.json"
    expected_hash = hashlib.sha256(claims_path.read_bytes()).hexdigest()

    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "commands" / "knowledge"))
    from knowledge_core import Knowledge  # noqa: E402

    k = Knowledge("cells", "java", knowledge_root=knowledge_root)
    assert k.claims_hash == expected_hash


def test_claims_hash_empty_when_no_claims_file(tmp_path):
    """When claims.json is absent, claims_hash must be empty string."""
    merged = tmp_path / "cells" / "java" / "merged"
    merged.mkdir(parents=True)
    (merged / "api_surface.json").write_text("[]", encoding="utf-8")
    import yaml
    (merged / "model.yaml").write_text(
        yaml.dump({"version": "1.0", "repo_sha": "abc"}), encoding="utf-8"
    )
    # No claims.json

    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "commands" / "knowledge"))
    from knowledge_core import Knowledge  # noqa: E402

    k = Knowledge("cells", "java", knowledge_root=tmp_path)
    assert k.claims_hash == ""


def test_claims_hash_unavailable_knowledge(tmp_path):
    """When knowledge is unavailable, claims_hash defaults to empty string."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "commands" / "knowledge"))
    from knowledge_core import Knowledge  # noqa: E402

    k = Knowledge("cells", "java", knowledge_root=tmp_path)  # empty dir → unavailable
    assert k.available is False
    assert k.claims_hash == ""


# ---------------------------------------------------------------------------
# dry-run-json claims_hash fields tests
# ---------------------------------------------------------------------------

def test_dry_run_json_includes_claims_hash_fields(tmp_path):
    """WOULD_UPDATE records must include current_claims_hash and knowledge_claims_hash."""
    from evidence.runner import attach_evidence
    from unittest.mock import MagicMock, patch

    f = _make_content_file(tmp_path, model_sha="old-sha", claims=[], claims_hash="")

    k = MagicMock()
    k.repo_sha = "new-sha"
    k.version = "1.0"
    k.claims_hash = "hash-of-knowledge-claims"
    k.platform = "java"
    k.available = True
    k.api_to_claim = {}
    k.classes = {}

    records = []
    with patch("evidence.runner.extract_tokens", return_value=[]), \
         patch("evidence.runner.verify_tokens", return_value=[]), \
         patch("evidence.runner._map_tokens_to_evidence", return_value=([], [])), \
         patch("evidence.runner._detect_formats", return_value=[]), \
         patch("evidence.runner._build_sections_evidence", return_value=[]):
        attach_evidence(f, k, dry_run=True, dry_run_records=records)

    assert len(records) == 1
    rec = records[0]
    assert "current_claims_hash" in rec
    assert "knowledge_claims_hash" in rec
    assert rec["knowledge_claims_hash"] == "hash-of-knowledge-claims"


def test_dry_run_json_marks_would_update_metadata_when_claims_hash_differs(tmp_path):
    """When model_sha matches but claims_hash differs, action must be WOULD_UPDATE_METADATA."""
    from evidence.runner import attach_evidence
    from unittest.mock import MagicMock, patch

    # File has matching model_sha but old claims_hash
    f = _make_content_file(tmp_path, model_sha="same-sha", claims=["CLM-cells-abc"],
                           claims_hash="old-claims-hash")

    k = MagicMock()
    k.repo_sha = "same-sha"   # matches → would normally be SKIP
    k.claims_hash = "new-claims-hash"  # differs → WOULD_UPDATE_METADATA
    k.platform = "java"
    k.available = True

    records = []
    status = attach_evidence(f, k, dry_run=True, force=False, dry_run_records=records)

    assert status == "SKIP (current)"
    assert len(records) == 1
    assert records[0]["action"] == "WOULD_UPDATE_METADATA"
    assert records[0]["current_claims_hash"] == "old-claims-hash"
    assert records[0]["knowledge_claims_hash"] == "new-claims-hash"


def test_no_frontmatter_write_in_phase1(tmp_path):
    """No content file must be modified by claims_hash detection (Phase 1)."""
    from evidence.runner import attach_evidence
    from unittest.mock import MagicMock, patch

    f = _make_content_file(tmp_path, model_sha="same-sha", claims=["CLM-cells-abc"],
                           claims_hash="old-hash")
    content_before = f.read_bytes()

    k = MagicMock()
    k.repo_sha = "same-sha"
    k.claims_hash = "new-hash"
    k.platform = "java"
    k.available = True

    records = []
    attach_evidence(f, k, dry_run=True, force=False, dry_run_records=records)

    assert f.read_bytes() == content_before, "Phase 1 must not write to content files"
