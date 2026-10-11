"""CONTRACT: root-cause records for S-122 (blind-spot-audit), Wave 3 of MISSION
MT025-2026-08-08-FORENSIC-BLIND-SPOT-HEAL-SKILLS.

Purpose: force every root-cause claim to name the system LAYER it lives in and a
resolvable file reference -- the distinction between "we found a symptom" and "we found
where in the machinery it comes from" that the original mission spec's Phase 7 asks for.
Deliberately thin: this module validates and shapes root-cause records; the actual
causal-tracing judgment (why this is the root cause, not a symptom) is the agent's, made
during S-122's root-cause phase and reusing S-67 (diagnose-skill-failure) per finding and
S-45 (gap-report) for cross-finding synthesis, per the plan's phase mapping.
"""
from __future__ import annotations

# Matches blind_spot_audit_run.py's taskcard `layer` field and S-123's system-before-
# content gate, which checks layer in {"script", "prompt", "validator", "governance_doc"}.
LAYERS: "frozenset[str]" = frozenset({"skill", "script", "prompt", "validator", "governance_doc", "data"})

_REQUIRED_FIELDS = (
    "root_cause_id", "layer", "file_ref", "finding_ids",
    "why_root_cause_not_symptom", "fix_direction", "risk_if_unfixed",
)


def build_root_cause(
    root_cause_id: str, *, layer: str, file_ref: str, finding_ids: "list[str]",
    why_root_cause_not_symptom: str, fix_direction: str, risk_if_unfixed: str,
    evidence: "list[str] | None" = None,
) -> dict:
    """Validate and shape one root-cause record. Raises ValueError on any missing/invalid
    field rather than silently accepting an under-specified claim -- this is deliberately
    stricter than a plain dict literal so "root cause" can't degrade into "vague guess"."""
    if layer not in LAYERS:
        raise ValueError(f"root_cause {root_cause_id!r}: invalid layer {layer!r}, must be one of {sorted(LAYERS)}")
    if not finding_ids:
        raise ValueError(f"root_cause {root_cause_id!r}: finding_ids must be non-empty (a root cause traces to real findings)")
    for field, value in (
        ("file_ref", file_ref), ("why_root_cause_not_symptom", why_root_cause_not_symptom),
        ("fix_direction", fix_direction), ("risk_if_unfixed", risk_if_unfixed),
    ):
        if not value or not value.strip():
            raise ValueError(f"root_cause {root_cause_id!r}: {field} must be non-empty")

    return {
        "root_cause_id": root_cause_id,
        "layer": layer,
        "file_ref": file_ref,
        "finding_ids": list(finding_ids),
        "why_root_cause_not_symptom": why_root_cause_not_symptom.strip(),
        "fix_direction": fix_direction.strip(),
        "risk_if_unfixed": risk_if_unfixed.strip(),
        "evidence": list(evidence or []),
    }


def validate_root_cause_set(root_causes: "list[dict]", *, all_finding_ids: "set[str]") -> "list[str]":
    """Cross-check a full set of root-cause records against the findings they claim to
    explain. Returns a list of warning strings (empty = clean) -- NOT raised, since an
    unexplained finding (a real blind spot with no assigned root cause yet) is a legitimate
    mid-analysis state the fix-planning phase surfaces and resolves, not a hard error at
    this layer."""
    warnings: "list[str]" = []
    seen_ids = {rc["root_cause_id"] for rc in root_causes}
    if len(seen_ids) != len(root_causes):
        warnings.append("duplicate root_cause_id values present")

    claimed_finding_ids: "set[str]" = set()
    for rc in root_causes:
        claimed_finding_ids.update(rc["finding_ids"])
        unknown = set(rc["finding_ids"]) - all_finding_ids
        if unknown:
            warnings.append(f"root_cause {rc['root_cause_id']!r} references unknown finding_ids: {sorted(unknown)}")

    unexplained = all_finding_ids - claimed_finding_ids
    if unexplained:
        warnings.append(f"{len(unexplained)} finding(s) have no root cause assigned yet: {sorted(unexplained)}")

    return warnings
