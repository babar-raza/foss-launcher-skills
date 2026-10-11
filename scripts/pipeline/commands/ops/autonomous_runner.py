"""autonomous_runner.py — Dry-run autonomous pipeline runner.

Reads product state (or infers from artifacts), determines next action,
and emits a next_action.json + audit_log.jsonl. NEVER dispatches content
writes or publishes without explicit dry_run=False.

Supports modes:
  --mode single         (default) Emit next action only.
  --mode shadow         Run full shadow pipeline through READY_FOR_REVIEW.
  --mode agent-review   Run shadow pipeline + Agent Decision Board review.
  --mode draft-write-dry-run  Full pipeline including dry-run content/ write.

Usage:
    python scripts/pipeline/commands/ops/autonomous_runner.py \\
        --dry-run --family {f} --platform {p} --output-dir PATH \\
        [--mode shadow|agent-review|draft-write-dry-run] [--max-steps 20]

The --dry-run flag is MANDATORY. The runner will refuse to start without it.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# --- Pipeline bootstrap ---
_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

from lib.product_state import Phase, ProductState, StopReason, infer_phase

RUNNER_SCHEMA_VERSION = "2.0.0"

# Phase -> next command mapping
PHASE_ACTIONS: dict[str, dict[str, str]] = {
    Phase.DISCOVERED.value: {
        "action_id": "scout",
        "command": "repo-scout {family} {platform}",
        "description": "Extract facts from FOSS repository",
    },
    Phase.SOURCE_CHANGED.value: {
        "action_id": "re-scout",
        "command": "repo-scout {family} {platform}",
        "description": "Re-extract facts after source change",
    },
    Phase.SNAPSHOT_CAPTURED.value: {
        "action_id": "extract-facts",
        "command": "knowledge-enrich {family} {platform}",
        "description": "Enrich scout artifacts with LLM claims",
    },
    Phase.FACTS_EXTRACTED.value: {
        "action_id": "verify-facts",
        "command": "truth-merge {family} {platform}",
        "description": "Merge and verify extracted facts",
    },
    Phase.FACTS_VERIFIED.value: {
        "action_id": "compile-plan",
        "command": "page-plan {family} {platform}",
        "description": "Compile deterministic page plan",
    },
    Phase.PLAN_COMPILED.value: {
        "action_id": "generate-content",
        "command": "page-draft {family} {platform}",
        "description": "Generate content from page plan",
    },
    Phase.CONTENT_GENERATED.value: {
        "action_id": "verify-claims",
        "command": "content-check {family} {platform}",
        "description": "Verify claims in generated content",
    },
    Phase.CLAIMS_VERIFIED.value: {
        "action_id": "evaluate-quality",
        "command": "content-eval {family} {platform}",
        "description": "Evaluate content quality",
    },
    Phase.QUALITY_EVALUATED.value: {
        "action_id": "run-regression",
        "command": "link-validate {family} {platform}",
        "description": "Run regression checks",
    },
    Phase.REGRESSION_PASSED.value: {
        "action_id": "request-review",
        "command": "publish-readiness-review {family} {platform}",
        "description": "Request human review",
    },
}

STOP_ACTIONS: dict[str, str] = {
    Phase.READY_FOR_REVIEW.value: "Ready for agent review",
    Phase.AGENT_REVIEWED.value: "Agent review complete",
    Phase.APPROVED_FOR_DRAFT_WRITE.value: "Approved for draft write",
    Phase.REPAIR_REQUIRED.value: "Candidates need repair",
    Phase.DRAFT_WRITTEN.value: "Draft content written",
    Phase.BLOCKED_EXTERNAL.value: "Blocked on external approval",
    Phase.QUARANTINED.value: "Quarantined — manual intervention required",
    Phase.RETRYABLE_FAILURE.value: "Retrying previous stage",
}


def determine_next_action(
    state: ProductState,
) -> dict:
    """Determine the next action for a product based on its state."""
    phase = state.phase

    if phase in STOP_ACTIONS:
        return {
            "schema_version": RUNNER_SCHEMA_VERSION,
            "action_id": "stop",
            "family": state.family,
            "platform": state.platform,
            "phase": phase,
            "stop_reason": state.stop_reason,
            "description": STOP_ACTIONS[phase],
            "command": None,
            "dry_run": True,
        }

    action_template = PHASE_ACTIONS.get(phase)
    if not action_template:
        return {
            "schema_version": RUNNER_SCHEMA_VERSION,
            "action_id": "unknown",
            "family": state.family,
            "platform": state.platform,
            "phase": phase,
            "stop_reason": "unknown_phase",
            "description": f"No action defined for phase: {phase}",
            "command": None,
            "dry_run": True,
        }

    return {
        "schema_version": RUNNER_SCHEMA_VERSION,
        "action_id": action_template["action_id"],
        "family": state.family,
        "platform": state.platform,
        "phase": phase,
        "stop_reason": state.stop_reason,
        "description": action_template["description"],
        "command": action_template["command"].format(
            family=state.family, platform=state.platform,
        ),
        "dry_run": True,
    }


def append_audit_log(log_path: Path, entry: dict) -> None:
    """Append a JSON line to the audit log."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry["timestamp"] = datetime.now(timezone.utc).isoformat()
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def run_shadow_pipeline(
    family: str,
    platform: str,
    output_dir: Path,
    max_steps: int = 20,
) -> dict:
    """Run the full shadow pipeline for a product.

    Executes: fact graph -> page plan -> shadow generation -> claim verify ->
    quality validate -> state transitions.

    Returns a summary dict with final state, metrics, and audit trail.
    """
    from lib.fact_graph import compile_fact_graph
    from commands.content.page_plan_compiler import compile_page_plan
    from commands.content.shadow_content_generator import (
        generate_candidates, _build_fact_index, _is_forbidden_output,
    )
    from lib.claim_mapper import verify_candidates, validate_page_plan_fact_refs
    from lib.schema_validators import (
        validate_shadow_candidate, validate_candidate_sections,
        validate_claim_verification_report,
    )

    audit_path = output_dir / "audit_log.jsonl"
    state = ProductState(family=family, platform=platform)
    step = 0

    def log(event: str, **kwargs):
        append_audit_log(audit_path, {
            "event": event, "family": family, "platform": platform,
            "phase": state.phase, "step": step, **kwargs,
        })

    def fail(reason: str) -> dict:
        state.transition(Phase.RETRYABLE_FAILURE, reason=reason)
        log("retryable_failure", reason=reason)
        return _finalize(state, output_dir, reason)

    # Step 1: Compile fact graph
    step += 1
    log("step_start", action="compile_fact_graph")
    try:
        graph = compile_fact_graph(family, platform)
    except Exception as e:
        return fail(f"fact_graph compilation failed: {e}")
    state.transition(Phase.SNAPSHOT_CAPTURED, reason="source snapshot from clone cache")
    state.transition(Phase.FACTS_EXTRACTED, reason=f"extracted {len(graph.facts)} facts")
    state.transition(Phase.FACTS_VERIFIED, reason="facts verified via compilation")
    log("step_complete", action="compile_fact_graph", fact_count=len(graph.facts))

    # Save fact graph
    fg_path = output_dir / "fact_graph.json"
    graph.write(fg_path)

    # Step 2: Compile page plan
    step += 1
    log("step_start", action="compile_page_plan")
    plan = compile_page_plan(graph)
    state.transition(Phase.PLAN_COMPILED, reason=f"planned {plan['total_page_count']} pages")
    log("step_complete", action="compile_page_plan", page_count=plan["total_page_count"])

    # Save page plan
    plan_path = output_dir / "page_plan.json"
    plan_path.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")

    # Step 2b: Validate page plan fact refs
    step += 1
    log("step_start", action="validate_page_plan_fact_refs")
    fact_index = _build_fact_index(graph)
    plan_errors = validate_page_plan_fact_refs(plan, fact_index)
    if plan_errors:
        return fail(f"page plan has {len(plan_errors)} invalid fact refs")
    log("step_complete", action="validate_page_plan_fact_refs", errors=0)

    # Step 3: Generate shadow candidates
    step += 1
    log("step_start", action="generate_candidates")
    candidates_dir = output_dir / "candidates"
    candidates_dir.mkdir(parents=True, exist_ok=True)
    records = generate_candidates(plan, graph, candidates_dir)
    state.transition(Phase.CONTENT_GENERATED,
                     reason=f"generated {len(records)} candidates")
    log("step_complete", action="generate_candidates", candidate_count=len(records))

    # Step 4: Quality validation on candidates
    step += 1
    log("step_start", action="quality_validation")
    quality_errors = []
    for md_file in sorted(candidates_dir.glob("*.md")):
        content = md_file.read_text(encoding="utf-8")
        errs = validate_shadow_candidate(content)
        if errs:
            quality_errors.extend([f"{md_file.name}: {e}" for e in errs])
    quality_report = {
        "candidates_checked": len(records),
        "candidates_with_errors": len(quality_errors),
        "errors": quality_errors,
    }
    (output_dir / "quality_report.json").write_text(
        json.dumps(quality_report, indent=2), encoding="utf-8")
    log("step_complete", action="quality_validation", errors=len(quality_errors))

    # Step 5: Claim verification
    step += 1
    log("step_start", action="claim_verification")
    claim_report = verify_candidates(candidates_dir, fact_index, family, platform)

    # Validate the report itself
    report_errors = validate_claim_verification_report(claim_report)
    if report_errors:
        return fail(f"claim verification report schema invalid: {report_errors}")

    (output_dir / "claim_verification_report.json").write_text(
        json.dumps(claim_report, indent=2, ensure_ascii=False), encoding="utf-8")

    if claim_report["failed"] > 0:
        state.transition(Phase.CLAIMS_VERIFIED,
                         reason=f"{claim_report['passed']} passed, {claim_report['failed']} failed")
        return fail(f"{claim_report['failed']} candidates failed claim verification")

    state.transition(Phase.CLAIMS_VERIFIED,
                     reason=f"all {claim_report['passed']} candidates passed")
    log("step_complete", action="claim_verification",
        passed=claim_report["passed"], failed=claim_report["failed"])

    # Step 6: Quality evaluation (structural)
    step += 1
    log("step_start", action="quality_evaluation")
    if quality_errors:
        return fail(f"{len(quality_errors)} quality errors found")
    state.transition(Phase.QUALITY_EVALUATED, reason="quality validation passed")
    log("step_complete", action="quality_evaluation")

    # Step 7: Regression check (placeholder — no prior content to regress against)
    step += 1
    log("step_start", action="regression_check")
    state.transition(Phase.REGRESSION_PASSED, reason="no prior content to regress")
    log("step_complete", action="regression_check")

    # Step 8: Ready for review
    step += 1
    state.transition(Phase.READY_FOR_REVIEW)
    log("ready_for_review",
        candidates_generated=len(records),
        claims_passed=claim_report["passed"],
        claims_failed=claim_report["failed"])

    return _finalize(state, output_dir, "all gates passed")


def run_agent_review_pipeline(
    family: str,
    platform: str,
    output_dir: Path,
    max_steps: int = 20,
    content_dir: Path | None = None,
) -> dict:
    """Run shadow pipeline + Agent Decision Board review.

    Extends run_shadow_pipeline with:
      - Agent Decision Board review of all candidates
      - Candidate repair for REPAIR_REQUIRED candidates
      - Final verdict: APPROVED_FOR_DRAFT_WRITE, REPAIR_REQUIRED, or QUARANTINED
    """
    from lib.agent_decision_board import review_candidates, DecisionType
    from lib.candidate_repair import repair_candidates_dir
    from lib.content_quality import score_candidates_dir

    audit_path = output_dir / "audit_log.jsonl"

    # Step 1: Run shadow pipeline first
    shadow_result = run_shadow_pipeline(family, platform, output_dir, max_steps)

    if shadow_result["final_phase"] != Phase.READY_FOR_REVIEW.value:
        return shadow_result

    # Load state from shadow output
    state = ProductState.read(output_dir / "product_state.json")
    candidates_dir = output_dir / "candidates"

    def log(event: str, **kwargs):
        append_audit_log(audit_path, {
            "event": event, "family": family, "platform": platform,
            "phase": state.phase, **kwargs,
        })

    # Build page_type_map from page plan
    page_plan = json.loads((output_dir / "page_plan.json").read_text(encoding="utf-8"))
    page_type_map: dict[str, str] = {}
    for sd_data in page_plan.get("subdomains", {}).values():
        for page in sd_data.get("pages", []):
            slug = page.get("slug", "")
            safe_name = slug.replace("/", "_").replace("\\", "_").replace(":", "_").replace("<", "_").replace(">", "_").replace("*", "_").replace("?", "_").replace('"', "_").replace("|", "_") + ".md"
            page_type_map[safe_name] = page.get("page_type", "reference")

    # Step 9: Agent Decision Board review
    log("step_start", action="agent_review")
    verdict = review_candidates(
        candidates_dir, family, platform,
        page_type_map=page_type_map,
        content_dir=content_dir,
    )
    state.transition(Phase.AGENT_REVIEWED, reason=f"reviewed {verdict.total_candidates} candidates")

    # Save verdict
    verdict.write(output_dir / "agent_verdict.json")
    log("step_complete", action="agent_review",
        approved=verdict.approved, repair=verdict.repair_required,
        quarantined=verdict.quarantined, non_delegable=verdict.non_delegable)

    # Step 10: Repair if needed
    if verdict.repair_required > 0:
        log("step_start", action="candidate_repair")
        repair_results = repair_candidates_dir(
            candidates_dir, page_type_map, family, platform,
            write_back=True,
        )
        repaired_count = sum(1 for r in repair_results if r.repaired)
        still_broken = sum(1 for r in repair_results if not r.repaired and r.actions)
        log("step_complete", action="candidate_repair",
            repaired=repaired_count, still_broken=still_broken)

        # Re-run agent review after repair
        verdict = review_candidates(
            candidates_dir, family, platform,
            page_type_map=page_type_map,
            content_dir=content_dir,
        )
        verdict.write(output_dir / "agent_verdict_post_repair.json")

    # Determine final state
    if verdict.verdict == "non_delegable_human_required":
        state.transition(Phase.BLOCKED_EXTERNAL, reason="non-delegable decision requires human")
        return _finalize(state, output_dir, "non-delegable — human review required")

    if verdict.verdict == "quarantined":
        state.transition(Phase.QUARANTINED, reason=f"{verdict.quarantined} candidates quarantined")
        return _finalize(state, output_dir, f"{verdict.quarantined} quarantined")

    if verdict.verdict == "repair_required":
        state.transition(Phase.REPAIR_REQUIRED, reason=f"{verdict.repair_required} still need repair")
        return _finalize(state, output_dir, f"{verdict.repair_required} still need repair after auto-fix")

    if verdict.verdict == "approved_for_draft_write":
        state.transition(Phase.APPROVED_FOR_DRAFT_WRITE,
                         reason=f"all {verdict.approved} candidates approved")
        return _finalize(state, output_dir, f"all {verdict.approved} candidates approved for draft write")

    # Mixed or unexpected
    state.transition(Phase.REPAIR_REQUIRED, reason=f"mixed verdict: {verdict.verdict}")
    return _finalize(state, output_dir, f"mixed verdict: {verdict.verdict}")


def run_draft_write_pipeline(
    family: str,
    platform: str,
    output_dir: Path,
    repo_root: Path,
    max_steps: int = 20,
    content_dir: Path | None = None,
    dry_run: bool = True,
) -> dict:
    """Full pipeline: shadow + agent review + controlled draft write.

    Always dry_run=True unless explicitly overridden (and even then,
    the write guard enforces dry_run=True in current version).
    """
    from lib.controlled_draft_writer import write_approved_candidates, WriteGuardError
    from lib.agent_decision_board import BoardVerdict

    # Run agent review pipeline first
    review_result = run_agent_review_pipeline(
        family, platform, output_dir, max_steps, content_dir,
    )

    if review_result["final_phase"] != Phase.APPROVED_FOR_DRAFT_WRITE.value:
        return review_result

    # Load verdict and state
    state = ProductState.read(output_dir / "product_state.json")
    candidates_dir = output_dir / "candidates"

    # Load page_type_map
    page_plan = json.loads((output_dir / "page_plan.json").read_text(encoding="utf-8"))
    page_type_map: dict[str, str] = {}
    for sd_data in page_plan.get("subdomains", {}).values():
        for page in sd_data.get("pages", []):
            slug = page.get("slug", "")
            safe_name = slug.replace("/", "_").replace("\\", "_").replace(":", "_").replace("<", "_").replace(">", "_").replace("*", "_").replace("?", "_").replace('"', "_").replace("|", "_") + ".md"
            page_type_map[safe_name] = page.get("page_type", "reference")

    # Load verdict
    verdict_path = output_dir / "agent_verdict.json"
    if (output_dir / "agent_verdict_post_repair.json").exists():
        verdict_path = output_dir / "agent_verdict_post_repair.json"
    verdict_data = json.loads(verdict_path.read_text(encoding="utf-8"))
    verdict = BoardVerdict(**{
        k: v for k, v in verdict_data.items()
        if k in BoardVerdict.__dataclass_fields__ and k != "decisions"
    })

    # Reconstruct decisions
    from lib.agent_decision_board import BoardDecision
    verdict.decisions = [BoardDecision(**d) for d in verdict_data.get("decisions", [])]

    # Attempt controlled write
    audit_path = output_dir / "audit_log.jsonl"
    try:
        manifest = write_approved_candidates(
            candidates_dir, verdict, page_type_map,
            repo_root, output_dir, dry_run=dry_run,
        )
        append_audit_log(audit_path, {
            "event": "draft_write",
            "family": family, "platform": platform,
            "dry_run": dry_run,
            "files_written": len(manifest.files_written),
        })

        if not dry_run:
            state.transition(Phase.DRAFT_WRITTEN,
                             reason=f"wrote {len(manifest.files_written)} files to content/")
        return _finalize(state, output_dir,
                         f"{'dry-run: would write' if dry_run else 'wrote'} "
                         f"{len(manifest.files_written)} files")

    except WriteGuardError as e:
        append_audit_log(audit_path, {
            "event": "draft_write_blocked",
            "family": family, "platform": platform,
            "error": str(e),
        })
        return _finalize(state, output_dir, f"write blocked: {e}")


def _finalize(state: ProductState, output_dir: Path, reason: str) -> dict:
    """Write final state and next_action, return summary."""
    # Write product state
    state_path = output_dir / "product_state.json"
    state_path.write_text(
        json.dumps(state.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Write next action
    next_action = determine_next_action(state)
    action_path = output_dir / "next_action.json"
    action_path.write_text(
        json.dumps(next_action, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return {
        "family": state.family,
        "platform": state.platform,
        "final_phase": state.phase,
        "stop_reason": state.stop_reason,
        "reason": reason,
        "transitions": len(state.transition_history),
        "is_terminal": state.is_terminal(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Autonomous pipeline runner (dry-run only).",
    )
    parser.add_argument("--dry-run", action="store_true", required=True,
                        help="MANDATORY: Run in dry-run mode (no content writes)")
    parser.add_argument("--family", required=True, help="Product family")
    parser.add_argument("--platform", required=True, help="Platform")
    parser.add_argument("--output-dir", required=True, help="Output directory")
    parser.add_argument("--state-file", help="Path to existing product_state.json (otherwise inferred)")
    parser.add_argument("--mode", choices=["single", "shadow", "agent-review", "draft-write-dry-run"],
                        default="single",
                        help="single: next action; shadow: full shadow; agent-review: +board review; draft-write-dry-run: +dry-run write")
    parser.add_argument("--max-steps", type=int, default=20,
                        help="Max steps for shadow mode (default: 20)")
    args = parser.parse_args(argv)

    if not args.dry_run:
        print("ERROR: --dry-run is mandatory. The runner never executes in live mode.", file=sys.stderr)
        return 1

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.mode == "shadow":
        print(f"Running shadow pipeline for {args.family}/{args.platform}...")
        summary = run_shadow_pipeline(args.family, args.platform, output_dir, args.max_steps)
        print(f"  Final phase: {summary['final_phase']}")
        print(f"  Stop reason: {summary['stop_reason']}")
        print(f"  Transitions: {summary['transitions']}")
        print(f"  Reason: {summary['reason']}")
        return 0 if summary["final_phase"] == Phase.READY_FOR_REVIEW.value else 1

    if args.mode == "agent-review":
        print(f"Running agent review pipeline for {args.family}/{args.platform}...")
        repo_root = Path(__file__).resolve().parents[4]
        content_dir = repo_root / "content"
        summary = run_agent_review_pipeline(
            args.family, args.platform, output_dir, args.max_steps,
            content_dir=content_dir,
        )
        print(f"  Final phase: {summary['final_phase']}")
        print(f"  Stop reason: {summary['stop_reason']}")
        print(f"  Reason: {summary['reason']}")
        return 0 if summary["final_phase"] == Phase.APPROVED_FOR_DRAFT_WRITE.value else 1

    if args.mode == "draft-write-dry-run":
        print(f"Running draft-write-dry-run pipeline for {args.family}/{args.platform}...")
        repo_root = Path(__file__).resolve().parents[4]
        content_dir = repo_root / "content"
        summary = run_draft_write_pipeline(
            args.family, args.platform, output_dir, repo_root,
            args.max_steps, content_dir=content_dir, dry_run=True,
        )
        print(f"  Final phase: {summary['final_phase']}")
        print(f"  Stop reason: {summary['stop_reason']}")
        print(f"  Reason: {summary['reason']}")
        return 0

    # Single mode — original behavior
    if args.state_file:
        state_path = Path(args.state_file)
        if not state_path.exists():
            print(f"ERROR: State file not found: {state_path}", file=sys.stderr)
            return 1
        state = ProductState.read(state_path)
    else:
        phase = infer_phase(args.family, args.platform)
        state = ProductState(
            family=args.family,
            platform=args.platform,
            phase=phase.value,
        )

    # Determine next action
    next_action = determine_next_action(state)

    # Write next_action.json
    action_path = output_dir / "next_action.json"
    action_path.write_text(
        json.dumps(next_action, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Append to audit log
    audit_path = output_dir / "audit_log.jsonl"
    append_audit_log(audit_path, {
        "event": "next_action_determined",
        "family": args.family,
        "platform": args.platform,
        "phase": state.phase,
        "action_id": next_action["action_id"],
        "dry_run": True,
    })

    print(f"Next action: {next_action['action_id']} — {next_action['description']}")
    print(f"  Phase: {state.phase}")
    if next_action.get("command"):
        print(f"  Command: {next_action['command']}")
    print(f"  Written to: {action_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
