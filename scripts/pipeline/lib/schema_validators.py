"""Schema Validators — JSON schema validation for ACT pipeline outputs.

Validates fact graphs, page plans, product states, external signals,
and runner next-action outputs against expected schemas.

Public API:
    validate_fact_graph     — validate a fact graph dict
    validate_page_plan      — validate a page plan dict
    validate_product_state  — validate a product state dict
    validate_external_signals — validate a signal batch dict
    validate_next_action    — validate a next_action dict
    ValidationError         — raised on schema violations
"""
from __future__ import annotations

from typing import Any


class ValidationError(Exception):
    """Raised when a schema validation fails."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(f"{len(errors)} validation error(s): {'; '.join(errors[:5])}")


def _check_required(data: dict, keys: list[str], context: str) -> list[str]:
    errors = []
    for key in keys:
        if key not in data:
            errors.append(f"{context}: missing required key '{key}'")
    return errors


def _check_type(data: dict, key: str, expected_type: type, context: str) -> list[str]:
    if key in data and not isinstance(data[key], expected_type):
        return [f"{context}: '{key}' expected {expected_type.__name__}, got {type(data[key]).__name__}"]
    return []


def validate_fact_graph(data: dict) -> list[str]:
    """Validate a fact graph dict. Returns list of error strings (empty = valid)."""
    errors = []
    errors.extend(_check_required(data, ["schema_version", "family", "platform", "facts"], "fact_graph"))
    errors.extend(_check_type(data, "facts", list, "fact_graph"))
    errors.extend(_check_type(data, "fact_count", int, "fact_graph"))

    if "facts" in data and isinstance(data["facts"], list):
        for i, fact in enumerate(data["facts"]):
            ctx = f"fact_graph.facts[{i}]"
            errors.extend(_check_required(fact, ["fact_id", "fact_type", "category", "family", "platform", "text"], ctx))
            if "fact_id" in fact and not isinstance(fact["fact_id"], str):
                errors.append(f"{ctx}: fact_id must be string")
            if "fact_type" in fact and fact["fact_type"] not in ("source", "inferred", "external", "manual"):
                errors.append(f"{ctx}: invalid fact_type '{fact['fact_type']}'")
            if "verification_status" in fact and fact["verification_status"] not in ("verified", "unverified", "rejected", "stale"):
                errors.append(f"{ctx}: invalid verification_status '{fact['verification_status']}'")
            if "confidence" in fact:
                conf = fact["confidence"]
                if not isinstance(conf, (int, float)) or conf < 0 or conf > 1:
                    errors.append(f"{ctx}: confidence must be 0.0-1.0, got {conf}")

    return errors


def validate_page_plan(data: dict) -> list[str]:
    """Validate a page plan dict."""
    errors = []
    errors.extend(_check_required(data, ["schema_version", "family", "platform", "subdomains", "total_page_count"], "page_plan"))
    errors.extend(_check_type(data, "subdomains", dict, "page_plan"))
    errors.extend(_check_type(data, "total_page_count", int, "page_plan"))

    if "subdomains" in data and isinstance(data["subdomains"], dict):
        for sd_name, sd_data in data["subdomains"].items():
            ctx = f"page_plan.subdomains.{sd_name}"
            errors.extend(_check_required(sd_data, ["page_count", "pages"], ctx))
            if "pages" in sd_data and isinstance(sd_data["pages"], list):
                for i, page in enumerate(sd_data["pages"]):
                    pctx = f"{ctx}.pages[{i}]"
                    errors.extend(_check_required(page, ["page_type", "slug", "title", "required_sections", "required_facts"], pctx))

    return errors


def validate_product_state(data: dict) -> list[str]:
    """Validate a product state dict."""
    errors = []
    errors.extend(_check_required(data, ["schema_version", "family", "platform", "phase", "stop_reason"], "product_state"))

    valid_phases = {
        "discovered", "source_changed", "snapshot_captured", "facts_extracted",
        "facts_verified", "plan_compiled", "content_generated", "claims_verified",
        "quality_evaluated", "regression_passed", "ready_for_review",
        "agent_reviewed", "repair_required", "approved_for_draft_write",
        "draft_written",
        "blocked_external", "retryable_failure", "quarantined",
    }
    if "phase" in data and data["phase"] not in valid_phases:
        errors.append(f"product_state: invalid phase '{data['phase']}'")

    if "retry_count" in data:
        if not isinstance(data["retry_count"], int) or data["retry_count"] < 0:
            errors.append(f"product_state: retry_count must be non-negative int")

    return errors


def validate_external_signals(data: dict) -> list[str]:
    """Validate an external signals batch dict."""
    errors = []
    errors.extend(_check_required(data, ["schema_version", "family", "platform", "source", "signals"], "external_signals"))
    errors.extend(_check_type(data, "signals", list, "external_signals"))

    if "signals" in data and isinstance(data["signals"], list):
        for i, sig in enumerate(data["signals"]):
            ctx = f"external_signals.signals[{i}]"
            errors.extend(_check_required(sig, ["signal_type", "text", "source", "advisory"], ctx))
            if "advisory" in sig and sig["advisory"] is not True:
                errors.append(f"{ctx}: advisory must be True (got {sig['advisory']})")

    return errors


def validate_next_action(data: dict) -> list[str]:
    """Validate a next_action dict."""
    errors = []
    errors.extend(_check_required(data, ["schema_version", "action_id", "family", "platform", "phase", "dry_run"], "next_action"))

    if "dry_run" in data and data["dry_run"] is not True:
        errors.append("next_action: dry_run must be True")

    return errors


def validate_claim_map(data: dict) -> list[str]:
    """Validate a claim map dict."""
    errors = []
    errors.extend(_check_required(data, ["schema_version", "candidate_path", "family", "platform",
                                          "total_refs", "supported_refs", "unsupported_refs", "is_valid"], "claim_map"))
    errors.extend(_check_type(data, "total_refs", int, "claim_map"))
    errors.extend(_check_type(data, "supported_refs", int, "claim_map"))
    errors.extend(_check_type(data, "unsupported_refs", int, "claim_map"))

    if "entries" in data and isinstance(data["entries"], list):
        for i, entry in enumerate(data["entries"]):
            ctx = f"claim_map.entries[{i}]"
            errors.extend(_check_required(entry, ["fact_id", "found_in_graph"], ctx))

    if "unsupported_symbols" in data and not isinstance(data["unsupported_symbols"], list):
        errors.append("claim_map: unsupported_symbols must be a list")

    # Consistency: supported + unsupported == total
    if all(k in data for k in ("total_refs", "supported_refs", "unsupported_refs")):
        if isinstance(data["total_refs"], int) and isinstance(data["supported_refs"], int) and isinstance(data["unsupported_refs"], int):
            if data["supported_refs"] + data["unsupported_refs"] != data["total_refs"]:
                errors.append(
                    f"claim_map: supported_refs ({data['supported_refs']}) + "
                    f"unsupported_refs ({data['unsupported_refs']}) != "
                    f"total_refs ({data['total_refs']})"
                )

    return errors


def validate_claim_verification_report(data: dict) -> list[str]:
    """Validate a claim verification report dict."""
    errors = []
    errors.extend(_check_required(data, ["schema_version", "family", "platform",
                                          "candidates_checked", "passed", "failed", "results"], "claim_report"))
    errors.extend(_check_type(data, "results", list, "claim_report"))

    if all(k in data for k in ("candidates_checked", "passed", "failed")):
        if isinstance(data["passed"], int) and isinstance(data["failed"], int) and isinstance(data["candidates_checked"], int):
            if data["passed"] + data["failed"] != data["candidates_checked"]:
                errors.append(
                    f"claim_report: passed ({data['passed']}) + failed ({data['failed']}) "
                    f"!= candidates_checked ({data['candidates_checked']})"
                )

    if "results" in data and isinstance(data["results"], list):
        for i, result in enumerate(data["results"]):
            ctx = f"claim_report.results[{i}]"
            errors.extend(_check_required(result, ["candidate", "status", "total_refs"], ctx))
            if "status" in result and result["status"] not in ("PASS", "FAIL"):
                errors.append(f"{ctx}: status must be PASS or FAIL, got '{result['status']}'")

    return errors


def validate_shadow_candidate(content: str) -> list[str]:
    """Validate a shadow candidate markdown string for required structure."""
    errors = []
    if "---" not in content:
        errors.append("candidate: missing frontmatter delimiters")
        return errors

    parts = content.split("---", 2)
    if len(parts) < 3:
        errors.append("candidate: incomplete frontmatter (need opening and closing ---)")
        return errors

    frontmatter = parts[1]
    body = parts[2]

    required_fm_keys = ["title", "draft", "shadow_candidate", "generator_version", "family", "platform"]
    for key in required_fm_keys:
        if f"{key}:" not in frontmatter:
            errors.append(f"candidate: missing frontmatter key '{key}'")

    if "shadow_candidate: true" not in frontmatter:
        errors.append("candidate: shadow_candidate must be true")

    if "draft: true" not in frontmatter:
        errors.append("candidate: draft must be true")

    if not body.strip():
        errors.append("candidate: empty body content")
    elif "# " not in body:
        errors.append("candidate: missing heading in body")

    return errors


REQUIRED_SECTIONS_BY_TYPE: dict[str, list[str]] = {
    # Methods is conditional (only present when the class has public methods),
    # so require only Description for reference pages.
    "reference": ["Description"],
    "documentation": ["Overview"],
    "product_landing": ["Key Features"],
    "blog_post": ["Introduction", "Conclusion"],
    "knowledge_base": ["Problem", "Solution"],
}


def validate_candidate_sections(content: str, page_type: str) -> list[str]:
    """Validate that a candidate has required sections for its page type."""
    errors = []
    required = REQUIRED_SECTIONS_BY_TYPE.get(page_type, [])
    for section in required:
        if f"## {section}" not in content:
            errors.append(f"candidate: missing required section '## {section}' for type {page_type}")
    return errors


def validate_and_raise(data: dict, validator_fn) -> None:
    """Validate data and raise ValidationError if invalid."""
    errors = validator_fn(data)
    if errors:
        raise ValidationError(errors)


# ── Refresh-pipeline schemas (aspose-org-foss-refresh-tidy-lightning §5) ────
#
# These five validators formalize the refresh-run contract records introduced
# by the FOSS Refresh Pipeline Recovery plan (RPR-B-01/02/03). Several checks
# below directly encode confirmed root causes from that plan's forensic audit
# as enforceable invariants, not just type-checking:
#   - a BODY_UPDATED page-coverage decision with an identical before/after
#     body hash is rejected outright (this is the exact PDF-NET-REFRESH-001
#     v26.7.0 bug: a KB page graded A->C from a frontmatter-only evidence
#     change with zero prose diff, yet nothing in the pipeline flagged it);
#   - frontmatter_only=True can never coexist with decision=BODY_UPDATED;
#   - a committed refresh-run manifest requires every validation field to be
#     PASS (never advance the baseline on a partially-failed run).

_BASELINE_LEDGER_SHA_SOURCES = {"scout", "manual-recovery", "orphaned-recovered"}
_BASELINE_LEDGER_STATUSES = {"attempted", "accepted", "superseded", "abandoned"}


def validate_baseline_ledger_entry(data: dict) -> list[str]:
    """Validate one append-only baseline_ledger.jsonl row (plan schema 5a)."""
    errors = []
    errors.extend(_check_required(
        data,
        ["run_id", "family", "platform", "new_repo_sha", "sha_source", "attempt_started_at", "status"],
        "baseline_ledger_entry",
    ))
    if "sha_source" in data and data["sha_source"] not in _BASELINE_LEDGER_SHA_SOURCES:
        errors.append(f"baseline_ledger_entry: invalid sha_source '{data['sha_source']}'")
    if "status" in data and data["status"] not in _BASELINE_LEDGER_STATUSES:
        errors.append(f"baseline_ledger_entry: invalid status '{data['status']}'")
    if data.get("status") == "accepted" and not data.get("accepted_at"):
        errors.append("baseline_ledger_entry: status=accepted requires a non-empty accepted_at")
    if data.get("sha_source") == "orphaned-recovered" and not data.get("orphaned_sha"):
        errors.append("baseline_ledger_entry: sha_source=orphaned-recovered requires a non-empty orphaned_sha")
    return errors


_PRODUCT_CHANGE_TYPES = {
    "API_ADDED", "API_REMOVED", "API_RESURRECTED", "API_MODIFIED",
    "API_SIGNATURE_CHANGED", "API_RENAMED", "FEATURE_ADDED", "FEATURE_REMOVED",
    "FEATURE_CHANGED", "BEHAVIOR_CHANGED", "CLAIM_MODIFIED", "LIMITATION_CHANGED",
}
_UPDATE_STRATEGIES = {
    "SURGICAL_CLAIM_REPLACEMENT", "TABLE_ROW_RECONCILIATION",
    "EXAMPLE_REGENERATION", "SECTION_REMOVAL", "PARAGRAPH_REWRITE",
    "REFERENCE_REGENERATION",
}


def validate_product_change_record(data: dict) -> list[str]:
    """Validate one semantic_changes.json entry, extended per plan schema 5b."""
    errors = []
    errors.extend(_check_required(
        data,
        ["change_id", "change_type", "api_symbol", "baseline_ref", "routed_strategy",
         "classification_confidence", "requires_llm"],
        "product_change_record",
    ))
    if "change_type" in data and data["change_type"] not in _PRODUCT_CHANGE_TYPES:
        errors.append(f"product_change_record: invalid change_type '{data['change_type']}'")
    if "routed_strategy" in data and data["routed_strategy"] not in _UPDATE_STRATEGIES:
        errors.append(f"product_change_record: invalid routed_strategy '{data['routed_strategy']}'")
    if "classification_confidence" in data:
        conf = data["classification_confidence"]
        if not isinstance(conf, (int, float)) or conf < 0 or conf > 1:
            errors.append(f"product_change_record: classification_confidence must be 0.0-1.0, got {conf}")
    if "requires_llm" in data and "routed_strategy" in data:
        expected = data["routed_strategy"] == "PARAGRAPH_REWRITE"
        if data["requires_llm"] != expected:
            errors.append(
                f"product_change_record: requires_llm={data['requires_llm']} is inconsistent with "
                f"routed_strategy={data['routed_strategy']!r} (requires_llm must be True iff "
                f"routed_strategy is PARAGRAPH_REWRITE)"
            )
    return errors


# MUST stay in exact sync with refresh_review.VALID_DECISIONS. The drift-guard
# test `test_page_coverage_decisions_match_refresh_review_source` (RPR-B-02's
# originally-specified enum-match test, added in RPR-D-03 after the integration
# caught EXISTING_IMPACTED_PAGES_UPDATED_VERIFIED missing here) fails if they
# ever diverge. Do not hand-edit one without the other.
_PAGE_COVERAGE_DECISIONS = {
    "BODY_UPDATED", "EVIDENCE_ONLY", "NOT_AFFECTED", "RETIRED", "GENERATED",
    "SEMANTIC_NOOP_PROVEN", "REFRESH_BLOCKED_UNPROVEN_NOOP",
    "CLAIM_EXTRACTION_MISSED_DELTA", "PAGE_MAPPING_MISSED_IMPACT",
    "GENERATED_ONLY_BODY_CHANGE_INSUFFICIENT", "EXISTING_IMPACTED_PAGES_UPDATED_VERIFIED",
    "GRADING_REPAIRED", "GRADING_BLOCKED", "TASKCARD_CREATED",
}
_PAGE_COVERAGE_DECISION_SOURCES = {"pia_per_page_citation", "oracle", "manual", "triage_confirm"}


def validate_page_coverage_ledger_entry(data: dict) -> list[str]:
    """Validate one page_decisions.json entry, extended per plan schema 5c.

    RPR-F-01/RPR-F-04 root-cause guard: a decision of BODY_UPDATED with an
    identical before/after body hash, or with frontmatter_only=True, is
    rejected — this is precisely the PDF-NET-REFRESH-001 v26.7.0 defect
    (34/82 non-reference pages recorded EVIDENCE_ONLY correctly, but nothing
    in the pipeline enforced that a BODY_UPDATED page could never have a
    frontmatter-only diff underneath it).
    """
    errors = []
    errors.extend(_check_required(
        data,
        ["page_id", "decision", "decision_reason", "decision_source",
         "body_diff_hash_before", "body_diff_hash_after", "frontmatter_only", "blocking"],
        "page_coverage_ledger_entry",
    ))
    if "decision" in data and data["decision"] not in _PAGE_COVERAGE_DECISIONS:
        errors.append(f"page_coverage_ledger_entry: invalid decision '{data['decision']}'")
    if "decision_source" in data and data["decision_source"] not in _PAGE_COVERAGE_DECISION_SOURCES:
        errors.append(f"page_coverage_ledger_entry: invalid decision_source '{data['decision_source']}'")
    if data.get("decision") == "BODY_UPDATED":
        if data.get("frontmatter_only") is True:
            errors.append(
                "page_coverage_ledger_entry: decision=BODY_UPDATED is incompatible with frontmatter_only=True"
            )
        before = data.get("body_diff_hash_before")
        after = data.get("body_diff_hash_after")
        if before is not None and after is not None and before == after:
            errors.append(
                "page_coverage_ledger_entry: decision=BODY_UPDATED but body_diff_hash_before == "
                "body_diff_hash_after (frontmatter-only refresh misrecorded as a body update — "
                "see PDF-NET-REFRESH-001 v26.7.0 regression)"
            )
    return errors


_PAGE_PATCH_VERDICTS = {
    "BODY_UPDATED",
    "GENERATED",
    "EVIDENCE_ONLY",
    "REFERENCE_UNCHANGED",
    "REFERENCE_SKIPPED",
    "REFERENCE_BLOCKED",
    "NO_ACTIONABLE_SECTIONS",
    "TARGET_REJECTED_LOCALIZED",
    "TARGET_REJECTED_AMBIGUOUS_LOCALE",
    "BLOCKED_FORBIDDEN_CLAIM",
    "BLOCKED_TEMPLATE_PROPAGATION",
    "SKIPPED_HASH_CHANGED",
    "SKIPPED_AUTO_UPDATABLE_FALSE",
}
# RPR-E-05: why a PARAGRAPH_REWRITE fell back to the deterministic template (if it did).
_FALLBACK_REASONS = {
    "NONE",                          # LLM ran and its output was used
    "LLM_UNAVAILABLE",               # router unconstructible (no import / not configured)
    "LLM_ERROR",                     # exception during call_chat
    "LLM_EMPTY_RESPONSE",            # result.data falsy
    "LINK_PRESERVATION_VIOLATION",   # RG-010 guard rejected the LLM output
    "CIRCUIT_OPEN",                  # run-scoped circuit already open — LLM not attempted
}


def validate_page_patch_receipt(data: dict) -> list[str]:
    """Validate one S-105 body-refresh receipt, extended per plan schema 5d.

    RPR-E-01 observability guard: when strategy_used=PARAGRAPH_REWRITE and
    the receipt claims BODY_UPDATED, exactly one of llm_invoked /
    template_fallback_used must be true — a receipt claiming neither (or
    both) fired means the observability added by RPR-E-01 to distinguish a
    genuine LLM rewrite from the dead-fallback bug's canned template is
    itself broken.
    """
    errors = []
    errors.extend(_check_required(
        data,
        ["receipt_id", "run_id", "page_path", "locale", "change_ids",
         "strategy_used", "old_hash", "new_hash", "verdict"],
        "page_patch_receipt",
    ))
    if "strategy_used" in data and data["strategy_used"] not in _UPDATE_STRATEGIES:
        errors.append(f"page_patch_receipt: invalid strategy_used '{data['strategy_used']}'")
    if "verdict" in data and data["verdict"] not in _PAGE_PATCH_VERDICTS:
        errors.append(f"page_patch_receipt: invalid verdict '{data['verdict']}'")
    if "fallback_reason" in data and data["fallback_reason"] is not None \
            and data["fallback_reason"] not in _FALLBACK_REASONS:
        errors.append(f"page_patch_receipt: invalid fallback_reason '{data['fallback_reason']}'")
    if data.get("strategy_used") == "PARAGRAPH_REWRITE" and data.get("verdict") == "BODY_UPDATED":
        llm_invoked = data.get("llm_invoked")
        template_used = data.get("template_fallback_used")
        if llm_invoked is None or template_used is None:
            errors.append(
                "page_patch_receipt: strategy_used=PARAGRAPH_REWRITE with verdict=BODY_UPDATED requires "
                "both llm_invoked and template_fallback_used to be recorded"
            )
        elif llm_invoked == template_used:
            errors.append(
                f"page_patch_receipt: exactly one of llm_invoked/template_fallback_used must be true "
                f"(got llm_invoked={llm_invoked}, template_fallback_used={template_used})"
            )
        # RPR-E-05: if the template fired, fallback_reason must say WHY (not NONE);
        # if the LLM's output was used, fallback_reason must be NONE/absent.
        fr = data.get("fallback_reason")
        if template_used is True and fr in (None, "NONE"):
            errors.append(
                "page_patch_receipt: template_fallback_used=True requires a fallback_reason "
                "other than NONE (RPR-E-05 observability)"
            )
        if llm_invoked is True and fr not in (None, "NONE"):
            errors.append(
                f"page_patch_receipt: llm_invoked=True is inconsistent with fallback_reason={fr!r}"
            )
    return errors


_REFRESH_PAGE_DISPOSITIONS = {
    "BODY_UPDATED",
    "EVIDENCE_ONLY",
    "NOT_AFFECTED",
    "SKIPPED",
    "BLOCKED",
    "GENERATED",
}


def validate_refresh_page_decision(data: dict) -> list[str]:
    """Validate a run-scoped page decision emitted by an actual writer.

    These rows describe pipeline intent and evidence ownership. They do not
    prove that a body changed; post-refresh verification independently derives
    that fact from Git using the run's explicit base.
    """
    errors: list[str] = []
    errors.extend(_check_required(
        data,
        [
            "schema_version",
            "run_id",
            "page_path",
            "surface",
            "locale",
            "intended_action",
            "disposition",
            "body_hash_before",
            "body_hash_after",
            "frontmatter_hash_before",
            "frontmatter_hash_after",
            "receipt_ref",
            "receipt_digest",
            "evidence_claims_checked",
            "evidence_apis_checked",
            "validator_results",
        ],
        "refresh_page_decision",
    ))
    if data.get("schema_version") != 1:
        errors.append("refresh_page_decision: schema_version must be 1")
    if data.get("disposition") not in _REFRESH_PAGE_DISPOSITIONS:
        errors.append(
            f"refresh_page_decision: invalid disposition {data.get('disposition')!r}"
        )
    for field in ("evidence_claims_checked", "evidence_apis_checked"):
        errors.extend(_check_type(data, field, list, "refresh_page_decision"))
    errors.extend(_check_type(data, "validator_results", dict, "refresh_page_decision"))
    validators = data.get("validator_results")
    required_validators = {"receipt", "forbidden_claims", "regrounding"}
    if isinstance(validators, dict):
        missing_validators = sorted(required_validators.difference(validators))
        unexpected_validators = sorted(set(validators).difference(required_validators))
        if missing_validators:
            errors.append(
                "refresh_page_decision: validator_results is missing "
                f"{missing_validators}"
            )
        if unexpected_validators:
            errors.append(
                "refresh_page_decision: validator_results contains unsupported "
                f"keys {unexpected_validators}"
            )
        for name in sorted(required_validators.intersection(validators)):
            if validators[name] not in {"PASS", "FAIL", "UNKNOWN"}:
                errors.append(
                    "refresh_page_decision: validator_results."
                    f"{name} must be PASS, FAIL, or UNKNOWN"
                )
    for field in (
        "run_id",
        "page_path",
        "surface",
        "locale",
        "intended_action",
        "body_hash_before",
        "body_hash_after",
        "frontmatter_hash_before",
        "frontmatter_hash_after",
        "receipt_ref",
        "receipt_digest",
    ):
        value = data.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(
                f"refresh_page_decision: '{field}' must be a non-empty string"
            )
    if (
        data.get("disposition") == "BODY_UPDATED"
        and data.get("body_hash_before") == data.get("body_hash_after")
    ):
        errors.append(
            "refresh_page_decision: BODY_UPDATED requires different normalized body hashes"
        )
    if data.get("receipt_digest") and not str(data["receipt_digest"]).startswith("sha256:"):
        errors.append("refresh_page_decision: receipt_digest must use sha256: prefix")
    return errors


_REFRESH_RUN_VALIDATION_FIELDS = ("post_refresh_verify", "oracle", "triage_confirm", "seo_stability")
_REFRESH_RUN_V3_VALIDATION_FIELDS = (
    "post_refresh_verify",
    "content_audit",
    "link_validation",
    "oracle",
    "triage_confirm",
    "seo_stability",
)
_REFRESH_RUN_STATUSES = {"in_progress", "blocked", "committed", "abandoned"}
_REFRESH_RUN_V3_STATES = {
    "CREATED",
    "INPUTS_PINNED",
    "PLANNED",
    "APPLYING",
    "VALIDATING",
    "READY_TO_COMMIT",
    "COMMITTED",
    "BLOCKED",
    "ABANDONED",
}
_REFRESH_RUN_V3_MODES = {"upstream", "remediation", "combined"}
_REFRESH_RUN_V3_RESULTS = {"NOT_RUN", "PASS", "FAIL", "UNKNOWN"}


def _validate_legacy_refresh_run_manifest(data: dict) -> list[str]:
    """Validate the historical schema-5e manifest shape."""
    errors = []
    errors.extend(_check_required(
        data,
        ["run_id", "family", "platform", "started_at", "baseline_ledger_ref",
         "product_change_refs", "page_coverage_ledger_ref", "patch_receipt_refs",
         "validation", "status"],
        "refresh_run_manifest",
    ))
    errors.extend(_check_type(data, "product_change_refs", list, "refresh_run_manifest"))
    errors.extend(_check_type(data, "patch_receipt_refs", list, "refresh_run_manifest"))
    # intentional_renames (schema 5e / RPR-F-05) is optional, but when present must be a
    # list of page ids — the SEO-stability allowlist Check 11 consumes.
    if "intentional_renames" in data:
        errors.extend(_check_type(data, "intentional_renames", list, "refresh_run_manifest"))
    # base_commit_sha (schema 5e / RPR-J-17) is optional -- the pre-refresh HEAD, captured
    # once at S-84 Step 1 before any commits land. Without it, post_refresh_verify's
    # git-founded checks (7, 8, 10, 11) default to "HEAD", which is vacuous once the
    # refresh has already been committed (HEAD then *is* the post-refresh state) --
    # confirmed against real pdf/net data, not merely theoretical. When present it must
    # be a non-empty string; consumers that can't resolve it fall back to "HEAD".
    if "base_commit_sha" in data and data["base_commit_sha"] is not None:
        errors.extend(_check_type(data, "base_commit_sha", str, "refresh_run_manifest"))
        if isinstance(data.get("base_commit_sha"), str) and not data["base_commit_sha"].strip():
            errors.append("refresh_run_manifest: base_commit_sha must not be an empty string (omit or use null)")

    if "status" in data and data["status"] not in _REFRESH_RUN_STATUSES:
        errors.append(f"refresh_run_manifest: invalid status '{data['status']}'")

    validation = data.get("validation")
    if not isinstance(validation, dict):
        errors.append("refresh_run_manifest: 'validation' must be a dict")
        validation = {}
    else:
        for field in _REFRESH_RUN_VALIDATION_FIELDS:
            if field not in validation:
                errors.append(f"refresh_run_manifest.validation: missing required key '{field}'")
            elif validation[field] not in ("PASS", "FAIL"):
                errors.append(f"refresh_run_manifest.validation.{field}: must be PASS or FAIL, got '{validation[field]}'")

    all_pass = validation and all(validation.get(f) == "PASS" for f in _REFRESH_RUN_VALIDATION_FIELDS)

    if data.get("status") == "committed":
        if not data.get("commit_sha"):
            errors.append("refresh_run_manifest: status=committed requires a non-empty commit_sha")
        if not all_pass:
            errors.append(
                "refresh_run_manifest: status=committed but not every validation field is PASS "
                "(a partially-failed run must never be recorded as committed — plan §13 rollback rule)"
            )
    elif data.get("commit_sha"):
        errors.append(
            f"refresh_run_manifest: commit_sha is set but status={data.get('status')!r} != 'committed'"
        )

    return errors


def validate_refresh_run_manifest(
    data: dict,
    phase: str | None = None,
) -> list[str]:
    """Validate a refresh-run manifest.

    Schema versions before 3 retain the historical schema-5e behavior. Schema
    version 3 is the run-bound state-machine contract. Its requirements are
    progressive: an early manifest is valid without pretending later-stage
    evidence exists, while ``READY_TO_COMMIT`` and ``COMMITTED`` require a
    complete all-PASS validation set.

    ``phase`` is optional and primarily useful to callers validating a proposed
    transition before it is persisted. When supplied it must match ``state``.
    """
    if data.get("schema_version") != 3:
        return _validate_legacy_refresh_run_manifest(data)

    errors: list[str] = []
    errors.extend(_check_required(
        data,
        [
            "schema_version",
            "run_id",
            "family",
            "platform",
            "mode",
            "state",
            "session_owner",
            "created_at",
            "updated_at",
            "base_commit_sha",
            "initial_model_sha",
            "initial_source_sha",
            "scope",
            "stage_checkpoints",
            "validation",
            "observed_heads",
        ],
        "refresh_run_manifest",
    ))

    state = data.get("state")
    if state not in _REFRESH_RUN_V3_STATES:
        errors.append(f"refresh_run_manifest: invalid state '{state}'")
    if phase is not None and state != phase:
        errors.append(
            f"refresh_run_manifest: state {state!r} does not match requested phase {phase!r}"
        )
    if data.get("mode") not in _REFRESH_RUN_V3_MODES:
        errors.append(f"refresh_run_manifest: invalid mode '{data.get('mode')}'")

    for field in (
        "run_id",
        "family",
        "platform",
        "session_owner",
        "created_at",
        "updated_at",
        "base_commit_sha",
    ):
        value = data.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"refresh_run_manifest: '{field}' must be a non-empty string")

    for field in ("initial_model_sha", "initial_source_sha", "target_model_sha", "target_source_sha"):
        if field in data and data[field] is not None:
            value = data[field]
            if not isinstance(value, str) or not value.strip():
                errors.append(f"refresh_run_manifest: '{field}' must be null or a non-empty string")

    if not isinstance(data.get("scope"), dict):
        errors.append("refresh_run_manifest: 'scope' must be a dict")
    if not isinstance(data.get("stage_checkpoints"), dict):
        errors.append("refresh_run_manifest: 'stage_checkpoints' must be a dict")
    if not isinstance(data.get("observed_heads"), list):
        errors.append("refresh_run_manifest: 'observed_heads' must be a list")
    for field in ("stage_attempt_refs", "validation_attempt_refs"):
        if field in data and not isinstance(data.get(field), list):
            errors.append(f"refresh_run_manifest: '{field}' must be a list")
    for field in ("stage_attempt_digests", "validation_attempt_digests"):
        mapping = data.get(field)
        if field in data and not isinstance(mapping, dict):
            errors.append(f"refresh_run_manifest: '{field}' must be a dict")
        elif isinstance(mapping, dict):
            for ref, digest in mapping.items():
                if (
                    not isinstance(ref, str)
                    or not ref
                    or not isinstance(digest, str)
                    or not digest.startswith("sha256:")
                ):
                    errors.append(
                        f"refresh_run_manifest: '{field}' must map "
                        "non-empty refs to sha256: digests"
                    )
                    break

    validation = data.get("validation")
    if not isinstance(validation, dict):
        errors.append("refresh_run_manifest: 'validation' must be a dict")
        validation = {}
    for field in _REFRESH_RUN_V3_VALIDATION_FIELDS:
        result = validation.get(field)
        if result not in _REFRESH_RUN_V3_RESULTS:
            errors.append(
                f"refresh_run_manifest.validation.{field}: must be one of "
                f"{sorted(_REFRESH_RUN_V3_RESULTS)}, got {result!r}"
            )

    state_rank = {
        "CREATED": 0,
        "INPUTS_PINNED": 1,
        "PLANNED": 2,
        "APPLYING": 3,
        "VALIDATING": 4,
        "READY_TO_COMMIT": 5,
        "COMMITTED": 6,
        "BLOCKED": -1,
        "ABANDONED": -1,
    }.get(state, -1)

    if state_rank >= 1:
        for field in ("initial_model_sha", "initial_source_sha"):
            if not data.get(field):
                errors.append(
                    f"refresh_run_manifest: state={state} requires non-empty '{field}'"
                )

    if state_rank >= 2:
        scope = data.get("scope") if isinstance(data.get("scope"), dict) else {}
        if not isinstance(scope.get("digest"), str) or not scope.get("digest"):
            errors.append(
                f"refresh_run_manifest: state={state} requires scope.digest"
            )
        if not isinstance(scope.get("paths"), list):
            errors.append(
                f"refresh_run_manifest: state={state} requires scope.paths as a list"
            )
        for field in ("target_model_sha", "target_source_sha"):
            if not data.get(field):
                errors.append(
                    f"refresh_run_manifest: state={state} requires non-empty '{field}'"
                )
        if data.get("target_model_sha") != data.get("target_source_sha"):
            errors.append(
                "refresh_run_manifest: target_model_sha must equal target_source_sha "
                "before planning or mutation"
            )

    if state_rank >= 4:
        if not isinstance(data.get("receipt_refs"), list):
            errors.append(
                f"refresh_run_manifest: state={state} requires receipt_refs as a list"
            )
        if not isinstance(data.get("page_decision_ref"), str) or not data.get("page_decision_ref"):
            errors.append(
                f"refresh_run_manifest: state={state} requires page_decision_ref"
            )

    if state in {"READY_TO_COMMIT", "COMMITTED"}:
        not_pass = [
            field for field in _REFRESH_RUN_V3_VALIDATION_FIELDS
            if validation.get(field) != "PASS"
        ]
        if not_pass:
            errors.append(
                f"refresh_run_manifest: state={state} requires every validation to PASS; "
                f"not PASS: {not_pass}"
            )
        if data.get("failure_reason"):
            errors.append(
                f"refresh_run_manifest: state={state} cannot carry failure_reason"
            )

    if state == "COMMITTED":
        if not isinstance(data.get("commit_sha"), str) or not data.get("commit_sha"):
            errors.append(
                "refresh_run_manifest: state=COMMITTED requires a non-empty commit_sha"
            )
    elif data.get("commit_sha"):
        errors.append(
            f"refresh_run_manifest: commit_sha is set but state={state!r} != 'COMMITTED'"
        )

    if state == "BLOCKED":
        if not isinstance(data.get("failure_reason"), str) or not data.get("failure_reason"):
            errors.append(
                "refresh_run_manifest: state=BLOCKED requires failure_reason"
            )
        resume_state = data.get("resume_state")
        if resume_state not in _REFRESH_RUN_V3_STATES - {"BLOCKED", "ABANDONED", "COMMITTED"}:
            errors.append(
                "refresh_run_manifest: state=BLOCKED requires a legal resume_state"
            )

    if state == "ABANDONED" and not data.get("failure_reason"):
        errors.append(
            "refresh_run_manifest: state=ABANDONED requires failure_reason"
        )

    return errors


# Ordered by lifecycle maturity. The subset past IMPLEMENTED requires non-empty
# evidence_refs (schema 5f rule) — a status claim beyond "code written" that cites
# nothing is exactly the prose-drift failure mode RPR-G-04 exists to close.
_TASKCARD_STATUSES = {
    "TODO", "READY", "IN_PROGRESS", "IMPLEMENTED", "FOCUSED_VERIFIED",
    "INTEGRATION_VERIFIED", "END_TO_END_VERIFIED", "PILOT_PROVEN",
    "INDEPENDENTLY_REVIEWED", "CLOSED", "REWORK_REQUIRED",
    "BLOCKED_LOCAL", "BLOCKED_EXTERNAL", "SUPERSEDED", "OUT_OF_SCOPE",
    "PAUSED",
}
# Statuses at or before which no evidence is yet required (nothing verified).
_TASKCARD_PRE_EVIDENCE_STATUSES = {"TODO", "READY", "IN_PROGRESS", "IMPLEMENTED"}
# Statuses representing a deliberate non-progress state rather than a
# verified/terminal outcome — same evidence exemption as BLOCKED_*/SUPERSEDED.
_TASKCARD_NON_PROGRESS_STATUSES = (
    "SUPERSEDED", "OUT_OF_SCOPE", "BLOCKED_LOCAL", "BLOCKED_EXTERNAL",
    "REWORK_REQUIRED", "PAUSED",
)


def validate_taskcard_record(data: dict) -> list[str]:
    """Validate one taskcards.jsonl row (plan schema 5f, §2.5 SW-4).

    The structured counterpart to a plan's §7 prose task cards. The core rule
    this schema exists to enforce: any status past IMPLEMENTED must cite at
    least one evidence_ref (a file path, commit SHA, or test name) — the exact
    check that would have flagged dazzling-strolling-shell's TC-W11-001.C7
    sitting at 'TODO' while the plan claimed progress, and the 8 DAR-table rows
    that drifted with nothing asserting they still matched reality.

    PAUSED (added for the eager context-switch-declaration mechanism, see
    docs/governance/planning-methodology.md) records that a step was
    deliberately set aside mid-session rather than silently dropped — it is
    non-terminal (still visible to plan-health-watchdog's stall query) but
    distinct from BLOCKED_*: blocked means "can't proceed", paused means
    "chose not to proceed yet". Requires a pause_reason, the same way
    verified statuses require evidence_refs.
    """
    errors = []
    errors.extend(_check_required(
        data,
        ["task_id", "mission_id", "status", "recorded_at", "evidence_refs", "recorded_by"],
        "taskcard_record",
    ))
    errors.extend(_check_type(data, "evidence_refs", list, "taskcard_record"))
    if "status" in data and data["status"] not in _TASKCARD_STATUSES:
        errors.append(f"taskcard_record: invalid status '{data['status']}'")
    status = data.get("status")
    if status == "PAUSED":
        reason = data.get("pause_reason")
        if not isinstance(reason, str) or not reason.strip():
            errors.append(
                "taskcard_record: status=PAUSED requires a non-empty pause_reason "
                "(a paused card with no stated reason is indistinguishable from a "
                "silently dropped one)"
            )
    # Evidence requirement for any verified/terminal status past IMPLEMENTED.
    if (
        status in _TASKCARD_STATUSES
        and status not in _TASKCARD_PRE_EVIDENCE_STATUSES
        and status not in _TASKCARD_NON_PROGRESS_STATUSES
    ):
        refs = data.get("evidence_refs")
        if not isinstance(refs, list) or not refs:
            errors.append(
                f"taskcard_record: status={status} requires a non-empty evidence_refs "
                f"(a status past IMPLEMENTED that cites no evidence is the prose-drift "
                f"failure mode schema 5f exists to prevent)"
            )
    return errors
