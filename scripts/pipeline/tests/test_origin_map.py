"""Tests for scripts/gap-eval/origin_map.py

Covers:
  - TestOriginMapFindingTypes      : one test per finding type → correct origin_class + repair_route
  - TestWrongApiNameDisambiguation : clone-cache grep routing (mock subprocess)
  - TestWrongClaimDisambiguation   : claims.json lookup routing
  - TestTier3NonDeterminismFlag    : non-det flag rules + safety assertion
  - TestOriginMapOutputFormat      : schema + field invariants
  - TestOriginMapCLI               : CLI contract (dry-run, bad input, empty findings, corrupt JSON)
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# ---------------------------------------------------------------------------
# Path setup — identical pattern to test_gap_eval_profile_safety.py
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[3]
_GAP_EVAL_DIR = _REPO_ROOT / "scripts" / "gap-eval"
sys.path.insert(0, str(_GAP_EVAL_DIR))
sys.path.insert(0, str(_REPO_ROOT / "scripts"))
sys.path.insert(0, str(_REPO_ROOT / "scripts" / "pipeline"))

import origin_map as om  # type: ignore

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "origin_map"


def _load_fixture(name: str) -> dict | list:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


def _api_surface() -> list[dict]:
    return _load_fixture("minimal_api_surface.json")  # type: ignore


def _api_names() -> set[str]:
    return om._build_api_name_set(_api_surface())


def _claims() -> list[dict]:
    return _load_fixture("minimal_claims.json")  # type: ignore


def _finding(**overrides) -> dict:
    """Build a minimal finding dict with sensible defaults."""
    base = {
        "id": "F-test-java-test-00000000",
        "type": "wrong-claim",
        "severity": "S",
        "tier_resolved_by": 1,
        "file": "content/docs.aspose.org/en/test/java/index.md",
        "line": 1,
        "old_value": "test value",
        "correct_value": None,
        "description": "test finding",
        "status": "open",
    }
    base.update(overrides)
    return base


def _classify(finding: dict, *, no_grep: bool = True, claims: list | None = None) -> dict:
    """Classify a single finding with minimal knowledge artifacts. Grep disabled by default."""
    return om.classify_finding(
        finding,
        family="test",
        platform="java",
        api_names=_api_names(),
        claims=claims if claims is not None else _claims(),
        clone_cache_path=Path("/nonexistent/clone/cache"),
        no_grep=no_grep,
    )


# ---------------------------------------------------------------------------
# Test classes
# ---------------------------------------------------------------------------

class TestOriginMapFindingTypes(unittest.TestCase):
    """One test per finding type — verify origin_class and repair_route."""

    def test_broken_link_upstream_s74(self):
        f = _finding(type="broken-link", tier_resolved_by=1)
        r = _classify(f)
        self.assertEqual(r["origin_class"], om.UPSTREAM)
        self.assertEqual(r["repair_route"], om.ROUTE_S74)
        self.assertEqual(r["origin_certainty"], om.HIGH)
        self.assertFalse(r["tier3_non_determinism_flag"])

    def test_knowledge_model_wrong_with_correct_value_pipeline_profile_stale(self):
        f = _finding(
            type="knowledge-model-wrong",
            old_value="old-pkg",
            correct_value="new-pkg",
            tier_resolved_by=1,
        )
        r = _classify(f)
        self.assertEqual(r["origin_class"], om.PIPELINE)
        self.assertEqual(r["origin_subclass"], om.SUB_PROFILE_STALE)
        self.assertEqual(r["repair_route"], om.ROUTE_HUMAN)
        self.assertEqual(r["origin_certainty"], om.HIGH)

    def test_knowledge_model_wrong_without_correct_value_pipeline_extraction_miss(self):
        f = _finding(type="knowledge-model-wrong", old_value="SomeClass", correct_value=None)
        r = _classify(f)
        self.assertEqual(r["origin_class"], om.PIPELINE)
        self.assertEqual(r["origin_subclass"], om.SUB_EXTRACTION_MISS)
        self.assertEqual(r["repair_route"], om.ROUTE_HUMAN)

    def test_phantom_api_always_pipeline_extraction_miss(self):
        f = _finding(type="phantom-api", old_value="GhostClass")
        r = _classify(f)
        self.assertEqual(r["origin_class"], om.PIPELINE)
        self.assertEqual(r["origin_subclass"], om.SUB_EXTRACTION_MISS)
        self.assertEqual(r["repair_route"], om.ROUTE_HUMAN)
        self.assertEqual(r["origin_certainty"], om.HIGH)

    def test_wrong_package_with_both_values_content_s46(self):
        """wrong-package where correct_value is known → generator used wrong pkg → CONTENT."""
        f = _finding(
            type="wrong-package",
            old_value="old-pkg",
            correct_value="new-pkg",
        )
        r = _classify(f)
        self.assertEqual(r["origin_class"], om.CONTENT)
        self.assertEqual(r["repair_route"], om.ROUTE_S46)

    def test_wrong_package_without_correct_value_ambiguous(self):
        f = _finding(type="wrong-package", old_value="unknown-pkg", correct_value=None)
        r = _classify(f)
        self.assertEqual(r["origin_class"], om.AMBIGUOUS)
        self.assertEqual(r["repair_route"], om.ROUTE_AMBIGUOUS)

    def test_unimplemented_as_working_in_limitations_content_s26(self):
        """Token appears in limitations.md → generator used it despite limitation → CONTENT."""
        f = _finding(
            type="unimplemented-as-working",
            old_value="LimitedFeature",
            tier_resolved_by=3,
            tier3_cache_hit=True,
            llm_confidence=0.8,
        )
        with patch.object(om, "_token_in_limitations", return_value=True):
            r = _classify(f)
        self.assertEqual(r["origin_class"], om.CONTENT)
        self.assertEqual(r["repair_route"], om.ROUTE_S26)
        self.assertFalse(r["tier3_non_determinism_flag"])

    def test_unimplemented_as_working_not_in_limitations_pipeline(self):
        """Token NOT in limitations.md → enrichment gap → PIPELINE."""
        f = _finding(
            type="unimplemented-as-working",
            old_value="MissingFromLimitations",
            tier_resolved_by=3,
            tier3_cache_hit=True,
            llm_confidence=0.8,
        )
        with patch.object(om, "_token_in_limitations", return_value=False):
            r = _classify(f)
        self.assertEqual(r["origin_class"], om.PIPELINE)
        self.assertEqual(r["repair_route"], om.ROUTE_HUMAN)

    def test_missing_section_in_site_plan_content_s26(self):
        f = _finding(
            type="missing-section",
            file="content/kb.aspose.org/en/test/java/howto.md",
        )
        with patch.object(om, "_page_in_site_plan", return_value=True):
            r = _classify(f)
        self.assertEqual(r["origin_class"], om.CONTENT)
        self.assertEqual(r["repair_route"], om.ROUTE_S26)

    def test_missing_section_not_in_site_plan_pipeline(self):
        f = _finding(
            type="missing-section",
            file="content/kb.aspose.org/en/test/java/howto.md",
        )
        with patch.object(om, "_page_in_site_plan", return_value=False):
            r = _classify(f)
        self.assertEqual(r["origin_class"], om.PIPELINE)
        self.assertEqual(r["repair_route"], om.ROUTE_HUMAN)
        self.assertEqual(r["origin_subclass"], om.SUB_PLANNER_GAP)

    def test_missing_section_no_site_plan_pipeline_low_certainty(self):
        f = _finding(type="missing-section")
        with patch.object(om, "_page_in_site_plan", return_value=None):
            r = _classify(f)
        self.assertEqual(r["origin_class"], om.PIPELINE)
        self.assertEqual(r["origin_certainty"], om.LOW)

    def test_structural_reference_page_class_in_surface_content(self):
        """Class in api_surface → malformed page, not extraction miss → CONTENT."""
        f = _finding(type="structural-reference-page", old_value="Document")
        r = _classify(f)  # "Document" is in minimal_api_surface.json
        self.assertEqual(r["origin_class"], om.CONTENT)
        self.assertEqual(r["repair_route"], om.ROUTE_S26)

    def test_structural_reference_page_class_not_in_surface_pipeline(self):
        f = _finding(type="structural-reference-page", old_value="UnknownClass")
        r = _classify(f)
        self.assertEqual(r["origin_class"], om.PIPELINE)
        self.assertEqual(r["repair_route"], om.ROUTE_HUMAN)

    def test_needs_review_always_ambiguous(self):
        f = _finding(type="needs-review", tier_resolved_by=4)
        r = _classify(f)
        self.assertEqual(r["origin_class"], om.AMBIGUOUS)
        self.assertEqual(r["repair_route"], om.ROUTE_AMBIGUOUS)
        self.assertFalse(r["tier3_non_determinism_flag"])

    def test_unknown_finding_type_ambiguous(self):
        f = _finding(type="some-future-type")
        r = _classify(f)
        self.assertEqual(r["origin_class"], om.AMBIGUOUS)


class TestWrongApiNameDisambiguation(unittest.TestCase):
    """Clone-cache grep routing for wrong-api-name findings."""

    def _finding_wapi(self, old_value: str = "FakeClass.fakeMethod") -> dict:
        return _finding(type="wrong-api-name", old_value=old_value)

    def test_token_in_api_surface_content_regardless_of_grep(self):
        """Token already in api_surface → usage context issue → CONTENT, no grep called."""
        f = self._finding_wapi(old_value="Document")  # in minimal_api_surface.json
        # T3-MOCK: target=subprocess.run reason="grep clone-cache boundary call" removal=PERMANENT
        with patch("subprocess.run") as mock_grep:
            r = _classify(f, no_grep=False)
        mock_grep.assert_not_called()
        self.assertEqual(r["origin_class"], om.CONTENT)
        self.assertEqual(r["repair_route"], om.ROUTE_S26)

    def test_token_found_in_clone_cache_pipeline_extraction_miss(self):
        """grep returns 'found' → token exists in source but scout missed → PIPELINE."""
        f = self._finding_wapi(old_value="UnextractedMethod")
        with patch.object(om, "_grep_clone_cache", return_value="found"):
            r = _classify(f, no_grep=False)
        self.assertEqual(r["origin_class"], om.PIPELINE)
        self.assertEqual(r["origin_subclass"], om.SUB_EXTRACTION_MISS)
        self.assertEqual(r["repair_route"], om.ROUTE_HUMAN)

    def test_token_not_in_clone_cache_content_hallucination(self):
        """grep returns 'not-found' → token never existed in source → CONTENT hallucination."""
        f = self._finding_wapi(old_value="TotallyFakeMethod")
        with patch.object(om, "_grep_clone_cache", return_value="not-found"):
            r = _classify(f, no_grep=False)
        self.assertEqual(r["origin_class"], om.CONTENT)
        self.assertEqual(r["origin_subclass"], om.SUB_HALLUCINATION)
        self.assertEqual(r["repair_route"], om.ROUTE_S46)

    def test_grep_timeout_produces_ambiguous(self):
        f = self._finding_wapi()
        # T3-MOCK: target=subprocess.run reason="grep clone-cache boundary call" removal=PERMANENT
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(["grep"], 10)):
            r = _classify(f, no_grep=False)
        self.assertEqual(r["origin_class"], om.AMBIGUOUS)
        self.assertEqual(r["repair_route"], om.ROUTE_AMBIGUOUS)

    def test_grep_file_not_found_produces_ambiguous(self):
        f = self._finding_wapi()
        # T3-MOCK: target=subprocess.run reason="grep clone-cache boundary call" removal=PERMANENT
        with patch("subprocess.run", side_effect=FileNotFoundError):
            r = _classify(f, no_grep=False)
        self.assertEqual(r["origin_class"], om.AMBIGUOUS)

    def test_no_grep_flag_produces_ambiguous_without_subprocess_call(self):
        """--no-grep must produce AMBIGUOUS and must NOT call subprocess.run."""
        f = self._finding_wapi()
        # T3-MOCK: target=subprocess.run reason="grep clone-cache boundary call" removal=PERMANENT
        with patch("subprocess.run") as mock_grep:
            r = _classify(f, no_grep=True)
        mock_grep.assert_not_called()
        self.assertEqual(r["origin_class"], om.AMBIGUOUS)
        self.assertEqual(r["repair_route"], om.ROUTE_AMBIGUOUS)


class TestWrongClaimDisambiguation(unittest.TestCase):
    """Claims.json lookup routing for wrong-claim findings."""

    def _finding_wclm(self, old_value: str, llm_confidence: float = 0.8,
                      cached: bool = True) -> dict:
        return _finding(
            type="wrong-claim",
            old_value=old_value,
            tier_resolved_by=3,
            llm_confidence=llm_confidence,
            tier3_cache_hit=cached,
        )

    def test_claim_in_claims_high_confidence_pipeline_enrichment_error(self):
        """Claim in claims.json with confidence ≥ 0.7 → enrichment produced bad claim."""
        # "Document.Save supports all major formats" is in minimal_claims.json with conf 0.85
        f = self._finding_wclm("Document.Save supports all major formats")
        r = _classify(f)
        self.assertEqual(r["origin_class"], om.PIPELINE)
        self.assertEqual(r["origin_subclass"], om.SUB_ENRICHMENT_ERROR)
        self.assertEqual(r["repair_route"], om.ROUTE_HUMAN)

    def test_claim_in_claims_low_confidence_pipeline_low_confidence(self):
        """Claim in claims.json with confidence < 0.5 → low-confidence claim reached content."""
        # "Use Document.Convert for format conversion" has conf 0.40
        f = self._finding_wclm("Use Document.Convert for format conversion")
        r = _classify(f)
        self.assertEqual(r["origin_class"], om.PIPELINE)
        self.assertEqual(r["origin_subclass"], om.SUB_LOW_CONFIDENCE)
        self.assertEqual(r["repair_route"], om.ROUTE_HUMAN)

    def test_claim_not_in_claims_content_hallucination_s26(self):
        """Claim not in claims.json → generator fabricated it → CONTENT hallucination."""
        f = self._finding_wclm("invented claim not in knowledge base at all")
        r = _classify(f)
        self.assertEqual(r["origin_class"], om.CONTENT)
        self.assertEqual(r["origin_subclass"], om.SUB_HALLUCINATION)
        self.assertEqual(r["repair_route"], om.ROUTE_S26)

    def test_low_llm_confidence_ambiguous_regardless_of_claims(self):
        """llm_confidence < 0.6 → AMBIGUOUS regardless of whether claim is in claims.json."""
        # Use a claim that IS in claims.json with high enrichment confidence
        f = self._finding_wclm(
            "Document.Save supports all major formats",
            llm_confidence=0.45,  # below threshold
        )
        r = _classify(f)
        self.assertEqual(r["origin_class"], om.AMBIGUOUS)
        self.assertEqual(r["origin_subclass"], om.SUB_LOW_CONFIDENCE)

    def test_llm_confidence_at_threshold_not_ambiguous(self):
        """llm_confidence exactly 0.6 should NOT be classified as ambiguous."""
        f = self._finding_wclm("invented claim not known", llm_confidence=0.6)
        r = _classify(f)
        # Should classify normally (CONTENT hallucination), not as AMBIGUOUS via confidence check
        self.assertNotEqual(r["origin_subclass"], om.SUB_LOW_CONFIDENCE)


class TestTier3NonDeterminismFlag(unittest.TestCase):
    """Non-determinism flag rules and safety assertion."""

    def test_tier3_live_finding_flagged(self):
        """tier_resolved_by=3 without tier3_cache_hit → flag=True."""
        f = _finding(type="wrong-claim", tier_resolved_by=3, llm_confidence=0.8)
        # No tier3_cache_hit field → non-deterministic
        r = _classify(f)
        self.assertTrue(r["tier3_non_determinism_flag"])

    def test_tier3_cached_finding_not_flagged(self):
        """tier_resolved_by=3 with tier3_cache_hit=True → flag=False."""
        f = _finding(
            type="wrong-claim",
            tier_resolved_by=3,
            llm_confidence=0.8,
            tier3_cache_hit=True,
        )
        r = _classify(f)
        self.assertFalse(r["tier3_non_determinism_flag"])

    def test_tier1_finding_never_flagged(self):
        f = _finding(type="broken-link", tier_resolved_by=1)
        r = _classify(f)
        self.assertFalse(r["tier3_non_determinism_flag"])

    def test_tier2_finding_never_flagged(self):
        f = _finding(type="wrong-api-name", tier_resolved_by=2)
        r = _classify(f, no_grep=True)
        self.assertFalse(r["tier3_non_determinism_flag"])

    def test_non_det_tier3_finding_always_ambiguous_even_if_would_be_content(self):
        """CRITICAL safety assertion: a live Tier 3 finding that would be CONTENT
        must still route to AMBIGUOUS due to non-determinism risk.

        This prevents automated repair of findings that may disappear on next run."""
        # wrong-claim not in claims.json → would normally be CONTENT/hallucination
        f = _finding(
            type="wrong-claim",
            old_value="invented claim not in knowledge",
            tier_resolved_by=3,
            llm_confidence=0.8,
            # No tier3_cache_hit → non-deterministic
        )
        r = _classify(f)
        # Must be AMBIGUOUS, not CONTENT — the non-determinism flag overrides routing
        self.assertEqual(r["origin_class"], om.AMBIGUOUS)
        self.assertEqual(r["repair_route"], om.ROUTE_AMBIGUOUS)
        self.assertTrue(r["tier3_non_determinism_flag"])


class TestOriginMapOutputFormat(unittest.TestCase):
    """Schema and field invariants on annotate_findings() output."""

    _REQUIRED_FIELDS = {
        "origin_class", "origin_subclass", "origin_certainty",
        "origin_evidence", "repair_route", "tier3_non_determinism_flag",
    }
    _VALID_CLASSES = {om.CONTENT, om.PIPELINE, om.UPSTREAM, om.AMBIGUOUS}
    _VALID_ROUTES = {om.ROUTE_S26, om.ROUTE_S46, om.ROUTE_S74, om.ROUTE_HUMAN, om.ROUTE_AMBIGUOUS}
    _VALID_CERTAINTIES = {om.HIGH, om.MEDIUM, om.LOW}

    def _annotate_fixture(self) -> list[dict]:
        data = _load_fixture("baseline_findings.json")
        findings = data["findings"]  # type: ignore
        return om.annotate_findings(
            findings,
            family="test",
            platform="java",
            api_surface_path=_FIXTURES / "minimal_api_surface.json",
            claims_path=_FIXTURES / "minimal_claims.json",
            clone_cache_path=Path("/nonexistent"),
            no_grep=True,
        )

    def test_all_required_fields_present(self):
        annotated = self._annotate_fixture()
        for f in annotated:
            for field in self._REQUIRED_FIELDS:
                self.assertIn(field, f, msg=f"Missing field '{field}' in finding {f.get('id')}")

    def test_origin_class_values_enumerated(self):
        annotated = self._annotate_fixture()
        for f in annotated:
            self.assertIn(f["origin_class"], self._VALID_CLASSES,
                          msg=f"Invalid origin_class '{f['origin_class']}' in {f.get('id')}")

    def test_repair_route_values_enumerated(self):
        annotated = self._annotate_fixture()
        for f in annotated:
            self.assertIn(f["repair_route"], self._VALID_ROUTES,
                          msg=f"Invalid repair_route '{f['repair_route']}' in {f.get('id')}")

    def test_origin_certainty_values_enumerated(self):
        annotated = self._annotate_fixture()
        for f in annotated:
            self.assertIn(f["origin_certainty"], self._VALID_CERTAINTIES,
                          msg=f"Invalid origin_certainty in {f.get('id')}")

    def test_findings_count_preserved(self):
        """annotate_findings must return one annotated finding per input finding."""
        data = _load_fixture("baseline_findings.json")
        raw = data["findings"]  # type: ignore
        annotated = om.annotate_findings(
            raw, "test", "java",
            _FIXTURES / "minimal_api_surface.json",
            _FIXTURES / "minimal_claims.json",
            Path("/nonexistent"),
            no_grep=True,
        )
        self.assertEqual(len(annotated), len(raw))

    def test_unclassifiable_findings_preserved_as_ambiguous(self):
        """Findings with unknown types must be preserved with origin_class=AMBIGUOUS."""
        findings = [_finding(type="future-unknown-type-xyz")]
        annotated = om.annotate_findings(
            findings, "test", "java",
            _FIXTURES / "minimal_api_surface.json",
            _FIXTURES / "minimal_claims.json",
            Path("/nonexistent"),
            no_grep=True,
        )
        self.assertEqual(len(annotated), 1)
        self.assertEqual(annotated[0]["origin_class"], om.AMBIGUOUS)

    def test_original_finding_fields_preserved(self):
        """All original finding fields must still be present after annotation."""
        f = _finding(type="broken-link", severity="S", line=99)
        annotated = om.annotate_findings(
            [f], "test", "java",
            _FIXTURES / "minimal_api_surface.json",
            _FIXTURES / "minimal_claims.json",
            Path("/nonexistent"),
            no_grep=True,
        )
        self.assertEqual(annotated[0]["severity"], "S")
        self.assertEqual(annotated[0]["line"], 99)


class TestOriginMapCLI(unittest.TestCase):
    """CLI contract tests."""

    def _run_cli(self, *args: str) -> "subprocess.CompletedProcess[str]":
        return subprocess.run(
            [sys.executable, str(_GAP_EVAL_DIR / "origin_map.py")] + list(args),
            capture_output=True, text=True,
        )

    def test_dry_run_writes_no_output_file(self):
        fixture = _FIXTURES / "baseline_findings.json"
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "out.json"
            result = self._run_cli(
                str(fixture), "test", "java",
                "--no-grep", "--dry-run", "--out", str(out),
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertFalse(out.exists(), "dry-run must not write output file")

    def test_missing_input_file_exits_nonzero(self):
        result = self._run_cli("/nonexistent/path.json", "test", "java")
        self.assertNotEqual(result.returncode, 0)

    def test_empty_findings_list_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            empty_json = Path(tmpdir) / "empty.json"
            empty_json.write_text(json.dumps({"findings": [], "family": "test", "platform": "java"}))
            out = Path(tmpdir) / "out.json"
            result = self._run_cli(
                str(empty_json), "test", "java",
                "--no-grep", "--out", str(out),
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            data = json.loads(out.read_text())
            self.assertEqual(data["findings"], [])

    def test_corrupt_json_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bad = Path(tmpdir) / "bad.json"
            bad.write_text("{this is not json}")
            result = self._run_cli(str(bad), "test", "java")
            self.assertNotEqual(result.returncode, 0)

    def test_output_contains_origin_summary(self):
        fixture = _FIXTURES / "baseline_findings.json"
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "out.json"
            result = self._run_cli(
                str(fixture), "test", "java",
                "--no-grep", "--out", str(out),
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            data = json.loads(out.read_text())
            self.assertIn("origin_summary", data)
            summary = data["origin_summary"]
            self.assertIn("total", summary)
            self.assertIn("by_class", summary)
            self.assertEqual(summary["total"], len(data["findings"]))

    def test_output_is_valid_json(self):
        fixture = _FIXTURES / "baseline_findings.json"
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "out.json"
            self._run_cli(
                str(fixture), "test", "java",
                "--no-grep", "--out", str(out),
            )
            if out.exists():
                # Must parse without error
                json.loads(out.read_text())  # raises if invalid


class TestTier3CacheClassTierFlag(unittest.TestCase):
    """Additional edge cases for the non-determinism flag."""

    def test_tier3_cache_hit_false_field_is_non_deterministic(self):
        """Explicit tier3_cache_hit=False is the same as absent: non-deterministic."""
        f = _finding(type="wrong-claim", tier_resolved_by=3, tier3_cache_hit=False)
        self.assertTrue(om._is_tier3_non_deterministic(f))

    def test_tier3_cache_hit_true_is_deterministic(self):
        f = _finding(type="wrong-claim", tier_resolved_by=3, tier3_cache_hit=True)
        self.assertFalse(om._is_tier3_non_deterministic(f))

    def test_tier1_always_deterministic(self):
        f = _finding(tier_resolved_by=1)
        self.assertFalse(om._is_tier3_non_deterministic(f))


if __name__ == "__main__":
    unittest.main()
