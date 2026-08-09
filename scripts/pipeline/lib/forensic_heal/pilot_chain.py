"""CONTRACT: 7-link pilot-chain resolver for S-123 (forensic-heal-sprint), Wave 5 of
MISSION MT025-2026-08-08-FORENSIC-BLIND-SPOT-HEAL-SKILLS.

Purpose: distinguish "we changed things" from "the healed system demonstrably works end to
end" by requiring a complete, resolvable chain from one real unaided finding all the way to
a re-verified, agentic-consumable result: unaided finding -> root cause -> taskcard ->
system-fix diff -> regen command -> verification artifact pair (before/after hashes that
actually differ) -> agentic-consumption re-check. Every link must resolve to a real
reference, not a placeholder -- an empty or duplicate before/after hash pair is treated as
unresolved, not as a pass.
"""
from __future__ import annotations

LINK_NAMES: "tuple[str, ...]" = (
    "unaided_finding", "root_cause", "taskcard", "system_fix_diff",
    "regen_command", "verification_artifact_pair", "agentic_consumption_recheck",
)


def resolve_pilot_chain(chain: dict) -> dict:
    """chain keys: unaided_finding_id, root_cause_id, task_id, system_fix_diff_ref,
    regen_command, verification_before_hash, verification_after_hash,
    agentic_consumption_recheck_passed (bool).

    Returns {"links": {name: bool}, "resolved": bool} -- resolved is True only if every
    link is True."""
    before = chain.get("verification_before_hash")
    after = chain.get("verification_after_hash")
    links = {
        "unaided_finding": bool(chain.get("unaided_finding_id")),
        "root_cause": bool(chain.get("root_cause_id")),
        "taskcard": bool(chain.get("task_id")),
        "system_fix_diff": bool(chain.get("system_fix_diff_ref")),
        "regen_command": bool(chain.get("regen_command")),
        "verification_artifact_pair": bool(before) and bool(after) and before != after,
        "agentic_consumption_recheck": chain.get("agentic_consumption_recheck_passed") is True,
    }
    return {"links": links, "resolved": all(links.values())}
