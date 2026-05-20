"""decision_engine.py — Per-surface freshness decision engine.

Ported from aspose.org scripts/pipeline/lib/decision_engine.py.

Separates input change evaluation from output drift evaluation.

Decision priority:
  1. Output drift (missing or drifted content) overrides input-unchanged.
  2. FRESH requires both inputs unchanged AND output current.
  3. Input changes are classified by fingerprint type
     (upstream > generator > metadata > policy).
  4. BASELINED_UNPROVEN or no stored manifest -> VALIDATE_ONLY.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from scripts.pipeline.lib.freshness_manifest import FreshnessManifest


# ---------------------------------------------------------------------------
# Decision constants (match manifest_status vocabulary)
# ---------------------------------------------------------------------------

FRESH = "FRESH"
BASELINED_UNPROVEN = "BASELINED_UNPROVEN"
REGENERATE_UPSTREAM = "REGENERATE_UPSTREAM"
REGENERATE_GENERATOR = "REGENERATE_GENERATOR"
REGENERATE_METADATA = "REGENERATE_METADATA"
REGENERATE_POLICY = "REGENERATE_POLICY"
RECONCILE_MISSING = "RECONCILE_MISSING"
RECONCILE_DRIFTED = "RECONCILE_DRIFTED"
VALIDATE_ONLY = "VALIDATE_ONLY"
BLOCKED = "BLOCKED"
DRY_RUN_PASS = "DRY_RUN_PASS"

# Internal intermediate decisions (not manifest statuses)
_INPUTS_UNCHANGED = "INPUTS_UNCHANGED"
_OUTPUT_CURRENT = "OUTPUT_CURRENT"

# Fingerprint -> decision mapping (priority: upstream > generator > metadata > policy)
_UPSTREAM_FINGERPRINTS = frozenset({"upstream_repo_sha", "local_knowledge_sha"})
_GENERATOR_FINGERPRINTS = frozenset({"generator_code_hash", "template_hash"})
_METADATA_FINGERPRINTS = frozenset({"products_json_hash"})
_POLICY_FINGERPRINTS = frozenset({"skill_version_hash", "config_hash"})


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OutputState:
    """Current observed output state for a (product, subdomain) pair."""

    output_exists: bool
    output_content_hash: Optional[str] = None
    actual_page_count: Optional[int] = None
    validation_status: Optional[str] = None


@dataclass
class Decision:
    """Result of the decision engine for a (product, subdomain) pair."""

    product: str
    subdomain: str
    decision: str
    changed_input_fingerprints: list
    input_decision: str
    output_decision: str
    explanation: str = ""

    def to_dict(self) -> dict:
        return {
            "product": self.product,
            "subdomain": self.subdomain,
            "decision": self.decision,
            "changed_input_fingerprints": self.changed_input_fingerprints,
            "input_decision": self.input_decision,
            "output_decision": self.output_decision,
            "explanation": self.explanation,
        }


# ---------------------------------------------------------------------------
# Internal evaluation functions
# ---------------------------------------------------------------------------

def _evaluate_output(
    current_outputs: OutputState,
    stored: Optional[FreshnessManifest],
) -> str:
    """Evaluate output drift independent of input changes.

    Returns one of: RECONCILE_MISSING, RECONCILE_DRIFTED, _OUTPUT_CURRENT.
    """
    if not current_outputs.output_exists:
        return RECONCILE_MISSING

    if stored is None:
        # No baseline to compare against — cannot confirm drift; assume current
        return _OUTPUT_CURRENT

    stored_hash = stored.output_state.get("output_content_hash")
    if (
        stored_hash is not None
        and current_outputs.output_content_hash is not None
        and current_outputs.output_content_hash != stored_hash
    ):
        return RECONCILE_DRIFTED

    return _OUTPUT_CURRENT


def _evaluate_inputs(
    current_inputs: dict,
    stored: Optional[FreshnessManifest],
) -> tuple:
    """Evaluate input changes relative to stored manifest.

    Returns (input_decision, changed_fingerprints).
    input_decision is one of: _INPUTS_UNCHANGED, VALIDATE_ONLY, REGENERATE_*.
    """
    if stored is None or stored.manifest_status == BASELINED_UNPROVEN:
        return VALIDATE_ONLY, []

    stored_fingerprints = stored.input_fingerprints or {}
    changed = [
        k for k in current_inputs
        if current_inputs[k] is not None and current_inputs[k] != stored_fingerprints.get(k)
    ]

    if not changed:
        return _INPUTS_UNCHANGED, []

    # Priority ordering: upstream > generator > metadata > policy
    changed_set = set(changed)
    if _UPSTREAM_FINGERPRINTS & changed_set:
        return REGENERATE_UPSTREAM, changed
    if _GENERATOR_FINGERPRINTS & changed_set:
        return REGENERATE_GENERATOR, changed
    if _METADATA_FINGERPRINTS & changed_set:
        return REGENERATE_METADATA, changed
    if _POLICY_FINGERPRINTS & changed_set:
        return REGENERATE_POLICY, changed

    # Changed fingerprints don't map to a known trigger — validate to be safe
    return VALIDATE_ONLY, changed


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def decide(
    product: str,
    subdomain: str,
    current_inputs: dict,
    current_outputs: OutputState,
    stored_manifest: Optional[FreshnessManifest],
) -> Decision:
    """Compute the freshness decision for a (product, subdomain) pair.

    Separates input change evaluation from output drift evaluation:
    - Output drift (missing or drifted content) overrides input-unchanged.
    - FRESH requires both inputs unchanged AND output current.
    - BASELINED_UNPROVEN or no stored manifest -> VALIDATE_ONLY.

    Args:
        product: Product slug "family/platform".
        subdomain: Surface name (e.g., "reference").
        current_inputs: Dict of fingerprint name -> current value (None = not collected).
        current_outputs: Current observed output state.
        stored_manifest: Previously stored manifest, or None for cold-start.

    Returns:
        Decision with final decision and intermediate reasoning.
    """
    output_decision = _evaluate_output(current_outputs, stored_manifest)
    input_decision, changed = _evaluate_inputs(current_inputs, stored_manifest)

    # Combine: output drift overrides input state
    if output_decision in (RECONCILE_MISSING, RECONCILE_DRIFTED):
        final = output_decision
        explanation = (
            f"Output drift ({output_decision}) overrides input decision ({input_decision})"
        )
    elif input_decision == _INPUTS_UNCHANGED and output_decision == _OUTPUT_CURRENT:
        final = FRESH
        explanation = "All inputs match manifest and output is current"
    elif input_decision == VALIDATE_ONLY:
        final = VALIDATE_ONLY
        explanation = "No proven input-output relationship — validation required"
    else:
        final = input_decision
        explanation = f"Input changes detected: {changed}"

    return Decision(
        product=product,
        subdomain=subdomain,
        decision=final,
        changed_input_fingerprints=changed,
        input_decision=input_decision,
        output_decision=output_decision,
        explanation=explanation,
    )
