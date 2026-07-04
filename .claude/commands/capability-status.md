# S-111: Capability Status — Parity Status Report

**Arguments**: $ARGUMENTS
```
[--verbose]   Show per-capability details, not just summary
```

**Examples:**
```
/capability-status
/capability-status --verbose
```

---

## Purpose

Report the current cross-agent capability parity status. Shows which capabilities are at
FULL_PARITY and which have gaps (missing adapters, semantic drift, orphan commands).

Use this skill at the start of any governance session to understand the current state
before running `/sync-capabilities`.

## Pre-conditions

- `skills/registry.yaml` must exist (canonical capability registry)
- Python environment must be active (`.venv` or system)

## Steps

1. **Load canonical registry** — Read `skills/registry.yaml` to get all capability IDs and names.

2. **Check adapter presence** — For each non-internal capability, verify:
   - `skills/{name}.md` exists (canonical contract)
   - `.claude/commands/{name}.md` exists (Claude Code adapter)
   - `.agents/skills/{name}/SKILL.md` exists (Codex adapter)
   - `.kilocode/skills/{name}/SKILL.md` exists (KiloCode adapter)

3. **Check semantic match** — Compare body hashes between canonical and each adapter.
   Differences indicate SEMANTIC_DRIFT.

4. **Report orphans** — Commands or agent skills with no canonical entry are ORPHAN.

5. **Print summary**:
   ```
   Parity status: X/N at FULL_PARITY
   Missing Claude adapters: Y
   Missing agent adapters: Z
   Semantic drift: W
   Orphan commands: V
   ```

6. **Exit 0** if all capabilities are at FULL_PARITY; **exit 1** otherwise.

## Implementation

```bash
python tools/capability_sync/validate_semantic_parity.py --check
python tools/capability_sync/detect_orphans.py --check
```

## Output

- Console parity summary with per-capability status (if `--verbose`)
- Exit 0: FULL_PARITY
- Exit 1: gaps detected

## Post-conditions

- No files are modified (read-only operation)
- If gaps are found, run `/sync-capabilities` to repair

## Recovery

If this skill fails to run, ensure:
1. `pyyaml` is installed: `pip install pyyaml`
2. `skills/registry.yaml` exists and is valid YAML
3. Python venv is active
