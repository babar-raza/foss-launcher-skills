# Skill Quality Gates

This document describes the skill quality gate system: what gates exist, when
they are mandatory, how to invoke them, and how to interpret their output.

Quality gates are skills that evaluate a precondition — a plan, a content
page, a knowledge model — before allowing a downstream action to proceed.
They exist because agents are vulnerable to executing stale, ambiguous, or
incomplete inputs blindly. Gates surface these problems before they cause
hard-to-reverse errors.

---

## Gate Inventory

| Skill | ID | When mandatory | Effect | Modes |
|-------|----|---------------|--------|-------|
| `plan-normalize` | S-91 | Before executing any plan that is inherited, stale (>7 days), or contains archive/sprint sections | Classifies each plan section, identifies open items, produces a NEXT ITEM recommendation | assess, amend, launch |
| `knowledge-bootstrap` | S-54 | Before any content generation or validation command | Detects and resolves stale knowledge before proceeding | check, refresh |
| `change-guard` | S-33 | Before writing content | Verifies no upstream knowledge changes invalidate the pending write | block, warn |
| `no-downgrade-guard` | S-55 | Before replacing existing content | Compares proposed vs existing page quality; blocks quality regression | block, warn |
| `content-check` | S-23 | Before writing any content file | Structural and quality check; required for content write hook | pass, fail |

---

## Plan Execution Gate (S-91)

The plan execution gate uses `plan-normalize` (S-91) to classify plan sections
and determine if a plan is safe to execute without amendment.

### When to invoke

Invoke `plan-normalize` before executing any plan that is:
- Inherited from a prior session (age > 7 days or cross-session)
- Contains sections labeled as completed, archived, or historical
- Was authored during a sprint that may now be closed
- Came from a summary or briefing (not the current agent's own plan)

### Output format

S-91 produces a verdict block:

```
PLAN-NORMALIZE VERDICT
======================
execution-ready-as-is: no | yes
blocking-reason: ...

A. VERDICT
B. SECTION MAP
C. OPEN WORK REGISTER
D. NEXT ITEM
E. EXCLUSIONS
F. AMENDED EXECUTION PACK
```

If S-91 returns `execution-ready-as-is: no`, do not proceed until the blocking
issues are resolved or the plan is amended by S-91 in `amend` mode.

---

## See Also

- `skills/plan-normalize.md` — full S-91 skill specification
- `AGENTS.md §6` — Skill-First Execution Mandate
- `docs/registries/skills.md` — complete skill registry
