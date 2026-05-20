# Adapted from aspose.org scripts/pipeline/lib/ for standalone use
"""Shared constants for the skill sync ecosystem.

Single source of truth for sets that must stay consistent across
sync_skills.py, sync_providers.py, and check_skill_registry.py.
"""
from __future__ import annotations

# Internal skills: exist in canonical skills/ and agents/kilocode but NOT in
# .claude/commands/ because they are sub-routines auto-invoked by other skills.
INTERNAL_SKILLS: frozenset[str] = frozenset({
    "knowledge-bootstrap",   # auto-invoked pre-condition gate
    "evidence-cite",         # auto-invoked by generation skills
    "gap-plan",              # planning sub-tool for remediation pipeline
    "path-guard",            # enforced automatically on every write
    "change-guard",          # auto-invoked before writes
    "no-downgrade-guard",    # sub-routine for quality comparison
    "rubric-align",          # sub-evaluator called by eval-page
    "project-phase-store",   # checkpoint infrastructure
})
