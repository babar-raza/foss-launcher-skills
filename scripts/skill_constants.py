"""skill_constants.py — Shared constants for the skill distribution system.

Imported by tools/distribute.py and tests to ensure consistent behaviour
across the distribution pipeline.
"""

# Skills that are internal sub-routines, auto-invoked by other skills.
# They are NOT user-invocable and are excluded from the Claude Code target
# (which shows skills as slash-commands in the IDE palette).
# Codex and Kilo Code targets include all skills.
INTERNAL_SKILLS: frozenset[str] = frozenset(
    {
        "path-guard",       # S-01: write-path enforcement oracle
        "rubric-align",     # S-17: quality gap analysis sub-routine
        "evidence-cite",    # S-24: auto-attach evidence frontmatter
        "change-guard",     # S-33: pre-write knowledge validation gate
    }
)
