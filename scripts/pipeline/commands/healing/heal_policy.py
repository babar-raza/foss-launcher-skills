"""heal_policy.py — Policy table mapping issue class → heal mode + skill.

Maps evaluation finding categories and levels to healing strategies,
bridging the triage system (which classifies findings) to the skill-driven
healing architecture (which executes fixes).

Usage (Python import):
    from heal_policy import lookup, is_heal_enabled

    policy = lookup(triaged_finding)
    if is_heal_enabled(triaged_finding):
        # proceed with healing
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from content_eval.remediation.triage import TriagedFinding


@dataclass(frozen=True, slots=True)
class HealPolicy:
    """Policy decision for a triaged finding."""

    heal_mode: str          # "auto", "llm", "regen", "human", "skip"
    skill: str              # Skill ID to invoke (empty for auto/skip/human)
    description: str        # Human-readable explanation
    regen_after: bool       # Whether page regeneration is needed post-fix
    effort: str             # "low", "medium", "high"


# ---------------------------------------------------------------------------
# Policy table — keyed by (fix_type, category) or (fix_type, *)
#
# Lookup order: exact (fix_type, category) first, then (fix_type, *).
# ---------------------------------------------------------------------------

_POLICY_TABLE: dict[tuple[str, str], HealPolicy] = {
    # --- Auto-fixable findings (deterministic fixers) ---
    ("auto", "*"): HealPolicy(
        heal_mode="auto",
        skill="",
        description="Deterministic fixer available — no LLM needed",
        regen_after=False,
        effort="low",
    ),

    # --- LLM-needed: category-specific routing ---
    ("llm", "AA"): HealPolicy(
        heal_mode="llm",
        skill="S-21",  # page-enhance
        description="API accuracy issue — knowledge-grounded rewrite",
        regen_after=False,
        effort="medium",
    ),
    ("llm", "PC"): HealPolicy(
        heal_mode="llm",
        skill="S-21",
        description="Platform contamination — code replacement needed",
        regen_after=False,
        effort="medium",
    ),
    ("llm", "FC"): HealPolicy(
        heal_mode="llm",
        skill="S-21",
        description="Forbidden claim — removal and rewrite",
        regen_after=False,
        effort="medium",
    ),
    ("llm", "PT"): HealPolicy(
        heal_mode="llm",
        skill="S-21",
        description="Prose truth issue — knowledge-grounded correction",
        regen_after=False,
        effort="medium",
    ),
    ("llm", "CP"): HealPolicy(
        heal_mode="llm",
        skill="S-21",
        description="Code plausibility — snippet replacement",
        regen_after=False,
        effort="medium",
    ),
    ("llm", "RL"): HealPolicy(
        heal_mode="llm",
        skill="S-21",
        description="Risk language — context-aware rewrite",
        regen_after=False,
        effort="medium",
    ),
    ("llm", "ST"): HealPolicy(
        heal_mode="llm",
        skill="S-21",
        description="Structural issue — knowledge-grounded generation",
        regen_after=False,
        effort="medium",
    ),
    ("llm", "RV"): HealPolicy(
        heal_mode="llm",
        skill="S-21",
        description="Page role issue — content generation from knowledge",
        regen_after=False,
        effort="medium",
    ),
    ("llm", "*"): HealPolicy(
        heal_mode="llm",
        skill="S-21",
        description="LLM-assisted fix — default to page-enhance",
        regen_after=False,
        effort="medium",
    ),

    # --- Upstream-blocked findings ---
    ("upstream", "*"): HealPolicy(
        heal_mode="regen",
        skill="S-79",  # causal-backtrack
        description="Upstream dependency — backtrack before local fix",
        regen_after=True,
        effort="high",
    ),

    # --- Human review ---
    ("human", "*"): HealPolicy(
        heal_mode="human",
        skill="",
        description="No automated fix available — manual review required",
        regen_after=False,
        effort="high",
    ),

    # --- Skip ---
    ("skip", "*"): HealPolicy(
        heal_mode="skip",
        skill="",
        description="INFO-level finding — no action needed",
        regen_after=False,
        effort="low",
    ),
}


def lookup(triaged: TriagedFinding) -> HealPolicy:
    """Look up the heal policy for a triaged finding.

    Resolution order:
      1. Exact match on (fix_type, category)
      2. Wildcard match on (fix_type, *)
      3. Fallback to human review
    """
    fix_type = str(triaged.fix_type)
    category = triaged.finding.category

    # Exact match
    key = (fix_type, category)
    if key in _POLICY_TABLE:
        return _POLICY_TABLE[key]

    # Wildcard match
    wildcard = (fix_type, "*")
    if wildcard in _POLICY_TABLE:
        return _POLICY_TABLE[wildcard]

    # Fallback
    return HealPolicy(
        heal_mode="human",
        skill="",
        description=f"No policy for {fix_type}/{category} — escalating to human",
        regen_after=False,
        effort="high",
    )


def is_heal_enabled(triaged: TriagedFinding) -> bool:
    """Return True if the finding has an automated healing path (auto, llm, or regen)."""
    policy = lookup(triaged)
    return policy.heal_mode in ("auto", "llm", "regen")


def get_policy_table() -> dict[tuple[str, str], HealPolicy]:
    """Return a copy of the policy table for inspection/testing."""
    return dict(_POLICY_TABLE)
