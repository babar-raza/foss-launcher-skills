"""Unit tests for audit/formats.py — verify_capability_matrix_claims_current
(H7 durable correctness guard, MT068-2026-09-11-IMAGING-NET-LAUNCH).

Tests that:
- a capability_matrix_cell claim whose row label still matches formats.json
  produces no finding
- a claim whose row label no longer matches (upstream format renamed/removed)
  produces a WARN, not a FAIL — knowledge staleness, not a page defect
- an already-unverified-tier claim (confidence < 1.0) is never re-checked --
  it never claimed source-verified certainty in the first place
- claims of any other kind are ignored entirely
- missing claims.json / formats.json causes a graceful skip, never a crash
"""
import json
import unittest
from pathlib import Path


class TestVerifyCapabilityMatrixClaimsCurrent(unittest.TestCase):
    def setUp(self):
        import audit.formats as fmt_mod
        fmt_mod._load_known_format_names.cache_clear()

    def tearDown(self):
        import audit.formats as fmt_mod
        fmt_mod._load_known_format_names.cache_clear()
        fmt_mod.configure()

    def _write(self, tmpdir: Path, *, formats: list[dict], claims: list[dict]) -> None:
        merged = tmpdir / "knowledge" / "imaging" / "net" / "merged"
        merged.mkdir(parents=True, exist_ok=True)
        (merged / "formats.json").write_text(json.dumps(formats), encoding="utf-8")
        (merged / "claims.json").write_text(json.dumps(claims), encoding="utf-8")

    def _run(self, tmpdir: Path, *, formats: list[dict], claims: list[dict]):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        import audit.formats as fmt_mod
        fmt_mod.configure(knowledge_root=tmpdir / "knowledge")
        self._write(tmpdir, formats=formats, claims=claims)
        return fmt_mod.verify_capability_matrix_claims_current("imaging", "net")

    def test_matching_row_label_produces_no_finding(self):
        with_tmp = Path(self._tmp())
        findings = self._run(
            with_tmp,
            formats=[{"format": "Png", "direction": "detect"}],
            claims=[{
                "claim_id": "CLM-imaging-abc123",
                "kind": "capability_matrix_cell",
                "text": "For PNG, Detect is supported (per README.md's Format table).",
                "confidence": 1.0,
            }],
        )
        self.assertEqual(findings, [])

    def test_drifted_row_label_produces_warn_not_fail(self):
        with_tmp = Path(self._tmp())
        findings = self._run(
            with_tmp,
            formats=[{"format": "Jpeg", "direction": "detect"}],  # PNG removed upstream
            claims=[{
                "claim_id": "CLM-imaging-abc123",
                "kind": "capability_matrix_cell",
                "text": "For PNG, Detect is supported (per README.md's Format table).",
                "confidence": 1.0,
            }],
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].level, "WARN")
        self.assertIn("PNG", findings[0].message)
        self.assertIn("CLM-imaging-abc123", findings[0].message)

    def test_annotated_row_label_strips_parenthetical_before_matching(self):
        with_tmp = Path(self._tmp())
        findings = self._run(
            with_tmp,
            formats=[{"format": "Wmf", "direction": "detect"}],
            claims=[{
                "claim_id": "CLM-imaging-def456",
                "kind": "capability_matrix_cell",
                "text": (
                    "For WMF (placeable), Width / Height is supported "
                    "(assumes 96 DPI) (per README.md's Format table)."
                ),
                "confidence": 1.0,
            }],
        )
        self.assertEqual(findings, [])

    def test_unverified_tier_claim_never_flagged(self):
        """A claim that was already <1.0 confidence at extraction time (no
        enum match then) has nothing to drift from -- must not be re-checked."""
        with_tmp = Path(self._tmp())
        findings = self._run(
            with_tmp,
            formats=[],  # no known formats at all
            claims=[{
                "claim_id": "CLM-slides-abc123",
                "kind": "capability_matrix_cell",
                "text": "For Threaded comment part, .NET is supported (per README.md's Feature table).",
                "confidence": 0.75,
            }],
        )
        self.assertEqual(findings, [])

    def test_other_claim_kinds_ignored(self):
        with_tmp = Path(self._tmp())
        findings = self._run(
            with_tmp,
            formats=[],
            claims=[{
                "claim_id": "CLM-imaging-xyz789",
                "kind": "format_support",
                "text": "Detects format Png via ImageFormat",
                "confidence": 1.0,
            }],
        )
        self.assertEqual(findings, [])

    def test_missing_claims_json_returns_empty_no_crash(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        import audit.formats as fmt_mod
        with_tmp = Path(self._tmp())
        fmt_mod.configure(knowledge_root=with_tmp / "knowledge")
        findings = fmt_mod.verify_capability_matrix_claims_current("imaging", "net")
        self.assertEqual(findings, [])

    _tmp_counter = 0

    def _tmp(self) -> str:
        import tempfile
        d = tempfile.mkdtemp(prefix="cap_matrix_drift_test_")
        self.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
        return d


if __name__ == "__main__":
    unittest.main()
