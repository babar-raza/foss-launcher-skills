# S-112: Sync Capabilities — Full Cross-Agent Synchronization Pipeline

**Arguments**: $ARGUMENTS
```
[--check]   Check only; report gaps without writing any files (dry-run)
```

**Examples:**
```
# Full sync (reads, generates adapters, writes reports)
/sync-capabilities

# Dry-run check only (no files written)
/sync-capabilities --check
```

---

## Purpose

Synchronize all agent adapter surfaces with the canonical `skills/registry.yaml`.
After running this skill, every capability in the registry has:
- A valid `.claude/commands/{name}.md` adapter (if not internal)
- A valid `.agents/skills/{name}/SKILL.md` adapter
- A valid `.kilocode/skills/{name}/SKILL.md` adapter
- Up-to-date `.governance/generated/` reports

This is the primary maintenance command for the cross-agent parity system.
Run it after any skill is added, modified, or deprecated.

## Pre-conditions

- `skills/registry.yaml` must exist and be valid
- `pyyaml` must be installed: `pip install pyyaml`
- Python environment must be active

## Steps

1. **Registry integrity** — Run `scripts/validate_skills.py` to verify registry has no
   duplicate IDs, all files exist, and internal rules are consistent.

2. **Inventory** — Run `tools/capability_sync/inventory_capabilities.py` and emit
   `.governance/generated/baseline.yaml`.

3. **Generate Claude commands** — Run `scripts/sync_commands.py --sync` to regenerate
   `.claude/commands/*.md` from canonical skill bodies (frontmatter stripped, internal excluded).

4. **Generate agent skills** — Run `scripts/sync_agents.py --sync` to regenerate
   `.agents/skills/` and `.kilocode/skills/` mirrors (frontmatter preserved).

5. **Generate capability indexes** — Run `tools/capability_sync/generate_capability_index.py`
   to produce `.governance/CLAUDE_CAPABILITY_INDEX.md`, `CODEX_CAPABILITY_INDEX.md`,
   and `AGENTS_CAPABILITY_INDEX.md`.

6. **Detect orphans** — Run `tools/capability_sync/detect_orphans.py` to find adapters
   with no canonical capability.

7. **Detect drift** — Run `tools/capability_sync/detect_adapter_drift.py --sync` to
   compare adapter hashes and emit `.governance/generated/drift-report.yaml`.

8. **Validate parity** — Run `tools/capability_sync/validate_semantic_parity.py --sync`
   to emit `.governance/generated/parity-report.yaml`.

9. **Validate discoverability** — Run `tools/capability_sync/validate_discoverability.py`
   to prove each agent can find its capabilities.

10. **Report** — Print pipeline summary with pass/fail per step.

## Implementation

```bash
# Full sync
python tools/capability_sync/run_sync.py

# Dry-run check
python tools/capability_sync/run_sync.py --check
```

## Output

- `.governance/generated/baseline.yaml` — capability inventory snapshot
- `.governance/generated/parity-report.yaml` — per-capability parity status
- `.governance/generated/drift-report.yaml` — adapter drift detection report
- `.governance/CLAUDE_CAPABILITY_INDEX.md` — generated Claude Code discovery index
- `.governance/CODEX_CAPABILITY_INDEX.md` — generated Codex discovery index
- `.governance/AGENTS_CAPABILITY_INDEX.md` — generated AGENTS.md discovery index (for human review)
- Updated `.claude/commands/*.md` adapters
- Updated `.agents/skills/*/SKILL.md` adapters
- Updated `.kilocode/skills/*/SKILL.md` adapters

## Post-conditions

- All capabilities in `skills/registry.yaml` have adapters for all agent surfaces
- `.governance/generated/parity-report.yaml` shows `final_verdict: FULL_PARITY`
- Exit 0

## Idempotency

Running this skill twice produces identical output. The second run reports "already in sync"
for all steps and makes no changes to any files.

## Recovery

If sync fails:
1. Check `skills/registry.yaml` for syntax errors: `python scripts/validate_skills.py`
2. Run individual steps manually to isolate the failure
3. Check that the Python venv is active and pyyaml is installed
