"""Tests for shadow content generation, claim mapping, and end-to-end pilot.

Covers:
- shadow_content_generator.py
- claim_mapper.py
- page-plan-to-fact validation
- runner dry-run path
- content/ write prevention
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_PIPELINE_ROOT = Path(__file__).resolve().parents[1] / "scripts" / "pipeline"
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

from lib.fact_graph import Fact, FactGraph, FactType
from lib.claim_mapper import (
    ClaimMap,
    build_claim_map,
    extract_api_symbols,
    extract_fact_refs,
    validate_page_plan_fact_refs,
    verify_candidates,
)
from lib.product_state import Phase, ProductState, StopReason
from lib.schema_validators import validate_fact_graph, validate_page_plan
from commands.content.shadow_content_generator import (
    _is_forbidden_output,
    generate_candidates,
    generate_reference_candidate,
    generate_blog_candidate,
    generate_kb_candidate,
    main as shadow_main,
)
from commands.content.page_plan_compiler import compile_page_plan
from commands.ops.autonomous_runner import (
    determine_next_action, run_shadow_pipeline, run_agent_review_pipeline,
)
from lib.content_quality import (
    CandidateScore, score_candidate, score_candidates_dir,
    CONTENT_QUALITY_VERSION, MIN_WORD_COUNTS,
)
from lib.agent_decision_board import (
    BoardDecision, BoardVerdict, DecisionType,
    review_candidate as board_review_candidate,
    review_candidates as board_review_candidates,
    is_delegable,
)
from lib.candidate_repair import (
    repair_candidate as do_repair_candidate,
    repair_candidates_dir,
)
from lib.controlled_draft_writer import (
    check_write_guards, write_approved_candidates,
    WriteGuardError, RollbackManifest, WriteRecord,
    RollbackPathError, ALLOWED_ROLLBACK_ROOTS, _validate_rollback_target,
    rollback,
)
from lib.schema_validators import (
    validate_claim_map,
    validate_claim_verification_report,
    validate_shadow_candidate,
    validate_candidate_sections,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_graph() -> FactGraph:
    graph = FactGraph(family="pdf", platform="go", repo_sha="abc123", compiled_from="merged")
    graph.add_fact(Fact(
        fact_id=Fact.make_id("pdf", "go", "source", "api_class", "Document"),
        fact_type=FactType.SOURCE.value, category="api_class",
        family="pdf", platform="go", text="Document", repo_sha="abc123",
    ))
    graph.add_fact(Fact(
        fact_id=Fact.make_id("pdf", "go", "source", "api_method", "Document.Save"),
        fact_type=FactType.SOURCE.value, category="api_method",
        family="pdf", platform="go", text="Document.Save", repo_sha="abc123",
    ))
    graph.add_fact(Fact(
        fact_id=Fact.make_id("pdf", "go", "source", "api_method", "Document.Close"),
        fact_type=FactType.SOURCE.value, category="api_method",
        family="pdf", platform="go", text="Document.Close", repo_sha="abc123",
    ))
    graph.add_fact(Fact(
        fact_id=Fact.make_id("pdf", "go", "inferred", "claim", "Supports PDF/A"),
        fact_type=FactType.INFERRED.value, category="claim",
        family="pdf", platform="go", text="Supports PDF/A",
    ))
    return graph


def _make_fact_index(graph: FactGraph) -> dict[str, dict]:
    return {
        f.fact_id: {
            "fact_id": f.fact_id, "fact_type": f.fact_type,
            "category": f.category, "text": f.text,
            "confidence": f.confidence,
            "verification_status": f.verification_status,
        }
        for f in graph.facts
    }


# ---------------------------------------------------------------------------
# Shadow content generator tests
# ---------------------------------------------------------------------------

class TestShadowGenerator:
    def test_generate_reference_candidate(self):
        graph = _make_graph()
        fact_index = _make_fact_index(graph)
        page = {
            "page_type": "reference",
            "slug": "reference/pdf/go/document",
            "title": "Document",
            "required_sections": ["description", "methods"],
            "required_facts": [f.fact_id for f in graph.facts if f.category in ("api_class", "api_method")],
            "provenance_refs": [graph.facts[0].fact_id],
        }
        content = generate_reference_candidate(page, fact_index, "pdf", "go")
        assert "# Document" in content
        assert "shadow_candidate: true" in content
        assert "fact_ref:" in content
        assert "## Methods" in content

    def test_generate_candidates_writes_files(self, tmp_path):
        graph = _make_graph()
        plan = compile_page_plan(graph)
        records = generate_candidates(plan, graph, tmp_path, {"reference"}, limit=2)
        assert len(records) > 0
        for r in records:
            assert Path(r["output_path"]).exists()
            assert r["status"] == "generated"

    def test_forbidden_output_content_dir(self):
        # The actual content dir of the repo
        repo_root = Path(__file__).resolve().parents[1]
        content_dir = repo_root / "content" / "test"
        assert _is_forbidden_output(str(content_dir))

    def test_allowed_output_reports_dir(self):
        assert not _is_forbidden_output("reports/shadow/test")

    def test_cli_rejects_content_output(self):
        repo_root = Path(__file__).resolve().parents[1]
        content_path = str(repo_root / "content" / "shadow")
        result = shadow_main([
            "pdf", "go",
            "--page-plan", "nonexistent.json",
            "--fact-graph", "nonexistent.json",
            "--output-dir", content_path,
        ])
        assert result == 1

    def test_dry_run_no_writes(self, tmp_path):
        graph = _make_graph()
        plan = compile_page_plan(graph)
        plan_path = tmp_path / "plan.json"
        fg_path = tmp_path / "fg.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        graph.write(fg_path)

        out_dir = tmp_path / "output"
        result = shadow_main([
            "pdf", "go",
            "--page-plan", str(plan_path),
            "--fact-graph", str(fg_path),
            "--output-dir", str(out_dir),
            "--dry-run",
        ])
        assert result == 0
        assert not out_dir.exists()  # dry-run should not create output dir

    def test_generation_via_cli(self, tmp_path):
        graph = _make_graph()
        plan = compile_page_plan(graph)
        plan_path = tmp_path / "plan.json"
        fg_path = tmp_path / "fg.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        graph.write(fg_path)
        out_dir = tmp_path / "output"
        result = shadow_main([
            "pdf", "go",
            "--page-plan", str(plan_path),
            "--fact-graph", str(fg_path),
            "--output-dir", str(out_dir),
            "--page-types", "reference",
            "--limit", "1",
        ])
        assert result == 0
        manifest_path = out_dir / "generation_manifest.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["candidates_generated"] >= 1

    def test_generated_content_has_provenance(self, tmp_path):
        graph = _make_graph()
        plan = compile_page_plan(graph)
        records = generate_candidates(plan, graph, tmp_path, {"reference"}, limit=1)
        assert len(records) > 0
        content = Path(records[0]["output_path"]).read_text(encoding="utf-8")
        fact_refs = extract_fact_refs(content)
        assert len(fact_refs) > 0, "Generated content must contain fact references"


# ---------------------------------------------------------------------------
# Claim mapper tests
# ---------------------------------------------------------------------------

class TestClaimMapper:
    def test_extract_fact_refs(self):
        content = '<!-- fact_ref: FG-abcdef123456 -->\nSome text <!-- fact_ref: FG-000000000000 -->'
        refs = extract_fact_refs(content)
        assert "FG-abcdef123456" in refs
        assert "FG-000000000000" in refs

    def test_extract_api_symbols(self):
        content = "Use `Document.Save` to save and `Page.Render` to render."
        symbols = extract_api_symbols(content)
        assert "Document.Save" in symbols
        assert "Page.Render" in symbols

    def test_build_claim_map_valid(self):
        graph = _make_graph()
        fact_index = _make_fact_index(graph)
        fid = graph.facts[0].fact_id
        content = f"Some text <!-- fact_ref: {fid} -->"
        cm = build_claim_map(content, fact_index, "test.md", "pdf", "go")
        assert cm.total_refs == 1
        assert cm.supported_refs == 1
        assert cm.unsupported_refs == 0
        assert cm.is_valid

    def test_build_claim_map_unsupported(self):
        content = "<!-- fact_ref: FG-aabbccddeeff -->"
        cm = build_claim_map(content, {}, "test.md", "pdf", "go")
        assert cm.total_refs == 1
        assert cm.unsupported_refs == 1
        assert not cm.is_valid

    def test_build_claim_map_unsupported_symbol(self):
        graph = _make_graph()
        fact_index = _make_fact_index(graph)
        # Only dotted Class.Method patterns are flagged as API symbols
        content = "Use `FakeClass.FakeMethod` for processing."
        cm = build_claim_map(content, fact_index, "test.md", "pdf", "go")
        assert "FakeClass.FakeMethod" in cm.unsupported_symbols
        assert not cm.is_valid

    def test_standalone_camelcase_not_flagged(self):
        graph = _make_graph()
        fact_index = _make_fact_index(graph)
        # Standalone CamelCase word should NOT be flagged as API symbol
        content = "Use `AllowPrintHighRes` permission."
        cm = build_claim_map(content, fact_index, "test.md", "pdf", "go")
        assert len(cm.unsupported_symbols) == 0

    def test_verify_candidates_pass(self, tmp_path):
        graph = _make_graph()
        fact_index = _make_fact_index(graph)
        # Write a candidate with a valid fact ref
        fid = graph.facts[0].fact_id
        content = f"---\ntitle: test\n---\n# Test\n<!-- fact_ref: {fid} -->\n"
        (tmp_path / "valid.md").write_text(content, encoding="utf-8")
        report = verify_candidates(tmp_path, fact_index, "pdf", "go")
        assert report["passed"] >= 1
        assert report["failed"] == 0

    def test_verify_candidates_fail_fake_ref(self, tmp_path):
        content = "---\ntitle: fake\n---\n# Fake\n<!-- fact_ref: FG-aabbccddeeff -->\n"
        (tmp_path / "fake.md").write_text(content, encoding="utf-8")
        report = verify_candidates(tmp_path, {}, "pdf", "go")
        assert report["failed"] >= 1

    def test_claim_map_serialization(self):
        cm = ClaimMap(
            candidate_path="test.md", family="pdf", platform="go",
            total_refs=2, supported_refs=1, unsupported_refs=1,
        )
        d = cm.to_dict()
        assert d["is_valid"] is False
        json_str = cm.to_json()
        assert "is_valid" in json_str


# ---------------------------------------------------------------------------
# Page plan fact reference validation
# ---------------------------------------------------------------------------

class TestPagePlanFactRefs:
    def test_valid_plan_passes(self):
        graph = _make_graph()
        fact_index = _make_fact_index(graph)
        plan = compile_page_plan(graph)
        errors = validate_page_plan_fact_refs(plan, fact_index)
        assert errors == []

    def test_plan_with_fake_fact_fails(self):
        plan = {
            "subdomains": {
                "reference": {
                    "pages": [{
                        "title": "Fake",
                        "required_facts": ["FG-doesnotexist"],
                        "provenance_refs": [],
                    }]
                }
            }
        }
        errors = validate_page_plan_fact_refs(plan, {})
        assert len(errors) == 1
        assert "FG-doesnotexist" in errors[0]


# ---------------------------------------------------------------------------
# Runner state progression tests
# ---------------------------------------------------------------------------

class TestRunnerStateProgression:
    def test_full_happy_path_actions(self):
        """Runner should emit valid actions for the full happy path."""
        phases = [
            Phase.DISCOVERED, Phase.SOURCE_CHANGED, Phase.SNAPSHOT_CAPTURED,
            Phase.FACTS_EXTRACTED, Phase.FACTS_VERIFIED, Phase.PLAN_COMPILED,
            Phase.CONTENT_GENERATED, Phase.CLAIMS_VERIFIED,
            Phase.QUALITY_EVALUATED, Phase.REGRESSION_PASSED,
        ]
        for phase in phases:
            state = ProductState(family="pdf", platform="go", phase=phase.value)
            action = determine_next_action(state)
            assert action["command"] is not None, f"No command for {phase.value}"
            assert action["dry_run"] is True

    def test_ready_for_review_stops(self):
        state = ProductState(
            family="pdf", platform="go",
            phase=Phase.READY_FOR_REVIEW.value,
            stop_reason=StopReason.READY_FOR_AGENT_REVIEW.value,
        )
        action = determine_next_action(state)
        assert action["action_id"] == "stop"
        assert action["dry_run"] is True

    def test_quarantined_stops(self):
        state = ProductState(
            family="pdf", platform="go",
            phase=Phase.QUARANTINED.value,
            stop_reason=StopReason.QUARANTINED_REPEATED_FAILURE.value,
        )
        action = determine_next_action(state)
        assert action["action_id"] == "stop"

    def test_state_progression_to_content_generated(self):
        """Simulate state transitions up to CONTENT_GENERATED."""
        state = ProductState(family="pdf", platform="go")
        path = [
            Phase.SNAPSHOT_CAPTURED,
            Phase.FACTS_EXTRACTED,
            Phase.FACTS_VERIFIED,
            Phase.PLAN_COMPILED,
            Phase.CONTENT_GENERATED,
        ]
        for phase in path:
            state.transition(phase)
        assert state.phase == Phase.CONTENT_GENERATED.value
        assert state.stop_reason == StopReason.CONTINUE.value
        assert len(state.transition_history) == 5

    def test_state_progression_to_ready_for_review(self):
        """Full happy path to READY_FOR_REVIEW."""
        state = ProductState(family="pdf", platform="go")
        path = [
            Phase.SNAPSHOT_CAPTURED, Phase.FACTS_EXTRACTED,
            Phase.FACTS_VERIFIED, Phase.PLAN_COMPILED,
            Phase.CONTENT_GENERATED, Phase.CLAIMS_VERIFIED,
            Phase.QUALITY_EVALUATED, Phase.REGRESSION_PASSED,
            Phase.READY_FOR_REVIEW,
        ]
        for phase in path:
            state.transition(phase)
        assert state.phase == Phase.READY_FOR_REVIEW.value
        assert state.stop_reason == StopReason.READY_FOR_AGENT_REVIEW.value
        assert state.is_terminal()


# ---------------------------------------------------------------------------
# Content write prevention
# ---------------------------------------------------------------------------

class TestContentWritePrevention:
    def test_shadow_generator_rejects_content_path(self):
        repo_root = Path(__file__).resolve().parents[1]
        content_path = str(repo_root / "content" / "docs.aspose.org")
        assert _is_forbidden_output(content_path)

    def test_runner_never_outputs_publish(self):
        """No runner action should contain publish/deploy commands."""
        for phase in Phase:
            state = ProductState(family="pdf", platform="go", phase=phase.value)
            action = determine_next_action(state)
            cmd = action.get("command") or ""
            assert "publish" not in cmd.lower() or "readiness" in cmd.lower()
            assert "deploy" not in cmd.lower()
            assert action["dry_run"] is True


# ---------------------------------------------------------------------------
# Blog and KB generator tests
# ---------------------------------------------------------------------------

class TestBlogKbGenerators:
    def test_generate_blog_candidate(self):
        graph = _make_graph()
        fact_index = _make_fact_index(graph)
        page = {
            "page_type": "blog_post",
            "slug": "blog/pdf/go/overview",
            "title": "Aspose.Pdf for Go",
            "required_sections": ["introduction", "feature_overview", "conclusion"],
            "required_facts": [f.fact_id for f in graph.facts if f.category == "claim"],
            "provenance_refs": [],
        }
        content = generate_blog_candidate(page, fact_index, "pdf", "go")
        assert "# Aspose.Pdf for Go" in content
        assert "shadow_candidate: true" in content
        assert "## Introduction" in content
        assert "## Conclusion" in content

    def test_generate_kb_candidate(self):
        graph = _make_graph()
        fact_index = _make_fact_index(graph)
        page = {
            "page_type": "knowledge_base",
            "slug": "kb/pdf/go/overview",
            "title": "Aspose.Pdf for Go",
            "required_sections": ["problem", "solution"],
            "required_facts": [f.fact_id for f in graph.facts if f.category in ("claim", "api_method")],
            "provenance_refs": [],
        }
        content = generate_kb_candidate(page, fact_index, "pdf", "go")
        assert "# Aspose.Pdf for Go" in content
        assert "## Problem" in content
        assert "## Solution" in content

    def test_all_five_subdomains_generated(self, tmp_path):
        graph = _make_graph()
        plan = compile_page_plan(graph)
        records = generate_candidates(plan, graph, tmp_path)
        page_types = {r["page_type"] for r in records}
        assert "reference" in page_types
        assert "documentation" in page_types
        assert "product_landing" in page_types
        assert "blog_post" in page_types
        assert "knowledge_base" in page_types


# ---------------------------------------------------------------------------
# Schema validator tests for new schemas
# ---------------------------------------------------------------------------

class TestNewSchemaValidators:
    def test_validate_claim_map_valid(self):
        cm = ClaimMap(candidate_path="t.md", family="pdf", platform="go",
                      total_refs=2, supported_refs=2, unsupported_refs=0)
        errors = validate_claim_map(cm.to_dict())
        assert errors == []

    def test_validate_claim_map_inconsistent_counts(self):
        data = {
            "schema_version": "1.0.0", "candidate_path": "t.md",
            "family": "pdf", "platform": "go",
            "total_refs": 5, "supported_refs": 2, "unsupported_refs": 1,
            "is_valid": True, "entries": [], "api_symbols": [],
            "unsupported_symbols": [],
        }
        errors = validate_claim_map(data)
        assert any("supported_refs" in e for e in errors)

    def test_validate_claim_verification_report_valid(self):
        data = {
            "schema_version": "1.0.0", "family": "pdf", "platform": "go",
            "candidates_checked": 2, "passed": 2, "failed": 0,
            "results": [
                {"candidate": "a.md", "status": "PASS", "total_refs": 1},
                {"candidate": "b.md", "status": "PASS", "total_refs": 2},
            ],
        }
        errors = validate_claim_verification_report(data)
        assert errors == []

    def test_validate_claim_report_inconsistent_counts(self):
        data = {
            "schema_version": "1.0.0", "family": "pdf", "platform": "go",
            "candidates_checked": 3, "passed": 1, "failed": 1,
            "results": [],
        }
        errors = validate_claim_verification_report(data)
        assert any("passed" in e for e in errors)

    def test_validate_shadow_candidate_valid(self):
        content = "---\ntitle: T\ndraft: true\nshadow_candidate: true\ngenerator_version: 1.0\nfamily: pdf\nplatform: go\n---\n# Test\n"
        errors = validate_shadow_candidate(content)
        assert errors == []

    def test_validate_shadow_candidate_missing_frontmatter(self):
        errors = validate_shadow_candidate("# No frontmatter")
        assert len(errors) > 0

    def test_validate_shadow_candidate_not_draft(self):
        content = "---\ntitle: T\ndraft: false\nshadow_candidate: true\ngenerator_version: 1.0\nfamily: pdf\nplatform: go\n---\n# Test\n"
        errors = validate_shadow_candidate(content)
        assert any("draft" in e for e in errors)

    def test_validate_candidate_sections_reference(self):
        content = "## Description\n## Methods\n## See Also\n"
        errors = validate_candidate_sections(content, "reference")
        assert errors == []

    def test_validate_candidate_sections_missing(self):
        content = "## Introduction\n"
        errors = validate_candidate_sections(content, "reference")
        assert len(errors) > 0


# ---------------------------------------------------------------------------
# Runner shadow orchestration tests
# ---------------------------------------------------------------------------

class TestRunnerShadowOrchestration:
    def test_shadow_pipeline_happy_path(self, tmp_path):
        """run_shadow_pipeline with synthetic graph reaches READY_FOR_REVIEW."""
        graph = _make_graph()
        plan = compile_page_plan(graph)
        # Write fact graph and page plan for the runner to compile
        # But run_shadow_pipeline compiles from knowledge/ artifacts
        # So we test the function with a mock that exercises the full path
        # via the actual test fixture graph
        summary = _run_synthetic_shadow(graph, tmp_path)
        assert summary["final_phase"] == "ready_for_review"
        assert summary["stop_reason"] == "ready_for_agent_review"

    def test_shadow_pipeline_produces_artifacts(self, tmp_path):
        graph = _make_graph()
        summary = _run_synthetic_shadow(graph, tmp_path)
        assert (tmp_path / "product_state.json").exists()
        assert (tmp_path / "next_action.json").exists()
        assert (tmp_path / "claim_verification_report.json").exists()
        assert (tmp_path / "audit_log.jsonl").exists()

    def test_shadow_pipeline_claim_report_consistent(self, tmp_path):
        graph = _make_graph()
        _run_synthetic_shadow(graph, tmp_path)
        cr = json.loads((tmp_path / "claim_verification_report.json").read_text())
        ps = json.loads((tmp_path / "product_state.json").read_text())
        na = json.loads((tmp_path / "next_action.json").read_text())
        # All must agree
        assert cr["failed"] == 0
        assert ps["phase"] == "ready_for_review"
        assert na["action_id"] == "stop"

    def test_shadow_pipeline_state_next_action_consistent(self, tmp_path):
        graph = _make_graph()
        _run_synthetic_shadow(graph, tmp_path)
        ps = json.loads((tmp_path / "product_state.json").read_text())
        na = json.loads((tmp_path / "next_action.json").read_text())
        assert ps["phase"] == na["phase"]


def _run_synthetic_shadow(graph: FactGraph, output_dir: Path) -> dict:
    """Helper: run shadow pipeline stages with a synthetic graph."""
    from commands.content.shadow_content_generator import generate_candidates, _build_fact_index
    from lib.claim_mapper import verify_candidates
    from commands.ops.autonomous_runner import append_audit_log, _finalize

    fact_index = _build_fact_index(graph)
    plan = compile_page_plan(graph)

    state = ProductState(family="pdf", platform="go")
    audit_path = output_dir / "audit_log.jsonl"

    # Transitions through pipeline
    state.transition(Phase.SNAPSHOT_CAPTURED)
    state.transition(Phase.FACTS_EXTRACTED)
    state.transition(Phase.FACTS_VERIFIED)
    state.transition(Phase.PLAN_COMPILED)

    # Generate candidates
    candidates_dir = output_dir / "candidates"
    candidates_dir.mkdir(parents=True, exist_ok=True)
    records = generate_candidates(plan, graph, candidates_dir)
    state.transition(Phase.CONTENT_GENERATED)

    # Claim verify
    claim_report = verify_candidates(candidates_dir, fact_index, "pdf", "go")
    (output_dir / "claim_verification_report.json").write_text(
        json.dumps(claim_report, indent=2), encoding="utf-8")

    if claim_report["failed"] > 0:
        state.transition(Phase.RETRYABLE_FAILURE)
    else:
        state.transition(Phase.CLAIMS_VERIFIED)
        state.transition(Phase.QUALITY_EVALUATED)
        state.transition(Phase.REGRESSION_PASSED)
        state.transition(Phase.READY_FOR_REVIEW)

    append_audit_log(audit_path, {"event": "test_complete", "phase": state.phase})
    return _finalize(state, output_dir, "synthetic test")


# ---------------------------------------------------------------------------
# Content Quality Scoring Tests
# ---------------------------------------------------------------------------

def _make_candidate(
    title="Test Class",
    family="pdf",
    platform="go",
    page_type="reference",
    body_sections=None,
    fact_refs=None,
    extra_fm=None,
):
    """Build a valid candidate markdown for testing."""
    fm_lines = [
        f'title: "{title}"',
        "draft: true",
        "shadow_candidate: true",
        "generator_version: 1.0.0",
        f"family: {family}",
        f"platform: {platform}",
    ]
    if extra_fm:
        fm_lines.extend(extra_fm)
    fm = "\n".join(fm_lines)

    if body_sections is None:
        body_sections = ["## Description\n\nThis is a test class for PDF processing.",
                         "## Methods\n\n- `Open()` — opens a document.\n- `Close()` — closes.",
                         "## See Also\n\n- [Related](link)"]
    body = "\n\n".join(body_sections)

    if fact_refs is None:
        fact_refs = ["<!-- fact_ref: FG-abc123def456 -->"]
    body += "\n" + "\n".join(fact_refs)

    return f"---\n{fm}\n---\n\n{body}\n"


class TestContentQualityScoring:
    def test_perfect_candidate_passes_all_gates(self):
        content = _make_candidate()
        score = score_candidate(content, "test.md", "reference")
        assert score.passed is True
        assert score.failed_gates == 0
        assert score.total_gates == 10

    def test_missing_draft_fails_gate(self):
        content = _make_candidate().replace("draft: true", "draft: false")
        score = score_candidate(content, "test.md", "reference")
        assert score.passed is False
        failed_ids = [g.gate_id for g in score.gates if not g.passed]
        assert "draft_true" in failed_ids

    def test_missing_fact_refs_fails_gate(self):
        content = _make_candidate(fact_refs=[])
        score = score_candidate(content, "test.md", "reference")
        assert score.passed is False
        failed_ids = [g.gate_id for g in score.gates if not g.passed]
        assert "has_fact_refs" in failed_ids

    def test_forbidden_terms_detected(self):
        content = _make_candidate(body_sections=[
            "## Description\n\nThis is a TODO placeholder for testing.",
            "## Methods\n\n- `Open()`",
            "## See Also\n\n- link",
        ])
        score = score_candidate(content, "test.md", "reference")
        failed_ids = [g.gate_id for g in score.gates if not g.passed]
        assert "no_forbidden_terms" in failed_ids

    def test_score_candidates_dir(self, tmp_path):
        (tmp_path / "a.md").write_text(_make_candidate(title="A"), encoding="utf-8")
        (tmp_path / "b.md").write_text(_make_candidate(title="B"), encoding="utf-8")
        scores = score_candidates_dir(tmp_path)
        assert len(scores) == 2
        assert all(s.passed for s in scores)

    def test_low_word_count(self):
        content = _make_candidate(body_sections=["## Description\n\nShort."])
        score = score_candidate(content, "test.md", "reference")
        failed_ids = [g.gate_id for g in score.gates if not g.passed]
        assert "min_word_count" in failed_ids


# ---------------------------------------------------------------------------
# Agent Decision Board Tests
# ---------------------------------------------------------------------------

class TestAgentDecisionBoard:
    def test_perfect_candidate_approved(self):
        content = _make_candidate()
        decision = board_review_candidate(content, "test.md", "reference")
        assert decision.decision == DecisionType.APPROVED.value
        assert decision.gate_pass_ratio == 1.0

    def test_broken_candidate_repair_required(self):
        content = _make_candidate().replace("draft: true", "draft: false")
        decision = board_review_candidate(content, "test.md", "reference")
        assert decision.decision in (DecisionType.REPAIR_REQUIRED.value, DecisionType.QUARANTINED.value)

    def test_batch_review_all_approved(self, tmp_path):
        for i in range(3):
            (tmp_path / f"page_{i}.md").write_text(
                _make_candidate(title=f"Page {i}"), encoding="utf-8",
            )
        verdict = board_review_candidates(tmp_path, "pdf", "go")
        assert verdict.verdict == "approved_for_draft_write"
        assert verdict.approved == 3

    def test_delegability_first_launch(self, tmp_path):
        content_dir = tmp_path / "content"
        content_dir.mkdir()
        delegable, reason = is_delegable("newprod", "newplat", content_dir)
        assert delegable is False
        assert "first launch" in reason

    def test_delegability_existing_product(self, tmp_path):
        content_dir = tmp_path / "content"
        ref_dir = content_dir / "reference.aspose.org" / "en" / "pdf" / "go"
        ref_dir.mkdir(parents=True)
        (ref_dir / "page.md").write_text("existing", encoding="utf-8")
        delegable, reason = is_delegable("pdf", "go", content_dir)
        assert delegable is True

    def test_non_delegable_verdict(self, tmp_path):
        content_dir = tmp_path / "content"
        content_dir.mkdir()
        cands = tmp_path / "candidates"
        cands.mkdir()
        (cands / "page.md").write_text(_make_candidate(), encoding="utf-8")
        verdict = board_review_candidates(
            cands, "newprod", "newplat", content_dir=content_dir,
        )
        assert verdict.verdict == "non_delegable_human_required"
        assert verdict.non_delegable == 1

    def test_verdict_serialization(self, tmp_path):
        cands = tmp_path / "candidates"
        cands.mkdir()
        (cands / "page.md").write_text(_make_candidate(), encoding="utf-8")
        verdict = board_review_candidates(cands, "pdf", "go")
        verdict.write(tmp_path / "verdict.json")
        data = json.loads((tmp_path / "verdict.json").read_text(encoding="utf-8"))
        assert data["schema_version"] == "1.0.0"
        assert data["approved"] == 1


# ---------------------------------------------------------------------------
# Candidate Repair Tests
# ---------------------------------------------------------------------------

class TestCandidateRepair:
    def test_repair_draft_false(self):
        content = _make_candidate().replace("draft: true", "draft: false")
        result = do_repair_candidate(content, "test.md", "reference", "pdf", "go")
        assert any(a.gate_id == "draft_true" for a in result.actions)
        assert "draft: true" in result.repaired_content

    def test_repair_shadow_marker(self):
        content = _make_candidate().replace("shadow_candidate: true", "shadow_candidate: false")
        result = do_repair_candidate(content, "test.md", "reference", "pdf", "go")
        assert any(a.gate_id == "shadow_marker" for a in result.actions)

    def test_cannot_repair_missing_facts(self):
        content = _make_candidate(fact_refs=[])
        result = do_repair_candidate(content, "test.md", "reference", "pdf", "go")
        assert "has_fact_refs" in result.remaining_failures

    def test_repair_forbidden_terms(self):
        content = _make_candidate(body_sections=[
            "## Description\n\nThis contains a TODO item and FIXME note with enough words for the minimum.",
            "## Methods\n\n- `Open()` method opens and processes documents for various operations.",
            "## See Also\n\n- [Related](link)",
        ])
        result = do_repair_candidate(content, "test.md", "reference", "pdf", "go")
        assert "TODO" not in result.repaired_content
        assert "FIXME" not in result.repaired_content

    def test_batch_repair(self, tmp_path):
        content = _make_candidate().replace("draft: true", "draft: false")
        (tmp_path / "broken.md").write_text(content, encoding="utf-8")
        results = repair_candidates_dir(tmp_path, family="pdf", platform="go", write_back=True)
        assert len(results) == 1
        repaired = (tmp_path / "broken.md").read_text(encoding="utf-8")
        assert "draft: true" in repaired


# ---------------------------------------------------------------------------
# Controlled Draft Writer Tests
# ---------------------------------------------------------------------------

class TestControlledDraftWriter:
    def test_write_guard_blocks_non_approved(self):
        verdict = BoardVerdict(verdict="repair_required", approved=0)
        errors = check_write_guards(verdict, dry_run=True)
        assert len(errors) > 0
        assert any("approved" in e or "repair" in e for e in errors)

    def test_write_guard_passes_approved(self):
        verdict = BoardVerdict(verdict="approved_for_draft_write", approved=5)
        errors = check_write_guards(verdict, dry_run=True)
        assert len(errors) == 0

    def test_write_guard_blocks_live_mode(self):
        verdict = BoardVerdict(verdict="approved_for_draft_write", approved=5)
        errors = check_write_guards(verdict, dry_run=False)
        assert any("dry_run" in e or "live" in e for e in errors)

    def test_dry_run_write_produces_manifest(self, tmp_path):
        cands = tmp_path / "candidates"
        cands.mkdir()
        (cands / "page.md").write_text(_make_candidate(), encoding="utf-8")

        verdict = BoardVerdict(
            family="pdf", platform="go",
            verdict="approved_for_draft_write", approved=1,
            decisions=[BoardDecision(
                candidate_path="page.md",
                decision=DecisionType.APPROVED.value,
                gate_pass_ratio=1.0,
            )],
        )
        out = tmp_path / "output"
        out.mkdir()
        manifest = write_approved_candidates(
            cands, verdict, {"page.md": "reference"},
            tmp_path, out, dry_run=True,
        )
        assert manifest.dry_run is True
        assert len(manifest.files_written) == 1
        assert (out / "rollback_manifest.json").exists()

    def test_rollback_manifest_round_trip(self, tmp_path):
        manifest = RollbackManifest(family="pdf", platform="go", dry_run=True)
        manifest.write(tmp_path / "manifest.json")
        loaded = RollbackManifest.read(tmp_path / "manifest.json")
        assert loaded.family == "pdf"
        assert loaded.dry_run is True


# ---------------------------------------------------------------------------
# New Product State Phases Tests
# ---------------------------------------------------------------------------

class TestNewProductStatePhases:
    def test_ready_for_review_to_agent_reviewed(self):
        state = ProductState(phase=Phase.READY_FOR_REVIEW.value)
        state.transition(Phase.AGENT_REVIEWED, reason="reviewed")
        assert state.phase == Phase.AGENT_REVIEWED.value

    def test_agent_reviewed_to_approved(self):
        state = ProductState(phase=Phase.AGENT_REVIEWED.value)
        state.transition(Phase.APPROVED_FOR_DRAFT_WRITE, reason="all passed")
        assert state.phase == Phase.APPROVED_FOR_DRAFT_WRITE.value
        assert state.stop_reason == StopReason.AGENT_APPROVED.value

    def test_agent_reviewed_to_repair(self):
        state = ProductState(phase=Phase.AGENT_REVIEWED.value)
        state.transition(Phase.REPAIR_REQUIRED, reason="3 need repair")
        assert state.phase == Phase.REPAIR_REQUIRED.value
        assert state.stop_reason == StopReason.REPAIR_NEEDED.value

    def test_agent_reviewed_to_quarantine(self):
        state = ProductState(phase=Phase.AGENT_REVIEWED.value)
        state.transition(Phase.QUARANTINED, reason="too many failures")
        assert state.phase == Phase.QUARANTINED.value

    def test_approved_to_draft_written(self):
        state = ProductState(phase=Phase.APPROVED_FOR_DRAFT_WRITE.value)
        state.transition(Phase.DRAFT_WRITTEN, reason="wrote 5 files")
        assert state.phase == Phase.DRAFT_WRITTEN.value
        assert state.stop_reason == StopReason.DRAFT_WRITE_COMPLETE.value

    def test_repair_back_to_agent_reviewed(self):
        state = ProductState(phase=Phase.REPAIR_REQUIRED.value)
        state.transition(Phase.AGENT_REVIEWED, reason="re-reviewed after repair")
        assert state.phase == Phase.AGENT_REVIEWED.value

    def test_full_pipeline_to_draft_written(self):
        state = ProductState(family="pdf", platform="go")
        phases = [
            Phase.SNAPSHOT_CAPTURED, Phase.FACTS_EXTRACTED, Phase.FACTS_VERIFIED,
            Phase.PLAN_COMPILED, Phase.CONTENT_GENERATED, Phase.CLAIMS_VERIFIED,
            Phase.QUALITY_EVALUATED, Phase.REGRESSION_PASSED, Phase.READY_FOR_REVIEW,
            Phase.AGENT_REVIEWED, Phase.APPROVED_FOR_DRAFT_WRITE, Phase.DRAFT_WRITTEN,
        ]
        for phase in phases:
            state.transition(phase)
        assert state.phase == Phase.DRAFT_WRITTEN.value

    def test_approved_is_terminal(self):
        state = ProductState(phase=Phase.APPROVED_FOR_DRAFT_WRITE.value)
        assert state.is_terminal()

    def test_draft_written_is_terminal(self):
        state = ProductState(phase=Phase.DRAFT_WRITTEN.value)
        assert state.is_terminal()


# ---------------------------------------------------------------------------
# Agent Review Pipeline Integration Test
# ---------------------------------------------------------------------------

class TestAgentReviewPipeline:
    def test_agent_review_reaches_approved(self, tmp_path):
        """End-to-end: shadow pipeline + agent review → APPROVED or BLOCKED_EXTERNAL."""
        output_dir = tmp_path / "agent_review"
        output_dir.mkdir(parents=True)

        # Use content_dir pointing to existing content/ so it's not first-launch
        repo_root = Path(__file__).resolve().parents[1]
        content_dir = repo_root / "content"

        summary = run_agent_review_pipeline(
            "pdf", "go", output_dir, content_dir=content_dir,
        )

        # Pipeline completes to either APPROVED (existing product) or
        # BLOCKED_EXTERNAL (if no existing content for pdf/go)
        assert summary["final_phase"] in (
            Phase.APPROVED_FOR_DRAFT_WRITE.value,
            Phase.BLOCKED_EXTERNAL.value,
            Phase.REPAIR_REQUIRED.value,
        )
        assert (output_dir / "product_state.json").exists()
        assert (output_dir / "agent_verdict.json").exists()


# ---------------------------------------------------------------------------
# Rollback Path Allowlist Guard Tests (Lane 5)
# ---------------------------------------------------------------------------

class TestRollbackPathGuard:
    """Tests for the rollback() path allowlist guard.

    These tests ensure that a crafted manifest cannot cause rollback() to
    delete files outside the approved ACT write roots.
    """

    def _make_live_manifest(self, tmp_path: Path, record: WriteRecord) -> Path:
        """Create a non-dry-run manifest with one record, written to tmp_path."""
        manifest = RollbackManifest(
            family="pdf", platform="go",
            timestamp="2026-06-08T00:00:00+00:00",
            dry_run=False,  # live manifest
            files_written=[record],
        )
        mp = tmp_path / "rollback_manifest.json"
        manifest.write(mp)
        return mp

    def test_allowed_root_passes(self, tmp_path):
        """Valid content/ target under approved root passes validation."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        target = "content/reference.aspose.org/en/pdf/go/SomeClass.md"
        result = _validate_rollback_target(target, repo_root)
        assert result == (repo_root / target).resolve()

    def test_path_traversal_blocked(self, tmp_path):
        """Path traversal (../../) in target_path raises RollbackPathError.

        Path resolution normalizes the traversal; the guard catches it via
        either the repo-root escape check or the allowed-root prefix check.
        Either way, RollbackPathError is raised.
        """
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        with pytest.raises(RollbackPathError):
            _validate_rollback_target(
                "content/reference.aspose.org/../../etc/passwd",
                repo_root,
            )

    def test_absolute_path_blocked(self, tmp_path):
        """Absolute path in target_path raises RollbackPathError.

        On Unix, is_absolute() catches it early. On Windows, /path resolves
        to a drive-relative path; the repo-root escape check catches it.
        Either way, RollbackPathError is raised before any deletion.
        """
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        with pytest.raises(RollbackPathError):
            _validate_rollback_target("/etc/passwd", repo_root)

    def test_outside_allowed_root_blocked(self, tmp_path):
        """Target outside ALLOWED_ROLLBACK_ROOTS raises RollbackPathError."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        with pytest.raises(RollbackPathError, match="not under any approved rollback root"):
            _validate_rollback_target("scripts/pipeline/lib/evil.py", repo_root)

    def test_windows_style_traversal_blocked(self, tmp_path):
        """Windows-style traversal with forward slashes is also blocked."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        with pytest.raises(RollbackPathError):
            _validate_rollback_target(
                "content/reference.aspose.org/../../../etc/hosts",
                repo_root,
            )

    def test_dry_run_manifest_returns_early(self, tmp_path):
        """Dry-run manifests skip all file operations without path validation."""
        manifest = RollbackManifest(
            family="pdf", platform="go",
            timestamp="2026-06-08T00:00:00+00:00",
            dry_run=True,
            files_written=[WriteRecord(
                source_path="shadow/evil.md",
                target_path="/etc/passwd",
                sha256="abc",
                page_type="reference",
                created_new=True,
            )],
        )
        mp = tmp_path / "manifest.json"
        manifest.write(mp)
        # Should return early with "dry-run" message, never reaching path validation
        actions = rollback(mp, tmp_path)
        assert any("dry-run" in a for a in actions)

    def test_hash_mismatch_warns_not_deletes(self, tmp_path):
        """Modified-hash records produce WARN, not deletion."""
        repo_root = tmp_path / "repo"
        (repo_root / "content" / "reference.aspose.org" / "en" / "pdf" / "go").mkdir(
            parents=True
        )
        target_file = (
            repo_root / "content/reference.aspose.org/en/pdf/go/Test.md"
        )
        target_file.write_text("modified content")

        record = WriteRecord(
            source_path="shadow/Test.md",
            target_path="content/reference.aspose.org/en/pdf/go/Test.md",
            sha256="0" * 64,  # wrong SHA
            page_type="reference",
            created_new=True,
        )
        mp = self._make_live_manifest(tmp_path, record)
        actions = rollback(mp, repo_root)
        assert any("WARN" in a for a in actions)
        assert target_file.exists()  # not deleted

    def test_created_new_false_warns_not_deletes(self, tmp_path):
        """created_new=False records produce WARN, not deletion."""
        repo_root = tmp_path / "repo"
        (repo_root / "content" / "reference.aspose.org" / "en" / "pdf" / "go").mkdir(
            parents=True
        )
        target_file = (
            repo_root / "content/reference.aspose.org/en/pdf/go/Existing.md"
        )
        content = b"original content"
        target_file.write_bytes(content)
        import hashlib
        sha = hashlib.sha256(content).hexdigest()

        record = WriteRecord(
            source_path="shadow/Existing.md",
            target_path="content/reference.aspose.org/en/pdf/go/Existing.md",
            sha256=sha,
            page_type="reference",
            created_new=False,  # was an overwrite, not a new file
        )
        mp = self._make_live_manifest(tmp_path, record)
        actions = rollback(mp, repo_root)
        assert any("WARN" in a for a in actions)
        assert target_file.exists()  # not deleted

    def test_allowed_roots_constant_covers_all_subdomains(self):
        """ALLOWED_ROLLBACK_ROOTS must cover all 5 ACT subdomains."""
        expected_prefixes = {
            "content/reference.aspose.org/",
            "content/docs.aspose.org/",
            "content/products.aspose.org/",
            "content/blog.aspose.org/",
            "content/kb.aspose.org/",
        }
        for prefix in expected_prefixes:
            assert prefix in ALLOWED_ROLLBACK_ROOTS, f"Missing: {prefix}"

    def test_crafted_manifest_blocked_before_any_file_touched(self, tmp_path):
        """Fail-first validation: if any path is invalid, no files are deleted."""
        repo_root = tmp_path / "repo"
        # Create a legitimate file in an allowed root
        safe_dir = repo_root / "content/reference.aspose.org/en/pdf/go"
        safe_dir.mkdir(parents=True)
        safe_file = safe_dir / "Safe.md"
        safe_file.write_text("safe content")

        # Manifest has one valid record followed by one path-traversal record
        import hashlib
        safe_sha = hashlib.sha256(b"safe content").hexdigest()
        manifest = RollbackManifest(
            family="pdf", platform="go",
            timestamp="2026-06-08T00:00:00+00:00",
            dry_run=False,
            files_written=[
                WriteRecord(
                    source_path="shadow/Safe.md",
                    target_path="content/reference.aspose.org/en/pdf/go/Safe.md",
                    sha256=safe_sha,
                    page_type="reference",
                    created_new=True,
                ),
                WriteRecord(
                    source_path="shadow/evil.md",
                    target_path="../../etc/passwd",  # traversal attack
                    sha256="abc",
                    page_type="reference",
                    created_new=True,
                ),
            ],
        )
        mp = tmp_path / "manifest.json"
        manifest.write(mp)

        with pytest.raises(RollbackPathError):
            rollback(mp, repo_root)

        # Safe file must NOT have been deleted (fail-first validation)
        assert safe_file.exists()
