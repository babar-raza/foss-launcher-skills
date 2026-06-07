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
