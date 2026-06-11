# ADR-002: Path Guard Write Protection

**Date:** 2026-05-20
**Status:** Accepted
**Deciders:** Project maintainers

---

## Context

The project generates content that is published to live websites (docs.aspose.org, blog.aspose.org, etc.). AI agents running the skill chain have broad file system access during execution. Without write-path enforcement, an agent could accidentally overwrite governance files, theme layouts, CI configurations, or other infrastructure files while intending to write content.

Several near-misses occurred during early development where agent prompts asked for "update all documentation" and the agent wrote to `AGENTS.md` or `scripts/` directories.

## Decision

We implemented a **mandatory write-path allowlist** enforced at two layers:

1. **Script layer**: `scripts/pipeline/commands/governance/path_guard.py` — a standalone validator that explicitly lists allowed write prefixes (`content/`, `knowledge/`, `reports/`, `data/`, `scripts/pipeline/`, `tests/`) and forbidden paths (`themes/`, `layouts/`, `configs/`, `AGENTS.md`, `CLAUDE.md`, and path_guard.py itself).

2. **Git hook layer**: `scripts/ci/hooks/check_write_path_hook.sh` — a pre-tool-use hook that runs path_guard validation before any file write, blocking writes outside allowed paths at the tool level.

Allowed paths reflect the principle: **agents may write new content and tests, but may not modify the project's own governance, CI, or theme infrastructure without explicit human authorization**.

## Alternatives Considered

- **Trust agents not to write to wrong paths**: Rejected. LLM agents are non-deterministic; a prompt change could cause writes to wrong paths.
- **Read-only filesystem for governance files**: Rejected as too complex to implement cross-platform in a development environment.
- **Review all writes manually**: Rejected as it eliminates the automation benefit.

## Consequences

**Positive:**
- Governance files (AGENTS.md, CLAUDE.md, path_guard.py itself) are protected from accidental agent overwrite.
- CI/theme infrastructure cannot be modified without ROOT_WRITE_AUTHORIZED override.
- The allowlist provides an auditable contract for what AI agents are permitted to modify.

**Negative:**
- Operators who legitimately need to update governance files must use the ROOT_WRITE_AUTHORIZED bypass (which is logged).
- New script categories must be added to the allowlist explicitly.

## Override Mechanism

Emergency bypasses are documented in `docs/BYPASS_REGISTRY.md`. All bypasses are audited and require explicit operator acknowledgment.
