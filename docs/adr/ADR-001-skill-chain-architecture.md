# ADR-001: Multi-Skill Chain Architecture

**Date:** 2026-04-01
**Status:** Accepted
**Deciders:** @prora

## Context

The Aspose FOSS documentation pipeline needs to generate and maintain content for 24 product families across 15 platforms, spanning 5 site types (docs, blog, kb, products, reference). The volume of work (24 × 15 × 5 = 1800 possible content surfaces) and the diversity of tasks (discovery, knowledge extraction, content drafting, quality evaluation, evidence verification, translation) make a monolithic script impractical.

The system must be operable by LLM agents (Claude) rather than just humans, requiring machine-readable task boundaries and composable units of work.

## Decision

We adopt a **93-skill flat chain architecture** where each skill (S-01 through S-110) is a self-contained Markdown specification that:

1. Declares its purpose, inputs, outputs, and preconditions
2. Maps to one or more Python script entry points
3. Can be chained with other skills via explicit output-to-input contracts
4. Is registered in `skills/registry.yaml` with a stable numeric ID

Skill chains are composed by orchestrators (agents or humans) following the execution graphs defined in `AGENTS.md` Section 6.

## Alternatives Considered

- **Monolithic pipeline script**: Rejected — single scripts cannot be selectively re-run, are harder to test, and don't compose across the 5 site types.
- **DAG workflow engine (Airflow, Prefect)**: Rejected — adds infrastructure dependency for a documentation tool; overkill for the execution volume.
- **Single LLM session with full context**: Rejected — context window limits prevent holding all 93 operations simultaneously.

## Consequences

- Each skill can be independently tested with unit tests
- New capabilities require adding a skill file + entry point, not modifying existing code
- Skill chains must be explicitly defined (no auto-discovery of dependencies)
- CI must validate skill registry integrity (enforced by `skill-registry-audit` workflow)

## Implementation

- Skill definitions: [`skills/`](../../skills/)
- Registry: [`skills/registry.yaml`](../../skills/registry.yaml)
- Entry points: [`pyproject.toml`](../../pyproject.toml) `[project.scripts]`
- Registry validator: [`scripts/validate_skills.py`](../../scripts/validate_skills.py)
- CI enforcement: [`.github/workflows/skill-registry-audit.yml`](../../.github/workflows/skill-registry-audit.yml)
