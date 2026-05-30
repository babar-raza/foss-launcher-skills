# Skills Reference

Status: Current
Audience: Operator, Agent, Contributor
Canonical reference: this page
Last code-backed audit: 2026-05-30

Skills are workflow procedures that route governed work through registered steps. The canonical skill source lives under `.agents/skills/` and mirrored command surfaces exist under `.claude/commands/` and `.kilocode/skills/`.

## Contracts

| Subject | Code/config surface |
|---|---|
| Skill registry checks | `scripts/ci/checks/check_skill_registry.py`, `check_skill_registry_json.py` |
| Skill chain resolution | `scripts/pipeline/commands/ops/skill_chain.py` |
| Skill context | `scripts/pipeline/commands/governance/skill_context.py` |
| Session logging | `scripts/pipeline/commands/ops/session_logger.py` |

## Usage Rule

Use scenario guides for human-readable workflows and this page for skill system contracts. Do not duplicate full skill catalogs in guides.
