# Adapted from aspose.org
"""evidence_verifier.py — Evidence frontmatter validation.

Extracted from knowledge_core.py (R-3a). Validates the evidence: frontmatter
block of a content file against a loaded knowledge model.

Public API:
    verify_evidence(frontmatter, knowledge, filepath) -> list[Finding]

Circular-import note: this module imports Knowledge only under TYPE_CHECKING.
At runtime, verify_evidence duck-types the knowledge parameter (calls
.repo_sha, .claim_ids, .classes, .has_method, .has_property, .has_enum_member)
without requiring the class itself. knowledge_core.py re-exports this function
for Sprint R-3a backward compatibility.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

# sibling-import guard
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from token_ops import Finding  # noqa: E402

if TYPE_CHECKING:
    from knowledge_core import Knowledge  # pragma: no cover


def verify_evidence(
    frontmatter: dict,
    knowledge: Knowledge,
    filepath: Path,
) -> list[Finding]:
    """Validate the evidence: frontmatter block against the knowledge model.

    Returns a list of Finding objects.
    - Missing evidence block         -> WARN
    - Stale model_sha                -> WARN
    - Invalid claim_id               -> FAIL  (only when claim index is populated)
    - Invalid api class/member       -> FAIL
    """
    findings = []
    evidence = frontmatter.get("evidence")

    if not evidence or not isinstance(evidence, dict):
        findings.append(Finding(
            "WARN", filepath, 0,
            "Missing `evidence:` frontmatter block — run attach_evidence.py",
        ))
        return findings

    # Model SHA — detect staleness
    ev_sha = evidence.get("model_sha", "")
    if not ev_sha:
        findings.append(Finding(
            "WARN", filepath, 0,
            "`evidence.model_sha` is missing — pin the knowledge model SHA",
        ))
    elif ev_sha != knowledge.repo_sha:
        findings.append(Finding(
            "WARN", filepath, 0,
            f"Evidence stale: model updated to {knowledge.repo_sha[:8]}, "
            f"evidence references {ev_sha[:8]} — rerun attach_evidence.py",
        ))

    # Claim ID validation
    can_validate_claims = bool(knowledge.claim_ids)
    if can_validate_claims:
        for claim_id in (evidence.get("claims") or []):
            if claim_id and claim_id not in knowledge.claim_ids:
                findings.append(Finding(
                    "FAIL", filepath, 0,
                    f"`evidence.claims` references unknown claim_id `{claim_id}`",
                    "Check merged/claims.json for valid IDs",
                ))
    elif evidence.get("claims"):
        findings.append(Finding(
            "WARN", filepath, 0,
            "Cannot validate claim IDs — claims.json is absent or empty for this product",
        ))

    # API reference validation
    for api_ref in evidence.get("apis", []):
        if not api_ref:
            continue
        if "." in api_ref:
            cls_name, member = api_ref.split(".", 1)
        else:
            cls_name, member = api_ref, None
        if cls_name not in knowledge.classes:
            findings.append(Finding(
                "FAIL", filepath, 0,
                f"`evidence.apis` references unknown class `{cls_name}` in `{api_ref}`",
                "Check merged/api_surface.json for valid class names",
            ))
        elif member and not knowledge.has_method(cls_name, member) \
                and not knowledge.has_property(cls_name, member) \
                and not knowledge.has_enum_member(cls_name, member):
            tier = getattr(knowledge, "surface_tier", 1)
            severity = "FAIL" if tier == 1 else "WARN"
            findings.append(Finding(
                severity, filepath, 0,
                f"`evidence.apis` references unknown member `{api_ref}`",
                "Check merged/api_surface.json for valid methods/properties",
            ))

    return findings
