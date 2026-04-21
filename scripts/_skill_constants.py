"""
Authoritative set of internal (auto-invoked) skill slugs.

Internal skills are NOT exposed in .claude/commands/ — they are invoked automatically
by other skills as sub-routines or guards, never directly by the operator.

Source of truth: skills/registry.yaml (internal: true entries).
This module is derived from that registry for use in scripts that cannot easily
parse YAML at import time (e.g. CI validators, git hooks).

If you add a new internal skill to registry.yaml, add its slug here too.
"""

INTERNAL_SKILLS: frozenset[str] = frozenset({
    "path-guard",          # enforced automatically on every write
    "project-phase-store", # checkpoint infrastructure for generation pipeline
    "rubric-align",        # sub-evaluator called by eval-page
    "evidence-cite",       # auto-invoked by generation skills
    "change-guard",        # auto-invoked before content writes
    "knowledge-bootstrap", # auto-invoked pre-condition gate
})
