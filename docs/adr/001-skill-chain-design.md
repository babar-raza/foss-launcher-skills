# ADR-001: Skill Chain Architecture

**Date:** 2026-05-15
**Status:** Accepted
**Deciders:** Project maintainers

---

## Context

The FOSS Launcher project must generate and maintain documentation for a large number of Aspose FOSS products across multiple platforms (docs, blog, kb, reference, products). Each content type requires a different sequence of operations: knowledge extraction → evidence grounding → content generation → validation → publication.

Early prototypes used a monolithic script per product. This became unmaintainable as the number of products grew beyond 20 and cross-product patterns emerged.

## Decision

We adopted a **numbered skill chain architecture** where:

1. Each discrete operation is a **skill** (S-01 through S-110+), implemented as a standalone Python script under `scripts/pipeline/commands/`.
2. Skills are organized into **phases**: Discovery (S-01–S-14), Planning (S-15–S-25), Generation (S-26–S-50), Validation (S-51–S-70), Healing (S-71–S-90), Maintenance (S-91–S-110).
3. Skills communicate through **file artifacts** (YAML, JSON, Markdown) in agreed paths, not through direct Python imports.
4. The **AGENTS.md** file is the authoritative governance document specifying which skills are required before others, which are optional, and which have hard-stop conditions.

## Alternatives Considered

- **Monolithic orchestrator**: A single Python file calling all operations. Rejected because it makes skills impossible to run independently during development and testing.
- **Celery/Airflow task queue**: Rejected as over-engineering; the skill chain is invoked by AI agents and operators interactively, not as a continuous production service.
- **Plugin system with dynamic loading**: Rejected because explicit numbered skills are easier to audit and debug.

## Consequences

**Positive:**
- Each skill is independently testable and runnable.
- New products can be added by running the skill chain without modifying existing code.
- Operators can re-run individual skills to heal specific failures.

**Negative:**
- Skills with sequential dependencies must be run in the correct order; the chain is not automatically enforced at the Python level (AGENTS.md provides the specification).
- File-based communication means artifact paths must be documented and consistent.

## Enforcement

- Path contracts are enforced by `scripts/pipeline/commands/governance/path_guard.py`.
- Pre-write validation is enforced by `scripts/pre_write.py`.
- The local quality gate (`scripts/local_gate.py`) validates skill registry consistency.
