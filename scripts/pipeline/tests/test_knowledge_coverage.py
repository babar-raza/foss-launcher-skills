"""Tests for knowledge_coverage.py — per-claim disposition table.

Verifies:
  - All claims in merged/claims.json receive exactly one disposition
  - ORPHANED count is 0 for well-formed knowledge with full coverage
  - SURFACE_ONLY is assigned to structural kinds (api_method, api_class, api_field)
  - USED_EVIDENCE is assigned when claim_id appears in evidence.claims
  - EXCLUDED_THRESHOLD is assigned for ERC-* claims when blog is blocked
  - compute_coverage returns correct summary structure
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Add scripts/pipeline/ to sys.path for direct invocation (pytest uses conftest.py).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from knowledge_coverage import (
    DISPOSITION,
    classify_claim,
    compute_coverage,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_claim(claim_id: str, kind: str, text: str = "", confidence: float = 0.9) -> dict:
    return {
        "claim_id": claim_id,
        "kind": kind,
        "text": text,
        "confidence": confidence,
    }


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def _write_yaml(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# classify_claim unit tests
# ---------------------------------------------------------------------------

class TestClassifyClaim(unittest.TestCase):

    def test_cited_claim_is_used_evidence(self):
        claim = _make_claim("CLM-x-001", "api_method")
        cited = {"CLM-x-001"}
        self.assertEqual(
            classify_claim(claim, cited, blog_blocked=False, kb_blocked=False, has_limitations=False),
            DISPOSITION["USED_EVIDENCE"],
        )

    def test_structural_kind_api_method_is_surface_only(self):
        claim = _make_claim("CLM-x-002", "api_method")
        self.assertEqual(
            classify_claim(claim, set(), blog_blocked=False, kb_blocked=False, has_limitations=False),
            DISPOSITION["SURFACE_ONLY"],
        )

    def test_structural_kind_api_class_is_surface_only(self):
        claim = _make_claim("CLM-x-003", "api_class")
        self.assertEqual(
            classify_claim(claim, set(), blog_blocked=False, kb_blocked=False, has_limitations=False),
            DISPOSITION["SURFACE_ONLY"],
        )

    def test_structural_kind_api_field_is_surface_only(self):
        claim = _make_claim("CLM-x-004", "api_field")
        self.assertEqual(
            classify_claim(claim, set(), blog_blocked=False, kb_blocked=False, has_limitations=False),
            DISPOSITION["SURFACE_ONLY"],
        )

    def test_erc_feature_claim_excluded_threshold_when_blog_blocked(self):
        claim = _make_claim("ERC-x-001", "feature", "AutoFilter supports filtered ranges.")
        self.assertEqual(
            classify_claim(claim, set(), blog_blocked=True, kb_blocked=False, has_limitations=False),
            DISPOSITION["EXCLUDED_THRESHOLD"],
        )

    def test_erc_api_claim_excluded_threshold_when_blog_blocked(self):
        claim = _make_claim("ERC-x-002", "api", "The AutoFilter class provides filtering.")
        self.assertEqual(
            classify_claim(claim, set(), blog_blocked=True, kb_blocked=False, has_limitations=False),
            DISPOSITION["EXCLUDED_THRESHOLD"],
        )

    def test_install_claim_excluded_tier_when_kb_blocked(self):
        claim = _make_claim("CLM-x-005", "install", "pip install aspose-cells")
        self.assertEqual(
            classify_claim(claim, set(), blog_blocked=False, kb_blocked=True, has_limitations=False),
            DISPOSITION["EXCLUDED_TIER"],
        )

    def test_format_claim_is_surface_only(self):
        claim = _make_claim("CLM-x-006", "format", "Supports XLSX export.")
        self.assertEqual(
            classify_claim(claim, set(), blog_blocked=False, kb_blocked=False, has_limitations=False),
            DISPOSITION["SURFACE_ONLY"],
        )

    def test_uncited_erc_api_claim_no_blog_no_kb_block_is_orphaned(self):
        claim = _make_claim("ERC-x-003", "api", "The Workbook class handles spreadsheets.")
        self.assertEqual(
            classify_claim(claim, set(), blog_blocked=False, kb_blocked=False, has_limitations=False),
            DISPOSITION["ORPHANED"],
        )


# ---------------------------------------------------------------------------
# compute_coverage integration test (uses temp filesystem)
# ---------------------------------------------------------------------------

class TestComputeCoverage(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.merged = self.tmp_path / "knowledge" / "test" / "net" / "merged"
        self.merged.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _write_minimal_knowledge(self, claims: list[dict], api_surface: list[dict] | None = None):
        """Write minimal merged/ knowledge artifacts to the temp dir."""
        _write_json(self.merged / "claims.json", claims)
        _write_json(self.merged / "api_surface.json", api_surface or [])
        _write_yaml(self.merged / "model.yaml", "stale_since: null\nversion: '1.0'\n")
        (self.merged / "limitations.md").write_text("No limitations detected.\n", encoding="utf-8")

    def test_all_claims_have_disposition(self):
        """Every claim must appear in output with exactly one disposition."""
        claims = [
            _make_claim("CLM-t-001", "api_method"),
            _make_claim("CLM-t-002", "api_class"),
            _make_claim("ERC-t-001", "api", "The Widget class handles widgets."),
        ]
        self._write_minimal_knowledge(claims)

        with patch("knowledge_coverage.discover_content", return_value=[]), \
             patch("knowledge_coverage._load_site_plan", return_value={}):
            result = compute_coverage("test", "net", knowledge_root=self.tmp_path / "knowledge")

        claim_ids_in_result = {r["claim_id"] for r in result["claims"]}
        self.assertEqual(claim_ids_in_result, {"CLM-t-001", "CLM-t-002", "ERC-t-001"})
        self.assertEqual(len(result["claims"]), 3)

    def test_structural_claims_are_surface_only(self):
        claims = [_make_claim("CLM-t-001", "api_method"), _make_claim("CLM-t-002", "api_class")]
        self._write_minimal_knowledge(claims)

        with patch("knowledge_coverage.discover_content", return_value=[]), \
             patch("knowledge_coverage._load_site_plan", return_value={}):
            result = compute_coverage("test", "net", knowledge_root=self.tmp_path / "knowledge")

        for r in result["claims"]:
            self.assertEqual(r["disposition"], DISPOSITION["SURFACE_ONLY"])

    def test_cited_claim_is_used_evidence(self):
        """A claim cited in evidence.claims on a page gets USED_EVIDENCE."""
        claims = [_make_claim("CLM-t-001", "api_method")]
        self._write_minimal_knowledge(claims)

        # Create a mock content page with the claim cited
        page = self.tmp_path / "page.md"
        page.write_text(
            "---\nevidence:\n  claims:\n  - CLM-t-001\n  apis: []\n---\nContent.\n",
            encoding="utf-8",
        )

        with patch("knowledge_coverage.discover_content", return_value=[page]), \
             patch("knowledge_coverage._load_site_plan", return_value={}):
            result = compute_coverage("test", "net", knowledge_root=self.tmp_path / "knowledge")

        self.assertEqual(result["claims"][0]["disposition"], DISPOSITION["USED_EVIDENCE"])

    def test_no_orphaned_claims_for_full_structural_coverage(self):
        """When all claims are structural, there should be zero ORPHANED."""
        claims = [
            _make_claim(f"CLM-t-{i:03d}", "api_method") for i in range(10)
        ]
        self._write_minimal_knowledge(claims)

        with patch("knowledge_coverage.discover_content", return_value=[]), \
             patch("knowledge_coverage._load_site_plan", return_value={}):
            result = compute_coverage("test", "net", knowledge_root=self.tmp_path / "knowledge")

        self.assertEqual(result["summary"]["orphaned_count"], 0)

    def test_summary_totals_match_claims_count(self):
        """Sum of all disposition counts must equal total_claims."""
        claims = [
            _make_claim("CLM-t-001", "api_method"),
            _make_claim("CLM-t-002", "api_class"),
            _make_claim("ERC-t-001", "api", "The Widget class."),
        ]
        self._write_minimal_knowledge(claims)

        with patch("knowledge_coverage.discover_content", return_value=[]), \
             patch("knowledge_coverage._load_site_plan", return_value={}):
            result = compute_coverage("test", "net", knowledge_root=self.tmp_path / "knowledge")

        total_from_dispositions = sum(result["summary"]["claim_dispositions"].values())
        self.assertEqual(total_from_dispositions, result["summary"]["total_claims"])
        self.assertEqual(result["summary"]["total_claims"], 3)

    def test_stale_knowledge_raises(self):
        """Stale knowledge should raise ValueError."""
        claims = [_make_claim("CLM-t-001", "api_method")]
        _write_json(self.merged / "claims.json", claims)
        _write_json(self.merged / "api_surface.json", [])
        _write_yaml(self.merged / "model.yaml", "stale_since: '2026-04-01'\nversion: '1.0'\n")

        with self.assertRaises(ValueError, msg="Expected stale knowledge to raise ValueError"):
            compute_coverage("test", "net", knowledge_root=self.tmp_path / "knowledge")


if __name__ == "__main__":
    unittest.main()
